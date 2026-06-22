"""Derived-table slices + generic table slice — replaces db.load calls."""

from fastapi import APIRouter, HTTPException, Query

from backend.app.core import db
from backend.app.core.serial import df_to_records
from backend.app.schemas.cycles import DerivedFrame

# Whitelist of tables the /table/{name} endpoint is allowed to serve.
# Prevents information leakage (e.g. sqlite_master, sqlite_sequence).
_ALLOWED_TABLES = {
    "derived_monthly", "derived_quarterly",
    "money_supply", "gdp", "cpi", "ppi", "pmi",
    "leverage", "social_finance", "lpr", "industrial",
    "house_price", "household_income", "new_credit", "bond_yield",
}

# Explicit paths (no blanket prefix) so /table/{name} isn't nested under /derived.
router = APIRouter(tags=["data"])


@router.get("/derived/monthly", response_model=DerivedFrame)
def derived_monthly(
    start: str | None = Query(None),
    end: str | None = Query(None),
    cols: str | None = Query(None, description="comma-separated column subset"),
    align_start: bool = Query(
        False,
        description=(
            "if true, start from the earliest date where ALL requested value cols are "
            "non-null in the SAME row (so charts don't begin with a long empty run). "
            "Respects an explicit `start` (takes the later of the two). "
            "If any requested col is all-NaN, the filter is skipped (graceful degradation: "
            "returns full table from the user-provided start or 1978)."
        ),
    ),
):
    import pandas as pd

    df = db.load("derived_monthly", start, end)
    if cols:
        # Dedupe: callers pass 'date' in cols (e.g. CreditCycle.vue uses
        # cols='date,m2_yoy'), which would otherwise make 'date' appear twice.
        # A duplicate date column turns df['date'] into a DataFrame (not a
        # Series), so df_to_records' is_datetime64 check fails and the date
        # stays ISO ('2020-01-01T00:00:00') instead of '2020-01-01'. That format
        # mismatch breaks the frontend's date-key join → series (e.g. M2 trend)
        # render all-null. Dedup fixes the join + drops the dup column.
        keep = list(dict.fromkeys(
            ["date"] + [c.strip() for c in cols.split(",") if c.strip()]
        ))
        df = df[[c for c in keep if c in df.columns]]

    if align_start and "date" in df.columns:
        # Start at the earliest row where every requested value column is
        # non-null — charts no longer begin in 1978 with a long empty run when
        # the series only exists from (e.g.) 2019. Respects an explicit user
        # `start` (takes the later of the two).
        value_cols = [c for c in df.columns if c != "date"]
        if value_cols:
            mask = df[value_cols].notna().all(axis=1)
            if mask.any():
                first_valid = df.loc[mask, "date"].iloc[0]
                if start is None or pd.Timestamp(first_valid) > pd.Timestamp(start):
                    df = df[df["date"] >= pd.Timestamp(first_valid)]

    return DerivedFrame(
        table="derived_monthly",
        columns=list(df.columns),
        records=df_to_records(df),
    )


@router.get("/derived/quarterly", response_model=DerivedFrame)
def derived_quarterly(start: str | None = None, end: str | None = None):
    df = db.load("derived_quarterly", start, end)
    return DerivedFrame(
        table="derived_quarterly",
        columns=list(df.columns),
        records=df_to_records(df),
    )


@router.get("/table/{name}", response_model=DerivedFrame)
def raw_table(name: str, start: str | None = None, end: str | None = None):
    """Generic slice of any table (e.g. house_price, leverage)."""
    if name not in _ALLOWED_TABLES:
        raise HTTPException(404, f"unknown table: {name}")
    df = db.load(name, start, end)
    return DerivedFrame(
        table=name,
        columns=list(df.columns),
        records=df_to_records(df),
    )
