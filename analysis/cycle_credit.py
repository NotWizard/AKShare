"""
Credit Cycle — classify easing vs tightening using M2 growth deviation.

M2_yoy is used as primary credit proxy (social finance data unavailable due to SSL).
m2_trend  = 12-month rolling mean of M2_yoy
credit_impulse = M2_yoy - m2_trend

Easing:     impulse > 0 AND rising (current > previous)
Tightening: impulse < 0 AND falling (current < previous)
Neutral:    everything else
"""

import sqlite3
import pandas as pd
import numpy as np


def classify_credit(db_path: str) -> pd.DataFrame:
    """Classify each month into a credit-cycle phase.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        Columns: date, m2_yoy, m2_trend, credit_impulse, phase.
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        "SELECT date, m2_yoy FROM derived_monthly WHERE m2_yoy IS NOT NULL",
        conn,
    )
    conn.close()

    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    # ── Trend and impulse ────────────────────────────────────────────────────
    df["m2_trend"] = df["m2_yoy"].rolling(window=12, min_periods=6).mean()
    df["credit_impulse"] = df["m2_yoy"] - df["m2_trend"]

    # ── Rising / falling impulse ─────────────────────────────────────────────
    impulse_rising = df["credit_impulse"] > df["credit_impulse"].shift(1)

    easing = (df["credit_impulse"] > 0) & impulse_rising
    tightening = (df["credit_impulse"] < 0) & ~impulse_rising

    df["phase"] = np.where(easing, "easing",
                  np.where(tightening, "tightening", "neutral"))

    return df[["date", "m2_yoy", "m2_trend", "credit_impulse", "phase"]]


if __name__ == "__main__":
    result = classify_credit("data/macro_data.db")
    print(result.tail(24).to_string(index=False))
