"""AI commentary service — generates macro analysis text from a data snapshot.

Architecture (see project standards — thin wrapper over analysis core):
    build_snapshot()  → structured JSON from compute_signals() (no analysis change)
    call_model()      → POST to an OpenAI-compatible /v1/chat/completions endpoint
    generate()        → snapshot → model → persist to SQLite commentary table

Triggers:
    - lifespan startup: fire-and-forget generate if DB empty or stale
    - refresh success:  caller marks stale + triggers regenerate (refresh-as-rerun)
    - manual POST:      sync generate (caller awaits)

Config via env vars (OpenAI-compatible, provider-agnostic):
    COMMENTARY_BASE_URL   e.g. https://api.openai.com/v1  or https://dashscope.aliyuncs.com/compatible-mode/v1
    COMMENTARY_API_KEY    secret key
    COMMENTARY_MODEL       model name, e.g. gpt-4o-mini / qwen-max
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from analysis.signals import compute_signals
from backend.app.core.db import DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMMENTARY_TABLE = "commentary"

# ── Config (OpenAI-compatible; provider chosen by env) ──────────────────────
BASE_URL = os.getenv("COMMENTARY_BASE_URL", "")
API_KEY = os.getenv("COMMENTARY_API_KEY", "")
MODEL = os.getenv("COMMENTARY_MODEL", "")

# Lock so concurrent generate() calls (startup + manual + refresh) never race.
_gen_lock = threading.Lock()
# Marks an in-flight generation so GET can return status="generating".
_busy = threading.Event()
# Set True after _ensure_table first succeeds; get_current skips the per-poll
# CREATE TABLE IF NOT EXISTS + commit (table provably exists for process lifetime).
_table_ready = False


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    global _table_ready
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {COMMENTARY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            data_as_of TEXT NOT NULL,
            composite_score INTEGER,
            phase_snapshot TEXT NOT NULL,
            text TEXT NOT NULL,
            model TEXT,
            stale INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    _table_ready = True


def _latest_data_date() -> str | None:
    """Return the newest date in derived_monthly — the 'data as of' stamp.

    Reuses the lru_cached _load_full DataFrame (warm after lifespan preload;
    cleared on refresh before mark_stale_and_regenerate) instead of opening a
    fresh sqlite connection per generate. Guards empty/missing-date so it
    returns None (not 'Na') on a fresh/empty DB.
    """
    try:
        import pandas as pd
        from backend.app.core.db import _load_full
        df = _load_full("derived_monthly")
        if df.empty or "date" not in df.columns:
            return None
        d = df["date"].max()
        return str(d)[:7] if pd.notna(d) else None  # YYYY-MM
    except Exception:
        return None


def build_snapshot() -> dict:
    """Assemble the structured data snapshot fed to the model.

    Reuses compute_signals() verbatim — analysis core stays untouched. The
    snapshot only carries latest-phase values the model may cite; it never
    includes raw time series, so the model cannot fabricate trends.
    """
    sig = compute_signals(str(DB_PATH))
    data_as_of = _latest_data_date()
    return {
        "data_as_of": data_as_of,
        "composite_score": sig["composite_score"],
        "interpretation": sig["interpretation"],
        "frameworks": {
            "merrill": sig["merrill"],
            "credit": sig["credit"],
            "inventory": sig["inventory"],
            "debt": sig["debt"],
        },
        "cross_lags": sig["cross_lags"],
    }


SYSTEM_PROMPT = (
    "你是宏观经济分析师。基于提供的数据快照撰写中文评论。"
    "规则：① 只能引用快照中存在的数值，不得编造任何未提供的指标、日期或趋势；"
    "② 分三段：综合信号研判 / 四大周期逐一点评 / 一句话结论；"
    "③ 250-400 字；④ 不给投资建议。"
)


def call_model(snapshot: dict) -> tuple[str, str]:
    """Call an OpenAI-compatible chat endpoint. Returns (text, model_name).

    Raises if base_url/key/model are unset or the request fails.
    """
    if not (BASE_URL and API_KEY and MODEL):
        raise RuntimeError(
            "commentary model not configured: set COMMENTARY_BASE_URL / "
            "COMMENTARY_API_KEY / COMMENTARY_MODEL"
        )
    import httpx

    url = BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": MODEL,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)},
        ],
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    text = data["choices"][0]["message"]["content"].strip()
    return text, MODEL


def generate(blocking: bool = True) -> dict:
    """Build snapshot → call model → persist. Returns the new commentary row.

    blocking=True  → caller waits for the model call (manual POST).
    blocking=False → fire-and-forget on a worker thread (startup/refresh).
    """
    if not blocking:
        t = threading.Thread(target=_generate_impl, kwargs={"_mark_done": True}, daemon=True)
        t.start()
        return {"status": "generating", "msg": "评论生成中…"}
    return _generate_impl()


def _generate_impl(_mark_done: bool = False) -> dict:
    if not _gen_lock.acquire(blocking=False):
        # Another generation is in flight — don't stack a second one.
        if _mark_done:
            _busy.set()
        return {"status": "generating", "msg": "已有生成在进行中…"}
    _busy.set()
    try:
        snapshot = build_snapshot()
        text, model_name = call_model(snapshot)
        row = _persist(snapshot, text, model_name)
        return row
    except Exception as e:
        return {"status": "error", "msg": f"生成失败：{type(e).__name__}: {e}"}
    finally:
        _busy.clear()
        _gen_lock.release()


def _persist(snapshot: dict, text: str, model_name: str) -> dict:
    conn = _connect()
    try:
        _ensure_table(conn)
        conn.execute(
            f"INSERT INTO {COMMENTARY_TABLE} "
            "(ts, data_as_of, composite_score, phase_snapshot, text, model, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            (
                _ts(),
                snapshot.get("data_as_of") or "",
                snapshot.get("composite_score"),
                json.dumps(snapshot, ensure_ascii=False),
                text,
                model_name,
            ),
        )
        conn.commit()
        row = _latest_row(conn)
    finally:
        conn.close()
    return _row_to_dict(row)


def _latest_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT * FROM {COMMENTARY_TABLE} ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _row_to_dict(row: sqlite3.Row | None) -> dict:
    if row is None:
        return {"status": "empty", "msg": "暂无评论", "text": ""}
    return {
        "ts": row["ts"],
        "data_as_of": row["data_as_of"],
        "composite_score": row["composite_score"],
        "text": row["text"],
        "model": row["model"],
        "stale": bool(row["stale"]),
        "status": "ok",
        "msg": None,
    }


def get_current() -> dict:
    """Return the latest commentary row, or a generating/empty status."""
    if _busy.is_set():
        return {"status": "generating", "msg": "评论生成中…", "text": ""}
    try:
        conn = _connect()
        if not _table_ready:
            _ensure_table(conn)
        row = _latest_row(conn)
        conn.close()
        return _row_to_dict(row)
    except Exception:
        return {"status": "empty", "msg": "暂无评论", "text": ""}


def mark_stale_and_regenerate() -> dict:
    """Called after a successful data refresh: mark old rows stale + trigger
    a fresh generation (refresh-as-rerun policy)."""
    try:
        conn = _connect()
        _ensure_table(conn)
        conn.execute(f"UPDATE {COMMENTARY_TABLE} SET stale = 1 WHERE stale = 0")
        conn.commit()
        conn.close()
    except Exception:
        pass
    return generate(blocking=False)


def ensure_on_startup() -> None:
    """lifespan hook: generate if no commentary exists yet (fire-and-forget)."""
    try:
        conn = _connect()
        _ensure_table(conn)
        row = _latest_row(conn)
        conn.close()
        if row is None:
            generate(blocking=False)
    except Exception:
        pass  # startup must never crash on commentary


if __name__ == "__main__":
    # manual smoke test: python -m backend.app.core.commentary
    print(json.dumps(build_snapshot(), ensure_ascii=False, indent=2))
