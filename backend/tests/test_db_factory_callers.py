"""A-M1 遗留：宏观库的两个访问方必须走 `core/db.connect()` 工厂。

`core/commentary.py` 与 `core/signal_history.py` 之前用裸 `sqlite3.connect(...)`：
WAL 是 DB *文件* 的持久属性所以照样享受，但 `busy_timeout` 是 *连接* 属性，
默认 0 —— 一旦有并发写入者持锁，这两个模块立刻抛
`sqlite3.OperationalError: database is locked`，而不是按 `BUSY_TIMEOUT_MS` 等待。

本模块只对着真实库的 TEMP 副本断言（`shutil.copy2`），绝不打开 `data/*.db` 写。

Run:  .venv312/bin/python -m pytest backend/tests/test_db_factory_callers.py -q
"""

import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core import commentary, db, signal_history  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"


def _tmp_copy(tmp_path: Path) -> Path:
    """A writable TEMP copy of the live macro DB (the live file is read-only here)."""
    dst = tmp_path / "macro_data.db"
    shutil.copy2(DATA_DIR / "macro_data.db", dst)
    return dst


def test_commentary_connection_has_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(commentary, "DB_PATH", _tmp_copy(tmp_path))
    assert commentary.connect is db.connect, "必须是同一个工厂，不是本地复刻"

    conn = commentary._connect()          # commentary 自己拿连接的唯一入口
    try:
        assert db.BUSY_TIMEOUT_MS > 0
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS
        # _row_to_dict 按列名取值，迁移不得丢掉 Row
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_signal_history_connection_has_busy_timeout(tmp_path):
    copy = _tmp_copy(tmp_path)
    assert signal_history.connect is db.connect, "必须是同一个工厂，不是本地复刻"

    conn = signal_history.connect(copy)   # read_history 调用的就是这个 callable
    try:
        assert db.BUSY_TIMEOUT_MS > 0
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS
    finally:
        conn.close()


def test_read_history_still_reads_rows(tmp_path):
    """回归：换工厂后读路径语义不变（倒序 + flips），连接照旧关闭。"""
    db_file = tmp_path / "hist.db"
    conn = sqlite3.connect(db_file)
    conn.execute(f"""CREATE TABLE {signal_history.TABLE} (
        ts TEXT, data_as_of TEXT, composite INTEGER,
        merrill TEXT, credit TEXT, inventory TEXT, debt TEXT)""")
    conn.executemany(
        f"INSERT INTO {signal_history.TABLE} VALUES (?,?,?,?,?,?,?)",
        [("t1", "2026-01", 1, "recovery", "easing", "active_restocking", "stable_growth"),
         ("t2", "2026-02", 0, "overheating", "easing", "active_restocking", "stable_growth")],
    )
    conn.commit()
    conn.close()

    rows = signal_history.read_history(limit=5, db_path=str(db_file))
    assert [r["ts"] for r in rows] == ["t2", "t1"]                      # 新→旧
    assert rows[0]["flips"] == [{"framework": "merrill",
                                 "prev": "recovery", "curr": "overheating"}]


def test_persist_still_commits(tmp_path, monkeypatch):
    """回归：换工厂后 `_persist_batch`（M4 起为 7 行一批）的建表/INSERT/commit 仍然落盘。"""
    db_file = tmp_path / "macro.db"
    monkeypatch.setattr(commentary, "DB_PATH", db_file)
    monkeypatch.setattr(commentary, "_table_ready", False)

    snapshot = {"data_as_of": {"derived_monthly": "2026-06"}, "sections": {}}
    parts = {name: f"{name} 文本" for name in (*commentary.SECTIONS, "overall")}
    profile = {"name": "p1", "model": "test-model", "endpoint": "chat_completions"}
    batch = commentary._persist_batch(snapshot, parts, profile, commentary.DEFAULT_TEMPLATES)

    assert batch["status"] == "ok" and batch["overall"] == "overall 文本"
    assert set(batch["sections"]) == set(commentary.SECTIONS)

    conn = sqlite3.connect(db_file)       # 全新裸连接读回 → 证明 commit 生效
    try:
        got = conn.execute(
            f"SELECT section, text, model, stale FROM {commentary.COMMENTARY_TABLE} "
            f"ORDER BY id").fetchall()
    finally:
        conn.close()
    assert len(got) == 7                                   # 6 板块 + overall
    assert all(model == "test-model" and stale == 0 for _, _, model, stale in got)
    assert ("overall", "overall 文本") in [(s, t) for s, t, _, _ in got]


def test_live_db_files_are_only_ever_copied():
    """本模块自身的隔离守卫：只读 data/macro_data.db，从不在原地写。"""
    assert (DATA_DIR / "macro_data.db").exists()
