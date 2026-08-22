"""
Credit Cycle — classify easing vs tightening using M2 growth deviation.

M2_yoy is used as primary credit proxy (social finance data unavailable due to SSL).
m2_trend  = 12-month rolling mean of M2_yoy
credit_impulse = M2_yoy - m2_trend
impulse_smooth = 3-month rolling mean of credit_impulse

Easing:     smoothed impulse above the dead-zone AND rising, N months running
Tightening: smoothed impulse below −dead-zone AND falling, N months running
Neutral:    everything else (in particular: any impulse inside the dead-zone)
"""

import sqlite3
import pandas as pd
import numpy as np

from analysis.cycle_merrill import db_versioned_cache

# ── Chatter filters (mirror the Merrill clock's dead-zone + persistence) ─────
# WHY smoothing: a single month's M2 print carries seasonal/base noise, so the
# raw impulse ratchets up and down month to month. Three months = one quarter is
# the shortest window that damps a one-month print without adding real lag.
IMPULSE_SMOOTH_WINDOW = 3
# WHY a dead-zone: M2 YoY is published to 0.1 pp, so a deviation of a few
# hundredths from a 12-month mean is measurement granularity, not policy. Real
# 2026 prints deviated by 0.04–0.10 pp and the old rule still called them
# easing/tightening; 0.25 pp keeps those inside "neutral" while the genuine 2025-12
# easing impulse (0.5+ pp) and the 2026-06 contraction (−0.53 pp) still register.
IMPULSE_DEAD_ZONE = 0.25
# WHY persistence: one month above the dead-zone can still be a revision artefact;
# two consecutive months in the same direction is the same low bar the Merrill
# growth axis uses to confirm a turn.
PHASE_PERSIST = 2


def _confirmed(mask: pd.Series, persist: int) -> pd.Series:
    """True where *mask* has held for `persist` CONSECUTIVE periods."""
    return (
        mask.astype(float).rolling(persist, min_periods=persist).sum() >= persist
    ).fillna(False)


def classify_credit_phases(
    df: pd.DataFrame,
    smooth_window: int = IMPULSE_SMOOTH_WINDOW,
    dead_zone: float = IMPULSE_DEAD_ZONE,
    persist: int = PHASE_PERSIST,
) -> pd.DataFrame:
    """Classify credit phases on a chronologically-sorted frame (pure, DB-free).

    Expects a ``credit_impulse`` column; returns a copy with ``impulse_smooth``
    and ``phase`` added. Split out from :func:`classify_credit` so the
    dead-zone/persistence logic is unit-testable on constructed impulses.
    """
    out = df.copy().reset_index(drop=True)

    out["impulse_smooth"] = out["credit_impulse"].rolling(
        smooth_window, min_periods=2
    ).mean()
    slope = out["impulse_smooth"].diff()

    easing = _confirmed((out["impulse_smooth"] > dead_zone) & (slope > 0), persist)
    tightening = _confirmed((out["impulse_smooth"] < -dead_zone) & (slope < 0), persist)

    out["phase"] = np.where(easing, "easing",
                   np.where(tightening, "tightening", "neutral"))
    return out


@db_versioned_cache(maxsize=4)
def classify_credit(db_path: str) -> pd.DataFrame:
    """Classify each month into a credit-cycle phase.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        Columns: date, m2_yoy, m2_trend, credit_impulse, impulse_smooth, phase.
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

    # ── Smoothed impulse + dead-zone + persistence (pure helper) ─────────────
    df = classify_credit_phases(df)

    return df[["date", "m2_yoy", "m2_trend", "credit_impulse", "impulse_smooth", "phase"]]


if __name__ == "__main__":
    result = classify_credit("data/macro_data.db")
    print(result.tail(24).to_string(index=False))
