"""Refresh driver — migrated from dashboard/refresh.py.

Spawns the gated fetch pipeline as a subprocess (reuses scripts/01_fetch_data.py
+ _pipeline.py, never imports akshare into this process), streams stdout for
real progress, then clears caches on success.

The progress callback is exposed so the API layer can drive an SSE stream.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from backend.app.core.cache import clear_all_caches
from backend.app.core.db import _load_full

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "01_fetch_data.py"
MANIFEST_PATH = PROJECT_ROOT / "data" / "last_run.json"
LOCK_PATH = PROJECT_ROOT / "data" / ".refresh.lock"
VENV_PY = PROJECT_ROOT / ".venv312" / "bin" / "python"

# Expected number of ✅ lines from 01_fetch_data.py stdout:
# 14 fetchers (money_supply, gdp, cpi, ppi, pmi, leverage, social_finance, lpr,
# industrial, house_price, household_income, new_credit, bond_yield, demographics)
# + 2 derived tables (derived_monthly, derived_quarterly) = 16 total.
# Lower bound only: a full run emits more ✅ lines (per-indicator sub-steps,
# extra derived tables); min(done, expected) clamps so progress just reaches
# 100% early. Initial fallback only: the 📋 计划抓取 K/N line refines expected
# per run (incremental mode skips tables outside their release window).
EXPECTED_FETCH_STEPS = 16


def is_running() -> bool:
    if not LOCK_PATH.exists():
        return False
    # Stale detection: if lockfile mtime > 10 minutes, treat as stale (backend crashed)
    mtime = LOCK_PATH.stat().st_mtime
    if time.time() - mtime > 600:  # 10 minutes
        LOCK_PATH.unlink(missing_ok=True)
        return False
    return True


def _subprocess_env() -> dict:
    env = dict(os.environ)
    # Apple-Silicon Homebrew default; override via EXPAT_LIB_PATH for Intel macs
    # (/usr/local/opt/expat/lib) or Linux (empty). run_app.sh 也设此值；直接经
    # uvicorn/pytest 启动时本处是唯一来源（不可空默认，否则子进程 expat 导入失败）。
    extra = os.getenv("EXPAT_LIB_PATH", "/opt/homebrew/opt/expat/lib")
    existing = env.get("DYLD_LIBRARY_PATH")
    env["DYLD_LIBRARY_PATH"] = extra + (":" + existing if existing else "")
    return env


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


def sources_health(manifest: dict) -> dict:
    """Derive per-source red/yellow/green from the manifest (pure function, no
    new storage — last_run.json is the only source of truth).

    规则：任一源 consecutive_failures ≥ 2 → red；否则任一源 1 连败或
    kept_previous warning（验证闸门拒收）→ yellow；其余 → green。
    sources 为空 → green + updated_at=None（前端画灰点 = 尚无运行记录）。
    """
    sources = manifest.get("sources") or []
    if not sources:
        return {"status": "green", "updated_at": None, "sources": []}
    tables = manifest.get("tables", {})
    status = "green"
    out = []
    for s in sources:
        warning = None
        tab = tables.get(s.get("table"))
        if tab and tab.get("status") == "kept_previous":
            warning = f"kept previous — {tab.get('reason', '')}"
        cf = s.get("consecutive_failures", 0) or 0
        out.append({**s, "warning": warning})
        if cf >= 2:
            status = "red"
        elif status != "red" and (cf == 1 or warning):
            status = "yellow"
    return {"status": status, "updated_at": manifest.get("ts"), "sources": out}


def read_sources_health() -> dict:
    """Read data/last_run.json and derive sources health. Never raises;
    absent/corrupt manifest → green + updated_at=None. No caching (file is tiny)."""
    try:
        m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        m = {}
    try:
        return sources_health(m if isinstance(m, dict) else {})
    except Exception:
        return {"status": "green", "updated_at": None, "sources": []}


def run_refresh(progress_cb=None, stop_event=None, full=False) -> dict:
    """Run the fetch pipeline as a subprocess; clear caches on success.

    Streams stdout so ``progress_cb(fraction)`` is driven by per-table ✅ lines.
    Single-flight: a lockfile prevents two refreshes racing on the staging DB.
    Supports cancellation via ``stop_event`` (threading.Event): if set, the
    subprocess is killed early and the lockfile released.
    ``full=True`` appends --full (bypass the release calendar, fetch all tables).
    Returns a UI-friendly result dict.
    """
    if is_running():
        return {"status": "busy", "msg": "已有刷新在进行中，请稍候…",
                "ts": None, "updated": [], "kept_previous": []}

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch()
    proc = None
    try:
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        cmd = [py, str(FETCH_SCRIPT)] + (["--full"] if full else [])
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        expected, done = EXPECTED_FETCH_STEPS, 0
        if progress_cb:
            progress_cb(0.0)
        tail = []
        deadline = time.time() + 300
        for line in proc.stdout:
            # Check for cancellation signal
            if stop_event is not None and stop_event.is_set():
                proc.kill()
                return {"status": "cancelled", "msg": "刷新已取消（客户端断开）",
                        "ts": None, "updated": [], "kept_previous": []}
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
            if time.time() > deadline:
                proc.kill()
                return {"status": "error", "msg": "❌ 采集超时（>5 分钟）",
                        "detail": "".join(tail),
                        "ts": None, "updated": [], "kept_previous": []}
        proc.wait()
        if proc.returncode != 0:
            return {"status": "error",
                    "msg": f"❌ 采集脚本退出码 {proc.returncode}",
                    "detail": "".join(tail),
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
        return {"status": "error", "msg": f"❌ 刷新异常：{type(e).__name__}: {e}",
                "ts": None, "updated": [], "kept_previous": []}
    finally:
        if proc is not None:
            proc.wait()
        LOCK_PATH.unlink(missing_ok=True)
