"""Version-keyed cache invalidation (G03).

The API's in-memory table cache (``db._load_full``) must reflect an on-disk DB
swap WITHOUT any manual ``clear_all_caches()`` call: a CLI/cron run of
``scripts/01_fetch_data.py`` swaps ``data/macro_data.db`` via ``os.replace`` and
never touches the long-running API process, so cache invalidation cannot be tied
to the refresh CALL PATH — it must be tied to the DATA.

Root cause of the pre-fix bug: the lru_cache key was the table name only (the DB
path is fixed), so a swap left the stale DataFrame cached forever. The fix makes
the key a function of the DB *version* ``(mtime_ns, size)``.

These tests point ``db.DB_PATH`` at a TEMP copy (via monkeypatch) and NEVER
mutate ``data/macro_data.db``.

Run:  .venv312/bin/python -m pytest backend/tests/test_cache_version.py -q
"""

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import db  # noqa: E402
from backend.app.core.cache import clear_all_caches  # noqa: E402


def _write_table(path, values):
    """(Re)create table ``t (date TEXT, v REAL)`` at *path*, one row per value."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("DROP TABLE IF EXISTS t")
        conn.execute("CREATE TABLE t (date TEXT, v REAL)")
        conn.executemany(
            "INSERT INTO t (date, v) VALUES (?, ?)",
            [(f"2020-01-{i + 1:02d}", float(val)) for i, val in enumerate(values)],
        )
        conn.commit()
    finally:
        conn.close()


def _bump_mtime(path):
    """Force a strictly-greater mtime so the (mtime_ns, size) version differs
    even if the rewrite happened to land in the same coarse-clock tick."""
    st = os.stat(path)
    later = st.st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))


def test_load_reflects_db_swap_without_manual_clear(tmp_path, monkeypatch):
    """The core regression: a disk swap invalidates the cache automatically.

    FAILS on the original (table-only key) code — a stale cached DataFrame is
    returned. PASSES once the key includes the DB version. Uses ONLY the public
    surface (``db.load`` / ``db.DB_PATH`` / ``clear_all_caches``) so it runs
    unchanged on both the old and the new implementation.
    """
    db_file = tmp_path / "macro_data.db"
    _write_table(db_file, [1.0])
    monkeypatch.setattr(db, "DB_PATH", db_file)

    # Clean baseline — allowed because it is BEFORE the first load, not between
    # the swap and the re-read. The swap-invalidation under test uses NO clear.
    clear_all_caches()

    df1 = db.load("t")
    assert list(df1["v"]) == [1.0]

    # Simulate an atomic refresh swap: rewrite the file with NEW data. A new row
    # count changes size; _bump_mtime guarantees the mtime moves too.
    _write_table(db_file, [2.0, 3.0])
    _bump_mtime(db_file)

    # NO clear_all_caches() here — invalidation must be automatic.
    df2 = db.load("t")
    assert list(df2["v"]) == [2.0, 3.0], (
        "stale cached DataFrame returned — cache key is not a function of the DB "
        "version (this is the pre-fix failure mode)"
    )


def test_db_version_changes_on_swap_and_missing_fallback(tmp_path, monkeypatch):
    """`_db_version()` moves when the file changes and degrades gracefully when
    the DB is absent (fresh install must still import / not crash)."""
    db_file = tmp_path / "macro_data.db"
    _write_table(db_file, [1.0])
    monkeypatch.setattr(db, "DB_PATH", db_file)

    v1 = db._db_version()
    _write_table(db_file, [2.0, 3.0])
    _bump_mtime(db_file)
    assert db._db_version() != v1

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "does_not_exist.db")
    assert db._db_version() == (0, 0)


def test_clear_all_caches_still_exists_and_callable():
    """Regression guard for backend.app.core.refresh, which calls this on
    returncode==0. It is now a harmless memory-reclaim (no longer
    correctness-critical) but must remain importable and callable."""
    assert callable(clear_all_caches)
    clear_all_caches()  # must not raise
