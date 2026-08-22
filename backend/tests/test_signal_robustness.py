"""Quantitative signal robustness — G23 (+ G03b cache version keys).

Every case is a deterministic, constructed SQLite DB under ``tmp_path``; the
live ``data/macro_data.db`` is never opened for writing (only ``shutil.copy2``
would be allowed, and no test needs it).

The five bugs pinned here (all found against real data):

A-H1  cross-period misalignment — ``compute_signals`` summed four phases taken
      from four DIFFERENT dates, and the inventory frame was pinned 10 months in
      the past because ``classify_inventory`` required pmi_official AND ip_yoy in
      the same row (pmi ends 2025-08, ip runs to 2026-06).
A-H2  a MISSING input produced a STRONG signal: an empty classifier frame raised
      IndexError (``/api/v1/signals`` → 500), and real-estate's missing
      12m-momentum fell back to ``0.0``, which ``_score_price_momentum`` reads as
      −100% MoM ⇒ the most bearish score possible.
A-H3  debt-cycle degeneracy — ``any_deleveraging`` came first in ``np.select``,
      so one deleveraging sector labelled the whole economy
      "beautiful_deleveraging" while the other two levered hard; and
      ``gdp_yoy > 0`` made the three bearish branches unreachable in practice.
A-M5  credit phase chatter — a bare ``impulse > impulse.shift(1)`` flipped
      easing↔neutral on ±0.01 pp wiggles.
G03b  ``classify_*`` / ``_analyze_real_estate_cached`` were keyed on the db_path
      STRING only, so ``/api/v1/cycles/*`` and ``/api/v1/real-estate`` served
      pre-swap data until ``/api/v1/signals`` happened to be hit.

Run:  .venv312/bin/python -m pytest backend/tests/test_signal_robustness.py -q
"""

import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.cycle_credit import classify_credit  # noqa: E402
from analysis.cycle_debt import classify_debt  # noqa: E402
from analysis.cycle_inventory import classify_inventory  # noqa: E402
from analysis.cycle_merrill import classify_merrill  # noqa: E402
from analysis.real_estate import (  # noqa: E402
    _analyze_real_estate_cached,
    analyze_real_estate,
)
from analysis.signals import compute_signals  # noqa: E402

INSUFFICIENT = "insufficient_data"
INVENTORY_PHASES = {
    "active_restocking", "passive_restocking",
    "active_destocking", "passive_destocking",
}
DEBT_PHASES = {
    "beautiful_deleveraging", "ugly_deleveraging",
    "leveraging_boom", "leveraging_bust",
    "stable_growth", "stable_contraction",
}

# ── DB fixtures ──────────────────────────────────────────────────────────────
# Only the columns the classifiers actually SELECT (plus the four
# cross_indicator needs) — a schema-valid subset, declared with real types so an
# empty table still round-trips.
_SCHEMA = {
    "derived_monthly": (
        "date TEXT, m1_yoy REAL, m2_yoy REAL, m2_m1_spread REAL, cpi_yoy REAL, "
        "ppi_yoy REAL, pmi_official REAL, pmi_ma6 REAL, ip_yoy REAL, ip_trend REAL"
    ),
    "derived_quarterly": "date TEXT, gdp_yoy REAL",
    "leverage": "date TEXT, household REAL, non_fin_corp REAL, gov_total REAL",
    "house_price": (
        "date TEXT, city TEXT, new_yoy REAL, new_mom REAL, used_yoy REAL, used_mom REAL"
    ),
    "lpr": "date TEXT, lpr_1y REAL, lpr_5y REAL",
}


def _cols(table):
    return [c.strip().split()[0] for c in _SCHEMA[table].split(",")]


def build_db(path, *, monthly=(), quarterly=(), leverage=(), house_price=(), lpr=()):
    """(Re)create a schema-valid macro DB at *path* holding exactly these rows.

    Rows are dicts; absent keys become NULL. Tables are dropped first so the
    same path can be rewritten in place — that is how the G03b tests simulate
    the CLI/cron ``os.replace`` swap.
    """
    rows_by_table = {
        "derived_monthly": monthly, "derived_quarterly": quarterly,
        "leverage": leverage, "house_price": house_price, "lpr": lpr,
    }
    conn = sqlite3.connect(path)
    try:
        for table, ddl in _SCHEMA.items():
            cols = _cols(table)
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(f"CREATE TABLE {table} ({ddl})")
            conn.executemany(
                f"INSERT INTO {table} ({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})",
                [tuple(r.get(c) for c in cols) for r in rows_by_table[table]],
            )
        conn.commit()
    finally:
        conn.close()
    _bump_mtime(path)
    return str(path)


