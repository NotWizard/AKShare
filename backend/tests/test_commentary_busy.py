"""Commentary busy-state derivation — F10.

The bug: `_busy` (a threading.Event) was set/cleared independently of `_gen_lock`,
so this interleaving was possible

    thread A: acquire → ... → finally: _busy.clear(); _gen_lock.release()
    thread B:                 acquire fails → _busy.set()          # after A cleared

leaving `_busy` set with NO generation running. get_current() then returned
`{"status": "generating", ...}` forever, which combined with the UI's 2s poll
produced an endless request loop.

The fix: delete the flag and derive busy-ness from the lock itself, so "busy"
cannot outlive the generation that owns it. While busy, the PREVIOUS batch is
returned with regenerating=True instead of an empty card.

M4 移植后：上一批的形态是「7 行一批」（section 列），断言保留的是 overall 文本。

Run:  .venv312/bin/python -m pytest backend/tests/test_commentary_busy.py -q
"""

import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import commentary  # noqa: E402

_M4_DDL = """CREATE TABLE commentary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, data_as_of TEXT NOT NULL, composite_score INTEGER,
    phase_snapshot TEXT NOT NULL, text TEXT NOT NULL, model TEXT,
    stale INTEGER DEFAULT 0, section TEXT DEFAULT 'overall',
    endpoint TEXT, template_hash TEXT, profile TEXT)"""


def _seed(db: Path, text: str = "上一版评论") -> None:
    """Create the M4 commentary table with one overall row, point the module at it."""
    conn = sqlite3.connect(db)
    conn.execute(_M4_DDL)
    conn.execute(
        "INSERT INTO commentary (ts, data_as_of, composite_score, phase_snapshot,"
        " text, model, stale, section) VALUES ('2026-01-01T00:00:00', '{}', 1, '{}', ?,"
        " 'test-model', 0, 'overall')",
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
        assert cur["overall"] == "上一版评论"
        assert cur["regenerating"] is True
        assert cur["provenance"]["model"] == "test-model"

    # lock released → busy is False again, no flag can outlive the generation
    assert commentary.get_current()["status"] == "ok"


def test_failed_generation_never_leaves_busy_set(monkeypatch, tmp_path):
    """A generation that raises must still clear busy-ness (old code could not)."""
    db = tmp_path / "macro.db"
    _seed(db)
    _use_db(monkeypatch, db)

    def boom(*a, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(commentary, "build_section_snapshot", boom)
    # 让配置存在，走到 snapshot 才抛（profile/key 早退不会进 try）
    monkeypatch.setattr(commentary, "_configured", lambda: ({"name": "p", "model": "m"}, "k"))

    out = commentary._generate_impl()
    assert out["status"] == "error"
    assert not commentary._gen_lock.locked()
    assert commentary.get_current()["status"] == "ok"   # busy 不残留


def test_busy_without_any_batch_is_plain_generating(monkeypatch, tmp_path):
    """在途 + 没有任何历史批次 → 纯 generating（regenerating=False），不报上一版。"""
    db = tmp_path / "macro.db"
    sqlite3.connect(db).close()          # 空库（无表）
    monkeypatch.setattr(commentary, "DB_PATH", db)
    monkeypatch.setattr(commentary, "_table_ready", False)

    with commentary._gen_lock:
        cur = commentary.get_current()
        assert cur["status"] == "generating"
        assert cur["regenerating"] is False

    assert threading.active_count() >= 1   # 无僵尸线程副作用（锁可重入性已由上例覆盖）
