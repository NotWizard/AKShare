"""
Composite Signal System — aggregate four cycle classifiers into a single score.

Frameworks scored:
    Merrill Lynch:  recovery(+1) overheating(0) stagflation(−1) recession(−1)
    Credit:         easing(+1) neutral(0) tightening(−1)
    Inventory:      active_restocking(+1) passive_destocking(0)
                    passive_restocking(0) active_destocking(−1)
    Debt:           beautiful_deleveraging(+1) leveraging_boom(+1) stable_growth(+1)
                    ugly_deleveraging(−1) leveraging_bust(−1) stable_contraction(−1)

Composite: weighted mean of the AVAILABLE sub-signals, rescaled to [−4, +4] so the
bands below keep their meaning whatever the coverage. With all four present and
fresh (every weight 1.0) it is exactly the old sum of four scores.
    • a framework with no data (phase ``insufficient_data``, or any phase outside
      its score map) is EXCLUDED — never summed as a neutral 0;
    • a framework whose newest input is older than its publication cadence allows
      keeps HALF weight and is flagged, because the four frameworks are published
      on different calendars and are NOT the same as-of date.

Interpretation bands:
    +3 to +4 : strongly bullish
    +1 to +2 : mildly bullish
         0   : neutral
    −1 to −2 : mildly bearish
    −3 to −4 : strongly bearish
"""

import functools
import math
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

# Allow imports when run as a script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.cycle_merrill import INSUFFICIENT_DATA, classify_merrill
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

FRAMEWORKS = ("merrill", "credit", "inventory", "debt")

_SCORE_MAPS = {
    "merrill": MERRILL_SCORES,
    "credit": CREDIT_SCORES,
    "inventory": INVENTORY_SCORES,
    "debt": DEBT_SCORES,
}

# How many months a framework may legitimately lag the newest observation across
# all frameworks (its own publication cadence + one release lag) before its phase
# is describing a period the composite does not: annual GDP is up to a year plus a
# quarter behind, quarterly leverage a quarter plus a quarter, monthly series at
# most a couple of months. Beyond this the sub-signal is flagged and down-weighted
# rather than summed as if it were current.
_STALE_TOLERANCE_MONTHS = {"merrill": 15, "credit": 3, "inventory": 3, "debt": 6}

# A sub-signal can also be stale from the INSIDE: the inventory demand axis is a
# carried-forward PMI, so its frame reports how old that input is.
_INPUT_STALENESS_KEY = {"inventory": "pmi_stale_months"}

# WHY half and not a decay curve: a stale macro reading is still evidence (these
# cycles are persistent), it just must not outvote current data. One flat factor
# is auditable and adds no knob that we have no data to fit.
_STALE_WEIGHT = 0.5


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


def _db_version(db_path: str) -> tuple:
    """Cheap content tag for *db_path*: ``(mtime_ns, size)``.

    Mirrors ``backend.app.core.db._db_version`` but keyed on the *argument*
    path — ``compute_signals`` is always called with an explicit ``db_path``
    (the real DB in production, a temp copy in tests). Replicated (not imported)
    so the ``analysis`` package stays importable without the ``backend`` package
    on ``sys.path``. Missing file → ``(0, 0)`` (fresh install must not crash).
    """
    try:
        st = os.stat(db_path)
    except OSError:
        return (0, 0)
    return (st.st_mtime_ns, st.st_size)


# The four cycle classifiers are version-keyed themselves now (G03b:
# analysis.cycle_merrill.db_versioned_cache), so dropping them here is no longer
# required for correctness — it is a memory reclaim that runs exactly when a new
# DB version makes the old entries dead weight. Captured at import, so a test that
# monkeypatches the module-level names still runs fresh functions while these
# originals get cleared harmlessly. (cross_indicator's leading_lag_analysis is
# uncached — always fresh.)
_DOWNSTREAM_DB_PATH_CACHES = (
    classify_merrill,
    classify_credit,
    classify_inventory,
    classify_debt,
)


