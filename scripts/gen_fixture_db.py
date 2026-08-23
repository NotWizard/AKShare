#!/usr/bin/env python3
"""Generate the committed test-fixture SQLite DBs (G16).

Several backend tests read the real ``data/macro_data.db`` / ``data/crcl_monitor.db``
(``shutil.copy2`` a temp copy, or skip when the file is absent). CI has no real
DB, so those tests could not run there. This script builds two SMALL,
schema-faithful fixture DBs under ``backend/tests/fixtures/`` that
``backend/tests/conftest.py`` seeds into ``data/`` when the real files are absent.

Design choices that make the fixtures trustworthy:
  * The macro fixture's RAW tables are SYNTHESISED (no real data leaks into the
    repo) with the exact columns ``scripts/02_compute_derived.py`` requires, then
    the REAL ``compute_derived`` is run to produce ``derived_monthly`` /
    ``derived_quarterly``. So the derived layer is consistent with the raw layer
    BY CONSTRUCTION — ``test_derived_golden`` (raw→derived recompute) passes on
    the fixture exactly as it does on the live DB.
  * ~36 monthly / 12 quarterly / 7 annual rows: enough that all four cycle
    classifiers produce a real phase (so ``compute_signals`` has a non-null
    ``as_of``), while the file stays a few KB.
  * The CRCL fixture is built through ``crcl_db.ensure_schema`` (the ONE authoritative
    DDL) plus a couple of rows, then normalised back to a rollback journal so the
    committed file is a single artefact with no ``-wal``/``-shm`` sidecars.

Deterministic: no randomness, no wall-clock — re-running produces byte-stable
tables (SQLite page layout aside). Regenerate with:

    .venv312/bin/python scripts/gen_fixture_db.py
"""

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(HERE))          # so compute_derived can `import _pipeline`
sys.path.insert(0, str(PROJECT_ROOT))  # so `import backend...` resolves

FIXTURES_DIR = PROJECT_ROOT / "backend" / "tests" / "fixtures"
MACRO_FIXTURE = FIXTURES_DIR / "macro_data.db"
CRCL_FIXTURE = FIXTURES_DIR / "crcl_monitor.db"


