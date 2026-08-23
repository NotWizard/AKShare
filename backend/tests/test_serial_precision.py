"""Serializer float precision — records must not carry binary float noise (F17).

``df_to_records`` rebuilds every row as a dict, so any value that is exact in
decimal but not in binary (``0.1 + 8.2`` → ``8.299999999999999``, ``8.3 + noise``
→ ``8.300000000000001``) was written out with its full 17-digit repr. On
``derived_monthly`` (582 rows × 31 columns) that is CPU + payload waste, and a
high-entropy mantissa compresses badly.

4 decimals is ample here: the smallest non-zero magnitude in any table served
through this function is ~3.6e-3 (``credit_impulse``/``impulse_smooth``, unit 亿),
and every other column is a percent / rate / index with 1–2 meaningful decimals.

Pre-fix: ``test_float_noise_is_rounded`` FAILS (8.300000000000001 survives).
The non-finite and non-float cases PASS pre-fix and must keep passing — they
guard the earlier "nan / ±inf → null" fix and the date/int/str passthrough.

Run:  cd backend && ../.venv312/bin/python -m pytest tests/test_serial_precision.py -q
Deterministic, no network, no DB.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from backend.app.core.serial import df_to_records  # noqa: E402


def test_float_noise_is_rounded():
    """Binary noise is dropped; 4 decimals of real precision are kept."""
    assert 0.1 + 8.2 != 8.3          # premise: the input really is noisy
    df = pd.DataFrame(
        {
            "noisy": [0.1 + 8.2, 1 / 3, 2.0 / 3],
            "small": [0.0036105, 0.00495, 1e-9],
            "big": [1234567.891234, -98.7654321, 0.0],
        }
    )
    recs = df_to_records(df)

    assert recs[0]["noisy"] == 8.3            # pre-fix: 8.300000000000001
    assert recs[1]["noisy"] == 0.3333
    assert recs[2]["noisy"] == 0.6667         # rounds, not truncates
    assert recs[0]["small"] == 0.0036         # 亿-unit noise floor survives
    assert recs[1]["small"] == 0.005          # 0.00495 → 0.005 (4 dp)
    assert recs[2]["small"] == 0.0            # below 4 dp → 0.0, not 1e-9
    assert recs[0]["big"] == 1234567.8912
    assert recs[1]["big"] == -98.7654         # sign preserved
    assert recs[2]["big"] == 0.0

    # And the serialized form is short — the point of the fix.
    assert repr(recs[0]["noisy"]) == "8.3"


def test_nonfinite_still_becomes_none():
    """Regression guard: the nan / ±inf → null contract is untouched."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
            "v": [float("nan"), float("inf"), float("-inf"), 3.14159265],
        }
    )
    recs = df_to_records(df)

    assert recs[0]["v"] is None
    assert recs[1]["v"] is None
    assert recs[2]["v"] is None
    assert recs[3]["v"] == 3.1416           # finite → rounded, never None
    assert recs[0]["date"] == "2024-01-01"  # ISO date formatting preserved


def test_non_float_columns_pass_through_unchanged():
    """Dates / strings / ints must not be touched by the rounding pass."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-31", "2024-02-29"]),
            "phase": ["easing", "tightening"],
            "n": [1234567890, -7],
        }
    )
    recs = df_to_records(df)

    assert [r["date"] for r in recs] == ["2024-01-31", "2024-02-29"]
    assert [r["phase"] for r in recs] == ["easing", "tightening"]
    assert [r["n"] for r in recs] == [1234567890, -7]
    assert all(isinstance(r["n"], int) for r in recs)  # ints stay ints
