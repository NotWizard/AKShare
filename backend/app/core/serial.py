"""Serialization helpers — turn cached DataFrames into JSON-safe records.

Dates → ISO 'YYYY-MM-DD', NaN → null. Keeps the payload small and TS-friendly.
"""

import math

import pandas as pd


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → list[dict] with ISO dates and nulls for NaN."""
    out = df
    if "date" in out.columns and pd.api.types.is_datetime64_any_dtype(out["date"]):
        # Only copy the date column (assign creates a new DataFrame with the
        # formatted date; other columns remain views, no full copy).
        out = out.assign(date=out["date"].dt.strftime("%Y-%m-%d"))

    cleaned = []
    for rec in out.to_dict(orient="records"):
        cleaned.append({
            k: (None if (isinstance(v, float) and math.isnan(v)) else v)
            for k, v in rec.items()
        })
    return cleaned
