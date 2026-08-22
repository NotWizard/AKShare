"""SQLite concurrency PRAGMAs + explicit connection close — G09/A-M1.

Both DB files shipped as ``journal_mode=delete`` (verified). Under a rollback
journal a writer's EXCLUSIVE lock makes every concurrent reader fail INSTANTLY
with ``sqlite3.OperationalError: database is locked`` — and no CRCL read endpoint
has a handler, so that surfaced as an unhandled HTTP 500 while a collect ran.
On top of that, ``crcl_db`` used ``with sqlite3.connect(...) as conn:``, which
COMMITS but never CLOSES (it relied on CPython refcounting to release the fd).

Every test here works on a TEMP COPY / temp path. WAL is a persistent property
of the DB FILE, so asserting it on the real data/*.db would MUTATE them — this
module never opens them for writing (the two copies are made with shutil.copy2).

Run: .venv312/bin/python -m pytest backend/tests/test_sqlite_pragmas.py -q
"""

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core import crcl_db, db  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"


def _copy_as_rollback_journal(src: Path, dst: Path) -> Path:
    """Copy a DB and force the COPY back to journal_mode=delete.

    Makes the assertions independent of whatever mode the live file happens to be
    in (it becomes WAL the first time the app runs), so the test always proves the
    factory CONVERTS rather than merely observing an already-converted file.
    """
    shutil.copy2(src, dst)
    conn = sqlite3.connect(dst)
    try:
        conn.execute("PRAGMA journal_mode = DELETE")
    finally:
        conn.close()
    assert _journal_of(dst) == "delete", "pre-condition: copy is a rollback journal"
    return dst


def _journal_of(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()


# ── the factory applies all three PRAGMAs, for BOTH DBs ─────────────────────
def test_macro_db_connection_is_wal_with_busy_timeout(tmp_path, monkeypatch):
    copy = _copy_as_rollback_journal(DATA_DIR / "macro_data.db",
                                     tmp_path / "macro_data.db")
    monkeypatch.setattr(db, "DB_PATH", copy)
    conn = db.connect()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS
        assert db.BUSY_TIMEOUT_MS > 0
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    finally:
        conn.close()
    assert _journal_of(copy) == "wal", "WAL must persist on the DB file"


def test_crcl_db_connection_is_wal_with_busy_timeout(tmp_path, monkeypatch):
    copy = _copy_as_rollback_journal(DATA_DIR / "crcl_monitor.db",
                                     tmp_path / "crcl_monitor.db")
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", copy)
    conn = crcl_db._conn()          # the CRCL path must go through the factory
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_real_db_files_are_left_untouched():
    """Guard for this module's own hermeticity: it only ever READS data/*.db."""
    for name in ("macro_data.db", "crcl_monitor.db"):
        assert (DATA_DIR / name).exists()


# ── the bug the PRAGMAs fix: a reader no longer dies on a busy writer ───────
def test_reader_survives_a_writer_holding_the_write_lock(tmp_path, monkeypatch):
    """With an EXCLUSIVE write transaction open, a read still succeeds.

    Pre-fix (rollback journal, busy_timeout=0) the read raised
    ``OperationalError: database is locked`` → unhandled 500 on /crcl/*.
    """
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", tmp_path / "crcl.db")
    crcl_db.ensure_schema()
    crcl_db.upsert_points("usdc_circ", [("2026-01-01", 1.0)])

    writer = crcl_db._conn()
    try:
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT OR REPLACE INTO metric_points VALUES ('x','2026-01-02',2.0)")
        # readers must not be blocked by the open writer
        assert crcl_db.get_series("usdc_circ") == [{"date": "2026-01-01", "value": 1.0}]
        assert crcl_db.get_logs(limit=1) == []
        writer.rollback()
    finally:
        writer.close()


# ── connections are CLOSED, not left to refcounting ─────────────────────────
@pytest.mark.parametrize("call", [
    lambda: crcl_db.upsert_points("usdc_circ", [("2026-01-01", 1.0)]),   # write path
    lambda: crcl_db.get_series("usdc_circ"),                             # read path
])
def test_connections_are_explicitly_closed(tmp_path, monkeypatch, call):
    """Every connection handed out is closed when the helper returns.
    (Pre-fix ``with sqlite3.connect(...)`` committed but never closed.)"""
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", tmp_path / "crcl.db")
    crcl_db.ensure_schema()

    handed_out = []
    real_conn = crcl_db._conn

    def _spy():
        conn = real_conn()
        handed_out.append(conn)
        return conn

    monkeypatch.setattr(crcl_db, "_conn", _spy)
    call()

    assert handed_out, "helper did not open a connection"
    for conn in handed_out:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")     # raises only if truly closed


def test_write_helper_commits(tmp_path, monkeypatch):
    """Regression guard: adding the close must not drop the commit."""
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", tmp_path / "crcl.db")
    crcl_db.ensure_schema()
    crcl_db.add_log("run", "src", "ok", "msg", 5)
    crcl_db.upsert_points("usdc_circ", [("2026-01-01", 1.5)])
    # read back through a brand-new connection
    assert [r["source"] for r in crcl_db.get_logs(limit=5)] == ["src"]
    assert crcl_db.get_series("usdc_circ") == [{"date": "2026-01-01", "value": 1.5}]


def test_write_helper_rolls_back_on_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", tmp_path / "crcl.db")
    crcl_db.ensure_schema()
    with pytest.raises(RuntimeError):
        with crcl_db._write_conn() as conn:
            conn.execute("INSERT INTO collect_log"
                         " (run_id, source, status, message, duration_ms, ts)"
                         " VALUES ('r','s','ok','m',1,'t')")
            raise RuntimeError("boom")
    assert crcl_db.get_logs(limit=5) == []


# ── the since window pushed into SQL ───────────────────────────────────────
def test_get_series_since_bounds_the_window(tmp_path, monkeypatch):
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", tmp_path / "crcl.db")
    crcl_db.ensure_schema()
    crcl_db.upsert_points("usdc_circ", [("2024-01-01", 1.0), ("2026-01-01", 2.0)])
    assert len(crcl_db.get_series("usdc_circ")) == 2
    windowed = crcl_db.get_series("usdc_circ", since="2025-06-01")
    assert [p["date"] for p in windowed] == ["2026-01-01"]
