"""
Merrill Lynch Investment Clock — classify macroeconomic phases.

Growth signal:  GDP_yoy vs a robust trailing-median potential-growth estimate,
                with an epsilon dead-zone + N-consecutive persistence (hysteresis)
                so base-effect spikes and sub-pp noise cannot flip the phase.
Inflation signal: CPI_yoy vs 2.0% threshold

Phases:
    Recovery    (GDP↑ CPI↓)  → #2ecc71 green
    Overheating (GDP↑ CPI↑)  → #e74c3c red
    Stagflation (GDP↓ CPI↑)  → #f39c12 orange
    Recession   (GDP↓ CPI↓)  → #3498db blue

This module also hosts the primitives shared by the whole cycle family — the
growth axis (:func:`potential_growth` / :func:`growth_above_trend`, reused by
the debt cycle so both frameworks judge growth the same way), the
``insufficient_data`` phase name, and :func:`db_versioned_cache`. They live here
because this module imports nothing from ``analysis``: every other cycle module
can import from it, whereas hosting them in ``analysis/signals.py`` would be an
import cycle (signals imports all four classifiers).
"""

import functools
import os
import sqlite3
import pandas as pd
import numpy as np

PHASE_COLORS = {
    "recovery": "#2ecc71",
    "overheating": "#e74c3c",
    "stagflation": "#f39c12",
    "recession": "#3498db",
}

# Phase name used by every framework for a period it CANNOT classify (an input
# is absent). It is deliberately not one of the real phases and carries no score
# in analysis/signals.py, so a data gap is excluded from the composite instead of
# being scored — a missing input must never look like a verdict.
INSUFFICIENT_DATA = "insufficient_data"

# Growth-axis defaults (single source for the Merrill clock and the debt cycle).
POTENTIAL_WINDOW = 5   # periods in the trailing potential-growth median
GROWTH_EPS = 0.5       # pp dead-zone around potential before "below trend"
GROWTH_PERSIST = 2     # consecutive below-potential periods to confirm a downturn
CPI_THRESHOLD = 2.0    # % CPI YoY dividing low vs high inflation


def _db_version(db_path: str) -> tuple:
    """Cheap content tag for *db_path*: ``(mtime_ns, size)`` — one ``stat()``.

    Same tag as ``backend.app.core.db._db_version``, but keyed on the *argument*
    path (the classifiers are always called with an explicit ``db_path``: the
    real DB in production, a temp copy in tests). A missing file must not crash a
    fresh install, so it degrades to ``(0, 0)``.
    """
    try:
        st = os.stat(db_path)
    except OSError:
        return (0, 0)
    return (st.st_mtime_ns, st.st_size)


def db_versioned_cache(maxsize: int = 4):
    """``lru_cache`` for ``f(db_path, ...)`` whose key also carries the DB version.

    A CLI/cron refresh swaps the DB with ``os.replace`` and never touches the
    long-running API process, so invalidation cannot hang off the refresh CALL
    PATH — it has to hang off the DATA. Keying on ``(db_path, version, *args)``
    turns a swapped file into a fresh key, hence a fresh read, with no
    ``clear_all_caches()`` required (G03/G03b).

    ``cache_clear``/``cache_info`` are re-exported on the wrapper because
    ``backend/app/core/cache.py`` calls ``cache_clear()`` on these public names.
    """
    def decorate(fn):
        @functools.lru_cache(maxsize=maxsize)
        def cached(db_path, version, *args):
            return fn(db_path, *args)

        @functools.wraps(fn)
        def wrapper(db_path, *args):
            return cached(db_path, _db_version(db_path), *args)

        wrapper.cache_clear = cached.cache_clear
        wrapper.cache_info = cached.cache_info
        return wrapper

    return decorate


def potential_growth(gdp_yoy: pd.Series, window: int = POTENTIAL_WINDOW) -> pd.Series:
    """Robust potential-growth proxy: the trailing rolling MEDIAN of *gdp_yoy*.

    WHY a median (not the old rolling mean): gdp_yoy here is the Q1 single-quarter
    YoY, so the 2020 COVID trough (−6.8) and the 2021 low-base rebound (+18.9) are
    extreme outliers. A mean folds those spikes into the "trend" (it reached ~8.4
    in 2024), pushing normal ~5% growth "below trend" ⇒ false recession. The
    median is robust: the crash and the rebound sit at the two extremes of the
    window, so it lands on a representative middle year and a single anomaly
    cannot move it. The result approximates potential/target growth and adapts as
    China's trend growth structurally steps down.
    """
    return gdp_yoy.rolling(window, min_periods=1).median()


