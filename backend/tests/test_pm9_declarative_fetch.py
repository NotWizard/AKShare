"""P-M9 declarative-fetcher behaviour preservation (G26).

`scripts/01_fetch_data.py` collapsed ~7 copy-pasted fetcher bodies into a
declarative ``FETCH_SPECS`` table (scripts/_specs.py) + one generic
fetch/rename/coerce/persist loop. This is a REFACTOR: the table-driven path must
produce a byte-identical frame to the old bespoke code for the same raw input.

Each test embeds the ORIGINAL inline logic (date parser + per-column
pd.to_numeric + dropna/sort/reset) and asserts the generic ``_build_spec_frame``
— and the generated ``fetch_<name>`` end-to-end — yields an identical DataFrame.
A wrong column mapping / parser in the spec would make these fail.

Run:  .venv312/bin/python -m pytest backend/tests/test_pm9_declarative_fetch.py -q
"""

import importlib.util
import re
import sqlite3
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import _specs as S  # noqa: E402


def _load_fetch_module():
    """scripts/01_fetch_data.py under its own name; stub akshare (heavy import)."""
    sys.modules.setdefault("akshare", types.ModuleType("akshare"))
    spec = importlib.util.spec_from_file_location(
        "_fetch_data_pm9_test", SCRIPTS / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── raw akshare-shaped fixtures (Chinese column names, out of order + a junk row) ─
def _raw_money_supply():
    return pd.DataFrame({
        # deliberately unsorted + one unparseable date ("2026年6月" has no ".")
        "统计时间": ["2026.3", "2026.1", "2026.2", "坏数据"],
        "货币和准货币（广义货币M2）": ["300.1", "298.0", 299.5, "1.0"],
        "货币和准货币（广义货币M2）同比增长": [8.1, 8.3, "8.2", None],
        "货币(狭义货币M1)": [10.0, 10.1, 10.2, 10.3],
        "货币(狭义货币M1)同比增长": [1.1, 1.2, 1.3, 1.4],
        "流通中现金(M0)": [5.0, 5.1, 5.2, 5.3],
        "流通中现金(M0)同比增长": [2.1, 2.2, 2.3, 2.4],
        "活期存款": [50.0, 51.0, 52.0, 53.0],
        "定期存款": [60.0, 61.0, 62.0, 63.0],
        "储蓄存款": [70.0, 71.0, 72.0, 73.0],
    })


def _old_money_supply(df):
    def parse_date(s):
        parts = str(s).split(".")
        if len(parts) == 2:
            return f"{parts[0]}-{int(parts[1]):02d}-01"
        return None
    result = pd.DataFrame({
        "date": [parse_date(x) for x in df["统计时间"]],
        "m2": pd.to_numeric(df["货币和准货币（广义货币M2）"], errors="coerce"),
        "m2_yoy": pd.to_numeric(df["货币和准货币（广义货币M2）同比增长"], errors="coerce"),
        "m1": pd.to_numeric(df["货币(狭义货币M1)"], errors="coerce"),
        "m1_yoy": pd.to_numeric(df["货币(狭义货币M1)同比增长"], errors="coerce"),
        "m0": pd.to_numeric(df["流通中现金(M0)"], errors="coerce"),
        "m0_yoy": pd.to_numeric(df["流通中现金(M0)同比增长"], errors="coerce"),
        "demand_deposit": pd.to_numeric(df.get("活期存款", pd.Series()), errors="coerce"),
        "time_deposit": pd.to_numeric(df.get("定期存款", pd.Series()), errors="coerce"),
        "savings": pd.to_numeric(df.get("储蓄存款", pd.Series()), errors="coerce"),
    })
    return result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _raw_gdp():
    return pd.DataFrame({
        "季度": ["2024年第4季度", "2024年第1季度", "2026年第1-2季度", "无效"],
        "国内生产总值-绝对值": [100.0, 25.0, 60.0, 1.0],
        "国内生产总值-同比增长": [5.0, 5.3, 5.1, 4.0],
        "第一产业-绝对值": [10.0, 2.0, 6.0, 0.1],
        "第二产业-绝对值": [40.0, 10.0, 24.0, 0.4],
        "第三产业-绝对值": [50.0, 13.0, 30.0, 0.5],
    })


def _old_gdp(df):
    def parse_quarter(s):
        m = re.match(r"(\d{4})年第(\d)(?:-(\d))?季度", str(s))
        if m:
            year = int(m.group(1))
            q = int(m.group(3) or m.group(2))
            month = (q - 1) * 3 + 1
            return f"{year}-{month:02d}-01"
        return None
    result = pd.DataFrame({
        "date": [parse_quarter(x) for x in df["季度"]],
        "gdp_abs": pd.to_numeric(df["国内生产总值-绝对值"], errors="coerce"),
        "gdp_yoy": pd.to_numeric(df["国内生产总值-同比增长"], errors="coerce"),
        "gdp_primary": pd.to_numeric(df.get("第一产业-绝对值", pd.Series()), errors="coerce"),
        "gdp_secondary": pd.to_numeric(df.get("第二产业-绝对值", pd.Series()), errors="coerce"),
        "gdp_tertiary": pd.to_numeric(df.get("第三产业-绝对值", pd.Series()), errors="coerce"),
    })
    return result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _raw_industrial():
    return pd.DataFrame({
        "月份": ["2008年03月份", "2008年02月份", "2008年12月份", "坏"],
        "同比增长": [6.6, 5.4, "7.1", None],
        "累计增长": [6.0, 5.0, 7.0, 1.0],
    })


def _old_industrial(df):
    def parse_month(s):
        m = re.match(r"(\d{4})年(\d{2})月份", str(s))
        if m:
            return f"{m.group(1)}-{m.group(2)}-01"
        return None
    result = pd.DataFrame({
        "date": [parse_month(x) for x in df["月份"]],
        "ip_yoy": pd.to_numeric(df["同比增长"], errors="coerce"),
        "ip_cumulative": pd.to_numeric(df["累计增长"], errors="coerce"),
    })
    return result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _raw_new_credit():
    return pd.DataFrame({
        "月份": ["2026年5月份", "2026年11月", "2026年1月份", "坏"],
        "当月": [1000.0, "2000", 3000.0, None],
    })


def _old_new_credit(df):
    def parse_month(s):
        m = re.match(r"(\d{4})年(\d{1,2})月", str(s))
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-01"
        return None
    result = pd.DataFrame({
        "date": [parse_month(x) for x in df["月份"]],
        "new_rmb_loan": pd.to_numeric(df["当月"], errors="coerce"),
    })
    return result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


CASES = {
    "money_supply": (_raw_money_supply, _old_money_supply, "macro_china_supply_of_money"),
    "gdp": (_raw_gdp, _old_gdp, "macro_china_gdp"),
    "industrial": (_raw_industrial, _old_industrial, "macro_china_gyzjz"),
    "new_credit": (_raw_new_credit, _old_new_credit, "macro_china_new_financial_credit"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_build_spec_frame_matches_old_inline_body(name):
    """The generic builder reproduces the old bespoke frame byte-for-byte."""
    mod = _load_fetch_module()
    raw_fn, old_fn, _ = CASES[name]
    raw = raw_fn()
    got = mod._build_spec_frame(raw.copy(), S.FETCH_SPECS[name])
    want = old_fn(raw.copy())
    pd.testing.assert_frame_equal(got, want)


@pytest.mark.parametrize("name", list(CASES))
def test_generated_fetcher_end_to_end_matches_old(tmp_path, name):
    """fetch_<name> (generic runner + save_to_db) returns the same frame the old
    bespoke fetcher would have, and records it as updated in the manifest."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    raw_fn, old_fn, api = CASES[name]
    raw = raw_fn()
    setattr(mod.ak, api, lambda *a, **k: raw.copy())

    conn = sqlite3.connect(tmp_path / f"{name}.db")
    got = getattr(mod, f"fetch_{name}")(conn)
    conn.close()

    pd.testing.assert_frame_equal(got, old_fn(raw.copy()))


def test_new_credit_swallows_source_error_like_the_old_body(tmp_path):
    """The old fetch_new_credit wrapped the fetch in try/except → empty frame →
    gate records kept_previous (retryable). The declarative version preserves it
    via swallow_errors, unlike money_supply/gdp which let the exception propagate."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})

    def boom(*a, **k):
        raise ConnectionError("source down")
    mod.ak.macro_china_new_financial_credit = boom

    conn = sqlite3.connect(tmp_path / "nc.db")
    out = mod.fetch_new_credit(conn)     # must NOT raise
    conn.close()
    assert out.empty
    assert mod._MANIFEST["tables"]["new_credit"]["status"] == "kept_previous"

    # contrast: money_supply has no swallow → the error propagates to run_fetcher
    mod.ak.macro_china_supply_of_money = boom
    with pytest.raises(ConnectionError):
        mod.fetch_money_supply(sqlite3.connect(tmp_path / "ms.db"))
