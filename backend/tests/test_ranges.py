"""TABLE_SPECS ranges gate — validate() rejects out-of-domain df, passes in-range.

口径：非空值越界比例 >10% 拒收（reason 含列名与区间）；恰 10% 通过；
NaN 不计入分母；整表量纲错（×1000）必拒。

Run:  .venv312/bin/python -m pytest backend/tests/test_ranges.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from _pipeline import validate  # noqa: E402

N = 220  # ≥ cpi.min_rows(200)


def _df(values):
    return pd.DataFrame({
        "date": pd.date_range("2008-01-01", periods=len(values), freq="MS")
                 .strftime("%Y-%m-%d"),
        "cpi_yoy": values,
    })


def test_in_range_passes():
    ok, reason = validate(_df([2.0] * N), "cpi")
    assert ok and reason == "pass"


def test_bounds_inclusive():
    # 边界值本身合法（越界判定为严格 < lo / > hi）
    ok, reason = validate(_df([-5.0, 10.0] * (N // 2)), "cpi")
    assert ok, reason


def test_15pct_outliers_rejected():
    values = [99.0] * 33 + [2.0] * (N - 33)  # 15% 越界
    ok, reason = validate(_df(values), "cpi")
    assert not ok
    assert "cpi_yoy" in reason and "[-5, 30]" in reason


def test_exactly_10pct_outliers_pass():
    values = [99.0] * 22 + [2.0] * (N - 22)  # 恰 10% → 不过线
    ok, reason = validate(_df(values), "cpi")
    assert ok, reason


def test_nan_excluded_from_ratio():
    # 非空 120 中 11 越界 = 9.2% → 通过；NaN 行只占行数、不入分母
    values = [99.0] * 11 + [2.0] * 109 + [np.nan] * 100
    ok, reason = validate(_df(values), "cpi")
    assert ok, reason


def test_whole_table_scale_error_rejected():
    ok, reason = validate(_df([2000.0] * N), "cpi")  # 单位×1000
    assert not ok and "cpi_yoy" in reason