def _bump_mtime(path):
    """Force a strictly-greater mtime so the (mtime_ns, size) version differs even
    when a rewrite lands in the same coarse-clock tick (same trick as
    test_cache_version.py)."""
    st = os.stat(path)
    later = st.st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))


def _months(start, n):
    return list(pd.date_range(start, periods=n, freq="MS").strftime("%Y-%m-%d"))


def _quarters(start, n):
    return list(pd.date_range(start, periods=n, freq="QS").strftime("%Y-%m-%d"))


def _years(first, n):
    return [f"{first + i}-01-01" for i in range(n)]


def _monthly_rows(dates, **series):
    """Zip equal-length column lists into monthly row dicts."""
    return [
        {"date": d, **{k: v[i] for k, v in series.items()}}
        for i, d in enumerate(dates)
    ]


# ── 1. A-H1: the inventory frame must not be pinned by a PMI publication gap ──
def test_inventory_latest_month_not_pinned_by_pmi_gap(tmp_path):
    """ip_yoy-only months still classify (pmi carried forward + marked stale).

    Pre-fix: ``WHERE pmi_official IS NOT NULL AND ip_yoy IS NOT NULL`` dropped
    every month after the last PMI print, so the "current" inventory phase was
    10 months old while the composite summed it as if it were today's.
    """
    dates = _months("2024-01-01", 24)
    ip = [5.0] * 23 + [6.0]                     # flat, then a clear pickup
    pmi = [51.0] * 14 + [None] * 10             # PMI stops 10 months early
    db = build_db(tmp_path / "m.db", monthly=_monthly_rows(dates, ip_yoy=ip, pmi_official=pmi))

    out = classify_inventory(db)

    assert out["date"].max() == pd.Timestamp(dates[-1]), (
        "inventory frame still truncated at the last PMI print — the classifier "
        "requires both columns in the same row (pre-fix failure)"
    )
    assert len(out) == 24
    # ip_trend needs 3 points, so only the first two rows are unclassifiable.
    assert set(out["phase"].iloc[2:]) <= INVENTORY_PHASES
    last = out.iloc[-1]
    assert last["phase"] == "active_restocking"   # carried PMI 51 > 50, ip > trend
    assert last["pmi_official"] is None or pd.isna(last["pmi_official"])  # never fabricated
    assert last["pmi_used"] == 51.0                                        # carried forward
    assert last["pmi_stale_months"] == 10                                  # …and flagged


def test_inventory_marks_rows_it_cannot_classify(tmp_path):
    """No production signal (ip_trend not yet defined) ⇒ insufficient_data, not
    a destocking (bearish) verdict by NaN-comparison accident."""
    dates = _months("2024-01-01", 4)
    db = build_db(
        tmp_path / "m.db",
        monthly=_monthly_rows(dates, ip_yoy=[5.0] * 4, pmi_official=[51.0] * 4),
    )
    out = classify_inventory(db)
    assert list(out["phase"].iloc[:2]) == [INSUFFICIENT, INSUFFICIENT]
    assert out["phase_color"].notna().all()       # colour map must cover it


# ── 2. A-H1/A-H2: composite renormalises over AVAILABLE sub-signals ──────────
def _three_of_four_db(tmp_path):
    """merrill/credit/inventory all clearly +1; leverage table EMPTY ⇒ no debt."""
    dates = _months("2025-01-01", 18)                      # …through 2026-06
    m2 = [8.0] * 12 + [8.6, 9.2, 9.8, 10.4, 11.0, 11.6]    # sustained easing
    ip = [5.0] * 17 + [6.0]
    return build_db(
        tmp_path / "m.db",
        monthly=_monthly_rows(
            dates, m2_yoy=m2, ip_yoy=ip,
            cpi_yoy=[1.0] * 18, pmi_official=[51.0] * 18,
        ),
        quarterly=[{"date": d, "gdp_yoy": 5.0} for d in _years(2020, 7)],
        leverage=(),
    )


