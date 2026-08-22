"""
Real Estate Analysis — household leverage, price momentum, rate environment.

Dimensions scored 0–100 (100 = most favourable for housing demand):

1. Leverage space:  headroom = 70% − household leverage  (more headroom → higher score)
2. Price momentum:  12-month rolling mean of new_mom across selected cities
                     (positive and rising → higher score)
3. Rate environment: lpr_5y vs its own historical median since 2019
                     (below median → higher score = cheaper credit)

A dimension with no data scores NEUTRAL and is EXCLUDED from the composite (which
renormalises over what is left) — never scored at an extreme, and never silently
averaged in as if it were measured.
"""

import sqlite3
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from analysis.cycle_merrill import db_versioned_cache

# Theoretical ceiling for household leverage ratio (%)
HOUSEHOLD_LEVERAGE_CAP = 70.0

# Midpoint of the 0–100 scale: what an *unmeasured* dimension reports. WHY not
# 0.0 (the old fallback): 0 is the score of a −3% MoM price collapse, so a data
# gap used to read as the most bearish input possible. 50 says "no information",
# which is also what the radar chart's own null-fallback renders least misleadingly.
NEUTRAL_SCORE = 50.0

ALL_CITIES = ["北京", "上海", "深圳", "广州", "杭州", "南京", "成都", "武汉", "天津", "重庆"]


def _score_leverage_space(headroom: float) -> float:
    """Score leverage headroom: 0 pp → 0, 15+ pp → 100."""
    return float(np.clip(headroom / 15.0 * 100, 0, 100))


def _score_price_momentum(mom_12m: float) -> float:
    """Score price momentum using new_mom index (100 = flat).

    new_mom is a month-on-month price index: 100 = no change,
    101 = +1% MoM, 99 = −1% MoM.
    Centre score at 100 → 50, ±3 pp → 0 / 100.
    """
    deviation = mom_12m - 100.0  # e.g. 99.75 → -0.25
    return float(np.clip(50 + deviation * (100 / 3), 0, 100))


def _score_rate_env(deviation_from_median: float) -> float:
    """Score rate environment: below median → higher score.

    deviation = current_lpr_5y − historical_median
    Negative deviation (cheap credit) → high score.
    """
    # ±200 bp maps to 0–100
    return float(np.clip(50 - deviation_from_median * 25, 0, 100))


def analyze_real_estate(
    db_path: str,
    cities: Optional[List[str]] = None,
) -> Dict:
    """Run a multi-dimensional real-estate assessment (cached).

    Wrapper around :func:`_analyze_real_estate_impl` that converts ``cities`` to
    a hashable, NORMALISED tuple so results can be memoised: the same city set in
    a different order (or with duplicates) is the same query, and must not evict
    a live entry from the small cache (F15).
    """
    if cities is None:
        cities = ALL_CITIES
    return _analyze_real_estate_cached(db_path, tuple(sorted(set(cities))))


@db_versioned_cache(maxsize=8)
def _analyze_real_estate_cached(db_path: str, cities_tuple: tuple) -> Dict:
    return _analyze_real_estate_impl(db_path, list(cities_tuple))


