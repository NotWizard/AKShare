"""Derived-calculation口径 (G20) — no partial windows, no row-offset "YoY", no look-ahead.

Every case here is a number that used to LOOK real:

  * P-M1 ``rolling(12, min_periods=1).sum()`` then ``pct_change(12)`` divided a
    12-month sum by a 1-month value, so the head of ``sf_stock_yoy`` was a few
    hundred percent (720.4 / 377.7 / 274.8 on the live data) presented as YoY.
  * P-M2 ``pct_change(12)`` / ``shift(12)`` / ``shift(4)`` are ROW offsets on a
    frame that was only ``sort_values("date")`` — one missing month or quarter
    silently turned a 12-month change into an 11/13-month one.
  * P-M4 annual household income is stamped ``YYYY-01-01`` but published the
    FOLLOWING January, so ``merge_asof(direction="backward")`` back-filled it
    into that same year → ~12 months of look-ahead in ``hh_debt_to_income`` /
    ``hh_income_share``.

All frames are synthetic and every DB is a tmp file — the live DB is never opened.

Run:  .venv312/bin/python -m pytest backend/tests/test_derived_calc.py -q
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _derived_mod():
    """Load scripts/02_compute_derived.py (digit-start name → importlib), same
    technique as _pipeline.run_derived."""
    spec = importlib.util.spec_from_file_location(
        "_compute_derived_calc_test", ROOT / "scripts" / "02_compute_derived.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(db, **tables):
    conn = sqlite3.connect(db)
    for name, df in tables.items():
        df.to_sql(name, conn, if_exists="replace", index=False)
    conn.commit()
    monthly, quarterly = _derived_mod().compute_derived(conn)
    conn.close()
    return monthly, quarterly


# ── synthetic raw tables ─────────────────────────────────────────────────────
def _money(n, start="2015-01-01"):
    """money_supply is the monthly anchor; values are irrelevant here."""
    d = pd.date_range(start, periods=n, freq="MS")
    return pd.DataFrame({"date": d.strftime("%Y-%m-01"), "m1": 1.0, "m1_yoy": 5.0,
                         "m2": 2.0, "m2_yoy": 9.0, "m0": 0.5, "m0_yoy": 3.0})


def _social(n, start="2015-01-01", drop=()):
    """Strictly increasing, all-distinct totals so a misaligned window is visible."""
    d = pd.date_range(start, periods=n, freq="MS")
    df = pd.DataFrame({"date": d.strftime("%Y-%m-01"),
                       "total": [1000.0 + i * i for i in range(n)],
                       "rmb_loan": [500.0 + i for i in range(n)]})
    return df.drop(index=list(drop)).reset_index(drop=True)


def _leverage(quarters):
    return pd.DataFrame({
        "date": quarters,
        "household": [50.0 + i for i in range(len(quarters))],
        "non_fin_corp": [150.0 + i for i in range(len(quarters))],
        "gov_total": [40.0 + i for i in range(len(quarters))],
        "gov_central": [20.0] * len(quarters),
        "gov_local": [20.0] * len(quarters),
        "real_economy": [240.0 + i for i in range(len(quarters))],
    })


def _gdp(years):
    return pd.DataFrame({"date": [f"{y}-01-01" for y in years],
                         "gdp_abs": [250000.0 + 10000.0 * i for i in range(len(years))],
                         "gdp_yoy": [5.0 + 0.1 * i for i in range(len(years))]})


def _hh_income(income_by_year, with_available_from=True):
    df = pd.DataFrame({"date": [f"{y}-01-01" for y in sorted(income_by_year)],
                       "income_per_capita": [30000.0] * len(income_by_year),
                       "population_10k": [140000.0] * len(income_by_year),
                       "income_abs": [income_by_year[y] for y in sorted(income_by_year)]})
    if with_available_from:
        # what fetch_household_income now stamps: reference year Y is published
        # with the following January's NBS release
        df["available_from"] = [f"{y + 1}-01-01" for y in sorted(income_by_year)]
    return df


QUARTERS = [f"{y}-{m:02d}-01" for y in (2019, 2020, 2021, 2022) for m in (3, 6, 9, 12)]


# ── P-M1: a partial rolling window may not masquerade as a YoY ────────────────
def test_sf_stock_yoy_head_is_nan_not_a_bogus_number(tmp_path):
    """min_periods=12: the 12-month stock estimate needs a FULL year before any
    YoY can be taken from it. Pre-fix (min_periods=1) row 12 was
    (12-month sum ÷ 1-month value − 1)×100 → hundreds of percent, plotted as a
    real credit-growth number."""
    n = 36
    sf = _social(n)
    monthly, _ = _run(tmp_path / "d.db", money_supply=_money(n), social_finance=sf)
    got = monthly["sf_stock_yoy"]

    # 12 months to fill the window + 12 more before a YoY exists → rows 0..22 NaN
    assert got.head(23).isna().all()
    assert pd.isna(got.iloc[12]), "row 12 is the pre-fix bogus value (was ~+300%)"

    tot = sf["total"]
    expected = (tot[12:24].sum() / tot[0:12].sum() - 1) * 100
    assert got.iloc[23] == pytest.approx(expected)


def test_loan_stock_yoy_head_is_nan_too(tmp_path):
    """new_credit carries the identical construct — fixed the same way."""
    n = 30
    nc = pd.DataFrame({"date": pd.date_range("2015-01-01", periods=n, freq="MS").strftime("%Y-%m-01"),
                       "new_rmb_loan": [800.0 + i * i for i in range(n)]})
    monthly, _ = _run(tmp_path / "d.db", money_supply=_money(n), new_credit=nc)
    assert monthly["loan_stock_yoy"].head(23).isna().all()
    expected = (nc["new_rmb_loan"][12:24].sum() / nc["new_rmb_loan"][0:12].sum() - 1) * 100
    assert monthly["loan_stock_yoy"].iloc[23] == pytest.approx(expected)


# ── P-M2: 12 months means 12 CALENDAR months ─────────────────────────────────
def test_missing_month_yields_a_true_12_calendar_month_change(tmp_path):
    """With month 18 absent from social_finance, a row offset of 12 lands on
    month 17 — a wrong number that looks perfectly plausible. On a calendar
    index the missing partner propagates as NaN instead."""
    n = 40
    gap = 18
    full = _social(n)
    dates, totals = full["date"].tolist(), dict(zip(full["date"], full["total"]))
    monthly, _ = _run(tmp_path / "d.db", money_supply=_money(n),
                      social_finance=_social(n, drop=[gap]))
    got = monthly.set_index("date")["sf_impulse"]

    # month 30 − month 18: the partner is missing → NaN (pre-fix: month 17 value)
    assert pd.isna(got[dates[30]])
    # month 29 − month 17: both present → exact 12-calendar-month difference
    assert got[dates[29]] == pytest.approx(totals[dates[29]] - totals[dates[17]])
    # and specifically NOT the row-offset answer the old code produced
    assert got[dates[29]] != pytest.approx(totals[dates[29]] - totals[dates[16]])


def test_leverage_year_change_uses_four_calendar_quarters(tmp_path):
    """Same defect on the quarterly frame: household_change = current − 4
    QUARTERS ago, not current − 4 rows ago."""
    quarters = [q for q in QUARTERS if q != "2020-09-01"]
    lev = _leverage(quarters)
    hh = dict(zip(lev["date"], lev["household"]))
    _, q = _run(tmp_path / "d.db", money_supply=_money(24, "2019-01-01"), leverage=lev)
    got = q.set_index("date")["household_change"]

    # 2021Q3 − 2020Q3: partner missing → NaN (pre-fix: 4 rows back = 2020Q2)
    assert pd.isna(got["2021-09-01"])
    assert got["2021-12-01"] == pytest.approx(hh["2021-12-01"] - hh["2020-12-01"])
    assert got["2021-12-01"] != pytest.approx(hh["2021-12-01"] - hh["2020-06-01"])


# ── P-M4: no value may be read before it existed ─────────────────────────────
INCOME = {2019: 40000.0, 2020: 44000.0, 2021: 48000.0}


def test_annual_income_is_not_readable_before_its_publication_date(tmp_path):
    """Reference year Y is published in January Y+1, so no quarter OF year Y may
    carry it. Pre-fix merge_asof(on="date", backward) matched 2020-01-01 into
    2020-03-01 → ~12 months of look-ahead straight into hh_debt_to_income."""
    _, q = _run(tmp_path / "d.db", money_supply=_money(48, "2019-01-01"),
                leverage=_leverage(QUARTERS), gdp=_gdp([2019, 2020, 2021, 2022]),
                household_income=_hh_income(INCOME))
    got = q.set_index("date")["income_abs"]

    for m in (3, 6, 9, 12):
        assert got[f"2020-{m:02d}-01"] == pytest.approx(INCOME[2019])   # not 2020's
        assert got[f"2021-{m:02d}-01"] == pytest.approx(INCOME[2020])
        assert got[f"2022-{m:02d}-01"] == pytest.approx(INCOME[2021])
        # 2018 was never published in this fixture → nothing to show in 2019
        assert pd.isna(got[f"2019-{m:02d}-01"])
    # the look-ahead must not survive anywhere downstream either
    ratio = q.set_index("date")["hh_debt_to_income"]
    assert ratio["2019-03-01"] != ratio["2019-03-01"] or pd.isna(ratio["2019-03-01"])
    assert pd.notna(ratio["2020-03-01"])


def test_annual_income_lag_holds_for_tables_without_available_from(tmp_path):
    """Back-compat: the live household_income table predates the availability
    column, so the same one-year lag must be inferred from the reference year."""
    _, q = _run(tmp_path / "d.db", money_supply=_money(48, "2019-01-01"),
                leverage=_leverage(QUARTERS), gdp=_gdp([2019, 2020, 2021, 2022]),
                household_income=_hh_income(INCOME, with_available_from=False))
    got = q.set_index("date")["income_abs"]
    assert got["2020-06-01"] == pytest.approx(INCOME[2019])
    assert got["2021-06-01"] == pytest.approx(INCOME[2020])
    assert pd.isna(got["2019-06-01"])


def test_derived_quarterly_schema_is_unchanged_by_the_asof_join(tmp_path):
    """The availability key is a join helper, not a column of the output — the
    frontend reads derived_quarterly directly."""
    _, q = _run(tmp_path / "d.db", money_supply=_money(48, "2019-01-01"),
                leverage=_leverage(QUARTERS), gdp=_gdp([2019, 2020, 2021, 2022]),
                household_income=_hh_income(INCOME))
    assert "_asof" not in q.columns and "available_from" not in q.columns
    assert {"income_abs", "hh_debt_abs", "hh_income_share", "hh_debt_to_income"} <= set(q.columns)