def test_missing_sub_signal_is_excluded_and_composite_renormalised(tmp_path):
    """A sub-signal with no data is EXCLUDED and the composite is renormalised
    over what is left — it is not silently summed as a neutral 0.

    Pre-fix: ``merrill_df.iloc[-1]`` on the empty debt frame raised IndexError;
    had it survived, ``DEBT_SCORES.get(phase, 0)`` would have counted the missing
    framework as "neutral", diluting a unanimous +1 read to 3/4.
    """
    sig = compute_signals(_three_of_four_db(tmp_path))

    assert sig["merrill"]["phase"] == "recovery"
    assert sig["credit"]["phase"] == "easing"
    assert sig["inventory"]["phase"] == "active_restocking"

    assert sig["debt"]["phase"] == INSUFFICIENT
    assert sig["debt"]["included"] is False
    assert sig["debt"]["as_of"] is None
    assert sig["excluded"] == ["debt"]
    assert sig["included"] == ["merrill", "credit", "inventory"]

    # 3 available sub-signals, all +1 ⇒ full-scale +4, NOT the diluted sum of 3.
    assert sig["composite_raw"] == pytest.approx(4.0)
    assert sig["composite_score"] == 4
    assert isinstance(sig["composite_score"], int)


def test_every_sub_signal_exposes_its_own_as_of(tmp_path):
    """Each framework carries the date it actually describes + its lag against
    the common as-of frontier, so a caller can see the periods are not aligned."""
    sig = compute_signals(_three_of_four_db(tmp_path))

    assert sig["as_of"] == "2026-06-01"                    # newest observation
    assert sig["merrill"]["as_of"] == "2026-01-01"         # annual → 5 months back
    assert sig["credit"]["as_of"] == "2026-06-01"
    assert sig["inventory"]["as_of"] == "2026-06-01"
    assert sig["merrill"]["stale_months"] == 5             # within annual cadence
    assert sig["merrill"]["stale"] is False
    assert sig["credit"]["stale_months"] == 0
    # existing keys keep their existing meaning/format
    assert sig["merrill"]["date"] == "2026"
    assert sig["credit"]["date"] == "2026-06"


def test_stale_sub_signal_is_down_weighted_not_summed_as_current(tmp_path):
    """A sub-signal whose newest input is months behind the frontier is flagged
    and down-weighted; a fresh unanimous read is unchanged (weights all 1.0)."""
    dates = _months("2025-01-01", 18)
    ip = [5.0] * 17 + [6.0]
    pmi = [51.0] * 8 + [None] * 10          # PMI 10 months stale at the frontier
    db = build_db(
        tmp_path / "m.db",
        monthly=_monthly_rows(
            dates, m2_yoy=[8.0] * 18, ip_yoy=ip,
            cpi_yoy=[1.0] * 18, pmi_official=pmi,
        ),
        quarterly=[{"date": d, "gdp_yoy": 5.0} for d in _years(2020, 7)],
        leverage=[{"date": d, "household": 60.0, "non_fin_corp": 150.0,
                   "gov_total": 50.0} for d in _quarters("2024-01-01", 9)],
    )
    sig = compute_signals(db)

    assert sig["inventory"]["as_of"] == "2026-06-01"   # ip is current…
    assert sig["inventory"]["pmi_stale_months"] == 10  # …but its demand axis is not
    assert sig["inventory"]["stale"] is True
    assert sig["inventory"]["weight"] == 0.5
    assert "inventory" in sig["stale"]
    assert sig["credit"]["weight"] == 1.0


# ── 3. A-H2: an empty DB is "no data", never a signal, never a 500 ───────────
def test_empty_db_yields_insufficient_data_everywhere(tmp_path):
    """Pre-fix this raised ``IndexError: single positional indexer is out-of-bounds``."""
    sig = compute_signals(build_db(tmp_path / "m.db"))

    for name in ("merrill", "credit", "inventory", "debt"):
        assert sig[name]["phase"] == INSUFFICIENT
        assert sig[name]["included"] is False
        assert sig[name]["score"] == 0
    assert sig["excluded"] == ["merrill", "credit", "inventory", "debt"]
    assert sig["composite_score"] == 0
    assert sig["composite_raw"] == 0.0
    assert sig["interpretation"]                      # still a usable summary