def _load_compute_derived():
    """Load scripts/02_compute_derived.py (digit-start name → importlib)."""
    spec = importlib.util.spec_from_file_location(
        "_compute_derived_fixture", HERE / "02_compute_derived.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _months(start, n):
    return list(pd.date_range(start, periods=n, freq="MS").strftime("%Y-%m-%d"))


def _quarters(start, n):
    return list(pd.date_range(start, periods=n, freq="QS").strftime("%Y-%m-%d"))


def _series(base, step, n):
    """A gently trending series [base, base+step, …] — realistic-looking, no noise."""
    return [round(base + step * i, 3) for i in range(n)]


def _write_raw_tables(conn):
    """Synthesise the raw source tables with exactly the columns compute_derived reads."""
    n = 36
    m = _months("2023-01-01", n)

    money_supply = pd.DataFrame({
        "date": m,
        "m1": _series(60.0, 0.2, n),
        "m1_yoy": _series(3.0, 0.05, n),        # rising → widening spread
        "m2": _series(280.0, 1.0, n),
        "m2_yoy": _series(8.0, 0.02, n),        # sustained easing bias
        "m0": _series(9.0, 0.03, n),
        "m0_yoy": _series(9.0, 0.04, n),
    })
    cpi = pd.DataFrame({
        "date": m,
        "cpi_yoy": _series(1.0, 0.01, n),       # low inflation
        "cpi_mom": _series(0.1, 0.0, n),
    })
    ppi = pd.DataFrame({
        "date": m,
        "ppi_yoy": _series(-1.0, 0.05, n),
        "ppi_mom": _series(0.0, 0.0, n),
    })
    pmi = pd.DataFrame({
        "date": m,
        "pmi_official": _series(50.5, 0.0, n),  # just above the 50 line
        "pmi_caixin": _series(50.3, 0.0, n),
        "pmi_non_mfg": _series(51.0, 0.0, n),
        "pmi_caixin_svc": _series(51.5, 0.0, n),
    })
    industrial = pd.DataFrame({
        "date": m,
        "ip_yoy": _series(5.0, 0.02, n),        # above its own trend → restocking
        "ip_cumulative": _series(5.0, 0.01, n),
    })
    lpr = pd.DataFrame({
        "date": m,
        "lpr_1y": _series(3.45, 0.0, n),
        "lpr_5y": _series(4.0, 0.0, n),
    })

    # Annual GDP (date = Y-01-01), gdp_yoy comfortably above its rolling median.
    years = list(range(2019, 2026))
    gdp = pd.DataFrame({
        "date": [f"{y}-01-01" for y in years],
        "gdp_abs": _series(90.0, 5.0, len(years)),
        "gdp_yoy": [5.2, 6.0, 8.4, 3.0, 5.2, 5.0, 5.0],
    })

    # Quarterly leverage: household deleveraging slightly while corp/gov lever up
    # (net leveraging) — a non-degenerate debt-cycle input.
    q = _quarters("2023-03-01", 12)
    household = _series(62.0, -0.1, 12)
    non_fin_corp = _series(168.0, 0.4, 12)
    gov_total = _series(78.0, 0.5, 12)
    leverage = pd.DataFrame({
        "date": q,
        "household": household,
        "non_fin_corp": non_fin_corp,
        "gov_total": gov_total,
        "gov_central": _series(22.0, 0.2, 12),
        "gov_local": _series(56.0, 0.3, 12),
        "real_economy": [round(h + c + g, 3)
                         for h, c, g in zip(household, non_fin_corp, gov_total)],
    })

    hp_months = _months("2024-01-01", 14)
    house_price = pd.DataFrame([
        {"date": d, "city": c,
         "new_yoy": -1.5, "new_mom": -0.2, "used_yoy": -2.0, "used_mom": -0.3}
        for d in hp_months for c in ("北京", "上海", "广州")
    ])

    for name, df in (
        ("money_supply", money_supply), ("cpi", cpi), ("ppi", ppi), ("pmi", pmi),
        ("industrial", industrial), ("lpr", lpr), ("gdp", gdp),
        ("leverage", leverage), ("house_price", house_price),
    ):
        df.to_sql(name, conn, if_exists="replace", index=False)


def _write_signal_history(conn):
    """A few append-only snapshot rows so /signals/history returns real data."""
    rows = [
        ("2025-10-01T00:00:00Z", "2025-09", 3, "recovery", "easing", "active_restocking", "leveraging_boom"),
        ("2025-11-01T00:00:00Z", "2025-10", 2, "recovery", "neutral", "active_restocking", "leveraging_boom"),
        ("2025-12-01T00:00:00Z", "2025-11", 3, "recovery", "easing", "active_restocking", "leveraging_boom"),
    ]
    conn.execute(
        "CREATE TABLE IF NOT EXISTS signal_history ("
        "ts TEXT, data_as_of TEXT, composite INTEGER, "
        "merrill TEXT, credit TEXT, inventory TEXT, debt TEXT)")
    conn.executemany(
        "INSERT INTO signal_history VALUES (?,?,?,?,?,?,?)", rows)


def _finalise_rollback_journal(path):
    """Checkpoint any WAL and force the committed file to journal_mode=delete, then
    drop the -wal/-shm sidecars, so the fixture is a single clean artefact."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.commit()
    finally:
        conn.close()
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def build_macro_fixture():
    MACRO_FIXTURE.unlink(missing_ok=True)
    conn = sqlite3.connect(MACRO_FIXTURE)
    try:
        _write_raw_tables(conn)
        # Run the REAL derived-layer computation so raw↔derived stay consistent.
        _load_compute_derived().compute_derived(conn)
        _write_signal_history(conn)
        conn.commit()
    finally:
        conn.close()
    _finalise_rollback_journal(MACRO_FIXTURE)
    print(f"  ✅ {MACRO_FIXTURE.relative_to(PROJECT_ROOT)} "
          f"({MACRO_FIXTURE.stat().st_size // 1024} KB)")


def build_crcl_fixture():
    CRCL_FIXTURE.unlink(missing_ok=True)
    # Point crcl_db at the fixture path and use its authoritative DDL + writers.
    from backend.app.core import crcl_db
    orig = crcl_db.CRCL_DB_PATH
    crcl_db.CRCL_DB_PATH = CRCL_FIXTURE
    try:
        crcl_db.ensure_schema()
        crcl_db.upsert_points("usdc_circ", [("2025-11-01", 42000.0), ("2025-12-01", 43500.0)])
        crcl_db.upsert_points("crcl_price", [("2025-11-01", 28.0), ("2025-12-01", 31.2)])
        crcl_db.set_snapshot("valuation", {"price": 31.2, "pe": 45.0})
        crcl_db.add_log("fixture-run", "seed", "ok", "fixture seed", 12)
    finally:
        crcl_db.CRCL_DB_PATH = orig
    _finalise_rollback_journal(CRCL_FIXTURE)
    print(f"  ✅ {CRCL_FIXTURE.relative_to(PROJECT_ROOT)} "
          f"({CRCL_FIXTURE.stat().st_size // 1024} KB)")


def main():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    print("Building test fixtures ...")
    build_macro_fixture()
    build_crcl_fixture()
    print("Done.")


if __name__ == "__main__":
    main()
