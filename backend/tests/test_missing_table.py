"""缺表降级：白名单内但物理不存在的表，端点必须 200 空帧而非 500。

背景：`fiscal`/`external_demand` 是 M2 新增表，旧 live 库从未采集过它们，
`/api/v1/table/fiscal` 因 `SELECT * FROM [fiscal]` 抛未捕获的 `OperationalError`
直接 HTTP 500 → 「财政与外需」整页错误卡。根因修复落在 `db._load_full_versioned`：
只吞 "no such table" 这一良性情形返回空帧，其余（schema 漂移/损坏）仍冒泡。

用**临时库**（只建部分白名单表）而非依赖真库状态——这样即使后续采集把
`fiscal` 建出来，本测试仍稳定。

Run:  .venv312/bin/python -m pytest backend/tests/test_missing_table.py -q
"""

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.app.core import db  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """只含 gdp 一张白名单表的临时库；fiscal/external_demand 故意缺席。"""
    p = tmp_path / "macro_data.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE gdp (date TEXT, gdp_abs REAL, gdp_yoy REAL)")
    conn.execute("INSERT INTO gdp VALUES ('2026-01-01', 100.0, 5.0)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", p)
    db._load_full_versioned.cache_clear()   # 别命中真库缓存
    yield p
    db._load_full_versioned.cache_clear()


client = TestClient(app)


def test_existing_whitelisted_table_returns_rows(tmp_db):
    r = client.get("/api/v1/table/gdp")
    assert r.status_code == 200
    body = r.json()
    assert body["table"] == "gdp"
    assert len(body["records"]) == 1
    assert body["records"][0]["gdp_yoy"] == 5.0


@pytest.mark.parametrize("name", ["fiscal", "external_demand"])
def test_missing_whitelisted_table_degrades_to_empty_not_500(tmp_db, name):
    """核心回归：白名单内但库中不存在的表 → 200 空帧（不是 500）。"""
    r = client.get(f"/api/v1/table/{name}")
    assert r.status_code == 200, f"{name} 应优雅降级为空帧，而非 {r.status_code}"
    body = r.json()
    assert body["records"] == []
    assert body["columns"] == []


def test_non_whitelisted_table_is_404(tmp_db):
    """非白名单名（含 sqlite 内部表）→ 404，不泄露、不 500。"""
    for name in ("sqlite_master", "sqlite_sequence", "not_a_table"):
        r = client.get(f"/api/v1/table/{name}")
        assert r.status_code == 404, f"{name} 应 404，得到 {r.status_code}"


def test_load_returns_empty_frame_for_missing_table(tmp_db):
    """db 层直接断言：缺表 → 空 DataFrame，而非抛 OperationalError。"""
    out = db.load("external_demand")
    assert out.empty
    assert list(out.columns) == []
