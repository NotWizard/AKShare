"""Cycle classification endpoints — thin wrappers over analysis/* (unchanged)."""

from fastapi import APIRouter, HTTPException, Query

from analysis.cycle_credit import classify_credit
from analysis.cycle_debt import classify_debt
from analysis.cycle_inventory import classify_inventory
from analysis.cycle_merrill import classify_merrill
from backend.app.core import db
from backend.app.core.serial import df_to_records
from backend.app.schemas.cycles import CycleFrame

router = APIRouter(prefix="/cycles", tags=["cycles"])

_VALUE_COL = {
    "merrill": ("gdp_yoy", None),
    "credit": ("m2_yoy", "credit_impulse"),
    "inventory": ("pmi_official", None),
    "debt": ("household", None),
}


@router.get("/{name}", response_model=CycleFrame)
def get_cycle(
    name: str,
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    name = name.lower()
    classifiers = {
        "merrill": classify_merrill,
        "credit": classify_credit,
        "inventory": classify_inventory,
        "debt": classify_debt,
    }
    if name not in classifiers:
        raise HTTPException(404, f"unknown cycle: {name}")

    # classify_* read straight from DB_PATH; date-slice afterward for the range.
    full = classifiers[name](str(db.DB_PATH))
    df = full
    if (start or end) and "date" in full.columns:
        import pandas as pd
        mask = pd.Series([True] * len(full))
        if start:
            mask &= full["date"] >= pd.Timestamp(start)
        if end:
            mask &= full["date"] <= pd.Timestamp(end)
        df = full[mask]

    value_col = _VALUE_COL[name][0]
    phase_col = "overall_phase" if name == "debt" else "phase"
    latest_phase = None
    latest_value = None
    if len(df):
        latest_phase = str(df.iloc[-1].get(phase_col)) if phase_col in df.columns else None
        if value_col in df.columns:
            import math
            v = df.iloc[-1][value_col]
            latest_value = None if (isinstance(v, float) and math.isnan(v)) else float(v)

    return CycleFrame(
        series=df_to_records(df),
        latest_phase=latest_phase,
        latest_value=latest_value,
        value_col=value_col,
    )
