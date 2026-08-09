"""Append-only signal history — one row per successful pipeline commit."""

import sqlite3
import sys
from pathlib import Path

# repo root on sys.path so `import analysis` resolves when run via scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.signals import compute_signals  # noqa: E402

TABLE = "signal_history"
_CREATE = """CREATE TABLE IF NOT EXISTS signal_history (
    ts TEXT NOT NULL, data_as_of TEXT, composite INTEGER NOT NULL,
    merrill TEXT, credit TEXT, inventory TEXT, debt TEXT)"""


def append_signal_history(db_path, ts):
    """成功提交后追加一行 composite+四相位快照。抛异常由调用方告警兜底。"""
    sig = compute_signals(str(db_path))          # 提交后的新库
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE)
        try:  # data_as_of 口径同 commentary._latest_data_date
            row = conn.execute("SELECT MAX(date) FROM derived_monthly").fetchone()
            data_as_of = str(row[0])[:7] if row and row[0] else None
        except sqlite3.Error:
            data_as_of = None
        conn.execute(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?)",
            (ts, data_as_of, sig["composite_score"], sig["merrill"]["phase"],
             sig["credit"]["phase"], sig["inventory"]["phase"], sig["debt"]["phase"]))
        conn.commit()
    finally:
        conn.close()
