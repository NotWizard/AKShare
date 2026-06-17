"""Refresh driver — migrated from dashboard/refresh.py.

Spawns the gated fetch pipeline as a subprocess (reuses scripts/01_fetch_data.py
+ _pipeline.py, never imports akshare into this process), streams stdout for
real progress, then clears caches on success.

The progress callback is exposed so the API layer can drive an SSE stream.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from backend.app.core.cache import clear_all_caches

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "01_fetch_data.py"
MANIFEST_PATH = PROJECT_ROOT / "data" / "last_run.json"
LOCK_PATH = PROJECT_ROOT / "data" / ".refresh.lock"
VENV_PY = PROJECT_ROOT / ".venv312" / "bin" / "python"


def is_running() -> bool:
    return LOCK_PATH.exists()


def _subprocess_env() -> dict:
    env = dict(os.environ)
    extra = "/opt/homebrew/opt/expat/lib"
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


def run_refresh(progress_cb=None) -> dict:
    """Run the fetch pipeline as a subprocess; clear caches on success.

    Streams stdout so ``progress_cb(fraction)`` is driven by per-table ✅ lines.
    Single-flight: a lockfile prevents two refreshes racing on the staging DB.
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
        proc = subprocess.Popen(
            [py, str(FETCH_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            env=_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        expected, done = 14, 0   # ~12 fetchers + 2 derived
        if progress_cb:
            progress_cb(0.0)
        tail = []
        deadline = time.time() + 300
        for line in proc.stdout:
            tail.append(line)
            tail = tail[-60:]
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
