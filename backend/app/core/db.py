"""Database access — migrated from dashboard/db.py (lru_cache intact).

Same semantics: ``_load_full`` returns each table's full DataFrame; ``load``
returns a sliced view. The cache key now includes a cheap DB *version* tag
(``_db_version()`` = ``(mtime_ns, size)``): an atomic ``os.replace`` swap of the
DB file — from ANY source (the API's own refresh flow OR a manual/cron run of
``scripts/01_fetch_data.py``) — changes mtime_ns+size, hence the key, hence the
next read comes from the new file automatically. Invalidation is thus tied to
the DATA, not to the refresh CALL PATH; ``core/cache.py``'s ``clear_all_caches()``
survives only as a memory-reclaim helper.
"""

import functools
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "macro_data.db"


def _db_version() -> tuple:
    """Cheap content tag for the DB file: ``(mtime_ns, size)``.

    One ``stat()`` (~microseconds) per call — used as part of the cache key so a
    file swap yields a fresh key → fresh read. A missing DB (fresh install,
    before the first fetch) must not crash import or the first call, so fall
    back to ``(0, 0)``.
    """
    try:
        st = DB_PATH.stat()
    except OSError:
        return (0, 0)
    return (st.st_mtime_ns, st.st_size)


@functools.lru_cache(maxsize=32)
def _load_full_versioned(table: str, version: tuple) -> pd.DataFrame:
    """Load and cache the full table; ``date`` parsed to datetime once.

    ``version`` is intentionally unused in the body: it exists only to make the
    lru_cache key a function of the DB file's identity, so a swap invalidates the
    entry automatically.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(f"SELECT * FROM [{table}]", conn)
    finally:
        conn.close()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _load_full(table: str) -> pd.DataFrame:
    """Public full-table loader: caches per ``(table, current DB version)``."""
    return _load_full_versioned(table, _db_version())


def load(table: str, start_date=None, end_date=None) -> pd.DataFrame:
    """Return *table* as a DataFrame, optionally sliced by date range.

    ``start_date``/``end_date`` are validated at the API boundary — the
    endpoints type them as ``datetime.date`` so FastAPI returns 422 on
    malformed input before this runs. They therefore arrive here as valid
    ``date``/``None`` (or valid ISO strings from internal callers) and are
    converted directly. No defensive ``except`` that would silently drop the
    filter and return the full table on bad input.
    """
    df = _load_full(table)
    if start_date is None and end_date is None:
        return df
    if "date" not in df.columns:
        return df
    out = df
    if start_date is not None:
        out = out[out["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        out = out[out["date"] <= pd.Timestamp(end_date)]
    return out
