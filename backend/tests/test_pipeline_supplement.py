"""NIFD leverage supplement (G26 / P-M8) — one source of truth, and 03 goes
through the validated staging swap instead of raw-writing the live DB.

Two defects this locks down:

  * DOUBLE COPY: the NIFD quarterly-leverage table lived in BOTH
    01_fetch_data.py and 03_supplement_leverage.py as separate literals, kept in
    sync by hand. They are now a single module (nifd_leverage) both consumers
    import, so they can never drift.
  * 03 WROTE LIVE DIRECTLY: the old supplement() did sqlite3.connect(live) +
    INSERT INTO leverage + commit — bypassing validate() (could write duplicate
    dates / out-of-range values), the UNIQUE index (to_sql/replace elsewhere left
    it index-less), the backup + vintage snapshot + atomic swap, AND the derived
    recompute (raw leverage advanced while derived_quarterly stayed stale — the
    P-M6 inconsistency). It now runs the same staged path as the main pipeline:
    copy live→staging, gated write, enforce_indexes, run_derived, atomic swap;
    any failure discards staging and leaves the live DB byte-identical.

Everything runs on temp files; run_derived is stubbed (its own inputs are tested
elsewhere) — the live DB is never opened.

Run:  .venv312/bin/python -m pytest backend/tests/test_pipeline_supplement.py -q
"""

import importlib.util
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

import nifd_leverage  # noqa: E402

# 2013Q1..2024Q4 quarter-end month-starts (48 rows ≥ leverage.min_rows=40), all
# strictly before the 2025+ NIFD dates → a clean run supplements exactly 6 rows.
QDATES = [f"{y}-{m:02d}-01" for y in range(2013, 2025) for m in (3, 6, 9, 12)]


def _load_03():
    spec = importlib.util.spec_from_file_location(
        "_supp_leverage_test", SCRIPTS / "03_supplement_leverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_01():
    """01 imports akshare at top level; stub it (unused here)."""
    sys.modules.setdefault("akshare", types.ModuleType("akshare"))
    spec = importlib.util.spec_from_file_location(
        "_fetch_supp_test", SCRIPTS / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_live(path, dates):
    """A CNBS-shaped leverage table like fetch_leverage writes (no index yet —
    to_sql, exactly the live-DB starting condition)."""
    conn = sqlite3.connect(path)
    pd.DataFrame({
        "date": list(dates),
        "household": [60.0] * len(dates), "non_fin_corp": [170.0] * len(dates),
        "gov_total": [60.0] * len(dates), "gov_central": [25.0] * len(dates),
        "gov_local": [35.0] * len(dates), "real_economy": [290.0] * len(dates),
        "fin_asset": [50.0] * len(dates), "fin_liability": [69.0] * len(dates),
    }).to_sql("leverage", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


def _paths(tmp_path):
    return dict(db_path=tmp_path / "macro.db", staging_path=tmp_path / "macro.db.staging",
                backup_dir=tmp_path / "backups", vintage_dir=tmp_path / "vintages")


# ── P-M8: single source of truth ─────────────────────────────────────────────
def test_nifd_data_is_a_single_source_shared_by_01_and_03():
    """THE P-M8 DOUBLE-COPY BUG. 01 and 03 must reference the SAME nifd module
    function object; neither may keep its own literal."""
    canon = nifd_leverage.nifd_supplement_df
    mod03, mod01 = _load_03(), _load_01()
    assert getattr(mod03, "nifd_supplement_df", None) is canon
    assert getattr(mod01, "nifd_supplement_df", None) is canon
    assert not hasattr(mod01, "_NIFD_DATA")      # old per-file literal is gone
    df = canon()
    assert list(df.columns) == nifd_leverage.COLUMNS
    assert len(df) == len(nifd_leverage.NIFD_DATA) == 6


# ── P-M8: 03 goes through the validated staging swap ──────────────────────────
def test_supplement_goes_through_staging_indexes_and_recomputes_derived(tmp_path, monkeypatch):
    """THE P-M8 DIRECT-WRITE BUG. A clean run must (a) recompute derived on
    staging, (b) land the new rows in live only via the atomic swap, and (c)
    leave a real UNIQUE index on leverage — the old raw INSERT did none of these."""
    mod = _load_03()
    p = _paths(tmp_path)
    _seed_live(p["db_path"], QDATES)

    calls = []
    def spy_derived(conn):
        calls.append("derived")   # proves raw+derived stay atomic on staging
        pd.DataFrame({"date": ["2099-01-01"], "sentinel": [1.0]}).to_sql(
            "derived_quarterly", conn, if_exists="replace", index=False)
    monkeypatch.setattr(mod, "run_derived", spy_derived)

    n = mod.supplement(**p)

    assert n == 6
    assert calls == ["derived"]
    assert not p["staging_path"].exists()        # consumed by the atomic swap

    conn = sqlite3.connect(p["db_path"])
    lev = set(pd.read_sql("SELECT date FROM leverage", conn)["date"])
    assert {"2025-03-01", "2026-06-01"} <= lev
    assert len(lev) == len(QDATES) + 6
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='leverage'")}
    assert "ux_leverage_date" in idx
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO leverage (date, household) VALUES ('2026-06-01', 1.0)")
    # the derived recompute ran on staging and its output rode the swap into live
    assert pd.read_sql("SELECT * FROM derived_quarterly", conn)["sentinel"].iloc[0] == 1.0
    conn.close()


def test_derived_failure_discards_staging_and_leaves_live_untouched(tmp_path, monkeypatch):
    """A failure anywhere in the staged run must keep the last consistent snapshot:
    live byte-identical, staging removed."""
    mod = _load_03()
    p = _paths(tmp_path)
    _seed_live(p["db_path"], QDATES)
    before = Path(p["db_path"]).read_bytes()
    monkeypatch.setattr(mod, "run_derived",
                        lambda conn: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        mod.supplement(**p)

    assert Path(p["db_path"]).read_bytes() == before
    assert not p["staging_path"].exists()


def test_gate_rejection_aborts_without_touching_live(tmp_path, monkeypatch):
    """The supplement is now subject to validate(): a rejection raises and the
    live DB is never touched (the old direct INSERT had no gate at all)."""
    mod = _load_03()
    p = _paths(tmp_path)
    _seed_live(p["db_path"], QDATES)
    before = Path(p["db_path"]).read_bytes()
    monkeypatch.setattr(mod, "validate", lambda *a, **k: (False, "forced test reject"))
    monkeypatch.setattr(mod, "run_derived", lambda conn: pytest.fail("must not recompute"))

    with pytest.raises(ValueError, match="拒收"):
        mod.supplement(**p)

    assert Path(p["db_path"]).read_bytes() == before
    assert not p["staging_path"].exists()


def test_noop_when_all_nifd_dates_already_present(tmp_path, monkeypatch):
    """Nothing to add → no commit, no swap, no derived recompute (never write an
    empty/unchanged snapshot as if a run had landed)."""
    mod = _load_03()
    p = _paths(tmp_path)
    _seed_live(p["db_path"], QDATES + [d[0] for d in nifd_leverage.NIFD_DATA])
    before = Path(p["db_path"]).read_bytes()
    spy = []
    monkeypatch.setattr(mod, "run_derived", lambda conn: spy.append(1))

    n = mod.supplement(**p)

    assert n == 0 and spy == []
    assert Path(p["db_path"]).read_bytes() == before
    assert not p["staging_path"].exists()


def test_missing_live_db_raises_clearly(tmp_path):
    mod = _load_03()
    with pytest.raises(FileNotFoundError):
        mod.supplement(**_paths(tmp_path))   # db_path does not exist yet
