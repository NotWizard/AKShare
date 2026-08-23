"""Lead-lag reporting must be sign-consistent with its own docstring (A-L2).

``analysis/cross_indicator._best_lag_corr`` documents "the lag with the highest
POSITIVE correlation" (and the frontend renders it as "M1 → PPI 领先约 N 个月
（相关 r = X）"), but pre-fix it selected with ``valid["corr"].abs().idxmax()``
while returning the SIGNED r. So a pair whose strongest relationship is INVERSE
was reported as *the* leading relationship, with a negative r glued to a "leads
by k months" label — selection and return contradicted each other.

The probe below is a 12-month sinusoid against its own mirror image, so the lag
table is r(k) = −cos(πk/6): a perfect −1.0 at lag 0 and a perfect +1.0 at lag 6.
Abs-selection therefore locks onto the −1.0 (first of the two ties) and reports
"leads by 0 months, r = −1.0"; positive selection reports the +1.0 at lag 6.

Pre-fix: ``test_inverse_pair_reports_the_positive_peak`` FAILS (r = −1.0, lag 0).
The purely-positive and no-data cases pass both before and after (no regression).

Note the statistic is full-sample / in-sample descriptive, not a real-time
signal, and ``signals.py`` only surfaces it as ``cross_lags`` display data.

Run:  cd backend && ../.venv312/bin/python -m pytest tests/test_cross_lag_semantics.py -q
Deterministic, no network, no DB.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from analysis.cross_indicator import _best_lag_corr  # noqa: E402

_N = 120  # 10 years of monthly points — well past the 24-observation floor


def _cycle(period: int = 12, n: int = _N) -> pd.Series:
    """Clean sinusoid, `period` months per cycle."""
    return pd.Series(np.sin(2 * np.pi * np.arange(n) / period))


def test_inverse_pair_reports_the_positive_peak():
    """Strongest |r| is negative → the reported (lag, r) must be the positive peak."""
    x = _cycle()
    y = -x                     # perfectly anti-phase: r(0) = −1, r(6) = +1

    lag, r, table = _best_lag_corr(x, y)

    # The trap: abs-selection would have picked the −1.0 at lag 0.
    abs_pick = table.loc[table["corr"].abs().idxmax()]
    assert int(abs_pick["lag"]) == 0
    assert abs_pick["corr"] == pytest.approx(-1.0)

    # Post-fix: selection follows the documented direction …
    assert r > 0, "a negative r must never be reported as the leading relationship"
    assert r == pytest.approx(table["corr"].max())
    assert lag == 6                                   # half of the 12-month cycle
    # … and the returned r is exactly the table entry for the returned lag.
    assert r == pytest.approx(float(table.loc[table["lag"] == lag, "corr"].iloc[0]))


def test_positive_pair_unchanged():
    """No regression for the ordinary case: the positive peak was already picked."""
    x = _cycle()
    y = x.shift(-3)            # peak at lag 3 under this module's alignment

    lag, r, table = _best_lag_corr(x, y)

    assert lag == 3
    assert r == pytest.approx(1.0)
    assert r == pytest.approx(table["corr"].max())


def test_full_lag_table_is_signed_and_complete():
    """corr_df keeps every lag with its sign — the caller can still see inverses."""
    x = _cycle()
    _, _, table = _best_lag_corr(x, -x, max_lag=12)

    assert list(table["lag"]) == list(range(13))
    assert table["corr"].min() < 0 < table["corr"].max()


def test_too_short_sample_returns_nan_not_a_lag():
    """< 24 aligned observations at every lag → (0, nan), never a fake best lag."""
    short = pd.Series(np.arange(10, dtype=float))

    lag, r, table = _best_lag_corr(short, short)

    assert lag == 0
    assert np.isnan(r)
    assert table["corr"].isna().all()
