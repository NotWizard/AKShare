"""
Composite Signal System — aggregate four cycle classifiers into a single score.

Frameworks scored:
    Merrill Lynch:  recovery(+1) overheating(0) stagflation(−1) recession(−1)
    Credit:         easing(+1) neutral(0) tightening(−1)
    Inventory:      active_restocking(+1) passive_destocking(0)
                    passive_restocking(0) active_destocking(−1)
    Debt:           beautiful_deleveraging(+1) leveraging_boom(+1) stable_growth(+1)
                    ugly_deleveraging(−1) leveraging_bust(−1) stable_contraction(−1)

Composite: sum of four scores → range [−4, +4]

Interpretation bands:
    +3 to +4 : strongly bullish
    +1 to +2 : mildly bullish
         0   : neutral
    −1 to −2 : mildly bearish
    −3 to −4 : strongly bearish
"""

import sys
from pathlib import Path
from typing import Dict

import pandas as pd

# Allow imports when run as a script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.cycle_merrill import classify_merrill
from analysis.cycle_credit import classify_credit
from analysis.cycle_inventory import classify_inventory
from analysis.cycle_debt import classify_debt
from analysis.cross_indicator import leading_lag_analysis

# ── Per-framework scoring maps ───────────────────────────────────────────────
MERRILL_SCORES = {
    "recovery": +1,
    "overheating": 0,
    "stagflation": -1,
    "recession": -1,
}

CREDIT_SCORES = {
    "easing": +1,
    "neutral": 0,
    "tightening": -1,
}

INVENTORY_SCORES = {
    "active_restocking": +1,
    "passive_restocking": 0,
    "passive_destocking": 0,
    "active_destocking": -1,
}

DEBT_SCORES = {
    "beautiful_deleveraging": +1,
    "leveraging_boom": +1,
    "stable_growth": +1,
    "ugly_deleveraging": -1,
    "leveraging_bust": -1,
    "stable_contraction": -1,
}


def _interpret(score: int) -> str:
    """Map composite score to interpretation text."""
    if score >= 3:
        return "Strongly bullish — most cycles aligned in expansion"
    elif score >= 1:
        return "Mildly bullish — growth signals outweigh headwinds"
    elif score == 0:
        return "Neutral — conflicting signals across frameworks"
    elif score >= -2:
        return "Mildly bearish — headwinds building across multiple cycles"
    else:
        return "Strongly bearish — most cycles aligned in contraction"


def compute_signals(db_path: str) -> Dict:
    """Compute composite macro signals from all four cycle frameworks.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    dict
        Keys:
            merrill       : dict  — current phase + score
            credit        : dict  — current phase + score
            inventory     : dict  — current phase + score
            debt          : dict  — current phase + score (overall_phase)
            cross_lags    : dict  — leading-lag correlation summary
            composite_score : int   — sum in [−4, +4]
            interpretation  : str   — plain-English summary
    """
    # ── Run classifiers ──────────────────────────────────────────────────────
    merrill_df = classify_merrill(db_path)
    credit_df = classify_credit(db_path)
    inventory_df = classify_inventory(db_path)
    debt_df = classify_debt(db_path)
    cross = leading_lag_analysis(db_path)

    # ── Latest phase from each framework ────────────────────────────────────
    m_latest = merrill_df.iloc[-1]
    c_latest = credit_df.iloc[-1]
    i_latest = inventory_df.iloc[-1]
    d_latest = debt_df.iloc[-1]

    merrill_phase = str(m_latest["phase"])
    credit_phase = str(c_latest["phase"])
    inventory_phase = str(i_latest["phase"])
    debt_phase = str(d_latest["overall_phase"])

    merrill_score = MERRILL_SCORES.get(merrill_phase, 0)
    credit_score = CREDIT_SCORES.get(credit_phase, 0)
    inventory_score = INVENTORY_SCORES.get(inventory_phase, 0)
    debt_score = DEBT_SCORES.get(debt_phase, 0)

    composite = merrill_score + credit_score + inventory_score + debt_score

    return {
        "merrill": {
            "date": m_latest["date"].strftime("%Y") if hasattr(m_latest["date"], "strftime") else str(m_latest["date"]),
            "phase": merrill_phase,
            "gdp_yoy": float(m_latest["gdp_yoy"]) if pd.notna(m_latest["gdp_yoy"]) else None,
            "cpi_yoy": float(m_latest["cpi_yoy"]) if pd.notna(m_latest["cpi_yoy"]) else None,
            "score": merrill_score,
        },
        "credit": {
            "date": c_latest["date"].strftime("%Y-%m") if hasattr(c_latest["date"], "strftime") else str(c_latest["date"]),
            "phase": credit_phase,
            "m2_yoy": float(c_latest["m2_yoy"]) if pd.notna(c_latest["m2_yoy"]) else None,
            "credit_impulse": float(c_latest["credit_impulse"]) if pd.notna(c_latest["credit_impulse"]) else None,
            "score": credit_score,
        },
        "inventory": {
            "date": i_latest["date"].strftime("%Y-%m") if hasattr(i_latest["date"], "strftime") else str(i_latest["date"]),
            "phase": inventory_phase,
            "pmi_official": float(i_latest["pmi_official"]) if pd.notna(i_latest["pmi_official"]) else None,
            "score": inventory_score,
        },
        "debt": {
            "date": d_latest["date"].strftime("%Y-%m") if hasattr(d_latest["date"], "strftime") else str(d_latest["date"]),
            "phase": debt_phase,
            "household_phase": str(d_latest["household_phase"]),
            "corp_phase": str(d_latest["corp_phase"]),
            "gov_phase": str(d_latest["gov_phase"]),
            "score": debt_score,
        },
        "cross_lags": {
            "m1_ppi_best_lag": cross["m1_ppi_best_lag"],
            "m1_ppi_max_corr": round(cross["m1_ppi_max_corr"], 3) if pd.notna(cross["m1_ppi_max_corr"]) else None,
            "spread_cpi_best_lag": cross["spread_cpi_best_lag"],
            "spread_cpi_max_corr": round(cross["spread_cpi_max_corr"], 3) if pd.notna(cross["spread_cpi_max_corr"]) else None,
        },
        "composite_score": composite,
        "interpretation": _interpret(composite),
    }


if __name__ == "__main__":
    import json
    result = compute_signals("data/macro_data.db")
    print(json.dumps(result, indent=2, default=str))