def test_signals_endpoint_does_not_500_on_empty_db(tmp_path, monkeypatch):
    """``/api/v1/signals`` must degrade to "no data", not blow up (fresh install)."""
    from fastapi.testclient import TestClient

    from backend.app.core import db as core_db
    from backend.app.main import app

    monkeypatch.setattr(core_db, "DB_PATH", Path(build_db(tmp_path / "m.db")))
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200, "endpoint 500s on an empty DB (pre-fix failure)"
    body = resp.json()
    assert body["composite_score"] == 0
    # response_model keeps the sub-dicts opaque, so the flags survive the wire
    assert body["merrill"]["phase"] == INSUFFICIENT
    assert body["merrill"]["included"] is False
    assert body["credit"]["as_of"] is None


# ── 4. A-H2(b): missing price momentum must be neutral, not maximally bearish ─
def _real_estate_db(tmp_path, *, price_months=3, household=60.0):
    """Leverage + LPR available; house_price too short for the 12m momentum
    window (min_periods=6) ⇒ the momentum dimension has no value."""
    lpr_dates = _months("2025-01-01", 14)
    return build_db(
        tmp_path / "m.db",
        leverage=[{"date": "2026-03-01", "household": household,
                   "non_fin_corp": 150.0, "gov_total": 50.0}],
        lpr=[{"date": d, "lpr_5y": 4.0 if i < 13 else 3.5}
             for i, d in enumerate(lpr_dates)],
        house_price=[{"date": d, "city": c, "new_mom": 100.0}
                     for d in _months("2026-01-01", price_months)
                     for c in ("北京", "上海")],
    )


def test_missing_price_momentum_is_neutral_not_most_bearish(tmp_path):
    """Pre-fix: ``current_mom_12m = 0.0`` → ``_score_price_momentum(0.0)`` = 0.0,
    i.e. "no data" scored as −100% MoM — the single most bearish input possible."""
    a = analyze_real_estate(_real_estate_db(tmp_path))["assessment"]

    assert a["price_mom_12m"] is None, "0.0 is not a price index — do not fabricate it"
    assert a["price_momentum_score"] == 50.0, (
        "missing momentum still scored at an extreme (pre-fix: 0.0 = maximally bearish)"
    )
    assert a["price_momentum_available"] is False
    assert a["excluded_dimensions"] == ["price_momentum"]

    # composite renormalised over the two dimensions that DO have data
    assert a["composite_score"] == pytest.approx(
        (a["leverage_space_score"] + a["rate_env_score"]) / 2
    )
    assert a["composite_score"] > 45, "a data gap must not drag the composite down"


def test_real_estate_survives_an_empty_price_table(tmp_path):
    """Pre-fix: ``price_df_pivot.index[-1]`` raised IndexError on an empty frame."""
    a = analyze_real_estate(_real_estate_db(tmp_path, price_months=0))["assessment"]
    assert a["as_of_price"] is None
    assert a["price_momentum_score"] == 50.0
    assert a["summary"]


def test_real_estate_all_dimensions_missing_is_insufficient(tmp_path):
    """Nothing available ⇒ no composite at all (rather than a fabricated score)."""
    a = analyze_real_estate(build_db(tmp_path / "m.db"))["assessment"]
    assert a["composite_score"] is None
    assert sorted(a["excluded_dimensions"]) == ["leverage_space", "price_momentum", "rate_env"]
    assert a["summary"]


# ── 5. A-H3: debt phase follows the NET sector direction ─────────────────────
def _debt_db(tmp_path, gdp_by_year):
    """9 quarters: household deleveraging −2.0pp/4q while corp +6.0 and gov +6.0
    lever hard ⇒ economy-wide leverage is RISING by 10pp of GDP."""
    q = _quarters("2022-01-01", 9)
    hh = [60.0] * 5 + [59.5, 59.0, 58.5, 58.0]
    corp = [150.0] * 5 + [151.5, 153.0, 154.5, 156.0]
    gov = [50.0] * 5 + [51.5, 53.0, 54.5, 56.0]
    return build_db(
        tmp_path / "m.db",
        leverage=[{"date": d, "household": hh[i], "non_fin_corp": corp[i],
                   "gov_total": gov[i]} for i, d in enumerate(q)],
        quarterly=[{"date": f"{y}-01-01", "gdp_yoy": g} for y, g in gdp_by_year],
    )


