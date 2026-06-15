"""
Merrill Lynch Investment Clock — classify macroeconomic phases.

Growth signal:  GDP_yoy vs rolling 4-year mean (annual data in derived_quarterly)
Inflation signal: CPI_yoy vs 2.0% threshold

Phases:
    Recovery    (GDP↑ CPI↓)  → #2ecc71 green
    Overheating (GDP↑ CPI↑)  → #e74c3c red
    Stagflation (GDP↓ CPI↑)  → #f39c12 orange
    Recession   (GDP↓ CPI↓)  → #3498db blue
"""

import sqlite3
import pandas as pd
import numpy as np

PHASE_COLORS = {
    "recovery": "#2ecc71",
    "overheating": "#e74c3c",
    "stagflation": "#f39c12",
    "recession": "#3498db",
}


def classify_merrill(db_path: str) -> pd.DataFrame:
    """Classify each year into a Merrill Lynch investment-clock phase.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database (data/macro_data.db).

    Returns
    -------
    pd.DataFrame
        Columns: date, gdp_yoy, cpi_yoy, gdp_trend, phase, phase_color.
    """
    conn = sqlite3.connect(db_path)

    # ── Annual GDP ──────────────────────────────────────────────────────────
    gdp = pd.read_sql(
        "SELECT date, gdp_yoy FROM derived_quarterly WHERE gdp_yoy IS NOT NULL",
        conn,
    )
    gdp["date"] = pd.to_datetime(gdp["date"])
    gdp = gdp.drop_duplicates(subset=["date"], keep="last")

    # ── Monthly CPI → annual mean ───────────────────────────────────────────
    cpi_monthly = pd.read_sql(
        "SELECT date, cpi_yoy FROM derived_monthly WHERE cpi_yoy IS NOT NULL",
        conn,
    )
    cpi_monthly["date"] = pd.to_datetime(cpi_monthly["date"])
    cpi_monthly = cpi_monthly.drop_duplicates(subset=["date"], keep="last")
    cpi_monthly["year"] = cpi_monthly["date"].dt.year
    cpi_annual = (
        cpi_monthly.groupby("year")["cpi_yoy"]
        .mean()
        .reset_index()
        .rename(columns={"cpi_yoy": "cpi_yoy"})
    )

    conn.close()

    # ── Merge on year ────────────────────────────────────────────────────────
    gdp["year"] = gdp["date"].dt.year
    df = gdp.merge(cpi_annual, on="year", how="inner").sort_values("date").reset_index(drop=True)

    # ── Growth signal: rolling 4-year mean ──────────────────────────────────
    df["gdp_trend"] = df["gdp_yoy"].rolling(window=4, min_periods=2).mean()

    # ── Classify ─────────────────────────────────────────────────────────────
    gdp_up = df["gdp_yoy"] > df["gdp_trend"]
    cpi_up = df["cpi_yoy"] > 2.0

    conditions = [
        gdp_up & ~cpi_up,   # recovery
        gdp_up & cpi_up,    # overheating
        ~gdp_up & cpi_up,   # stagflation
        ~gdp_up & ~cpi_up,  # recession
    ]
    choices = ["recovery", "overheating", "stagflation", "recession"]
    df["phase"] = np.select(conditions, choices, default="recession")
    df["phase_color"] = df["phase"].map(PHASE_COLORS)

    return df[["date", "gdp_yoy", "cpi_yoy", "gdp_trend", "phase", "phase_color"]]


if __name__ == "__main__":
    result = classify_merrill("data/macro_data.db")
    print(result.to_string(index=False))
