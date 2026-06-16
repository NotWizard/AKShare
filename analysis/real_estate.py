"""
Real Estate Analysis — household leverage, price momentum, rate environment.

Dimensions scored 0–100 (100 = most favourable for housing demand):

1. Leverage space:  headroom = 70% − household leverage  (more headroom → higher score)
2. Price momentum:  12-month rolling mean of new_mom across selected cities
                     (positive and rising → higher score)
3. Rate environment: lpr_5y vs its own historical median since 2019
                     (below median → higher score = cheaper credit)
"""

import functools
import sqlite3
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Theoretical ceiling for household leverage ratio (%)
HOUSEHOLD_LEVERAGE_CAP = 70.0

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
    a hashable tuple so results can be memoised.
    """
    if cities is None:
        cities = ALL_CITIES
    return _analyze_real_estate_cached(db_path, tuple(cities))


@functools.lru_cache(maxsize=8)
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
    latest_lev = leverage_df.dropna(subset=["leverage_space"]).iloc[-1]
    latest_mom = price_df_pivot["mom_12m"].dropna()
    latest_lpr = lpr_df.dropna(subset=["rate_deviation"]).iloc[-1]

    current_headroom = float(latest_lev["leverage_space"])
    current_mom_12m = float(latest_mom.iloc[-1]) if not latest_mom.empty else 0.0
    current_rate_dev = float(latest_lpr["rate_deviation"])

    assessment = {
        "as_of_leverage": latest_lev["date"].strftime("%Y-%m"),
        "household_leverage": float(latest_lev["household"]),
        "leverage_space_pp": current_headroom,
        "leverage_space_score": _score_leverage_space(current_headroom),

        "as_of_price": price_df_pivot.index[-1].strftime("%Y-%m"),
        "price_mom_12m": current_mom_12m,
        "price_momentum_score": _score_price_momentum(current_mom_12m),

        "as_of_lpr": latest_lpr["date"].strftime("%Y-%m"),
        "lpr_5y": float(latest_lpr["lpr_5y"]),
        "lpr_5y_median": float(latest_lpr["lpr_5y_median"]),
        "rate_deviation_bp": current_rate_dev,
        "rate_env_score": _score_rate_env(current_rate_dev),
    }

    # Composite: equal weight
    scores = [
        assessment["leverage_space_score"],
        assessment["price_momentum_score"],
        assessment["rate_env_score"],
    ]
    assessment["composite_score"] = float(np.mean(scores))

    if assessment["composite_score"] >= 65:
        assessment["summary"] = "Supportive — ample leverage room, positive momentum, cheap credit"
    elif assessment["composite_score"] >= 45:
        assessment["summary"] = "Neutral — mixed signals across dimensions"
    else:
        assessment["summary"] = "Constrained — limited leverage room, weak momentum, or expensive credit"

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
