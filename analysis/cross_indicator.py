"""
Cross-Indicator Analysis — leading/lag correlation structure.

Two key relationships tested:
1. M1_yoy leads PPI_yoy (expected best lag ≈ 6 months)
2. M2_M1_spread leads CPI_yoy (expected best lag ≈ 6–12 months)

For each pair, rolling correlations are computed at lags 0–12 months.
The lag with the highest absolute Pearson correlation is reported.
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
    """Find lag (in months) that maximises Pearson r between lead(+k) and lag_var.

    Returns (best_lag, max_corr, corr_series).
    A positive lag means the first series LEADS by that many months.
    """
    records = []
    for k in range(0, max_lag + 1):
        shifted_lead = lead.shift(-k)  # lead moved earlier → it "leads" by k months
        aligned = pd.DataFrame({"x": shifted_lead, "y": lag_var}).dropna()
        if len(aligned) < 24:
            records.append({"lag": k, "corr": np.nan})
            continue
        r = aligned["x"].corr(aligned["y"])
        records.append({"lag": k, "corr": r})

    corr_df = pd.DataFrame(records)
    valid = corr_df.dropna(subset=["corr"])
    if valid.empty:
        return 0, np.nan, corr_df

    # Best lag by highest positive correlation (direction matters for leading indicators)
    best_idx = valid["corr"].abs().idxmax()
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
