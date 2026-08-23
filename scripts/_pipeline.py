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
    commit_staging()         → vintage snapshot of pre-commit live (data/vintages/,
                               rotated to MAX_VINTAGES), then atomic os.replace(staging → live)
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
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "macro_data.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"
VINTAGE_DIR = PROJECT_ROOT / "data" / "vintages"
STAGING_PATH = PROJECT_ROOT / "data" / "macro_data.db.staging"
MANIFEST_PATH = PROJECT_ROOT / "data" / "last_run.json"
MAX_BACKUPS = 10
MAX_VINTAGES = 12
# A fetched table whose distinct-date count drops below prev × SHRINK_FLOOR is
# treated as partial/eroded and rejected (previous good table kept).
SHRINK_FLOOR = 0.8

# Per-table data contracts. A fetcher's output must satisfy every listed check
# before it may replace the staging table.
#   min_rows  : absolute lower bound on row count (blocks catastrophic overwrite)
#   required  : columns that must exist, not be all-NaN, and (except "date") carry
#               a NUMERIC dtype — a required series that arrived as strings means
#               the source changed shape and the fetcher forgot to coerce, which
#               would turn every downstream pd.to_numeric into silent NaN.
#   ranges    : column → (lo, hi) value domain; validate() rejects when >10% of
#               non-null values fall outside (blocks unit/scale errors, absorbs
#               isolated revisions). Bounds calibrated on live DB min–max 2026-08-09.
#   key       : the table's GRAIN — the column tuple that uniquely identifies a
#               row (default ["date"]). validate() rejects duplicate keys, the
#               shrink guard counts distinct keys (not distinct dates), and
#               save_to_db materialises it as a UNIQUE INDEX after every load.
#   min_groups: for multi-series tables (key longer than ["date"]) the minimum
#               number of distinct series, so losing whole series is rejected
#               even on a first/cold load where no previous count exists.
#   max_date_lag: freshness ceiling in DAYS. A source can silently FREEZE — it
#               keeps returning "valid" rows that simply stop advancing — and the
#               row-count / range gates never notice. When the newest date is more
#               than max_date_lag days behind "today" the fetch is rejected
#               (kept_previous → health lamp turns amber). Only declared on tables
#               with a firm monthly/quarterly cadence; annual / naturally-sparse
#               tables (household_income, demographics, …) legitimately lag a year+
#               and omit it. Bounds are generous (well beyond the normal
#               inter-release gap) so only a genuine multi-month freeze trips them.
TABLE_SPECS = {
    "money_supply":     dict(min_rows=400, required=["m2_yoy"],
                             ranges=dict(m2_yoy=(0, 45))),
    "gdp":              dict(min_rows=15,  required=["gdp_yoy"],
                             ranges=dict(gdp_yoy=(-10, 25)), max_date_lag=400),
    # 东财当前全国 CPI/PPI 序列约 220+/240+ 行（较早期覆盖缩短），绝对下限按
    # 现状校准；对已有表的缩水防护由 distinct-date 反缩水县闸承担
    "cpi":              dict(min_rows=200, required=["cpi_yoy"],
                             ranges=dict(cpi_yoy=(-5, 10))),
    "ppi":              dict(min_rows=200, required=["ppi_yoy"],
                             ranges=dict(ppi_yoy=(-15, 20)), max_date_lag=200),
    "pmi":              dict(min_rows=200, required=["pmi_official"],
                             ranges=dict(pmi_official=(30, 70))),
    "leverage":         dict(min_rows=40,  required=["household"],
                             ranges=dict(household=(0, 120), non_fin_corp=(50, 300),
                                         gov_total=(0, 150), real_economy=(50, 500))),
    "social_finance":   dict(min_rows=50,  required=["total"],
                             ranges=dict(total=(-5000, 100000)), max_date_lag=200),
    "lpr":              dict(min_rows=100, required=["lpr_1y"],
                             ranges=dict(lpr_1y=(0, 10), lpr_5y=(0, 10))),
    "industrial":       dict(min_rows=100, required=["ip_yoy"],
                             ranges=dict(ip_yoy=(-20, 30), ip_cumulative=(-30, 45)),
                             max_date_lag=200),
    # 10-城市面板：粒度是 (date, city)，不是 date。只按 date 防缩水会漏掉「7 个城市
    # 失败但日期集不变」的坍塌（行数 1860→558 仍过 min_rows 且日期数不降），
    # if_exists="replace" 会因此删掉另外 7 城全部历史。min_groups 对齐
    # fetch_house_price 里硬编码的 10 城清单（新增城市时同步上调）。
    "house_price":      dict(min_rows=500, required=["date", "new_yoy"],
                             key=["date", "city"], min_groups=10),
    "household_income": dict(min_rows=8, required=["income_abs"]),  # annual, sparse; income_abs 派生入 hh_debt
    "new_credit":       dict(min_rows=100, required=["new_rmb_loan"], max_date_lag=200),
    "bond_yield":       dict(min_rows=100,  required=["y_10y"],
                             ranges=dict(y_10y=(0, 10)), max_date_lag=200),  # monthly resampled, ~20y
    "demographics":   dict(min_rows=8, required=["population"],
                           ranges=dict(urbanization_rate=(0, 100), birth_rate=(0, 60))),  # annual, ~30y, NBS/WB (may be blocked)
    # NBS 月度财政收支（2015- 起约 120+ 月）；同比为累计增长口径
    "fiscal":           dict(min_rows=100, required=["revenue_cum", "expenditure_cum"],
                             ranges=dict(revenue_cum_yoy=(-30, 40),
                                         expenditure_cum_yoy=(-40, 70)), max_date_lag=220),
    # NBS 月度货物进出口（美元计）+ 美国 ISM 制造业 PMI；出口同比上限留春节低基数脉冲裕量
    "external_demand":  dict(min_rows=100, required=["exports_yoy"],
                             ranges=dict(exports_yoy=(-40, 170),
                                         imports_yoy=(-40, 70),
                                         trade_total_yoy=(-30, 80)), max_date_lag=220),
}


