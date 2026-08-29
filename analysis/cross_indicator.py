"""
Cross-Indicator Analysis — historical leading/lag correlation structure.

Two key relationships tested:
1. M1_yoy leads PPI_yoy (expected best lag ≈ 6 months)
2. M2_M1_spread leads CPI_yoy (expected best lag ≈ 6–12 months)

For each pair, the FULL-SAMPLE Pearson correlation is computed at lags 0–12
months and the lag with the highest (most positive) correlation is reported.

This is an in-sample, purely descriptive statistic: every historical point is
correlated against its own future, so the result characterises the historical
lead-lag shape for display only — it is NOT a real-time or tradable signal, and
signals.py surfaces it merely as `cross_lags` display data (never in the
composite score).
"""

import sqlite3
from typing import Dict

import numpy as np
import pandas as pd

MAX_LAG = 12  # months


def _best_lag_corr(
    lead: pd.Series,
    lag_var: pd.Series,
    max_lag: int = MAX_LAG,
) -> tuple:
    """Find the lag (in months) with the highest positive full-sample Pearson r
    between lead(t) and lag_var(t+k).

    Returns (best_lag, best_corr, corr_series). A positive lag means the first
    series LEADS by that many months: the TARGET (lag_var) is shifted backward
    by k so that each t compares lead(t) against lag_var(t+k) — a peak at lag k
    means today's lead predicts the target k months ahead.

    (Shifting the LEAD series instead — the pre-2026-08-17 implementation —
    computes corr(lead(t+k), lag_var(t)), which measures "the target leads the
    lead series by k": with a true k₀-month lead (lag_var(t) ≈ lead(t−k₀)) the
    corr at k becomes autocorr(k+k₀), maximised at k=0 — a real lead is
    structurally unreportable. Direction regression is locked by
    backend/tests/test_cross_indicator.py.)

    Selection is by the highest SIGNED r (most positive), consistent with the
    "leading indicator co-moves with its target" framing — so the returned sign
    always matches the reported relationship (an inverse pair is never
    mislabelled as the leading one). The full signed corr_series is returned
    unchanged for callers that want to inspect inverses.

    This is an in-sample, full-sample descriptive statistic, not a real-time
    signal (see the module docstring).
    """
    records = []
    for k in range(0, max_lag + 1):
        shifted_lag = lag_var.shift(-k)  # 目标列前移 k：t 处对齐 (lead(t), lag(t+k))
        aligned = pd.DataFrame({"x": lead, "y": shifted_lag}).dropna()
        if len(aligned) < 24:
            records.append({"lag": k, "corr": np.nan})
            continue
        r = aligned["x"].corr(aligned["y"])
        records.append({"lag": k, "corr": r})

    corr_df = pd.DataFrame(records)
    valid = corr_df.dropna(subset=["corr"])
    if valid.empty:
        return 0, np.nan, corr_df

    # Highest SIGNED correlation → returned lag and r always share the reported
    # (positive, leading) direction. Selecting by abs() here would let a strong
    # NEGATIVE r win while still being reported as "leads by k months", which
    # contradicts the documented intent.
    best_idx = valid["corr"].idxmax()
    return int(valid.loc[best_idx, "lag"]), float(valid.loc[best_idx, "corr"]), corr_df


def leading_lag_analysis(db_path: str) -> Dict:
    """Compute leading/lag correlation structure across key macro pairs.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    dict
        Keys:
            m1_ppi_best_lag      : int   — months M1 leads PPI
            m1_ppi_max_corr      : float — Pearson r at best lag
            m1_ppi_corr_df       : DataFrame — full lag-corr table
            spread_cpi_best_lag  : int   — months spread leads CPI
            spread_cpi_max_corr  : float — Pearson r at best lag
            spread_cpi_corr_df   : DataFrame — full lag-corr table
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        """
        SELECT date, m1_yoy, ppi_yoy, m2_m1_spread, cpi_yoy
        FROM derived_monthly
        """,
        conn,
    )
    conn.close()

    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    # ── M1 → PPI ────────────────────────────────────────────────────────────
    m1 = df["m1_yoy"].copy()
    ppi = df["ppi_yoy"].copy()
    m1_ppi_lag, m1_ppi_r, m1_ppi_corr_df = _best_lag_corr(m1, ppi)

    # ── M2-M1 spread → CPI ──────────────────────────────────────────────────
    spread = df["m2_m1_spread"].copy()
    cpi = df["cpi_yoy"].copy()
    spread_cpi_lag, spread_cpi_r, spread_cpi_corr_df = _best_lag_corr(spread, cpi)

    return {
        "m1_ppi_best_lag": m1_ppi_lag,
        "m1_ppi_max_corr": m1_ppi_r,
        "m1_ppi_corr_df": m1_ppi_corr_df,
        "spread_cpi_best_lag": spread_cpi_lag,
        "spread_cpi_max_corr": spread_cpi_r,
        "spread_cpi_corr_df": spread_cpi_corr_df,
    }


if __name__ == "__main__":
    result = leading_lag_analysis("data/macro_data.db")
    print(f"M1→PPI:     best lag = {result['m1_ppi_best_lag']}m,  r = {result['m1_ppi_max_corr']:.3f}")
    print(f"Spread→CPI: best lag = {result['spread_cpi_best_lag']}m,  r = {result['spread_cpi_max_corr']:.3f}")
    print("\nM1→PPI correlation by lag:")
    print(result["m1_ppi_corr_df"].to_string(index=False))
