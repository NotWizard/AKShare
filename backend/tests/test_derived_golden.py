"""Golden derived-layer test — derived_monthly 派生列必须等于 02 的函数对原始表的重算。

防止 02 逻辑回归或 staging 半更新造成 raw↔derived 漂移。在 live DB 副本上跑
compute_derived（不动生产库），抽样三列覆盖三类派生形态：
m2_m1_spread（纯列算术）、real_rate（跨表 lpr−cpi）、pmi_ma6（滚动窗口）。

Run:  .venv312/bin/python -m pytest backend/tests/test_derived_golden.py -q
"""

import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.db import DB_PATH  # noqa: E402

SAMPLE_COLS = ["m2_m1_spread", "real_rate", "pmi_ma6"]
EPS = 1e-6


def _load_derived_mod():
    """Load scripts/02_compute_derived.py (digit-start name → importlib), same
    technique as _pipeline.run_derived."""
    p = Path(__file__).resolve().parents[2] / "scripts" / "02_compute_derived.py"
    spec = importlib.util.spec_from_file_location("_compute_derived_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_derived_columns_recompute_from_raw():
    if not DB_PATH.exists():
        pytest.skip("live DB absent")
    stored = pd.read_sql(
        f"SELECT date, {', '.join(SAMPLE_COLS)} FROM derived_monthly",
        sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True))
    stored["date"] = pd.to_datetime(stored["date"])

    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        shutil.copy2(DB_PATH, tmp)
        conn = sqlite3.connect(tmp)
        monthly, _ = _load_derived_mod().compute_derived(conn)
        conn.close()
    finally:
        Path(tmp).unlink(missing_ok=True)

    monthly["date"] = pd.to_datetime(monthly["date"])
    merged = stored.merge(monthly[["date"] + SAMPLE_COLS], on="date", how="left",
                          suffixes=("_stored", "_fresh"))
    assert len(merged) == len(stored) > 0
    for c in SAMPLE_COLS:
        assert np.allclose(merged[c + "_stored"], merged[c + "_fresh"],
                           atol=EPS, equal_nan=True), f"{c} drifted vs raw recompute"
