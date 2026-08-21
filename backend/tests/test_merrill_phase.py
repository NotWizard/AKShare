"""Merrill-clock phase classifier — growth/inflation quadrant correctness.

Guards the flagship bug where +5% GDP growth was mislabeled "recession":
the old growth axis compared gdp_yoy to its own rolling *mean*, which the 2021
Q1 base-effect rebound (~+18.9%, off the 2020 Q1 COVID trough of -6.8%) inflated
so that normal ~5% growth fell "below trend". The fix compares gdp_yoy to a
robust trailing *median* (potential growth) with an epsilon dead-zone and an
N-consecutive persistence requirement before flipping to a contractionary phase.

Deterministic, DB-free: every case is a constructed DataFrame fed to the pure
`classify_phases` helper.

Run:  .venv312/bin/python -m pytest backend/tests/test_merrill_phase.py -q
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.cycle_merrill import PHASE_COLORS, classify_phases  # noqa: E402


def _df(gdp, cpi):
    """Build a chronologically-ordered frame; scalar cpi is broadcast."""
    if not isinstance(cpi, (list, tuple)):
        cpi = [cpi] * len(gdp)
    return pd.DataFrame({"gdp_yoy": list(gdp), "cpi_yoy": list(cpi)})


def _phases(gdp, cpi):
    return list(classify_phases(_df(gdp, cpi))["phase"])


# ── 1. +5% growth with low inflation is NOT recession ────────────────────────
def test_five_percent_low_inflation_is_recovery_not_recession():
    """~5% growth at/above its robust trend + sub-2% CPI ⇒ recovery, not recession.

    (Old code: the +18.0 spike inflates the trailing mean so the trailing 5.0s
    read "below trend" ⇒ recession.)
    """
    phases = _phases([5.0, 5.0, 5.0, 18.0, 5.0, 5.0], cpi=1.0)
    assert phases[-1] != "recession"
    assert phases[-1] == "recovery"


# ── 2. A base-effect spike year must not pollute subsequent normal growth ─────
def test_base_effect_spike_does_not_pollute_following_years():
    """Every normal ~5% year AFTER the one-off spike stays out of recession."""
    gdp = [5.0, 5.0, 5.0, 18.0, 5.0, 5.0]
    phases = _phases(gdp, cpi=1.0)
    # indices 4 and 5 are the post-spike normal-growth years
    assert phases[4] == "recovery"
    assert phases[5] == "recovery"
    assert "recession" not in phases[4:]


# ── 3. Hysteresis: a single-period dip does NOT flip the phase ───────────────
def test_single_period_dip_does_not_flip_phase():
    """One isolated year below trend is noise — persistence keeps it expansionary."""
    gdp = [6.0, 6.0, 6.0, 6.0, 6.0, 3.0, 6.0, 6.0]  # lone dip at index 5
    phases = _phases(gdp, cpi=1.0)
    assert phases[5] != "recession"
    assert phases[5] == "recovery"


def test_sustained_dip_does_flip_phase():
    """A genuine downturn (>=2 consecutive years below trend) DOES flip to recession,
    proving the hysteresis is a persistence filter, not a phase that can never fall."""
    gdp = [6.0, 6.0, 6.0, 6.0, 6.0, 3.0, 3.0, 6.0]  # two consecutive dips
    phases = _phases(gdp, cpi=1.0)
    assert phases[5] != "recession"   # first dip: not yet confirmed
    assert phases[6] == "recession"   # second consecutive dip: confirmed downturn


# ── 4. Boundary equality is handled deterministically ────────────────────────
def test_growth_exactly_at_trend_is_up():
    """gdp_yoy exactly equal to potential (gap == 0) counts as expansion (>=), and
    CPI exactly at the 2.0 threshold counts as low (strict >). ⇒ recovery."""
    phases = _phases([5.0, 5.0, 5.0, 5.0, 5.0], cpi=[1.0, 1.0, 1.0, 1.0, 2.0])
    assert phases[-1] == "recovery"


def test_cpi_just_above_threshold_flips_inflation_axis():
    """Same flat 5% growth but CPI just above 2.0 ⇒ overheating (growth still up)."""
    phases = _phases([5.0, 5.0, 5.0, 5.0, 5.0], cpi=[1.0, 1.0, 1.0, 1.0, 2.01])
    assert phases[-1] == "overheating"


def test_classification_is_deterministic():
    """Same input ⇒ identical output (no randomness / path-dependence on re-run)."""
    df = _df([5.0, 5.0, 18.0, 5.0, 5.0], cpi=1.0)
    a = list(classify_phases(df)["phase"])
    b = list(classify_phases(df)["phase"])
    assert a == b


# ── 5. Output contract: phase_color always maps a known phase ────────────────
def test_phase_color_maps_every_phase():
    out = classify_phases(_df([5.0, 5.0, 18.0, 5.0, 2.0, 5.0], cpi=[1, 3, 1, 3, 1, 1]))
    assert set(out["phase"]).issubset(set(PHASE_COLORS))
    assert out["phase_color"].notna().all()
