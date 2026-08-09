"""Sources health — pure-function red/yellow/green rules + endpoint shape.

Run:  .venv312/bin/python -m pytest backend/tests -q
"""

import sys
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
    m = {"ts": "2026-08-09T10:00:00", "tables": {"cpi": {"status": "updated"}},
         "sources": [_src("cpi"), _src("ppi")]}
    h = sources_health(m)
    assert h["status"] == "green"
    assert h["updated_at"] == "2026-08-09T10:00:00"
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
    assert sources_health({}) == {"status": "green", "updated_at": None, "sources": []}


def test_empty_sources():
    assert sources_health({"ts": "t", "sources": []})["updated_at"] is None


def test_endpoint_shape():
    resp = client.get("/api/v1/sources/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("green", "yellow", "red")
    assert body["updated_at"] is None or isinstance(body["updated_at"], str)
    assert isinstance(body["sources"], list)
