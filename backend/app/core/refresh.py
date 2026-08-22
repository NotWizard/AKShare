"""Refresh driver — migrated from dashboard/refresh.py.

Spawns the gated fetch pipeline as a subprocess (reuses scripts/01_fetch_data.py
+ _pipeline.py, never imports akshare into this process), streams stdout for
real progress, then clears caches on success.

The progress callback is exposed so the API layer can drive an SSE stream.
"""

import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from backend.app.core.cache import clear_all_caches
from backend.app.core.db import _load_full
# Single source of truth for the refresh lock (flock-based, shared with the CLI).
# is_running/LOCK_PATH are re-exported here so the API layer and callers keep
# importing them from backend.app.core.refresh unchanged.
from backend.app.core.locking import LOCK_PATH, is_running, refresh_lock

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "01_fetch_data.py"
MANIFEST_PATH = PROJECT_ROOT / "data" / "last_run.json"
VENV_PY = PROJECT_ROOT / ".venv312" / "bin" / "python"

# Wall-clock ceiling for a single refresh subprocess. Enforced independently of
# whether the child emits any stdout (see run_refresh) so a silent no-timeout
# network hang inside akshare is actually killed. Env-overridable so tests can
# set it to a couple of seconds.
REFRESH_TIMEOUT_S = int(os.getenv("REFRESH_TIMEOUT_S", "300"))

# Env flag: run_refresh (which already holds the flock in THIS process) sets this
# in the child's environment so scripts/01_fetch_data.py skips re-acquiring the
# same lock (the parent holds it). A manual CLI run has it unset and acquires.
LOCK_HELD_ENV = "REFRESH_LOCK_HELD"

# Expected number of ✅ lines from 01_fetch_data.py stdout:
# 16 fetchers (money_supply, gdp, cpi, ppi, pmi, leverage, social_finance, lpr,
# industrial, house_price, household_income, new_credit, bond_yield, demographics,
# fiscal, external_demand) + 2 derived tables (derived_monthly, derived_quarterly)
# = 18 total.
# Lower bound only: a full run emits more ✅ lines (per-indicator sub-steps,
# extra derived tables); min(done, expected) clamps so progress just reaches
# 100% early. Initial fallback only: the 📋 计划抓取 K/N line refines expected
# per run (incremental mode skips tables outside their release window).
EXPECTED_FETCH_STEPS = 18


# Env vars the fetch child actually needs. Everything else is DROPPED (F12):
# the old `dict(os.environ)` handed the collector — which never talks to an LLM —
# the whole parent environment including COMMENTARY_API_KEY, so a compromised or
# merely chatty third-party dependency in that child could read the secret.
_ENV_ALLOWLIST = (
    "PATH", "HOME", "TMPDIR", "TZ",              # process basics
    "LANG", "LC_ALL", "LC_CTYPE",                # text encoding
    "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "LD_LIBRARY_PATH",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",  # corporate CA bundles
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)


def _subprocess_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST}
    # Apple-Silicon Homebrew default; override via EXPAT_LIB_PATH for Intel macs
    # (/usr/local/opt/expat/lib) or Linux (empty). run_app.sh 也设此值；直接经
    # uvicorn/pytest 启动时本处是唯一来源（不可空默认，否则子进程 expat 导入失败）。
    extra = os.getenv("EXPAT_LIB_PATH", "/opt/homebrew/opt/expat/lib")
    existing = env.get("DYLD_LIBRARY_PATH")
    env["DYLD_LIBRARY_PATH"] = extra + (":" + existing if existing else "")
    # Pinned explicitly: the child prints Chinese progress lines to a pipe, and
    # narrowing the env above must not leave it guessing at a non-UTF-8 locale.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _log_error_id(context: str, detail: str) -> str:
    """Log ``detail`` server-side under a fresh short id; return the id (F12).

    The child's output tail (stderr merged into stdout) routinely contains an
    uncaught traceback with absolute paths like ``/Users/<name>/…`` — useful in
    the server log, an information leak in an HTTP response body. Callers put
    ONLY the returned id in the response so an operator can still grep for it.
    """
    error_id = uuid.uuid4().hex[:8]
    logger.error("[refresh] %s (error_id=%s):\n%s", context, error_id, detail)
    return error_id


def read_manifest_summary() -> dict:
    """Parse data/last_run.json into a UI-friendly dict. Never raises."""
    if not MANIFEST_PATH.exists():
        return {"status": "unknown", "msg": "暂无刷新记录", "ts": None,
                "updated": [], "kept_previous": []}
    try:
        m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status": "unknown", "msg": "manifest 读取失败", "ts": None,
                "updated": [], "kept_previous": []}
    tables = m.get("tables", {})
    updated = [t for t, v in tables.items() if v.get("status") == "updated"]
    kept = [t for t, v in tables.items() if v.get("status") == "kept_previous"]
    msg = f"✅ 已更新 {len(updated)} 张表"
    if kept:
        msg += f" ｜ ⏭️ 跳过 {len(kept)}：{', '.join(kept)}"
    return {
        "status": "ok",
        "msg": msg,
        "ts": m.get("ts"),
        "akshare": m.get("akshare"),
        "updated": updated,
        "kept_previous": kept,
    }