def growth_above_trend(
    gdp_yoy: pd.Series,
    potential_window: int = POTENTIAL_WINDOW,
    growth_eps: float = GROWTH_EPS,
    growth_persist: int = GROWTH_PERSIST,
) -> pd.Series:
    """Boolean growth axis: is growth at/above potential (with hysteresis)?

    Kills the flip-flop where 5.0 vs 5.1 flipped the phase:
      • dead-zone — growth within `growth_eps` of potential counts as "at trend"
        (expansion), never a downturn on sub-pp noise/revisions;
      • persistence — a downturn is confirmed only after `growth_persist`
        CONSECUTIVE periods clearly below potential; one isolated dip is ignored.
    "Up" is the low-bar default, restored immediately on a return to trend, so the
    state can never get stuck (unlike a symmetric Schmitt trigger, which stayed
    "down" once China's growth flattened at ~5%).

    NaN growth yields ``True`` (no evidence of a downturn); callers that must
    distinguish "unknown" from "expanding" have to test for NaN themselves — see
    ``analysis/cycle_debt.py``, which marks those periods ``insufficient_data``.
    """
    gap = gdp_yoy - potential_growth(gdp_yoy, potential_window)
    below = (gap < -growth_eps).astype(float)
    confirmed_down = (
        below.rolling(growth_persist, min_periods=growth_persist).sum() >= growth_persist
    )
    return ~confirmed_down.fillna(False)


def classify_phases(
    df: pd.DataFrame,
    potential_window: int = POTENTIAL_WINDOW,
    growth_eps: float = GROWTH_EPS,
    growth_persist: int = GROWTH_PERSIST,
    cpi_threshold: float = CPI_THRESHOLD,
) -> pd.DataFrame:
    """Classify Merrill phases on a chronologically-sorted frame (pure, DB-free).

    Expects columns ``gdp_yoy`` and ``cpi_yoy``. Returns a copy with ``gdp_trend``
    (a robust potential-growth estimate), ``phase`` and ``phase_color`` added.
    Split out from ``classify_merrill`` so the quadrant logic is unit-testable on
    constructed data (see backend/tests/test_merrill_phase.py).

    Parameters tune the growth axis:
        potential_window : trailing window (periods) for the potential-growth median
        growth_eps       : dead-zone half-width (pp) around potential before "down"
        growth_persist   : consecutive below-trend periods required to confirm "down"
        cpi_threshold    : absolute CPI YoY (%) dividing low vs high inflation
    """
    out = df.copy().reset_index(drop=True)

    # ── Growth axis: gap vs a ROBUST potential-growth estimate ───────────────
    # Rationale for the median and for the dead-zone + persistence hysteresis
    # lives on potential_growth() / growth_above_trend(), which the debt cycle
    # imports so both frameworks judge "is growth below potential" identically.
    out["gdp_trend"] = potential_growth(out["gdp_yoy"], potential_window)
    gdp_up = growth_above_trend(
        out["gdp_yoy"], potential_window, growth_eps, growth_persist
    )

    # ── Inflation axis: absolute CPI threshold (already sound — no relative-trend
    # flaw to fix). Strict '>' keeps the boundary deterministic (exactly the
    # threshold counts as low inflation).
    cpi_up = out["cpi_yoy"] > cpi_threshold

    conditions = [
        gdp_up & ~cpi_up,   # recovery
        gdp_up & cpi_up,    # overheating
        ~gdp_up & cpi_up,   # stagflation
        ~gdp_up & ~cpi_up,  # recession
    ]
    choices = ["recovery", "overheating", "stagflation", "recession"]
    out["phase"] = np.select(conditions, choices, default="recession")
    out["phase_color"] = out["phase"].map(PHASE_COLORS)
    return out


@db_versioned_cache(maxsize=4)
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
    # derived_quarterly 现为季频（年 GDP 经 merge_asof ffill 到各季）；按年去重恢复年频，
    # 保证 classify_phases 的潜在增速中位数按「年」滚动（否则季度上窗口跨度缩水，误判阶段）。
    gdp = pd.read_sql(
        "SELECT date, gdp_yoy FROM derived_quarterly WHERE gdp_yoy IS NOT NULL",
        conn,
    )
    gdp["date"] = pd.to_datetime(gdp["date"])
    gdp = gdp.drop_duplicates(subset=["date"], keep="last")
    gdp = gdp.sort_values("date").reset_index(drop=True)
    gdp["year"] = gdp["date"].dt.year
    gdp = gdp.drop_duplicates(subset=["year"], keep="last").drop(columns=["year"])

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

    # ── Growth + inflation quadrant (pure helper, unit-tested separately) ─────
    df = classify_phases(df)

    return df[["date", "gdp_yoy", "cpi_yoy", "gdp_trend", "phase", "phase_color"]]


if __name__ == "__main__":
    result = classify_merrill("data/macro_data.db")
    print(result.to_string(index=False))
