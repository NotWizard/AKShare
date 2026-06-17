"""Staged ingestion pipeline — never mutate the production DB until validated.

Principle (root cure for silent data loss):
    A fetched table may NEVER replace a good one directly. Every refresh runs
    against a STAGING copy of the live DB, each table passes a validation gate,
    and the live DB is touched only by a final atomic rename. A bad / empty /
    partial / eroded fetch is skipped, so staging keeps the previously-good table.

Flow:
    backup(live)            → data/backups/macro_data_<ts>.db   (pruned to MAX_BACKUPS)
    open_staging(live)       → data/macro_data.db.staging        (full copy, old data inside)
    [fetchers → save_to_db]  → gated write to staging only
    run_derived(staging)     → recompute derived tables on staging
    commit_staging()         → atomic os.replace(staging → live)
    write_manifest(...)       → data/last_run.json               (audit trail)

Crash safety: a hard crash mid-run only ever damaged the staging file; the live
DB is untouched until the final atomic rename.

All functions accept explicit paths (defaulting to the module constants) so the
pipeline is unit-testable against a temp directory without touching real data.
"""

import importlib.util
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "macro_data.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"
STAGING_PATH = PROJECT_ROOT / "data" / "macro_data.db.staging"
MANIFEST_PATH = PROJECT_ROOT / "data" / "last_run.json"
MAX_BACKUPS = 10
# A fetched table whose distinct-date count drops below prev × SHRINK_FLOOR is
# treated as partial/eroded and rejected (previous good table kept).
SHRINK_FLOOR = 0.8

# Per-table data contracts. A fetcher's output must satisfy every listed check
# before it may replace the staging table.
#   min_rows  : absolute lower bound on row count (blocks catastrophic overwrite)
#   required  : columns that must exist and not be all-NaN
TABLE_SPECS = {
    "money_supply":     dict(min_rows=400, required=["m2_yoy"]),
    "gdp":              dict(min_rows=15,  required=["gdp_yoy"]),
    "cpi":              dict(min_rows=300, required=["cpi_yoy"]),
    "ppi":              dict(min_rows=250, required=["ppi_yoy"]),
    "pmi":              dict(min_rows=200, required=["pmi_official"]),
    "leverage":         dict(min_rows=40,  required=["household"]),
    "social_finance":   dict(min_rows=50,  required=["total"]),
    "lpr":              dict(min_rows=100, required=["lpr_1y"]),
    "industrial":       dict(min_rows=100, required=["ip_yoy"]),
    "house_price":      dict(min_rows=500, required=["date"]),
    "household_income": dict(min_rows=8),                 # annual data, naturally sparse
    "new_credit":       dict(min_rows=100, required=["new_rmb_loan"]),
}


def _ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def iso_ts():
    return datetime.now().isoformat(timespec="seconds")


# ── count helpers (grain-aware) ───────────────────────────────────────────────
def table_distinct_dates(conn, table):
    """Distinct date count in a table (0 if absent / no date col). Used as the
    grain-fair basis for the shrink guard — robust against raw tables that carry
    duplicate dates (e.g. lpr). Table names are hardcoded constants from the
    fetchers, so direct interpolation is safe."""
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
        date_col = next((c for c in cols if c.lower() == "date"), None)
        if not date_col:
            return 0
        return conn.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT [{date_col}] FROM [{table}])"
        ).fetchone()[0]
    except sqlite3.Error:
        return 0


# ── validation gate ──────────────────────────────────────────────────────────
def validate(df, table, prev_distinct_dates=0):
    """Return (ok, reason). A fetched df must clear every check to replace a table."""
    spec = TABLE_SPECS.get(table, {})
    min_rows = spec.get("min_rows", 1)
    required = spec.get("required", [])

    if df is None or len(df) == 0:
        return False, "empty result"
    if len(df) < min_rows:
        return False, f"{len(df)} rows < min_rows {min_rows}"
    missing = [c for c in required if c not in df.columns]
    if missing:
        return False, f"missing required cols {missing}"
    for c in required:
        if c != "date" and df[c].isna().all():
            return False, f"column {c!r} all NaN"
    # shrink guard: detect distinct-date erosion vs the previously-good table
    if prev_distinct_dates and "date" in df.columns:
        new_dates = df["date"].nunique()
        if new_dates < prev_distinct_dates * SHRINK_FLOOR:
            return False, (
                f"distinct dates {new_dates} < prev {prev_distinct_dates}×{SHRINK_FLOOR} "
                "(partial/eroded fetch)"
            )
    return True, "pass"


# ── staged snapshot / atomic swap ────────────────────────────────────────────
def backup_db(db_path=DB_PATH, backup_dir=BACKUP_DIR):
    """Snapshot the live DB to a timestamped backup; prune to MAX_BACKUPS.
    Returns the backup Path, or None if the live DB does not yet exist."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / f"macro_data_{_ts()}.db"
    shutil.copy2(db_path, dst)
    backups = sorted(backup_dir.glob("macro_data_*.db"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)
    return dst


def open_staging(db_path=DB_PATH, staging_path=STAGING_PATH):
    """Copy the live DB → staging (so old good data is already present inside
    staging). If the live DB is absent, staging is removed so fetchers start
    fresh. Returns the staging path."""
    db_path, staging_path = Path(db_path), Path(staging_path)
    if db_path.exists():
        shutil.copy2(db_path, staging_path)
    elif staging_path.exists():
        staging_path.unlink()
    return staging_path


def commit_staging(staging_path=STAGING_PATH, db_path=DB_PATH):
    """Atomically promote staging → live (POSIX rename is atomic, same FS).
    Removes staging on success."""
    staging_path, db_path = Path(staging_path), Path(db_path)
    if not staging_path.exists():
        raise FileNotFoundError(f"staging not found: {staging_path}")
    os.replace(staging_path, db_path)  # atomic overwrite


def discard_staging(staging_path=STAGING_PATH):
    """Remove the staging file (used on fatal error)."""
    staging_path = Path(staging_path)
    if staging_path.exists():
        staging_path.unlink()


def write_manifest(manifest, path=MANIFEST_PATH):
    Path(path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ── derived recompute (folded in for raw+derived atomicity) ───────────────────
def run_derived(conn):
    """Load scripts/02_compute_derived.py (digit-start name → importlib) and run
    compute_derived(conn) against the given connection. Keeps raw + derived tables
    atomic under a single staging swap."""
    p = Path(__file__).resolve().parent / "02_compute_derived.py"
    spec = importlib.util.spec_from_file_location("_compute_derived_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compute_derived(conn)