# Staleness threshold for the manifest timestamp. Macro data is monthly, so a
# manifest older than ~40 days almost certainly means the scheduled refresh has
# silently stopped feeding fresh data (env-overridable via HEALTH_STALE_DAYS).
# Past 2× the threshold the data is badly stale → treated as a hard failure.
HEALTH_STALE_DAYS = int(os.getenv("HEALTH_STALE_DAYS", "40"))

# Severity ordering so staleness can only ESCALATE the per-source status, never
# downgrade it (a red source stays red even when the manifest is fresh).
_SEVERITY = {"green": 0, "yellow": 1, "red": 2}


def _staleness_status(updated_at, now, stale_days=None):
    """Severity contributed by manifest age: None when fresh / unparseable /
    absent, ``"yellow"`` once older than ``stale_days``, ``"red"`` past 2×.

    A missing or unparseable timestamp yields None (no staleness opinion); the
    empty-sources case is handled as ``unknown`` by the caller before this runs.
    """
    if not updated_at:
        return None
    stale_days = HEALTH_STALE_DAYS if stale_days is None else stale_days
    try:
        age_days = (now - datetime.fromisoformat(updated_at)).total_seconds() / 86400.0
    except (TypeError, ValueError):
        return None
    if age_days >= stale_days * 2:
        return "red"
    if age_days >= stale_days:
        return "yellow"
    return None


def sources_health(manifest: dict, now=None) -> dict:
    """Derive per-source red/yellow/green from the manifest (pure function, no
    new storage — last_run.json is the only source of truth).

    规则：任一源 consecutive_failures ≥ 2 → red；否则任一源 1 连败、
    kept_previous warning（验证闸门拒收）或 dual divergence warning（双源比对
    分歧）→ yellow；其余 → green。此外，manifest 时间戳过旧（宏观月频，默认
    > HEALTH_STALE_DAYS 天）→ 至少转黄、> 2× → 转红：陈旧数据绝不报绿。
    sources 为空 → unknown + updated_at=None（前端画灰点 = 尚无有效运行记录，
    绝不当作健康的绿灯——O-C1/B1 修复点）。
    ``now`` 可注入以便测试，默认 datetime.now()。
    """
    sources = manifest.get("sources") or []
    if not sources:
        return {"status": "unknown", "updated_at": None, "sources": []}
    if now is None:
        now = datetime.now()
    tables = manifest.get("tables", {})
    status = "green"
    out = []
    for s in sources:
        warning = None
        tab = tables.get(s.get("table"))
        if tab and tab.get("status") == "kept_previous":
            warning = f"kept previous — {tab.get('reason', '')}"
        elif s.get("dual", {}).get("divergent"):
            d = s["dual"]
            warning = (f"dual-source divergence — {d.get('series')} "
                       f"{d.get('primary')} vs {d.get('secondary')} @ {d.get('date')}")
        cf = s.get("consecutive_failures", 0) or 0
        out.append({**s, "warning": warning})
        if cf >= 2:
            status = "red"
        elif status != "red" and (cf == 1 or warning):
            status = "yellow"
    updated_at = manifest.get("ts")
    stale = _staleness_status(updated_at, now)
    if stale and _SEVERITY[stale] > _SEVERITY[status]:
        status = stale
    return {"status": status, "updated_at": updated_at, "sources": out}


def read_sources_health() -> dict:
    """Read data/last_run.json and derive sources health. Never raises;
    absent/corrupt manifest or a derivation error → unknown + updated_at=None
    (gray, never a false green). No caching (file is tiny)."""
    try:
        m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        m = {}
    try:
        return sources_health(m if isinstance(m, dict) else {})
    except Exception:
        return {"status": "unknown", "updated_at": None, "sources": []}


def _build_cmd(full: bool) -> list:
    """Build the fetch-subprocess command. Split out as a seam so tests can
    monkeypatch it to a fake child (e.g. a sleeper that emits no output) without
    rewiring run_refresh."""
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    return [py, str(FETCH_SCRIPT)] + (["--full"] if full else [])


def run_refresh(progress_cb=None, stop_event=None, full=False) -> dict:
    """Run the fetch pipeline as a subprocess; clear caches on success.

    Streams stdout so ``progress_cb(fraction)`` is driven by per-table ✅ lines.
    Single-flight via an OS-level ``flock`` (see backend.app.core.locking): the
    lock is acquired atomically for the WHOLE refresh, so two concurrent callers
    can never both spawn a fetcher and race on the shared staging DB — the loser
    gets ``BlockingIOError`` and a "busy" result. The kernel drops the lock if
    this process dies (no stale-file heuristic). The same lock is shared with a
    manual ``python scripts/01_fetch_data.py`` run.
    Supports cancellation via ``stop_event`` (threading.Event): if set, the
    subprocess is killed early. ``full=True`` appends --full (bypass the release
    calendar). Returns a UI-friendly result dict.
    """
    try:
        with refresh_lock():
            return _run_refresh_locked(progress_cb, stop_event, full)
    except BlockingIOError:
        return {"status": "busy", "msg": "已有刷新在进行中，请稍候…",
                "ts": None, "updated": [], "kept_previous": []}


