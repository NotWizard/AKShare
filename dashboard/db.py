"""Thin database access helper — load any table as a filtered DataFrame.

Note: ``_load_full`` caches each table's full DataFrame in memory. ``load`` then
returns a sliced view; callers that need to mutate must ``.copy()`` first to
avoid polluting the cache.
"""

import functools
import sqlite3
import pandas as pd
from dashboard.config import DB_PATH


@functools.lru_cache(maxsize=32)
def _load_full(table: str) -> pd.DataFrame:
    """Load and cache the full table; ``date`` parsed to datetime once."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(f"SELECT * FROM [{table}]", conn)
    finally:
        conn.close()

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])

    return df


def load(table: str, start_date=None, end_date=None) -> pd.DataFrame:
    """Return *table* as a DataFrame, optionally sliced by date range.

    Parameters
    ----------
    table : str
        Table name (e.g. ``'derived_monthly'``).
    start_date, end_date : str or datetime-like, optional
        Inclusive date boundaries applied after loading.
    """
    df = _load_full(table)

    if start_date is None and end_date is None:
        return df

    if 'date' not in df.columns:
        return df

    out = df
    if start_date is not None:
        out = out[out['date'] >= pd.Timestamp(start_date)]
    if end_date is not None:
        out = out[out['date'] <= pd.Timestamp(end_date)]
    return out
