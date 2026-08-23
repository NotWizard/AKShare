"""F13-rest: `get_current` 必须区分"全新安装尚无该表"与"真实读取失败"。

改前是 `except Exception: → {"status": "empty", "msg": "暂无评论"}`，于是
`AttributeError`/`KeyError` 这类编程错误、以及 schema 漂移/镜像损坏，全被伪装成
良性的"暂无评论"——UI 上一个真实故障完全看不见。

处理方式照抄同类模块 `core/signal_history.read_history`（`2e437dc`）：只咽下
`sqlite3.OperationalError` 且消息含 "no such table" 这一个良性分支（fresh install
不 500），其余一律冒泡。

Run:  .venv312/bin/python -m pytest backend/tests/test_commentary_errors.py -q
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import commentary  # noqa: E402


def _empty_db(tmp_path: Path) -> Path:
    """A real DB file with NO commentary table (fresh install)."""
    db = tmp_path / "macro.db"
    sqlite3.connect(db).close()
    return db


def test_programming_error_propagates(monkeypatch, tmp_path):
    """非 sqlite 的编程错误必须冒泡，不得变成 status="empty"。"""
    monkeypatch.setattr(commentary, "DB_PATH", _empty_db(tmp_path))
    monkeypatch.setattr(commentary, "_table_ready", True)

    def boom(conn):
        raise AttributeError("'NoneType' object has no attribute 'fetchone'")

    monkeypatch.setattr(commentary, "_latest_row", boom)

    with pytest.raises(AttributeError):
        commentary.get_current()


def test_non_benign_sqlite_error_propagates(monkeypatch, tmp_path):
    """schema 漂移（no such column）不是良性分支 → 必须冒泡。"""
    monkeypatch.setattr(commentary, "DB_PATH", _empty_db(tmp_path))
    monkeypatch.setattr(commentary, "_table_ready", True)

    def drift(conn):
        raise sqlite3.OperationalError("no such column: ts")

    monkeypatch.setattr(commentary, "_latest_row", drift)

    with pytest.raises(sqlite3.OperationalError):
        commentary.get_current()


def test_missing_table_still_returns_benign_empty(monkeypatch, tmp_path):
    """唯一良性分支：表真的不存在 → 仍回"暂无评论"（fresh install 不 500）。"""
    monkeypatch.setattr(commentary, "DB_PATH", _empty_db(tmp_path))
    monkeypatch.setattr(commentary, "_table_ready", True)   # 跳过 CREATE TABLE

    out = commentary.get_current()
    assert out == {"status": "empty", "msg": "暂无评论", "text": ""}


def test_fresh_install_creates_table_and_reports_empty(monkeypatch, tmp_path):
    """常规 fresh install 路径（_table_ready=False）不受收窄影响：建表后回 empty。"""
    db = _empty_db(tmp_path)
    monkeypatch.setattr(commentary, "DB_PATH", db)
    monkeypatch.setattr(commentary, "_table_ready", False)

    assert commentary.get_current()["status"] == "empty"
    conn = sqlite3.connect(db)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    finally:
        conn.close()
    assert commentary.COMMENTARY_TABLE in names
