"""In-dashboard data refresh.

Spawns the gated fetch pipeline (`scripts/01_fetch_data.py`) as a **subprocess**,
then invalidates every in-memory cache so the dashboard reads fresh data next.
The heavy/network akshare work stays isolated in the subprocess; this module
never imports akshare.

Why cache clearing is mandatory: `db._load_full` and the 6 cycle/classifier
lru_caches are keyed by the db_path *string*, which does not change across the
pipeline's atomic `os.replace(staging → live)`. Without clearing, the dashboard
keeps serving the pre-refresh DataFrames — a refresh that "succeeds" but shows
stale data.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dashboard import db as _db
import analysis.cycle_merrill as _merrill
import analysis.cycle_credit as _credit
import analysis.cycle_inventory as _inventory
import analysis.cycle_debt as _debt
import analysis.signals as _signals
import analysis.real_estate as _real_estate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "01_fetch_data.py"
MANIFEST_PATH = PROJECT_ROOT / "data" / "last_run.json"
LOCK_PATH = PROJECT_ROOT / "data" / ".refresh.lock"
VENV_PY = PROJECT_ROOT / ".venv312" / "bin" / "python"

# Every lru_cache keyed by the (unchanging) db_path string — must be cleared
# after an atomic swap, else the dashboard serves pre-refresh data.
_CACHE_TARGETS = (
    _db._load_full,
    _merrill.classify_merrill,
    _credit.classify_credit,
    _inventory.classify_inventory,
    _debt.classify_debt,
    _signals.compute_signals,
    _real_estate._analyze_real_estate_cached,
)


def clear_all_caches():
    """Invalidate all data-backed lru_caches so the next read hits the new DB."""
    for fn in _CACHE_TARGETS:
        fn.cache_clear()


def is_running():
    """True if a refresh is already in progress (single-flight guard)."""
    return LOCK_PATH.exists()


def _subprocess_env():
    """macOS Homebrew Python needs the expat dynamic lib path; mirror run_dashboard.sh."""
    env = dict(os.environ)
    extra = "/opt/homebrew/opt/expat/lib"
    existing = env.get("DYLD_LIBRARY_PATH")
    env["DYLD_LIBRARY_PATH"] = extra + (":" + existing if existing else "")
    return env


def read_manifest_summary():
    """Parse data/last_run.json into a UI-friendly dict. Returns a dict even on
    missing/empty manifest (never raises)."""
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


def run_refresh(progress_cb=None):
    """Run the fetch pipeline as a subprocess; on success clear caches.

    Streams stdout so ``progress_cb(fraction)`` can be driven by per-table
    completion log lines (real progress, not a fake spinner). Single-flight: a
    lockfile prevents two refreshes racing on the staging DB. Returns a
    UI-friendly result dict (same shape as read_manifest_summary, plus
    status='busy'/'error' on those paths).
    """
    if is_running():
        return {"status": "busy", "msg": "已有刷新在进行中，请稍候…",
                "ts": None, "updated": [], "kept_previous": []}

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch()
    proc = None
    try:
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        proc = subprocess.Popen(
            [py, str(FETCH_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            env=_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # ~12 fetchers + 2 derived tables complete with a '✅' line; count them
        # for real progress. Clamp at 1.0 so the bar never overshoots.
        expected, done = 14, 0
        if progress_cb:
            progress_cb(0.0)
        tail = []
        deadline = time.time() + 300
        for line in proc.stdout:
            tail.append(line)
            tail = tail[-60:]  # keep only the recent tail for error reporting
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
            return {
                "status": "error",
                "msg": f"❌ 采集脚本退出码 {proc.returncode}",
                "detail": "".join(tail),
                "ts": None, "updated": [], "kept_previous": [],
            }
        if progress_cb:
            progress_cb(1.0)
        # success → invalidate caches so the next read is fresh
        clear_all_caches()
        return read_manifest_summary()
    except Exception as e:  # defensive: never let the web callback crash
        if proc is not None:
            proc.kill()
        return {"status": "error", "msg": f"❌ 刷新异常：{type(e).__name__}: {e}",
                "ts": None, "updated": [], "kept_previous": []}
    finally:
        if proc is not None:
            proc.wait()
        LOCK_PATH.unlink(missing_ok=True)
