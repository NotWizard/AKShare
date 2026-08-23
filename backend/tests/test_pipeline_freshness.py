"""Ingestion freshness + dtype gate (G26 / P-M7) — catch a source that every
other gate waves through.

Two silent-but-wrong failure modes the row-count / range / grain gates miss:

  * FROZEN source: the fetcher keeps returning perfectly valid rows that simply
    stop advancing (an upstream cache/API freezes on some old month). min_rows,
    ranges and uniqueness all pass, so the stale snapshot overwrote the good one
    every run and the dashboard silently showed month-old data as current. The
    ``max_date_lag`` gate rejects a fetch whose newest date is too far behind
    ``today``.
  * RESHAPED source: a required numeric column arrives as strings ("5.0%",
    thousands separators, a unit suffix) because the source changed format. The
    fetcher's pd.to_numeric was skipped/renamed and the column lands as object
    dtype; every downstream pd.to_numeric then silently NaN-s it. The dtype gate
    rejects a non-numeric required column.

Everything runs on synthetic frames / temp files — the live DB is never opened.

Run:  .venv312/bin/python -m pytest backend/tests/test_pipeline_freshness.py -q
"""

import importlib.util
import sqlite3
import sys
import types
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import _pipeline as P  # noqa: E402

TODAY = date(2026, 8, 23)


def _series(col="ppi_yoy", newest="2026-07-01", n=220):
    """A frame that clears every OTHER gate: unique daily dates ending exactly at
    ``newest`` (so the freshness lag is exact), enough rows, in-range values."""
    dates = pd.date_range(end=pd.Timestamp(newest), periods=n, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, col: [1.0 + (i % 10) * 0.1 for i in range(n)]})


# ── P-M7 freshness ────────────────────────────────────────────────────────────
def test_recent_monthly_fetch_passes():
    ok, reason = P.validate(_series(newest="2026-07-01"), "ppi", today=TODAY)
    assert ok, reason


def test_frozen_source_is_rejected():
    """THE P-M7 BUG. Every value is in range, dates are unique and above
    min_rows — the only defect is that the newest date is ~14 months old because
    the source froze. Pre-fix nothing looked at the calendar, so the stale
    snapshot replaced the good table under a status="updated" manifest entry."""
    ok, reason = P.validate(_series(newest="2025-06-01"), "ppi", today=TODAY)
    assert not ok
    assert "max_date_lag" in reason and "stale" in reason


def test_freshness_boundary_rejects_one_day_past_the_limit():
    """The limit itself is fresh; one day older is stale."""
    lag = P.TABLE_SPECS["ppi"]["max_date_lag"]
    at = pd.Timestamp(TODAY) - pd.Timedelta(days=lag)
    over = pd.Timestamp(TODAY) - pd.Timedelta(days=lag + 1)
    assert P.validate(_series(newest=at), "ppi", today=TODAY)[0]
    assert not P.validate(_series(newest=over), "ppi", today=TODAY)[0]


def test_future_dated_fetch_never_false_rejects():
    assert P.validate(_series(newest="2030-01-01"), "ppi", today=TODAY)[0]


def test_table_without_max_date_lag_is_exempt():
    """Annual / naturally-sparse tables legitimately lag a year+, so they omit
    max_date_lag and must never be freshness-rejected. money_supply carries no
    max_date_lag: a 2020-vintage frame still passes on a 2026 clock."""
    ok, reason = P.validate(_series("m2_yoy", newest="2020-01-01", n=500), "money_supply",
                            today=TODAY)
    assert ok, reason


# ── P-M7 dtype ────────────────────────────────────────────────────────────────
def test_required_string_column_is_rejected():
    """A numeric required column that arrived as strings (source reshaped) is
    rejected instead of being stored as object dtype that silently NaN-s."""
    reshaped = _series(newest="2026-07-01")
    reshaped["ppi_yoy"] = reshaped["ppi_yoy"].astype(str)
    ok, reason = P.validate(reshaped, "ppi", today=TODAY)
    assert not ok
    assert "ppi_yoy" in reason and "numeric" in reason


def test_numeric_with_some_nans_still_passes_dtype():
    """A genuine float column with holes is numeric — only a non-numeric dtype
    is rejected, not sparsity."""
    holed = _series(newest="2026-07-01")
    holed.loc[holed.index[:50], "ppi_yoy"] = float("nan")
    assert P.validate(holed, "ppi", today=TODAY)[0]


# ── integration: the gate feeds save_to_db's kept_previous path ───────────────
def _load_fetch_module():
    """scripts/01_fetch_data.py under its own name; stub akshare (heavy import,
    unused here) — same technique as test_pipeline_guards."""
    sys.modules.setdefault("akshare", types.ModuleType("akshare"))
    spec = importlib.util.spec_from_file_location(
        "_fetch_data_freshness_test", SCRIPTS / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stale_fetch_keeps_previous_via_save_to_db(tmp_path):
    """End-to-end: a frozen-source frame (newest 2020, unambiguously stale on any
    plausible clock) must be rejected by save_to_db and recorded as
    kept_previous — bad data never overwrites the good staging table."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    conn = sqlite3.connect(tmp_path / "s.db")

    mod.save_to_db(_series(newest="2020-01-01"), "ppi", conn)
    conn.commit()

    entry = mod._MANIFEST["tables"]["ppi"]
    assert entry["status"] == "kept_previous"
    assert "stale" in entry["reason"]
    # the stale frame must not have landed in the DB
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "ppi" not in tables
    conn.close()
