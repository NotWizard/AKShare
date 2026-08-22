"""
Inventory (Kitchin) Cycle — classify restocking vs destocking phases.

Demand signal:     PMI official vs 50 threshold (carried forward when the PMI
                   release lags industrial output, with the age exposed)
Production signal: ip_yoy vs ip_trend (6-month MA, pre-computed in derived_monthly)

Active restocking   (主动补库存): PMI > 50 AND ip_yoy > ip_trend
Passive restocking  (被动补库存): PMI < 50 AND ip_yoy > ip_trend
Active destocking   (主动去库存): PMI < 50 AND ip_yoy < ip_trend
Passive destocking  (被动去库存): PMI > 50 AND ip_yoy < ip_trend
Insufficient data:               either axis unavailable (no verdict at all)
"""

import sqlite3
import pandas as pd
import numpy as np

from analysis.cycle_merrill import INSUFFICIENT_DATA, db_versioned_cache

PHASE_COLORS = {
    "active_restocking": "#2ecc71",
    "passive_restocking": "#f39c12",
    "active_destocking": "#e74c3c",
    "passive_destocking": "#3498db",
    # Same slate grey the frontend falls back to for an unknown phase.
    INSUFFICIENT_DATA: "#64748b",
}


@db_versioned_cache(maxsize=4)
def classify_inventory(db_path: str) -> pd.DataFrame:
    """Classify each month into an inventory-cycle phase.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        Columns: date, pmi_official, pmi_ma6, ip_yoy, ip_trend, pmi_used,
        pmi_stale_months, phase, phase_color.
    """
    conn = sqlite3.connect(db_path)
    # WHY only ip_yoy is required: the two inputs are published on different
    # calendars (official PMI ends 2025-08 while ip_yoy runs to 2026-06), so
    # demanding both in the SAME row silently truncated the frame to the older
    # series and the "current" inventory phase was 10 months stale. ip_yoy vs its
    # trend is the axis that cannot be substituted; the PMI level is carried
    # forward below with its age attached.
    df = pd.read_sql(
        """
        SELECT date, pmi_official, pmi_ma6, ip_yoy, ip_trend
        FROM derived_monthly
        WHERE ip_yoy IS NOT NULL
        """,
        conn,
    )
    conn.close()

    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    # Fall back to ip_trend pre-computed in DB; compute if missing
    if df["ip_trend"].isna().all():
        df["ip_trend"] = df["ip_yoy"].rolling(window=6, min_periods=3).mean()
    else:
        df["ip_trend"] = df["ip_trend"].fillna(
            df["ip_yoy"].rolling(window=6, min_periods=3).mean()
        )

    # ── Demand axis: last known PMI + how old it is ───────────────────────────
    # pmi_official stays RAW (never back-filled) so charts and the API cannot
    # show a fabricated print; pmi_used is what the classification consumed and
    # pmi_stale_months is its age, which analysis/signals.py uses to down-weight
    # the sub-signal instead of passing it off as current.
    df["pmi_used"] = df["pmi_official"].ffill()
    last_print = df["date"].where(df["pmi_official"].notna()).ffill()
    df["pmi_stale_months"] = (
        (df["date"].dt.year - last_print.dt.year) * 12
        + (df["date"].dt.month - last_print.dt.month)
    ).astype(float)

    # ── Classify ─────────────────────────────────────────────────────────────
    pmi_up = df["pmi_used"] > 50
    ip_up = df["ip_yoy"] > df["ip_trend"]
    # A NaN never satisfies '>' , so without this guard a missing axis fell
    # through to the old `default="active_destocking"` — i.e. no data produced the
    # most bearish phase. Listed FIRST so it wins over every quadrant.
    unknown = df["pmi_used"].isna() | df["ip_yoy"].isna() | df["ip_trend"].isna()

    conditions = [
        unknown,           # insufficient data
        pmi_up & ip_up,    # active restocking
        ~pmi_up & ip_up,   # passive restocking
        ~pmi_up & ~ip_up,  # active destocking
        pmi_up & ~ip_up,   # passive destocking
    ]
    choices = [
        INSUFFICIENT_DATA,
        "active_restocking",
        "passive_restocking",
        "active_destocking",
        "passive_destocking",
    ]
    df["phase"] = np.select(conditions, choices, default=INSUFFICIENT_DATA)
    df["phase_color"] = df["phase"].map(PHASE_COLORS)

    return df[[
        "date", "pmi_official", "pmi_ma6", "ip_yoy", "ip_trend",
        "pmi_used", "pmi_stale_months", "phase", "phase_color",
    ]]


if __name__ == "__main__":
    result = classify_inventory("data/macro_data.db")
    print(result.tail(24).to_string(index=False))
