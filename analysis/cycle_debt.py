"""
Debt Cycle (Dalio framework) — classify leveraging / deleveraging per sector.

Sector thresholds (4-quarter change):
    Leveraging:    change > +1.0 pp / 4 quarters
    Deleveraging:  change < -0.5 pp / 4 quarters
    Stable:        otherwise

The OVERALL phase follows the NET direction of the three sectors (their sum is
the change in real-economy leverage), combined with growth vs potential:
    Beautiful deleveraging: net deleveraging + growth at/above potential
    Ugly deleveraging:      net deleveraging + growth below potential
    Leveraging boom:        net leveraging   + growth at/above potential
    Leveraging bust:        net leveraging   + growth below potential
    Stable growth:          net stable       + growth at/above potential
    Stable contraction:     net stable       + growth below potential
    Insufficient data:      no 4-quarter change yet, or no GDP observation yet
"""

import sqlite3
import pandas as pd
import numpy as np

from analysis.cycle_merrill import (
    INSUFFICIENT_DATA,
    db_versioned_cache,
    growth_above_trend,
    potential_growth,
)

# Per-sector 4-quarter thresholds (unchanged).
SECTOR_LEVERAGING_PP = 1.0
SECTOR_DELEVERAGING_PP = -0.5
# Aggregate thresholds. The three sector ratios share one GDP denominator and add
# up to real-economy leverage (real data: 59.0 + 180.0 + 70.3 = 309.3 = the DB's
# `real_economy`), so their pp changes are directly summable — the sum IS the
# change in the economy-wide debt burden that Dalio's framework is about. Scaling
# the per-sector thresholds by the 3 sectors keeps the "stable" band the same
# width per sector: the aggregate crosses exactly when the AVERAGE sector does.
NET_LEVERAGING_PP = 3 * SECTOR_LEVERAGING_PP        # +3.0 pp of GDP / 4 quarters
NET_DELEVERAGING_PP = 3 * SECTOR_DELEVERAGING_PP    # −1.5 pp of GDP / 4 quarters


def _classify_sector(change: pd.Series) -> pd.Series:
    """Classify a sector's 4-quarter change into leveraging/deleveraging/stable."""
    return np.where(
        change > SECTOR_LEVERAGING_PP, "leveraging",
        np.where(change < SECTOR_DELEVERAGING_PP, "deleveraging", "stable")
    )


@db_versioned_cache(maxsize=4)
def classify_debt(db_path: str) -> pd.DataFrame:
    """Classify each quarter into a debt-cycle phase per sector and overall.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        Columns: date, household, non_fin_corp, gov_total, net_change,
                 gdp_yoy, gdp_trend,
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

    # ── GDP (annual in derived_quarterly) → carried to each quarter ─────────
    gdp = pd.read_sql(
        "SELECT date, gdp_yoy FROM derived_quarterly WHERE gdp_yoy IS NOT NULL",
        conn,
    )
    gdp["date"] = pd.to_datetime(gdp["date"])
    gdp = gdp.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

    conn.close()

    # ── Growth axis: vs POTENTIAL, not vs zero ──────────────────────────────
    # WHY: `gdp_yoy > 0` is true in every year of this dataset except 2020, so the
    # three bearish branches below were unreachable and the debt score was pinned
    # at +1. The Merrill clock already answers "is growth below potential" with a
    # robust trailing median plus a dead-zone and a 2-period persistence filter;
    # importing that exact helper keeps the two frameworks consistent and makes a
    # cyclical slowdown (2009 / 2012 / 2016 here) visible without letting a single
    # noisy year flip the phase. Computed on the ANNUAL series, then carried, so
    # the median window spans years rather than shrinking to a few quarters.
    gdp["gdp_trend"] = potential_growth(gdp["gdp_yoy"])
    gdp["growth_up"] = growth_above_trend(gdp["gdp_yoy"])

    # For each leverage quarter, take the most recent annual GDP observation
    # (backward as-of join — same semantics as the previous per-row scan).
    # merge_asof needs both sides non-empty; with either side missing every
    # quarter simply has no growth observation (→ insufficient_data below).
    if len(lev) and len(gdp):
        gdp_q = pd.merge_asof(lev[["date"]], gdp, on="date", direction="backward")
    else:
        gdp_q = pd.DataFrame({
            "date": lev["date"], "gdp_yoy": np.nan,
            "gdp_trend": np.nan, "growth_up": np.nan,
        })

    # ── 4-quarter change in leverage ────────────────────────────────────────
    lev["hh_change"] = lev["household"].diff(4)
    lev["corp_change"] = lev["non_fin_corp"].diff(4)
    lev["gov_change"] = lev["gov_total"].diff(4)

    lev["household_phase"] = _classify_sector(lev["hh_change"])
    lev["corp_phase"] = _classify_sector(lev["corp_change"])
    lev["gov_phase"] = _classify_sector(lev["gov_change"])

    # Net = change in real-economy leverage. min_count=3 keeps it NaN until all
    # three sectors have a 4-quarter change, so an incomplete history stays
    # "insufficient data" instead of reading as a stable economy.
    lev["net_change"] = lev[["hh_change", "corp_change", "gov_change"]].sum(
        axis=1, min_count=3
    )

    # ── Merge growth signal ─────────────────────────────────────────────────
    lev = lev.merge(
        gdp_q[["date", "gdp_yoy", "gdp_trend", "growth_up"]], on="date", how="left"
    )
    growth_known = lev["growth_up"].notna()
    growth_up = lev["growth_up"].fillna(False).astype(bool)

    # ── Overall phase (Dalio framework, NET sector direction) ───────────────
    # WHY net instead of the old `any_deleveraging` (which came first in
    # np.select): with "any", one deleveraging sector labelled the whole economy
    # "beautiful deleveraging" even while the other two levered hard — the real
    # 2026-Q1 print (household −2.5 pp, corporate +6.3 pp, government +7.1 pp,
    # i.e. +10.9 pp of GDP MORE debt) came out "beautiful".
    net_delev = lev["net_change"] < NET_DELEVERAGING_PP
    net_lev = lev["net_change"] > NET_LEVERAGING_PP
    # A NaN fails every comparison, so mark unclassifiable quarters explicitly and
    # list them FIRST — otherwise they fell into the `stable_*` branch and scored.
    unknown = lev["net_change"].isna() | ~growth_known

    conditions = [
        unknown,                                              # insufficient data
        net_delev & growth_up,                                # beautiful deleveraging
        net_delev & ~growth_up,                               # ugly deleveraging
        net_lev & growth_up,                                  # leveraging boom
        net_lev & ~growth_up,                                 # leveraging bust
        ~net_delev & ~net_lev & growth_up,                    # stable growth
        ~net_delev & ~net_lev & ~growth_up,                   # stable contraction
    ]
    choices = [
        INSUFFICIENT_DATA,
        "beautiful_deleveraging",
        "ugly_deleveraging",
        "leveraging_boom",
        "leveraging_bust",
        "stable_growth",
        "stable_contraction",
    ]
    lev["overall_phase"] = np.select(conditions, choices, default=INSUFFICIENT_DATA)

    cols = [
        "date", "household", "non_fin_corp", "gov_total", "net_change",
        "gdp_yoy", "gdp_trend",
        "household_phase", "corp_phase", "gov_phase", "overall_phase",
    ]
    return lev[cols]


if __name__ == "__main__":
    result = classify_debt("data/macro_data.db")
    print(result.tail(16).to_string(index=False))