def _ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def iso_ts():
    return datetime.now().isoformat(timespec="seconds")


# ── count helpers (grain-aware) ───────────────────────────────────────────────
def spec_key(table):
    """The table's grain — the column tuple that uniquely identifies a row.
    Defaults to ["date"]; multi-series tables declare their own (house_price →
    ["date", "city"])."""
    return list(TABLE_SPECS.get(table, {}).get("key", ["date"]))


def table_distinct_keys(conn, table, key=None):
    """Distinct GRAIN-KEY count in a table (0 if absent / key cols missing).

    Used as the grain-fair basis for the shrink guard: robust against raw tables
    that carry duplicate dates by design (house_price: 10 cities per date) as
    well as by accident (lpr). Table/column names are hardcoded constants from
    the fetchers and TABLE_SPECS, so direct interpolation is safe."""
    key = spec_key(table) if key is None else list(key)
    try:
        cols = {r[1].lower(): r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()}
        have = [cols[c.lower()] for c in key if c.lower() in cols]
        if not have:
            return 0
        cols_sql = ", ".join(f"[{c}]" for c in have)
        return conn.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT {cols_sql} FROM [{table}])"
        ).fetchone()[0]
    except sqlite3.Error:
        return 0


def table_distinct_dates(conn, table):
    """Distinct date count in a table (0 if absent / no date col)."""
    return table_distinct_keys(conn, table, key=["date"])


