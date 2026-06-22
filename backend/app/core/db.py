"""Database access — migrated verbatim from dashboard/db.py (lru_cache intact).

Same semantics: ``_load_full`` caches each table's full DataFrame; ``load``
returns a sliced view. The lru_cache key is the table name (the DB path is
fixed), so the refresh flow must call cache invalidation after a swap — see
core/cache.py.
"""

import functools
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "macro_data.db"


@functools.lru_cache(maxsize=32)
def _load_full(table: str) -> pd.DataFrame:
    """Load and cache the full table; ``date`` parsed to datetime once."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(f"SELECT * FROM [{table}]", conn)
    finally:
        conn.close()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load(table: str, start_date=None, end_date=None) -> pd.DataFrame:
    """Return *table* as a DataFrame, optionally sliced by date range."""
    df = _load_full(table)
    if start_date is None and end_date is None:
        return df
    if "date" not in df.columns:
        return df
    out = df
    try:
        if start_date is not None:
            out = out[out["date"] >= pd.Timestamp(start_date)]
        if end_date is not None:
            out = out[out["date"] <= pd.Timestamp(end_date)]
    except (ValueError, TypeError):
        # Invalid date string → skip the filter, return full table
        pass
    return out