def _invalidate_downstream_caches() -> None:
    for fn in _DOWNSTREAM_DB_PATH_CACHES:
        cache_clear = getattr(fn, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


def _month_gap(later: pd.Timestamp, earlier: pd.Timestamp) -> int:
    """Whole months between two observation dates (calendar, not day-count)."""
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _fmt(ts, fmt: str) -> Optional[str]:
    return ts.strftime(fmt) if hasattr(ts, "strftime") else (None if ts is None else str(ts))


def _num(row, col: str) -> Optional[float]:
    """Row value as a JSON-safe float; ``None`` for a missing row/column or NaN."""
    if row is None or col not in row or pd.isna(row[col]):
        return None
    return float(row[col])


def _sub_signal(
    name: str,
    df: pd.DataFrame,
    phase_col: str,
    date_fmt: str,
    numeric_cols: tuple = (),
    phase_cols: tuple = (),
) -> Dict:
    """Latest row of one classifier as a scored, self-describing sub-signal.

    An empty frame yields ``phase="insufficient_data"``, ``included=False`` and
    weight 0 — this is the guard for the crash that used to take ``/api/v1/signals``
    down with ``IndexError`` on a fresh/empty DB. Any phase that is not in the
    framework's score map is treated the same way, so an unrecognised phase can
    never be scored as if it were neutral.
    """
    row = df.iloc[-1] if df is not None and len(df) else None
    phase = str(row[phase_col]) if row is not None else INSUFFICIENT_DATA
    included = phase in _SCORE_MAPS[name]
    date = row["date"] if row is not None and pd.notna(row["date"]) else None

    out = {
        "date": _fmt(date, date_fmt),
        "as_of": _fmt(date, "%Y-%m-%d"),
        "phase": phase,
        "score": _SCORE_MAPS[name].get(phase, 0),
        "included": included,
        "weight": 1.0 if included else 0.0,
        "stale": False,
        "stale_months": None,
        # Private alignment reference (popped before returning): only a USABLE
        # observation may define the common as-of frontier.
        "_date": date if included else None,
    }
    out.update({c: _num(row, c) for c in numeric_cols})
    out.update({c: (str(row[c]) if row is not None else None) for c in phase_cols})
    return out


def _apply_staleness(subs: Dict[str, Dict], frontier: Optional[pd.Timestamp]) -> None:
    """Measure each sub-signal's lag against the common as-of and down-weight.

    Alignment note: the frameworks are annual/quarterly/monthly, so a single
    literal as-of date is impossible — truncating the monthly credit read back to
    the annual GDP date would throw away five months of the freshest information.
    Instead the common as-of is the NEWEST observation across frameworks and each
    sub-signal reports its own lag against it; only a lag beyond that framework's
    publication cadence is treated as stale.
    """
    if frontier is None:
        return
    for name, sub in subs.items():
        if not sub["included"] or sub["_date"] is None:
            continue
        lag = _month_gap(frontier, sub["_date"])
        input_key = _INPUT_STALENESS_KEY.get(name)
        input_lag = sub.get(input_key) if input_key else None
        effective = max(lag, int(input_lag or 0))
        sub["stale_months"] = lag
        if effective > _STALE_TOLERANCE_MONTHS[name]:
            sub["stale"] = True
            sub["weight"] = _STALE_WEIGHT


def _round_half_away_from_zero(x: float) -> int:
    """Deterministic rounding to the published integer scale.

    ``round()`` is banker's rounding (round(0.5) == 0, round(1.5) == 2), which
    would make ±0.5 asymmetric; half-away-from-zero keeps the sign handling
    symmetric so a bullish and a bearish edge case round the same way.
    """
    return int(math.floor(x + 0.5)) if x >= 0 else int(math.ceil(x - 0.5))


def compute_signals(db_path: str) -> Dict:
    """Compute composite macro signals, invalidating automatically on a DB swap.

    Thin wrapper: the cache key of :func:`_compute_signals_versioned` includes
    ``_db_version(db_path)`` so an atomic swap of the DB file — regardless of who
    performed it — yields a fresh key and a fresh computation, with no dependency
    on an explicit ``clear_all_caches()`` call.
    """
    return _compute_signals_versioned(db_path, _db_version(db_path))


@functools.lru_cache(maxsize=4)
def _compute_signals_versioned(db_path: str, version: tuple) -> Dict:
    """Cached body, keyed by ``(db_path, DB version)``.

    Runs only on a real version change (or first call). ``version`` is otherwise
    unused (key-only).

    Returns
    -------
    dict
        Keys:
            merrill       : dict  — current phase + score + as_of + coverage flags
            credit        : dict  — idem
            inventory     : dict  — idem
            debt          : dict  — idem (overall_phase)
            cross_lags    : dict  — leading-lag correlation summary
            as_of           : str   — newest observation across frameworks
            included        : list  — frameworks in the composite
            excluded        : list  — frameworks with no usable phase
            stale           : list  — frameworks kept at half weight
            composite_score : int   — renormalised sum in [−4, +4]
            composite_raw   : float — same, before rounding
            interpretation  : str   — plain-English summary (+ coverage note)
    """
    _invalidate_downstream_caches()
    # ── Run classifiers ──────────────────────────────────────────────────────
    frames = {
        "merrill": classify_merrill(db_path),
        "credit": classify_credit(db_path),
        "inventory": classify_inventory(db_path),
        "debt": classify_debt(db_path),
    }
    cross = leading_lag_analysis(db_path)

    # ── Latest phase from each framework, each with its OWN as-of ───────────
    subs = {
        "merrill": _sub_signal(
            "merrill", frames["merrill"], "phase", "%Y",
            numeric_cols=("gdp_yoy", "cpi_yoy"),
        ),
        "credit": _sub_signal(
            "credit", frames["credit"], "phase", "%Y-%m",
            numeric_cols=("m2_yoy", "credit_impulse"),
        ),
        "inventory": _sub_signal(
            "inventory", frames["inventory"], "phase", "%Y-%m",
            numeric_cols=("pmi_official", "pmi_used", "pmi_stale_months"),
        ),
        "debt": _sub_signal(
            "debt", frames["debt"], "overall_phase", "%Y-%m",
            numeric_cols=("net_change",),
            phase_cols=("household_phase", "corp_phase", "gov_phase"),
        ),
    }

    # Common as-of = the newest USABLE observation any framework has (each
    # sub-signal carries its own date in the private "_date" key).
    dates = [s["_date"] for s in subs.values() if s["_date"] is not None]
    frontier = max(dates) if dates else None
    _apply_staleness(subs, frontier)
    for sub in subs.values():
        sub.pop("_date")

    included = [n for n in FRAMEWORKS if subs[n]["included"]]
    excluded = [n for n in FRAMEWORKS if not subs[n]["included"]]
    stale = [n for n in FRAMEWORKS if subs[n]["stale"]]

    # ── Composite: weighted mean over available sub-signals, on the [−4,+4] scale
    weight_total = sum(subs[n]["weight"] for n in included)
    raw = (
        sum(subs[n]["weight"] * subs[n]["score"] for n in included)
        / weight_total * len(FRAMEWORKS)
        if weight_total else 0.0
    )
    composite = _round_half_away_from_zero(raw)

    interpretation = _interpret(composite)
    if excluded or stale:
        note = [f"coverage {len(included)}/{len(FRAMEWORKS)}"]
        if excluded:
            note.append("no data: " + ", ".join(excluded))
        if stale:
            note.append("stale, half weight: " + ", ".join(stale))
        interpretation += " | " + "; ".join(note)

    return {
        "merrill": subs["merrill"],
        "credit": subs["credit"],
        "inventory": subs["inventory"],
        "debt": subs["debt"],
        "cross_lags": {
            "m1_ppi_best_lag": cross["m1_ppi_best_lag"],
            "m1_ppi_max_corr": round(cross["m1_ppi_max_corr"], 3) if pd.notna(cross["m1_ppi_max_corr"]) else None,
            "spread_cpi_best_lag": cross["spread_cpi_best_lag"],
            "spread_cpi_max_corr": round(cross["spread_cpi_max_corr"], 3) if pd.notna(cross["spread_cpi_max_corr"]) else None,
        },
        "as_of": _fmt(frontier, "%Y-%m-%d"),
        "included": included,
        "excluded": excluded,
        "stale": stale,
        "composite_score": composite,
        "composite_raw": round(raw, 2),
        "interpretation": interpretation,
    }


if __name__ == "__main__":
    import json
    result = compute_signals("data/macro_data.db")
    print(json.dumps(result, indent=2, default=str))
