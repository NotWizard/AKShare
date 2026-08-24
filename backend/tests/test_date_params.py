"""F9 regression — malformed ``start``/``end`` must be rejected at the API
boundary (HTTP 422), not silently swallowed.

Before the fix the SAME bad input produced two dangerous, inconsistent results:
  * ``/api/v1/derived/monthly`` swallowed the ``ValueError`` in ``db.load`` and
    returned HTTP 200 with the ENTIRE unbounded table (silent wrong-scope).
  * ``/api/v1/cycles/credit`` had no guard, so ``pd.Timestamp(bad)`` raised and
    surfaced as an uncaught HTTP 500.

Typing the query params as ``datetime.date`` makes FastAPI validate the input
and return 422 BEFORE the handler runs — consistent for every endpoint. Valid
ISO dates keep slicing exactly as before.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core import db  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)


def test_monthly_invalid_start_is_422_not_silent_full_table():
    """Pre-fix: 200 + full unbounded table (silent). Post-fix: 422."""
    resp = client.get("/api/v1/derived/monthly?start=2024-13-01")
    assert resp.status_code == 422, (
        f"expected 422, got {resp.status_code} "
        f"(pre-fix this was a silent 200 full-table)"
    )


def test_monthly_invalid_end_is_422():
    resp = client.get("/api/v1/derived/monthly?end=2024-02-30")
    assert resp.status_code == 422


def test_cycles_invalid_start_is_422_not_500():
    """Pre-fix: uncaught ValueError → HTTP 500. Post-fix: 422."""
    resp = client.get("/api/v1/cycles/credit?start=not-a-date")
    assert resp.status_code == 422, (
        f"expected 422, got {resp.status_code} (pre-fix this was a 500)"
    )


def test_monthly_valid_range_still_slices():
    """Valid ISO range: 200, rows within range, and the slice actually
    narrows the table (proves the date filter is NOT skipped)."""
    full = client.get("/api/v1/derived/monthly")
    assert full.status_code == 200
    full_rows = full.json()["records"]

    resp = client.get("/api/v1/derived/monthly?start=2024-01-01&end=2024-12-31")
    assert resp.status_code == 200
    dates = [r["date"] for r in resp.json()["records"]]
    assert dates, "valid range returned no rows"
    assert min(dates) >= "2024-01-01" and max(dates) <= "2024-12-31"
    assert len(dates) < len(full_rows), "slice did not narrow the full table"


def test_cycles_valid_range_still_ok():
    """A valid ISO date on cycles keeps returning 200 (behavior unchanged)."""
    resp = client.get("/api/v1/cycles/credit?start=2020-01-01")
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest_phase"] in ("easing", "tightening", "neutral")


def test_db_load_slices_with_valid_date_string():
    """db.load stays lenient for internal callers passing valid ISO strings /
    date objects (no bare except needed)."""
    full = db.load("derived_monthly")
    sliced = db.load("derived_monthly", "2024-01-01", "2024-12-31")
    assert 0 < len(sliced) < len(full)
