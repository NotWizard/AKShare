"""Sources health — pure-function red/yellow/green rules + endpoint shape.

Run:  .venv312/bin/python -m pytest backend/tests -q
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core.refresh import sources_health  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)


def _src(table, cf=0, ok=True, error=None):
    return {"table": table, "channel": "test", "ok": ok, "elapsed_s": 0.1,
            "error": error, "consecutive_failures": cf, "last_success": None}


def test_green_all_ok():
    # 用动态新鲜时间戳：新增陈旧度规则会把任何写死的过去日期最终判为过期(黄)，
    # 故这里取 now() 以确定性地检验本意——全部源 ok + manifest 新鲜 → green。
    ts = datetime.now().isoformat(timespec="seconds")
    m = {"ts": ts, "tables": {"cpi": {"status": "updated"}},
         "sources": [_src("cpi"), _src("ppi")]}
    h = sources_health(m)
    assert h["status"] == "green"
    assert h["updated_at"] == ts
    assert all(s["warning"] is None for s in h["sources"])


def test_yellow_single_failure():
    h = sources_health({"ts": "t", "tables": {}, "sources": [_src("cpi", cf=1, ok=False)]})
    assert h["status"] == "yellow"


def test_yellow_kept_previous_warning():
    m = {"ts": "t",
         "tables": {"cpi": {"status": "kept_previous", "reason": "empty result"}},
         "sources": [_src("cpi")]}
    h = sources_health(m)
    assert h["status"] == "yellow"
    assert h["sources"][0]["warning"] == "kept previous — empty result"


def test_yellow_dual_divergence_warning():
    src = _src("cpi")
    src["dual"] = {"series": "cpi_yoy", "source": "ak.macro_china_cpi_yearly",
                   "date": "2025-07-01", "primary": 1.5, "secondary": 0.0,
                   "diff": 1.5, "divergent": True, "error": None}
    h = sources_health({"ts": "t", "tables": {"cpi": {"status": "updated"}},
                        "sources": [src]})
    assert h["status"] == "yellow"
    assert "dual-source divergence" in h["sources"][0]["warning"]


def test_green_dual_match_or_error_only():
    # divergent=False（含次源失败只记 error）→ 不触发 warning
    for dual in ({"series": "cpi_yoy", "divergent": False, "primary": 0.0,
                  "secondary": 0.0, "date": "2025-07-01", "error": None},
                 {"series": "cpi_yoy", "divergent": False, "primary": None,
                  "secondary": None, "date": None, "error": "Timeout: x"}):
        src = _src("cpi")
        src["dual"] = dual
        h = sources_health({"ts": "t", "tables": {"cpi": {"status": "updated"}},
                            "sources": [src]})
        assert h["status"] == "green"
        assert h["sources"][0]["warning"] is None


def test_red_two_consecutive_failures():
    h = sources_health({"ts": "t", "tables": {},
                        "sources": [_src("ppi", cf=2, ok=False, error="Timeout: x")]})
    assert h["status"] == "red"


def test_red_beats_yellow():
    h = sources_health({"ts": "t", "tables": {},
                        "sources": [_src("cpi", cf=1), _src("ppi", cf=3)]})
    assert h["status"] == "red"


def test_carried_over_entry_still_counts():
    # 增量窗口外跳过的源整条沿用上次（此处 cf=2）→ 依然 red
    h = sources_health({"ts": "t", "tables": {}, "sources": [_src("gdp", cf=2)]})
    assert h["status"] == "red"


def test_no_manifest():
    # 空 manifest（无 sources）→ unknown（灰），不再谎报 green（O-C1/B1 修复）
    assert sources_health({}) == {"status": "unknown", "updated_at": None, "sources": []}


def test_empty_sources():
    assert sources_health({"ts": "t", "sources": []})["updated_at"] is None


def test_endpoint_shape():
    resp = client.get("/api/v1/sources/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("green", "yellow", "red", "unknown")
    assert body["updated_at"] is None or isinstance(body["updated_at"], str)
    assert isinstance(body["sources"], list)
