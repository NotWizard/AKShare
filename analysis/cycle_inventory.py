"""
Inventory (Kitchin) Cycle — classify restocking vs destocking phases.

Demand signal:     PMI official vs 50 threshold
Production signal: ip_yoy vs ip_trend (6-month MA, pre-computed in derived_monthly)

Active restocking   (主动补库存): PMI > 50 AND ip_yoy > ip_trend
Passive restocking  (被动补库存): PMI < 50 AND ip_yoy > ip_trend
Active destocking   (主动去库存): PMI < 50 AND ip_yoy < ip_trend
Passive destocking  (被动去库存): PMI > 50 AND ip_yoy < ip_trend
"""

import functools
import sqlite3
import pandas as pd
import numpy as np

PHASE_COLORS = {
    "active_restocking": "#2ecc71",
    "passive_restocking": "#f39c12",
    "active_destocking": "#e74c3c",
    "passive_destocking": "#3498db",
}


@functools.lru_cache(maxsize=4)
def classify_inventory(db_path: str) -> pd.DataFrame:
    """Classify each month into an inventory-cycle phase.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        Columns: date, pmi_official, pmi_ma6, ip_yoy, ip_trend, phase, phase_color.
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        """
        SELECT date, pmi_official, pmi_ma6, ip_yoy, ip_trend
        FROM derived_monthly
        WHERE pmi_official IS NOT NULL AND ip_yoy IS NOT NULL
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

    # ── Classify ─────────────────────────────────────────────────────────────
    pmi_up = df["pmi_official"] > 50
    ip_up = df["ip_yoy"] > df["ip_trend"]

    conditions = [
        pmi_up & ip_up,    # active restocking
        ~pmi_up & ip_up,   # passive restocking
        ~pmi_up & ~ip_up,  # active destocking
        pmi_up & ~ip_up,   # passive destocking
    ]
    choices = [
        "active_restocking",
        "passive_restocking",
        "active_destocking",
        "passive_destocking",
    ]
    df["phase"] = np.select(conditions, choices, default="active_destocking")
    df["phase_color"] = df["phase"].map(PHASE_COLORS)

    return df[["date", "pmi_official", "pmi_ma6", "ip_yoy", "ip_trend", "phase", "phase_color"]]


if __name__ == "__main__":
    result = classify_inventory("data/macro_data.db")
    print(result.tail(24).to_string(index=False))