def enforce_indexes(conn, table, key=None):
    """Materialise the table's grain as a real DB constraint after a load.

    ``to_sql(if_exists="replace")`` DROPs and re-CREATEs the table, which also
    drops every index on it — that is why the live DB had 0 indexes, no UNIQUE
    key and silently accumulated duplicate dates (lpr 1536 rows / 154 dates).
    Re-creating the unique index right after each load is what makes it survive
    the replace, and it turns "duplicate rows" from a silent data defect into an
    IntegrityError at write time. A secondary date index is added for
    multi-series tables (the unique index already covers date-keyed ones).

    Returns the unique index name, or None when the key columns are absent."""
    key = spec_key(table) if key is None else list(key)
    cols = {r[1].lower(): r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()}
    have = [cols[c.lower()] for c in key if c.lower() in cols]
    if not have:
        return None
    cols_sql = ", ".join(f"[{c}]" for c in have)
    name = "ux_" + table + "_" + "_".join(c.lower() for c in have)
    conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS [{name}] ON [{table}] ({cols_sql})")
    if len(have) > 1 and "date" in cols:
        conn.execute(f"CREATE INDEX IF NOT EXISTS [ix_{table}_date] ON [{table}] ([date])")
    return name


# ── validation gate ──────────────────────────────────────────────────────────
def validate(df, table, prev_distinct_dates=0, today=None):
    """Return (ok, reason). A fetched df must clear every check to replace a table.

    ``prev_distinct_dates`` is the previously-good table's distinct GRAIN-KEY
    count (== distinct dates for date-keyed tables; see table_distinct_keys).
    ``today`` is the freshness reference date (defaults to date.today(); injected
    in tests for determinism)."""
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
    # dtype gate (P-M7): a required numeric column that arrived as strings/objects
    # means the source changed shape (数值带了单位/千分位/百分号后缀) and the fetcher
    # forgot to coerce — storing it silently NaN-s every downstream pd.to_numeric.
    # "date" is intentionally a string key and is exempt.
    for c in required:
        if c != "date" and not pd.api.types.is_numeric_dtype(df[c]):
            return False, f"column {c!r} is not numeric (dtype {df[c].dtype})"
    # value-range gate: >10% of non-null values outside the calibrated domain →
    # reject (whole-table unit/scale errors blocked, isolated revisions absorbed)
    for c, (lo, hi) in spec.get("ranges", {}).items():
        if c not in df.columns:
            continue
        s = df[c].dropna()
        if len(s) and ((s < lo) | (s > hi)).mean() > 0.10:
            return False, f"column {c!r}: >10% of non-null values outside [{lo}, {hi}]"
    # freshness gate (P-M7): a source can silently FREEZE — the newest date stops
    # advancing while every other gate still passes. Tables that declare
    # max_date_lag are rejected once their newest date falls more than that many
    # days behind ``today`` (kept_previous → health lamp turns amber). A future /
    # NaT newest date never trips it.
    max_lag = spec.get("max_date_lag")
    if max_lag and "date" in df.columns:
        newest = pd.to_datetime(df["date"], errors="coerce").max()
        ref = pd.Timestamp(date.today() if today is None else today)
        if pd.notna(newest):
            lag_days = (ref - newest).days
            if lag_days > max_lag:
                return False, (f"newest date {newest.date()} is {lag_days}d behind "
                               f"{ref.date()} > max_date_lag {max_lag}d (stale/frozen source)")
    # grain gate: the declared key must be unique. Duplicate keys are how the
    # live DB ended up with lpr 1536 rows / 154 dates and pmi 2 rows for
    # 2012-05 with different caixin values, which then forced order-dependent
    # drop_duplicates(keep="last") on every reader. Reject at the gate instead.
    key = [c for c in spec_key(table) if c in df.columns]
    if key:
        dups = int(df.duplicated(subset=key).sum())
        if dups:
            first = df[df.duplicated(subset=key, keep=False)][key].head(1).to_dict("records")
            return False, f"{dups} duplicate rows on key {key} (e.g. {first}) — grain violation"
    # series gate: a multi-series table must not silently lose whole series
    # (house_price: 3 of 10 cities still clears min_rows and leaves the date set
    # intact, while replace-write would delete the other 7 cities' history)
    group_cols = key[1:]
    min_groups = spec.get("min_groups", 0)
    if group_cols and min_groups:
        n_groups = len(df.drop_duplicates(subset=group_cols))
        if n_groups < min_groups:
            return False, (f"only {n_groups} distinct {group_cols} < min_groups {min_groups} "
                           "(partial series set)")
    # shrink guard: detect grain-key erosion vs the previously-good table
    if prev_distinct_dates and key:
        new_keys = len(df.drop_duplicates(subset=key))
        if new_keys < prev_distinct_dates * SHRINK_FLOOR:
            return False, (
                f"distinct {key} {new_keys} < prev {prev_distinct_dates}×{SHRINK_FLOOR} "
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


def snapshot_vintage(db_path=DB_PATH, vintage_dir=VINTAGE_DIR):
    """Copy the live DB into a timestamped vintage — the audit snapshot of the
    version BEFORE a staging commit (diff_vintage answers "what did the last
    refresh change"); rotate to MAX_VINTAGES by filename.
    Returns the vintage Path, or None if the live DB does not yet exist."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    vintage_dir = Path(vintage_dir)
    vintage_dir.mkdir(parents=True, exist_ok=True)
    dst = vintage_dir / f"macro_data_{_ts()}.db"
    shutil.copy2(db_path, dst)
    vintages = sorted(vintage_dir.glob("macro_data_*.db"))
    for old in vintages[:-MAX_VINTAGES]:
        old.unlink(missing_ok=True)
    return dst


def _checkpoint_wal(path):
    """把仍留在 `-wal` 边车里的已提交事务落进主库文件。

    后端连接工厂已启用 `journal_mode=WAL`（A-M1 修复），而本模块用
    `shutil.copy2` + `os.replace` 搬整个库文件——**copy2 不会带走 `-wal`**。
    因此若不先 checkpoint：复制出的 staging 会丢掉尚未落盘的那部分提交；
    交换后若还留着旧 inode 的 `-wal`，SQLite 理论上会把它恢复到新文件上。
    非 WAL / 只读 / 损坏库一律静默跳过（行为与启用 WAL 前一致）。
    """
    import sqlite3

    path = Path(path)
    if not path.exists():
        return
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        pass


def _drop_wal_sidecars(path):
    """删除属于已被替换 inode 的 `-wal`/`-shm` 残留（见 _checkpoint_wal）。"""
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def open_staging(db_path=DB_PATH, staging_path=STAGING_PATH):
    """Copy the live DB → staging (so old good data is already present inside
    staging). If the live DB is absent, staging is removed so fetchers start
    fresh. Returns the staging path."""
    db_path, staging_path = Path(db_path), Path(staging_path)
    if db_path.exists():
        _checkpoint_wal(db_path)   # 否则 copy2 丢掉仍在 -wal 中的已提交事务
        shutil.copy2(db_path, staging_path)
        _drop_wal_sidecars(staging_path)
    elif staging_path.exists():
        staging_path.unlink()
        _drop_wal_sidecars(staging_path)
    return staging_path


def commit_staging(staging_path=STAGING_PATH, db_path=DB_PATH, vintage_dir=VINTAGE_DIR):
    """Snapshot the live DB as a vintage (pre-commit audit copy), then atomically
    promote staging → live (POSIX rename is atomic, same FS). Removes staging on
    success. Returns the vintage Path (None if no live DB existed yet or the
    snapshot failed — a snapshot failure must not lose the run's commit)."""
    staging_path, db_path = Path(staging_path), Path(db_path)
    if not staging_path.exists():
        raise FileNotFoundError(f"staging not found: {staging_path}")
    try:
        vintage = snapshot_vintage(db_path, vintage_dir)
    except Exception as e:  # 快照失败（如 ENOSPC）不丢整轮成果：照常提交
        print(f"  ⚠️ vintage 快照失败（跳过快照，照常提交）: {e}")
        vintage = None
    _checkpoint_wal(staging_path)      # staging 自己的 -wal 必须先落盘
    _drop_wal_sidecars(staging_path)
    os.replace(staging_path, db_path)  # atomic overwrite
    _drop_wal_sidecars(db_path)        # 旧 inode 的边车不能留给新文件
    return vintage


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
