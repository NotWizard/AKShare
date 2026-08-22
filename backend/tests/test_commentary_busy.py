"""Commentary busy-state derivation — F10.

The bug: `_busy` (a threading.Event) was set/cleared independently of `_gen_lock`,
so this interleaving was possible

    thread A: acquire → ... → finally: _busy.clear(); _gen_lock.release()
    thread B:                 acquire fails → _busy.set()          # after A cleared

leaving `_busy` set with NO generation running. get_current() then returned
`{"status": "generating", "text": ""}` forever, which (a) blanked out a
perfectly good commentary and (b) combined with the UI's 2s poll produced an
endless request loop.

The fix: delete the flag and derive busy-ness from the lock itself, so "busy"
cannot outlive the generation that owns it. While busy, the PREVIOUS row is
returned with regenerating=True instead of an empty string.

Run:  .venv312/bin/python -m pytest backend/tests/test_commentary_busy.py -q
"""

import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import commentary  # noqa: E402


def _seed(db: Path, text: str = "上一版评论") -> None:
    """Create the commentary table with one row, and point the module at it."""
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE commentary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, data_as_of TEXT NOT NULL, composite_score INTEGER,
            phase_snapshot TEXT NOT NULL, text TEXT NOT NULL, model TEXT,
            stale INTEGER DEFAULT 0)"""
    )
    conn.execute(
        "INSERT INTO commentary (ts, data_as_of, composite_score, phase_snapshot, text, model, stale)"
        " VALUES ('2026-01-01T00:00:00', '2025-12', 1, '{}', ?, 'test-model', 0)",
        (text,),
    )
    conn.commit()
    conn.close()


def _use_db(monkeypatch, db: Path) -> None:
    monkeypatch.setattr(commentary, "DB_PATH", db)
    monkeypatch.setattr(commentary, "_table_ready", True)


def test_no_separate_busy_flag_exists():
    """The racy flag is gone — busy-ness must have exactly one source of truth."""
    assert not hasattr(commentary, "_busy")


def test_busy_is_derived_from_the_lock(monkeypatch, tmp_path):
    db = tmp_path / "macro.db"
    _seed(db)
    _use_db(monkeypatch, db)

    assert commentary.get_current()["status"] == "ok"

    with commentary._gen_lock:
        cur = commentary.get_current()
        assert cur["status"] == "generating"
        # previous commentary is preserved, not blanked out
        assert cur["text"] == "上一版评论"
        assert cur["regenerating"] is True
        assert cur["model"] == "test-model"

    # lock released → busy is False again, no flag can outlive the generation
    assert commentary.get_current()["status"] == "ok"


def test_failed_generation_never_leaves_busy_set(monkeypatch, tmp_path):
    """A generation that raises must still clear busy-ness (old code could not)."""
    db = tmp_path / "macro.db"
    _seed(db)
    _use_db(monkeypatch, db)
    monkeypatch.setattr(commentary, "build_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    out = commentary._generate_impl()
    assert out["status"] == "error"
    assert commentary._gen_lock.locked() is False
    assert commentary.get_current()["status"] == "ok"


def test_concurrent_generate_does_not_strand_busy(monkeypatch, tmp_path):
    """The exact old interleaving: a second caller is refused WHILE the first is
    finishing. Neither path may leave busy-ness set afterwards."""
    db = tmp_path / "macro.db"
    _seed(db)
    _use_db(monkeypatch, db)

    entered = threading.Event()
    release = threading.Event()

    def slow_snapshot():
        entered.set()
        release.wait(5)
        raise RuntimeError("stop before the model call")

    monkeypatch.setattr(commentary, "build_snapshot", slow_snapshot)

    first: dict = {}
    t = threading.Thread(target=lambda: first.update(commentary._generate_impl()))
    t.start()
    assert entered.wait(5)

    # second caller: acquire fails → reports generating, sets nothing
    second = commentary._generate_impl()
    assert second["status"] == "generating"
    # while the first still holds the lock, GET keeps the previous text
    assert commentary.get_current()["text"] == "上一版评论"

    release.set()
    t.join(5)
    assert first["status"] == "error"
    assert commentary._gen_lock.locked() is False
    assert commentary.get_current()["status"] == "ok"


def test_empty_db_while_generating_still_reports_generating(monkeypatch, tmp_path):
    """No previous row → empty text is correct (nothing to preserve)."""
    db = tmp_path / "macro.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE commentary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, data_as_of TEXT NOT NULL, composite_score INTEGER,
            phase_snapshot TEXT NOT NULL, text TEXT NOT NULL, model TEXT,
            stale INTEGER DEFAULT 0)"""
    )
    conn.commit()
    conn.close()
    _use_db(monkeypatch, db)

    with commentary._gen_lock:
        cur = commentary.get_current()
        assert cur["status"] == "generating"
        assert cur["text"] == ""
        assert cur["regenerating"] is False
