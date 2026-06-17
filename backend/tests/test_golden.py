"""Golden tests — the API must return exactly what db.load returns.

P0 exit criterion: GET /api/v1/derived/monthly == db.load('derived_monthly').
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core import db  # noqa: E402
from backend.app.core.serial import df_to_records  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_derived_monthly_matches_db_load():
    """GOLDEN: API output == direct db.load (the parity guarantee)."""
    resp = client.get("/api/v1/derived/monthly")
    assert resp.status_code == 200
    payload = resp.json()
    expected = df_to_records(db.load("derived_monthly"))
    assert payload["table"] == "derived_monthly"
    assert payload["columns"] == list(db.load("derived_monthly").columns)
    assert payload["records"] == expected
    assert len(payload["records"]) == len(expected) > 0


def test_derived_monthly_date_slice():
    resp = client.get("/api/v1/derived/monthly?start=2020-01-01&end=2020-12-31")
    assert resp.status_code == 200
    dates = [r["date"] for r in resp.json()["records"]]
    assert dates and min(dates) >= "2020-01-01" and max(dates) <= "2020-12-31"


def test_cycles_credit_returns_latest_phase():
    resp = client.get("/api/v1/cycles/credit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest_phase"] in ("easing", "tightening", "neutral")
    assert len(body["series"]) > 0


def test_signals_in_range():
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200
    s = resp.json()
    assert -4 <= s["composite_score"] <= 4
    assert s["interpretation"]


def test_refresh_status():
    resp = client.get("/api/v1/refresh/status")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "busy", "error", "unknown")
