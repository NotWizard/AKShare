"""JSON safety — non-finite floats (nan / ±inf) must never reach the wire or DB.

Starlette's default ``JSONResponse.render`` uses ``json.dumps(..., allow_nan=False)``,
so any ``nan`` / ``inf`` in a response body raises ``ValueError`` → HTTP 500 (a hard
500, not merely invalid JSON). Endpoints without a Pydantic ``response_model`` are
unprotected. The fix makes JSON-safety a transport-layer invariant via
``SafeJSONResponse`` (app-wide ``default_response_class``) plus source-level
sanitizing so poison never persists.

These tests FAIL on the pre-fix code (transport 500s; serial keeps ±inf; the
snapshot column stores a bare ``NaN`` literal) and PASS afterwards.

Run:  cd backend && ../.venv312/bin/python -m pytest tests/test_json_safety.py -q
Deterministic, no network.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core import crcl_db  # noqa: E402
from backend.app.core.serial import df_to_records  # noqa: E402
from backend.app.main import app  # noqa: E402


# --- transport layer: register a temp route whose body carries nan / ±inf -----

def _nan_route():
    return {
        "a_nan": float("nan"),
        "b_inf": float("inf"),
        "c_ninf": float("-inf"),
        "ok": 1.5,
        "nested": {"vals": [float("nan"), 2.0, float("inf")]},
    }


app.add_api_route("/__test_json_safety__", _nan_route, methods=["GET"])

# raise_server_exceptions=False so the pre-fix ValueError surfaces as a clean
# 500 response (evidence) rather than propagating out of client.get().
_client = TestClient(app, raise_server_exceptions=False)


def test_transport_nulls_nonfinite_floats():
    resp = _client.get("/__test_json_safety__")
    assert resp.status_code == 200, resp.text  # pre-fix: 500
    body = resp.json()
    assert body["a_nan"] is None
    assert body["b_inf"] is None
    assert body["c_ninf"] is None
    assert body["ok"] == 1.5
    assert body["nested"]["vals"] == [None, 2.0, None]


# --- serializer: df_to_records must null nan AND ±inf -------------------------

def test_df_to_records_nulls_nan_and_inf():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
            "v": [float("nan"), float("inf"), float("-inf"), 3.14],
        }
    )
    recs = df_to_records(df)
    assert recs[0]["v"] is None          # nan (already handled pre-fix)
    assert recs[1]["v"] is None          # +inf (pre-fix: stayed inf)
    assert recs[2]["v"] is None          # -inf (pre-fix: stayed -inf)
    assert recs[3]["v"] == 3.14          # finite passes through
    assert recs[0]["date"] == "2024-01-01"  # ISO date formatting preserved


# --- persistence: set_snapshot must not store a bare NaN literal --------------

def test_set_snapshot_strips_nonfinite(tmp_path, monkeypatch):
    db_path = tmp_path / "crcl_test.db"
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", db_path)
    crcl_db.ensure_schema()

    crcl_db.set_snapshot(
        "valuation",
        {"trailing_pe": float("nan"), "forward_pe": float("inf"), "price": 12.5},
    )

    # Round-trip through the public getter → non-finite become None.
    snaps = crcl_db.get_snapshots()
    assert snaps["valuation"]["trailing_pe"] is None
    assert snaps["valuation"]["forward_pe"] is None
    assert snaps["valuation"]["price"] == 12.5

    # And the raw stored text must be valid JSON with no NaN/Infinity literal.
    with sqlite3.connect(db_path) as c:
        raw = c.execute(
            "SELECT value FROM snapshot WHERE key = 'valuation'"
        ).fetchone()[0]
    assert "NaN" not in raw
    assert "Infinity" not in raw
    assert "null" in raw