def test_one_deleveraging_sector_does_not_own_the_verdict(tmp_path):
    """1 sector deleveraging + 2 levering hard is NOT "beautiful deleveraging".

    Pre-fix ``any_deleveraging`` came first in ``np.select``, so household
    −2.5pp outvoted corp +6.3 and gov +7.1 (the real 2026-Q1 configuration).
    """
    gdp = [(y, 5.0) for y in range(2020, 2025)]
    out = classify_debt(_debt_db(tmp_path, gdp))
    last = out.iloc[-1]

    assert last["household_phase"] == "deleveraging"      # per-sector detail kept
    assert last["corp_phase"] == "leveraging"
    assert last["gov_phase"] == "leveraging"
    assert last["overall_phase"] != "beautiful_deleveraging", (
        "one deleveraging sector still dictates the overall phase (pre-fix failure)"
    )
    assert last["overall_phase"] == "leveraging_boom"
    assert last["net_change"] == pytest.approx(10.0)      # −2 + 6 + 6 pp of GDP


def test_debt_bearish_branch_is_reachable_below_trend_growth(tmp_path):
    """Growth *below its own potential* (not below zero) opens the bust branch.

    Pre-fix ``gdp_yoy > 0`` was ~always true for China, so leveraging_bust /
    ugly_deleveraging / stable_contraction were effectively unreachable and the
    debt score was pinned at +1.
    """
    gdp = [(2020, 5.0), (2021, 5.0), (2022, 5.0), (2023, 2.0), (2024, 2.0)]
    out = classify_debt(_debt_db(tmp_path, gdp))
    last = out.iloc[-1]

    assert last["overall_phase"] == "leveraging_bust", (
        "positive-but-below-potential growth still read as expansion (pre-fix failure)"
    )
    assert last["gdp_yoy"] == 2.0 and last["gdp_yoy"] < last["gdp_trend"]


def test_debt_single_year_dip_does_not_flip_the_phase(tmp_path):
    """Hysteresis mirrors the Merrill fix: one below-potential year is noise."""
    gdp = [(2020, 5.0), (2021, 5.0), (2022, 5.0), (2023, 5.0), (2024, 2.0)]
    out = classify_debt(_debt_db(tmp_path, gdp))
    assert out.iloc[-1]["overall_phase"] == "leveraging_boom"


def test_debt_marks_quarters_it_cannot_classify(tmp_path):
    """No 4-quarter change yet (or no GDP observation yet) ⇒ insufficient_data,
    not the +1-scoring "stable_growth" default.

    On the real DB this is exactly the 2005 quarters, which the old code scored
    as stable_contraction (−1) purely because GDP data started in 2006.
    """
    out = classify_debt(_debt_db(tmp_path, [(2024, 5.0)]))
    assert list(out["overall_phase"].iloc[:4]) == [INSUFFICIENT] * 4
    assert set(out["overall_phase"]) <= DEBT_PHASES | {INSUFFICIENT}


# ── 6. A-M5: credit phase must not chatter on noise ──────────────────────────
def _credit_db(tmp_path, m2):
    return build_db(
        tmp_path / "m.db",
        monthly=_monthly_rows(_months("2025-01-01", len(m2)), m2_yoy=m2),
    )


def test_tiny_impulse_wiggle_does_not_flip_the_phase(tmp_path):
    """±0.01pp M2 wiggles (impulse ≈ 0.04↔0.05) must stay one phase.

    Pre-fix ``impulse > impulse.shift(1)`` alone flipped easing↔neutral every
    month — the real 2026 print sequence flipped four times in six months.
    """
    m2 = [8.0] * 12 + [8.05, 8.04, 8.05, 8.04, 8.05, 8.04]
    out = classify_credit(_credit_db(tmp_path, m2))
    tail = list(out["phase"].iloc[-6:])

    assert len(set(tail)) == 1, f"phase chatters on noise: {tail} (pre-fix failure)"
    assert tail[-1] == "neutral", "sub-threshold impulse is not a policy signal"
    # the impulse really is positive and really does wiggle — it is just noise
    assert 0.0 < out["credit_impulse"].iloc[-1] < 0.05
    assert out["credit_impulse"].iloc[-2] > out["credit_impulse"].iloc[-1]


def test_genuine_easing_still_classifies_as_easing(tmp_path):
    """The dead-zone must filter noise, not swallow real episodes."""
    m2 = [8.0] * 12 + [8.6, 9.2, 9.8, 10.4]
    out = classify_credit(_credit_db(tmp_path, m2))
    assert out["phase"].iloc[-1] == "easing"


