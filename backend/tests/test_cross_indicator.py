"""cross_indicator._best_lag_corr 方向性回归测试。

修复前 bug：lead 列被 shift(-k)（实测的是「y 领先 x」——真实 k₀ 个月领先在该
口径下变成 autocorr(k+k₀)，最大值落在 k=0，领先结构性不可报），且按 |r| 取峰
（强负相关被误报为「领先」；该半已在 signed-selection 修复中先行解决）。
本测试用确定性合成序列锁定正确语义：
  corr(lead(t), lag(t+k)) 在 k=真实领先月数 处取最大正相关。

Run:  .venv312/bin/python -m pytest backend/tests/test_cross_indicator.py -q
"""

import numpy as np
import pandas as pd

from analysis.cross_indicator import _best_lag_corr


def _smooth_wave(n=240, seed=7):
    """低噪声平滑序列（近似宏观同比的自相关结构）。"""
    rng = np.random.default_rng(seed)
    x = np.sin(np.arange(n) / 9.0) + rng.normal(0, 0.05, n)
    return pd.Series(x)


def test_detects_true_positive_lead():
    lead = _smooth_wave()
    lag = lead.shift(4).fillna(0.0)          # lag 完全复刻 lead、晚 4 个月
    best_lag, max_corr, _ = _best_lag_corr(lead, lag)
    assert best_lag == 4
    assert max_corr > 0.9


def test_zero_when_series_move_together():
    s = _smooth_wave()
    best_lag, max_corr, _ = _best_lag_corr(s, s.copy())
    assert best_lag == 0
    assert max_corr > 0.99


def test_inverse_relation_not_reported_as_lead():
    lead = _smooth_wave()
    inverse_lag = (-lead).shift(5).fillna(0.0)   # 负相关且晚 5 个月
    best_lag, max_corr, _ = _best_lag_corr(lead, inverse_lag)
    # 正向选择器：不得把强负相关当成「最佳领先」；r 必须保持符号真实
    assert max_corr < 0.5


def test_short_overlap_yields_nan_not_crash():
    a = pd.Series([1.0, 2.0, 3.0])
    b = pd.Series([1.0, 2.0, 3.0])
    best_lag, max_corr, corr_df = _best_lag_corr(a, b)
    assert best_lag == 0 and np.isnan(max_corr)
    assert len(corr_df) == 13          # 0..12 全部记录，corr 为 NaN
