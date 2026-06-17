"""Derived-table slices + generic table slice — replaces db.load calls."""

from fastapi import APIRouter, Query

from backend.app.core import db
from backend.app.core.serial import df_to_records
from backend.app.schemas.cycles import DerivedFrame

# Explicit paths (no blanket prefix) so /table/{name} isn't nested under /derived.
router = APIRouter(tags=["data"])


@router.get("/derived/monthly", response_model=DerivedFrame)
def derived_monthly(
    start: str | None = Query(None),
    end: str | None = Query(None),
    cols: str | None = Query(None, description="comma-separated column subset"),
):
    df = db.load("derived_monthly", start, end)
    if cols:
        keep = ["date"] + [c.strip() for c in cols.split(",") if c.strip()]
        df = df[[c for c in keep if c in df.columns]]
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
    df = db.load(name, start, end)
    return DerivedFrame(
        table=name,
        columns=list(df.columns),
        records=df_to_records(df),
    )