def _run_refresh_locked(progress_cb, stop_event, full) -> dict:
    """Body of run_refresh, executed while holding the refresh lock."""
    proc = None
    try:
        env = _subprocess_env()
        env[LOCK_HELD_ENV] = "1"  # 父进程已持锁 → 子脚本跳过重复获取，避免自我冲突
        proc = subprocess.Popen(
            _build_cmd(full),
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Pump child stdout in a reader thread into a queue so the wall-clock
        # deadline and stop_event are enforced even when the child emits NO
        # output for a long time (a bare no-timeout requests.get can hang
        # forever). The old `for line in proc.stdout:` blocked in readline(), so
        # the deadline check never ran until a line happened to arrive — a silent
        # hang could never be killed. Draining the queue with a per-iteration
        # timeout guarantees the loop keeps ticking regardless of child output.
        lines: "queue.Queue" = queue.Queue()

        def _pump():
            try:
                for line in proc.stdout:
                    lines.put(line)
            finally:
                lines.put(None)  # EOF sentinel

        reader = threading.Thread(target=_pump, daemon=True)
        reader.start()

        expected, done = EXPECTED_FETCH_STEPS, 0
        if progress_cb:
            progress_cb(0.0)
        tail = []
        deadline = time.time() + REFRESH_TIMEOUT_S
        while True:
            if stop_event is not None and stop_event.is_set():
                proc.kill()
                proc.wait()
                return {"status": "cancelled", "msg": "刷新已取消（客户端断开）",
                        "ts": None, "updated": [], "kept_previous": []}
            remaining = deadline - time.time()
            if remaining <= 0:
                proc.kill()
                proc.wait()
                eid = _log_error_id(
                    f"采集超时（>{REFRESH_TIMEOUT_S}s），子进程输出尾部", "".join(tail))
                return {"status": "error",
                        "msg": f"❌ 采集超时（>{REFRESH_TIMEOUT_S} 秒）",
                        "error_id": eid,
                        "ts": None, "updated": [], "kept_previous": []}
            try:
                # cap the wait so the deadline/stop_event are re-checked ~1s
                line = lines.get(timeout=min(1.0, remaining))
            except queue.Empty:
                continue  # 无新行也回到循环顶部重查 deadline / stop_event
            if line is None:
                break  # child stdout hit EOF → process is finishing
            tail.append(line)
            tail = tail[-60:]
            m = re.search(r"计划抓取 (\d+)/", line)
            if m:
                # 计划行口径本次实际抓取数 + derived_monthly/derived_quarterly 两条 ✅
                expected = int(m.group(1)) + 2
            if "✅" in line:
                done = min(done + 1, expected)
                if progress_cb:
                    progress_cb(done / expected)
        proc.wait()
        if proc.returncode != 0:
            eid = _log_error_id(
                f"采集脚本退出码 {proc.returncode}，子进程输出尾部", "".join(tail))
            return {"status": "error",
                    "msg": f"❌ 采集脚本退出码 {proc.returncode}",
                    "error_id": eid,
                    "ts": None, "updated": [], "kept_previous": []}
        if progress_cb:
            progress_cb(1.0)
        clear_all_caches()
        # Re-warm the 4 hot tables (mirrors lifespan preload) so the first
        # post-refresh request isn't cold-cache (~11ms → ~2ms each).
        for t in ("derived_monthly", "derived_quarterly", "leverage", "house_price"):
            try:
                _load_full(t)
            except Exception:
                pass
        # Refresh-as-rerun policy: mark old commentary stale + trigger a fresh
        # AI analysis on the updated data (fire-and-forget, non-blocking).
        from backend.app.core import commentary
        commentary.mark_stale_and_regenerate()
        return read_manifest_summary()
    except Exception as e:  # never let the API crash
        if proc is not None:
            proc.kill()
        # str(e) leaks absolute paths (e.g. FileNotFoundError "[Errno 2] …
        # '/Users/<name>/…'"), so only the exception TYPE reaches the client.
        eid = uuid.uuid4().hex[:8]
        logger.exception("[refresh] 刷新异常 (error_id=%s)", eid)
        return {"status": "error", "msg": f"❌ 刷新异常：{type(e).__name__}",
                "error_id": eid, "ts": None, "updated": [], "kept_previous": []}
    finally:
        # Guarantee no orphaned child (and reap it) whatever path we took above.
        if proc is not None:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

