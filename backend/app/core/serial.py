"""Serialization helpers — turn cached DataFrames into JSON-safe records.

Dates → ISO 'YYYY-MM-DD', non-finite floats (NaN/±Inf) → null. Keeps the
payload small and TS-friendly.
"""

import math
from typing import Any

import pandas as pd


def _finite_or_none(v: Any) -> Any:
    """Scalar guard: non-finite floats (nan / +inf / -inf) → None; else unchanged.

    Shared by serial + crcl_db so JSON-safety uses one definition of "poison".
    ``json.dumps(..., allow_nan=False)`` (Starlette's default) raises on any of
    the three, so all three must be nulled — not just nan.
    """
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


# Macro indicators are percents / rates / indices — 4 decimals is ample, and the
# smallest non-zero magnitude any table serves is ~3.6e-3 (credit_impulse, 亿).
_FLOAT_DP = 4


def _clean_record_float(v: Any) -> Any:
    """Row-scalar cleaner for df_to_records: non-finite float → None, finite
    float → rounded to _FLOAT_DP, everything else unchanged.

    Rounding drops binary-repr noise (``8.300000000000001`` → ``8.3``), which is
    both CPU + payload waste and compresses badly. Deliberately NOT folded into
    the shared ``_finite_or_none`` — crcl_db reuses that for snapshot
    persistence, which keeps full precision; only DataFrame transport rounds.
    """
    if isinstance(v, float):
        return round(v, _FLOAT_DP) if math.isfinite(v) else None
    return v


def _json_safe(obj: Any) -> Any:
    """Recursively replace non-finite floats with None in JSON-like data.

    Walks dicts / lists / tuples so nested payloads are sanitized too. Used by
    the transport layer (SafeJSONResponse) and before persisting snapshots.
    """
    if isinstance(obj, float):
        return _finite_or_none(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → list[dict] with ISO dates, nulls for non-finite floats, and
    finite floats rounded to 4 dp (drops binary-repr noise, shrinks payload)."""
    out = df
    if "date" in out.columns and pd.api.types.is_datetime64_any_dtype(out["date"]):
        # Only copy the date column (assign creates a new DataFrame with the
        # formatted date; other columns remain views, no full copy).
        out = out.assign(date=out["date"].dt.strftime("%Y-%m-%d"))

    cleaned = []
    for rec in out.to_dict(orient="records"):
        cleaned.append({k: _clean_record_float(v) for k, v in rec.items()})
    return cleaned
