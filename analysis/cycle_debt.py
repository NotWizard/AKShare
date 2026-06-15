"""
Debt Cycle (Dalio framework) — classify leveraging / deleveraging per sector.

Sector thresholds (4-quarter change):
    Leveraging:    change > +1.0 pp / quarter
    Deleveraging:  change < -0.5 pp / quarter
    Stable:        otherwise

Combines with GDP growth for overall phase:
    Beautiful deleveraging: deleveraging + GDP still growing (gdp_yoy > 0)
    Ugly deleveraging:      deleveraging + GDP declining (gdp_yoy ≤ 0)
    Leveraging boom:        leveraging + GDP growing
    Leveraging bust:        leveraging + GDP declining
    Stable growth:          stable + GDP growing
    Stable contraction:     stable + GDP declining
"""

import sqlite3
import pandas as pd
import numpy as np


def _classify_sector(change: pd.Series) -> pd.Series:
    """Classify a sector's 4-quarter change into leveraging/deleveraging/stable."""
    return np.where(
        change > 1.0, "leveraging",
        np.where(change < -0.5, "deleveraging", "stable")
    )


def classify_debt(db_path: str) -> pd.DataFrame:
    """Classify each quarter into a debt-cycle phase per sector and overall.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        Columns: date, household, non_fin_corp, gov_total,
                 household_phase, corp_phase, gov_phase, overall_phase.
    """
    conn = sqlite3.connect(db_path)

    # ── Leverage (quarterly) ─────────────────────────────────────────────────
    lev = pd.read_sql(
        """
        SELECT date, household, non_fin_corp, gov_total
        FROM leverage
        WHERE household IS NOT NULL AND non_fin_corp IS NOT NULL AND gov_total IS NOT NULL
        """,
        conn,
    )
    lev["date"] = pd.to_datetime(lev["date"])
    lev = lev.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    # ── GDP (annual in derived_quarterly) → forward-fill to quarter ─────────
    gdp = pd.read_sql(
        "SELECT date, gdp_yoy FROM derived_quarterly WHERE gdp_yoy IS NOT NULL",
        conn,
    )
    gdp["date"] = pd.to_datetime(gdp["date"])
    gdp = gdp.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    conn.close()

    # Build a quarterly date range and forward-fill annual GDP_yoy
    quarter_dates = lev["date"].copy()
    gdp_q = pd.DataFrame({"date": quarter_dates})
    gdp_q = gdp_q.merge(
        gdp.rename(columns={"gdp_yoy": "gdp_yoy_annual"}),
        how="left",
        on="date",
    )
    # For each quarter, find the most recent annual GDP observation
    gdp_q["gdp_yoy"] = np.nan
    for i, row in gdp_q.iterrows():
        past = gdp[gdp["date"] <= row["date"]]
        if not past.empty:
            gdp_q.loc[i, "gdp_yoy"] = past.iloc[-1]["gdp_yoy"]

    # ── 4-quarter change in leverage ────────────────────────────────────────
    lev["hh_change"] = lev["household"].diff(4)
    lev["corp_change"] = lev["non_fin_corp"].diff(4)
    lev["gov_change"] = lev["gov_total"].diff(4)

    lev["household_phase"] = _classify_sector(lev["hh_change"])
    lev["corp_phase"] = _classify_sector(lev["corp_change"])
    lev["gov_phase"] = _classify_sector(lev["gov_change"])

    # ── Merge GDP growth signal ─────────────────────────────────────────────
    lev = lev.merge(gdp_q[["date", "gdp_yoy"]], on="date", how="left")
    gdp_growing = lev["gdp_yoy"] > 0

    # ── Overall phase (Dalio framework) ─────────────────────────────────────
    any_deleveraging = (
        (lev["household_phase"] == "deleveraging")
        | (lev["corp_phase"] == "deleveraging")
        | (lev["gov_phase"] == "deleveraging")
    )
    any_leveraging = (
        (lev["household_phase"] == "leveraging")
        | (lev["corp_phase"] == "leveraging")
        | (lev["gov_phase"] == "leveraging")
    )

    conditions = [
        any_deleveraging & gdp_growing,    # beautiful deleveraging
        any_deleveraging & ~gdp_growing,   # ugly deleveraging
        any_leveraging & gdp_growing,      # leveraging boom
        any_leveraging & ~gdp_growing,     # leveraging bust
        ~any_deleveraging & ~any_leveraging & gdp_growing,   # stable growth
        ~any_deleveraging & ~any_leveraging & ~gdp_growing,  # stable contraction
    ]
    choices = [
        "beautiful_deleveraging",
        "ugly_deleveraging",
        "leveraging_boom",
        "leveraging_bust",
        "stable_growth",
        "stable_contraction",
    ]
    lev["overall_phase"] = np.select(conditions, choices, default="stable_growth")

    cols = [
        "date", "household", "non_fin_corp", "gov_total",
        "household_phase", "corp_phase", "gov_phase", "overall_phase",
    ]
    return lev[cols]


if __name__ == "__main__":
    result = classify_debt("data/macro_data.db")
    print(result.tail(16).to_string(index=False))
