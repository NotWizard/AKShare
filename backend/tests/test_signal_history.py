"""Signal history tests — flip annotation, append-only writes, endpoint shape.

Run:  .venv312/bin/python -m pytest backend/tests/test_signal_history.py -q
"""

import importlib.util
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core.db import DB_PATH  # noqa: E402
from backend.app.core.signal_history import annotate_flips, read_history  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)

FIELDS = ("ts", "data_as_of", "composite", "merrill", "credit", "inventory", "debt")


def _load_writer_mod():
    """Load scripts/signal_history.py (importlib, same technique as
    _pipeline.run_derived / test_derived_golden)."""
    p = Path(__file__).resolve().parents[2] / "scripts" / "signal_history.py"
    spec = importlib.util.spec_from_file_location("_signal_history_writer", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. flip detection (pure function, constructed sequences) ────────────────
def _row(ts, merrill="recovery", credit="easing", inventory="active_restocking",
         debt="beautiful_deleveraging"):
    return {"ts": ts, "data_as_of": None, "composite": 0,
            "merrill": merrill, "credit": credit,
            "inventory": inventory, "debt": debt}


def test_annotate_flips_no_flips():
    rows = [_row("t2"), _row("t1")]          # newest first
    out = annotate_flips(rows)
    assert all(r["flips"] == [] for r in out)


def test_annotate_flips_single_framework_direction():
    rows = [_row("t2", credit="tightening"), _row("t1")]
    out = annotate_flips(rows)
    assert out[0]["flips"] == [{"framework": "credit", "prev": "easing", "curr": "tightening"}]
    assert out[1]["flips"] == []              # oldest in window: no prev row


def test_annotate_flips_multi_and_none():
    rows = [_row("t3", merrill="overheating", credit=None),
            _row("t2", credit="easing"),
            _row("t1", credit=None)]
    out = annotate_flips(rows)
    # t3 vs t2: merrill flipped + credit None→easing counts as a flip
    assert {"framework": "merrill", "prev": "recovery", "curr": "overheating"} in out[0]["flips"]
    assert {"framework": "credit", "prev": "easing", "curr": None} in out[0]["flips"]
    # t2 vs t1: None→easing flip
    assert out[1]["flips"] == [{"framework": "credit", "prev": None, "curr": "easing"}]
    assert out[2]["flips"] == []


# ── 2. two writes → two rows (append-only, temp copy of live DB) ────────────
def test_two_writes_two_rows():
    if not DB_PATH.exists():
        pytest.skip("live DB absent")
    writer = _load_writer_mod()
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        shutil.copy2(DB_PATH, tmp)
        # isolation: drop rows inherited from the live copy so we count only ours
        conn = sqlite3.connect(tmp)
        conn.execute("DROP TABLE IF EXISTS signal_history")
        conn.commit()
        conn.close()
        writer.append_signal_history(tmp, "t1")
        writer.append_signal_history(tmp, "t2")

        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT ts, data_as_of, composite, merrill, credit, inventory, debt "
            "FROM signal_history ORDER BY rowid").fetchall()
        conn.close()
        assert len(rows) == 2                  # append-only: no dedup
        assert [r[0] for r in rows] == ["t1", "t2"]

        from analysis.signals import compute_signals
        sig = compute_signals(str(tmp))
        for r in rows:
            assert r[2] == sig["composite_score"]
            assert r[3] == sig["merrill"]["phase"]
            assert r[4] == sig["credit"]["phase"]
            assert r[5] == sig["inventory"]["phase"]
            assert r[6] == sig["debt"]["phase"]
            assert r[1] is None or re.fullmatch(r"\d{4}-\d{2}", r[1])
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── 3. endpoint shape ────────────────────────────────────────────────────────
def test_history_endpoint_shape():
    resp = client.get("/api/v1/signals/history")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert isinstance(items, list)
    assert all(items[i]["ts"] >= items[i + 1]["ts"] for i in range(len(items) - 1))
    for r in items:
        assert set(r) == set(FIELDS) | {"flips"}
    # flips annotations consistent with adjacent row diffs (newest first)
    for i in range(len(items) - 1):
        expected = [f for f in ("merrill", "credit", "inventory", "debt")
                    if items[i][f] != items[i + 1][f]]
        assert sorted(fl["framework"] for fl in items[i]["flips"]) == sorted(expected)


def test_history_endpoint_limit():
    resp = client.get("/api/v1/signals/history?limit=1")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 1
    assert client.get("/api/v1/signals/history?limit=0").status_code == 422


def test_read_history_missing_table_returns_empty():
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        assert read_history(db_path=tmp) == []   # fresh install: no 500
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── 4. boundaries + existing-rows +1 + limit bounds ─────────────────────────
def test_annotate_flips_empty():
    assert annotate_flips([]) == []


def test_annotate_flips_single_row():
    out = annotate_flips([_row("t1")])
    assert len(out) == 1 and out[0]["flips"] == []   # 唯一一行即最旧：无前值


def test_append_with_existing_rows_plus_one():
    """已有历史行时，一次成功提交（01_fetch commit 后调用 append）恰 +1 行。"""
    if not DB_PATH.exists():
        pytest.skip("live DB absent")
    writer = _load_writer_mod()
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        shutil.copy2(DB_PATH, tmp)
        writer.append_signal_history(tmp, "t-prev")   # 保底：确保已有历史行
        conn = sqlite3.connect(tmp)
        before = conn.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0]
        conn.close()
        assert before >= 1

        writer.append_signal_history(tmp, "t-new")    # 模拟一次成功刷新提交

        conn = sqlite3.connect(tmp)
        after = conn.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0]
        last_ts = conn.execute(
            "SELECT ts FROM signal_history ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        conn.close()
        assert after == before + 1                    # append-only：恰 +1，不去重
        assert last_ts == "t-new"                     # 新行在末尾（rowid 单调）
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_history_endpoint_limit_bounds():
    assert len(client.get("/api/v1/signals/history").json()["items"]) <= 60
    assert client.get("/api/v1/signals/history?limit=500").status_code == 200
    assert client.get("/api/v1/signals/history?limit=501").status_code == 422
