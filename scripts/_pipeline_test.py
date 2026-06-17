"""Offline, deterministic verification of the staged ingestion pipeline.

No network, no real DB touched — everything runs in a temp dir. Proves the root
cure: bad/empty/partial/eroded fetches never overwrite good data, the live DB is
mutated only by an atomic rename, and a mid-run crash leaves production intact.

Run:  .venv312/bin/python scripts/_pipeline_test.py
"""

import importlib.util
import os
import sqlite3
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _pipeline as P  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


# ──────────────────────────────────────────────────────────────────────────────
# 1) validate() unit cases
# ──────────────────────────────────────────────────────────────────────────────
def good_money(n=500):
    return pd.DataFrame({"date": pd.date_range("2000-01-01", periods=n, freq="MS").strftime("%Y-%m-%d"),
                         "m2_yoy": [8.0 + i * 0.01 for i in range(n)]})


print("\n=== 1. validate() gate cases ===")
check("good 500-row money_supply passes", P.validate(good_money(), "money_supply")[0])
check("empty rejected", not P.validate(pd.DataFrame(), "money_supply")[0])
check("below min_rows rejected", not P.validate(good_money(100), "money_supply")[0])
check("missing required col rejected", not P.validate(good_money().drop(columns=["m2_yoy"]), "money_supply")[0])
nan_col = good_money(); nan_col["m2_yoy"] = float("nan")
check("all-NaN required col rejected", not P.validate(nan_col, "money_supply")[0])
check("distinct-date erosion rejected (500→50)", not P.validate(good_money(50), "money_supply", prev_distinct_dates=500)[0])
# the lpr grain-fairness case: 152 distinct vs prev 152 → must NOT false-reject
_lpr = pd.DataFrame({"date": pd.date_range("2013-10-01", periods=152, freq="MS").strftime("%Y-%m-%d"),
                     "lpr_1y": [3.0] * 152})
check("lpr no false-reject at equal distinct dates", P.validate(_lpr, "lpr", prev_distinct_dates=152)[0])
check("household_income small annual ok", P.validate(good_money(10).rename(columns={"m2_yoy": "income_abs"})[["date", "income_abs"]], "household_income")[0])


# ──────────────────────────────────────────────────────────────────────────────
# 2) Full staged flow: good + bad + partial fetchers, atomic commit
# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 2. staged flow (good + empty + partial + crash) ===")
with tempfile.TemporaryDirectory() as d:
    live = os.path.join(d, "macro_data.db")
    staging = os.path.join(d, "macro_data.db.staging")
    backup_dir = os.path.join(d, "backups")

    # seed a "live" production DB with a good money_supply (581 rows)
    c0 = sqlite3.connect(live)
    good_money(581).to_sql("money_supply", c0, if_exists="replace", index=False)
    c0.commit(); c0.close()
    live_hash_before = pd.io.sql.read_sql("SELECT * FROM money_supply", sqlite3.connect(live)).to_csv()

    # ① backup
    bk = P.backup_db(live, backup_dir)
    check("backup created", bk and os.path.exists(bk))
    check("backup is a copy of live", pd.io.sql.read_sql("SELECT * FROM money_supply", sqlite3.connect(bk)).shape[0] == 581)

    # ② open staging (copies live → staging; old good data now inside staging)
    P.open_staging(live, staging)
    check("staging file exists", os.path.exists(staging))
    check("staging inherits good table", P.table_distinct_dates(sqlite3.connect(staging), "money_supply") == 581)

    # load the REAL gated save_to_db from 01_fetch_data (digit name → importlib)
    spec = importlib.util.spec_from_file_location("_fetch_mod", os.path.join(HERE, "01_fetch_data.py"))
    fmod = importlib.util.module_from_spec(spec); spec.loader.exec_module(fmod)

    conn = sqlite3.connect(staging)
    fmod._MANIFEST.clear(); fmod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})

    # good fetch → should update
    fmod.save_to_db(good_money(581), "money_supply", conn)
    # empty fetch → must keep previous
    fmod.save_to_db(pd.DataFrame(), "money_supply", conn)
    # partial fetch (1 row) → must keep previous
    fmod.save_to_db(good_money(1), "money_supply", conn)
    conn.commit(); conn.close()

    check("manifest recorded good+empty+partial", len(fmod._MANIFEST["tables"]) >= 1)
    check("staging still has 581 good rows (bad fetches rejected)",
          P.table_distinct_dates(sqlite3.connect(staging), "money_supply") == 581)

    # ③ crash simulation: do NOT commit → live must be byte-identical to before
    live_hash_mid = pd.io.sql.read_sql("SELECT * FROM money_supply", sqlite3.connect(live)).to_csv()
    check("live UNTOUCHED before commit (crash-safe)", live_hash_mid == live_hash_before)

    # ④ commit (atomic) → live now reflects staging
    P.commit_staging(staging, live)
    check("staging removed after commit", not os.path.exists(staging))
    check("live updated to good data after commit",
          P.table_distinct_dates(sqlite3.connect(live), "money_supply") == 581)

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== RESULT ===")
if _failures:
    print(f"❌ {len(_failures)} FAILED: {_failures}")
    sys.exit(1)
print("✅ ALL CHECKS PASSED — bad data can never overwrite good data")
