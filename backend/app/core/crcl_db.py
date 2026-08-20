"""CRCL monitor storage — separate SQLite DB (data/crcl_monitor.db).

Kept apart from macro_data.db: the CRCL module has its own lifecycle
(collect-on-startup + manual refresh) and must not touch the lru_cached
macro tables. Thread-safe via a module-level lock (uvicorn + worker threads).
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CRCL_DB_PATH = PROJECT_ROOT / "data" / "crcl_monitor.db"
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CRCL_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    with _lock, _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metric_points (
                metric TEXT NOT NULL,
                date   TEXT NOT NULL,
                value  REAL NOT NULL,
                PRIMARY KEY (metric, date)
            );
            CREATE TABLE IF NOT EXISTS snapshot (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                rule    TEXT NOT NULL,
                level   TEXT NOT NULL,
                status  TEXT NOT NULL,
                message TEXT NOT NULL,
                ts      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collect_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL,
                source      TEXT NOT NULL,
                status      TEXT NOT NULL,
                message     TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                ts          TEXT NOT NULL
            );
            """
        )


def upsert_points(metric: str, points: list[tuple[str, float]]) -> int:
    """Insert/replace (date, value) rows for one metric; returns row count."""
    if not points:
        return 0
    rows = [(metric, d, float(v)) for d, v in points]
    with _lock, _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO metric_points (metric, date, value) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)


def get_series(metric: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, value FROM metric_points WHERE metric = ? ORDER BY date",
            (metric,),
        ).fetchall()
    return [{"date": r["date"], "value": r["value"]} for r in rows]


def all_metrics() -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT metric FROM metric_points ORDER BY metric"
        ).fetchall()
    return [r["metric"] for r in rows]


def set_snapshot(key: str, value: dict) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshot (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), _now()),
        )


def get_snapshots() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value, updated_at FROM snapshot").fetchall()
    return {
        r["key"]: {**json.loads(r["value"]), "_updated_at": r["updated_at"]}
        for r in rows
    }


def add_log(run_id: str, source: str, status: str, message: str, duration_ms: int) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO collect_log (run_id, source, status, message, duration_ms, ts)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, source, status, message, duration_ms, _now()),
        )


def get_logs(limit: int = 100) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT run_id, source, status, message, duration_ms, ts"
            " FROM collect_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_alert(rule: str, level: str, status: str, message: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO alerts (rule, level, status, message, ts) VALUES (?, ?, ?, ?, ?)",
            (rule, level, status, message, _now()),
        )


def get_alert_history(limit: int = 100) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT rule, level, status, message, ts FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_rule_status() -> dict[str, dict]:
    """Latest status row per rule."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT rule, level, status, message, ts FROM alerts a"
            " WHERE id = (SELECT MAX(id) FROM alerts b WHERE b.rule = a.rule)"
        ).fetchall()
    return {r["rule"]: dict(r) for r in rows}
