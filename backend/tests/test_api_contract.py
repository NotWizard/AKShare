"""API contract tests (G18 · O-H7).

Locks the wire contract of the three read endpoints the frontend depends on to
their Pydantic ``response_model`` (and, for the model-less CRCL endpoint, its
documented shape), and ties the runtime responses back to the committed OpenAPI
schema.

Hermetic: each test runs against a TEMP COPY of the committed fixture DBs
(``backend/tests/fixtures/``), so it is deterministic and never touches the real
``data/*.db`` — it passes identically on a developer machine and on CI.

Run:  .venv312/bin/python -m pytest backend/tests/test_api_contract.py -q
"""

import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core import crcl_db, db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.schemas.cycles import CycleFrame, DerivedFrame  # noqa: E402
from backend.app.schemas.signals import SignalSummary  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient whose macro + CRCL DBs point at writable temp copies of the
    committed fixtures (no lifespan → no startup network collection)."""
    macro = tmp_path / "macro_data.db"
    crcl = tmp_path / "crcl_monitor.db"
    shutil.copy2(_FIXTURES / "macro_data.db", macro)
    shutil.copy2(_FIXTURES / "crcl_monitor.db", crcl)
    monkeypatch.setattr(db, "DB_PATH", macro)
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", crcl)
    return TestClient(app, raise_server_exceptions=False)


# ── /api/v1/signals → SignalSummary ──────────────────────────────────────────
def test_signals_response_matches_schema(client):
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200
    body = resp.json()

    model = SignalSummary.model_validate(body)   # raises on any contract breach
    assert -4 <= model.composite_score <= 4
    assert set(body) >= {"merrill", "credit", "inventory", "debt", "cross_lags",
                         "as_of", "included", "excluded", "stale", "composite_raw"}
    # the fixture has all four frameworks populated → a real, non-null frontier
    assert body["as_of"] and _ISO_DATE.fullmatch(body["as_of"])
    for fw in ("merrill", "credit", "inventory", "debt"):
        assert "phase" in body[fw] and "score" in body[fw]


# ── /api/v1/derived/monthly → DerivedFrame ───────────────────────────────────
def test_derived_monthly_response_matches_schema(client):
    resp = client.get("/api/v1/derived/monthly")
    assert resp.status_code == 200

    frame = DerivedFrame.model_validate(resp.json())
    assert frame.table == "derived_monthly"
    assert "date" in frame.columns
    assert frame.records, "fixture derived_monthly must not be empty"
    # dates serialise as plain ISO 'YYYY-MM-DD' (not full datetimes) — the
    # frontend's date-key join depends on this exact format.
    assert _ISO_DATE.fullmatch(frame.records[0]["date"])


# ── /api/v1/cycles/{name} → CycleFrame ───────────────────────────────────────
@pytest.mark.parametrize("name", ["merrill", "credit", "inventory", "debt"])
def test_cycles_response_matches_schema(client, name):
    resp = client.get(f"/api/v1/cycles/{name}")
    assert resp.status_code == 200
    frame = CycleFrame.model_validate(resp.json())
    assert frame.series, f"{name} cycle series is empty on the fixture"


# ── /api/v1/crcl/overview (no response_model → assert documented shape) ───────
def test_crcl_overview_documented_shape(client):
    resp = client.get("/api/v1/crcl/overview")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body) == {"snapshots", "alert_summary", "last_run", "metric_labels"}
    assert isinstance(body["snapshots"], dict)
    assert set(body["alert_summary"]) == {"triggered", "levels", "rule_count"}
    assert isinstance(body["alert_summary"]["triggered"], list)
    assert isinstance(body["metric_labels"], dict)


# ── runtime ↔ committed OpenAPI: the endpoints declare the models above ───────
def test_openapi_declares_the_read_models():
    schema = app.openapi()

    def _ref(path):
        return (schema["paths"][path]["get"]["responses"]["200"]["content"]
                ["application/json"]["schema"]["$ref"])

    assert _ref("/api/v1/signals").endswith("/SignalSummary")
    assert _ref("/api/v1/derived/monthly").endswith("/DerivedFrame")
    assert _ref("/api/v1/cycles/{name}").endswith("/CycleFrame")
    # crcl/overview has no response_model by design → no schema ref (free-form dict)
    overview = schema["paths"]["/api/v1/crcl/overview"]["get"]["responses"]["200"]
    assert "$ref" not in overview.get("content", {}).get(
        "application/json", {}).get("schema", {})