def test_genuine_tightening_still_classifies_as_tightening(tmp_path):
    m2 = [8.0] * 12 + [7.4, 6.8, 6.2, 5.6]
    out = classify_credit(_credit_db(tmp_path, m2))
    assert out["phase"].iloc[-1] == "tightening"


# ── 7. G03b: every cached classifier must follow a DB swap ───────────────────
def _swap_dataset(db, *, tag):
    """Rewrite the SAME path with a second vintage (v2 adds one period)."""
    n = 13 if tag == "v1" else 18
    build_db(
        db,
        monthly=_monthly_rows(
            _months("2025-01-01", n), m2_yoy=[8.0] * n, cpi_yoy=[1.0] * n,
            ip_yoy=[5.0] * n, pmi_official=[51.0] * n,
        ),
        quarterly=[{"date": d, "gdp_yoy": 5.0}
                   for d in _years(2020, 5 if tag == "v1" else 6)],
        leverage=[{"date": d, "household": 60.0 if tag == "v1" else 65.0,
                   "non_fin_corp": 150.0, "gov_total": 50.0}
                  for d in _quarters("2023-01-01", 8 if tag == "v1" else 9)],
        lpr=[{"date": d, "lpr_5y": 4.0} for d in _months("2025-01-01", 14)],
        house_price=[{"date": d, "city": c, "new_mom": 100.0}
                     for d in _months("2025-01-01", 14) for c in ("北京", "上海")],
    )
    return str(db)


@pytest.mark.parametrize(
    "classifier",
    [classify_merrill, classify_credit, classify_inventory, classify_debt],
    ids=["merrill", "credit", "inventory", "debt"],
)
def test_classifier_cache_follows_db_swap(tmp_path, classifier):
    """No manual ``clear_all_caches()``: the key must carry the DB version.

    Pre-fix the key was the db_path string, so ``/api/v1/cycles/{name}`` kept
    serving the pre-swap frame until ``/api/v1/signals`` cleared these caches as
    a side effect.
    """
    db = tmp_path / "m.db"
    first = classifier(_swap_dataset(db, tag="v1"))
    n_before = len(first)

    second = classifier(_swap_dataset(db, tag="v2"))     # in-place swap, no clear
    assert len(second) > n_before, (
        f"{classifier.__name__} returned the stale cached frame after a DB swap"
    )


def test_real_estate_cache_follows_db_swap(tmp_path):
    db = tmp_path / "m.db"
    first = analyze_real_estate(_swap_dataset(db, tag="v1"))["assessment"]
    assert first["household_leverage"] == 60.0

    second = analyze_real_estate(_swap_dataset(db, tag="v2"))["assessment"]
    assert second["household_leverage"] == 65.0, (
        "real-estate assessment is stale after a DB swap"
    )


def test_cycles_and_real_estate_endpoints_follow_swap_without_signals(tmp_path, monkeypatch):
    """End-to-end: the two endpoints refresh on their own, WITHOUT /signals being
    hit first (that side-effect dependency was the reviewer-confirmed gap)."""
    from fastapi.testclient import TestClient

    from backend.app.core import db as core_db
    from backend.app.main import app

    db = tmp_path / "m.db"
    monkeypatch.setattr(core_db, "DB_PATH", Path(_swap_dataset(db, tag="v1")))
    client = TestClient(app)

    n_before = len(client.get("/api/v1/cycles/inventory").json()["series"])
    lev_before = client.get("/api/v1/real-estate").json()["assessment"]["household_leverage"]

    _swap_dataset(db, tag="v2")

    assert len(client.get("/api/v1/cycles/inventory").json()["series"]) > n_before
    lev_after = client.get("/api/v1/real-estate").json()["assessment"]["household_leverage"]
    assert lev_after != lev_before


def test_real_estate_cache_key_normalises_cities(tmp_path):
    """F15: city order/duplicates must not thrash the 8-entry cache."""
    db = _swap_dataset(tmp_path / "m.db", tag="v1")
    _analyze_real_estate_cached.cache_clear()

    analyze_real_estate(db, ["北京", "上海"])
    analyze_real_estate(db, ["上海", "北京", "北京"])

    info = _analyze_real_estate_cached.cache_info()
    assert info.misses == 1, f"cities not normalised in the cache key: {info}"
    assert info.hits == 1