def _analyze_real_estate_impl(
    db_path: str,
    cities: List[str],
) -> Dict:
    """Run a multi-dimensional real-estate assessment.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.
    cities : list[str] | None
        Subset of cities to analyse. Defaults to all 10 tracked cities.

    Returns
    -------
    dict
        Keys: leverage_df, price_df, lpr_df, assessment.
        assessment is a dict with scores 0–100 for each dimension plus a summary.
    """
    conn = sqlite3.connect(db_path)

    # ── Household leverage (quarterly) ──────────────────────────────────────
    leverage_df = pd.read_sql(
        "SELECT date, household FROM leverage WHERE household IS NOT NULL",
        conn,
    )
    leverage_df["date"] = pd.to_datetime(leverage_df["date"])
    leverage_df = leverage_df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    leverage_df["leverage_space"] = HOUSEHOLD_LEVERAGE_CAP - leverage_df["household"]

    # ── House prices (monthly, filtered by city) ────────────────────────────
    placeholders = ",".join("?" * len(cities))
    price_df = pd.read_sql(
        f"SELECT date, city, new_yoy, new_mom, used_yoy, used_mom "
        f"FROM house_price WHERE city IN ({placeholders})",
        conn,
        params=cities,
    )
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.drop_duplicates(subset=["date", "city"], keep="last").sort_values("date").reset_index(drop=True)

    # 12-month rolling mean of new_mom across all selected cities
    price_df_pivot = price_df.pivot_table(
        index="date", columns="city", values="new_mom", aggfunc="mean"
    )
    price_df_pivot["avg_mom"] = price_df_pivot.mean(axis=1)
    price_df_pivot["mom_12m"] = price_df_pivot["avg_mom"].rolling(12, min_periods=6).mean()

    # ── LPR (monthly) ───────────────────────────────────────────────────────
    lpr_df = pd.read_sql(
        "SELECT date, lpr_5y FROM lpr WHERE lpr_5y IS NOT NULL",
        conn,
    )
    lpr_df["date"] = pd.to_datetime(lpr_df["date"])
    lpr_df = lpr_df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    lpr_df["lpr_5y_median"] = lpr_df["lpr_5y"].expanding(min_periods=12).median()
    lpr_df["rate_deviation"] = lpr_df["lpr_5y"] - lpr_df["lpr_5y_median"]

    conn.close()

    # ── Build assessment from latest available data ─────────────────────────
    # Every ``.iloc[-1]`` below is guarded: an empty frame means the dimension was
    # not measured, which must stay distinguishable from a measured bad reading
    # (the old code either raised IndexError or substituted 0.0 — see NEUTRAL_SCORE).
    lev_rows = leverage_df.dropna(subset=["leverage_space"])
    lpr_rows = lpr_df.dropna(subset=["rate_deviation"])
    mom_rows = price_df_pivot["mom_12m"].dropna() if len(price_df_pivot) else pd.Series(dtype=float)

    latest_lev = lev_rows.iloc[-1] if not lev_rows.empty else None
    latest_lpr = lpr_rows.iloc[-1] if not lpr_rows.empty else None
    current_mom_12m = float(mom_rows.iloc[-1]) if not mom_rows.empty else None

    assessment = {
        "as_of_leverage": latest_lev["date"].strftime("%Y-%m") if latest_lev is not None else None,
        "household_leverage": float(latest_lev["household"]) if latest_lev is not None else None,
        "leverage_space_pp": float(latest_lev["leverage_space"]) if latest_lev is not None else None,
        "leverage_space_score": (
            _score_leverage_space(float(latest_lev["leverage_space"]))
            if latest_lev is not None else NEUTRAL_SCORE
        ),
        "leverage_space_available": latest_lev is not None,

        "as_of_price": (
            price_df_pivot.index[-1].strftime("%Y-%m") if len(price_df_pivot) else None
        ),
        "price_mom_12m": current_mom_12m,
        "price_momentum_score": (
            _score_price_momentum(current_mom_12m)
            if current_mom_12m is not None else NEUTRAL_SCORE
        ),
        "price_momentum_available": current_mom_12m is not None,

        "as_of_lpr": latest_lpr["date"].strftime("%Y-%m") if latest_lpr is not None else None,
        "lpr_5y": float(latest_lpr["lpr_5y"]) if latest_lpr is not None else None,
        "lpr_5y_median": float(latest_lpr["lpr_5y_median"]) if latest_lpr is not None else None,
        "rate_deviation_bp": float(latest_lpr["rate_deviation"]) if latest_lpr is not None else None,
        "rate_env_score": (
            _score_rate_env(float(latest_lpr["rate_deviation"]))
            if latest_lpr is not None else NEUTRAL_SCORE
        ),
        "rate_env_available": latest_lpr is not None,
    }

    # Composite: equal weight over the dimensions that actually have data, so a
    # gap neither drags the score down nor pulls it toward a fabricated 50.
    dimensions = ("leverage_space", "price_momentum", "rate_env")
    scores = [
        assessment[f"{d}_score"] for d in dimensions
        if assessment[f"{d}_available"]
    ]
    assessment["excluded_dimensions"] = [
        d for d in dimensions if not assessment[f"{d}_available"]
    ]
    assessment["composite_score"] = float(np.mean(scores)) if scores else None

    if assessment["composite_score"] is None:
        assessment["summary"] = "Insufficient data — no dimension available"
    elif assessment["composite_score"] >= 65:
        assessment["summary"] = "Supportive — ample leverage room, positive momentum, cheap credit"
    elif assessment["composite_score"] >= 45:
        assessment["summary"] = "Neutral — mixed signals across dimensions"
    else:
        assessment["summary"] = "Constrained — limited leverage room, weak momentum, or expensive credit"
    if assessment["excluded_dimensions"] and scores:
        assessment["summary"] += (
            f" (scored on {len(scores)}/3 dimensions; no data: "
            + ", ".join(assessment["excluded_dimensions"]) + ")"
        )

    return {
        "leverage_df": leverage_df,
        "price_df": price_df,
        "lpr_df": lpr_df,
        "assessment": assessment,
    }


if __name__ == "__main__":
    result = analyze_real_estate("data/macro_data.db")
    for k, v in result["assessment"].items():
        print(f"{k:28s}: {v}")
