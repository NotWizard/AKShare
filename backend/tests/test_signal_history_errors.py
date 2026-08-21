"""F13: read_history must distinguish a fresh install (no table → []) from a
real read failure (schema drift / corruption → raise), instead of swallowing
every sqlite error as "no data". Pre-fix (except sqlite3.Error: return []) the
schema-drift case silently returned [] — this test would fail on that code.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import signal_history  # noqa: E402


def test_missing_table_returns_empty(tmp_path):
    # Fresh install: DB exists but the signal_history table doesn't → [] (benign).
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()
    assert signal_history.read_history(db_path=str(db)) == []


def test_schema_drift_raises_not_silently_empty(tmp_path):
    # Table exists but is missing the expected columns (schema drift). The SELECT
    # raises OperationalError "no such column"; this MUST surface, not become [].
    db = tmp_path / "drift.db"
    conn = sqlite3.connect(str(db))
    conn.execute(f"CREATE TABLE {signal_history.TABLE} (ts TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.OperationalError):
        signal_history.read_history(db_path=str(db))
