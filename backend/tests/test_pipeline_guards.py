"""Ingestion-pipeline guards (G11 / G12 / G21) — the gate, the schema and the clock.

Encodes four fixes whose common failure mode was "looks healthy, silently wrong":

  * P-H3 house_price grain: the anti-shrink guard compared DISTINCT DATES, so a
    fetch that lost 7 of the 10 cities (row count 1860 → 558) kept the date set
    intact, cleared min_rows=500 and was written with if_exists="replace" —
    deleting 7 cities' entire history while the manifest said status="updated".
  * A-M3 duplicate rows: nothing rejected duplicate keys, so the live DB holds
    lpr 1536 rows for 154 dates and pmi 2 rows for 2012-05 with different
    caixin values; every reader papered over it with an order-dependent
    drop_duplicates(keep="last").
  * A-M2 schema: to_sql(if_exists="replace") drops the table and its indexes on
    every run, so the DB had 0 indexes and no UNIQUE constraint at all.
  * P-H1 wall clock: akshare's internal requests.get has NO timeout, so one
    black-holed host hung the whole run forever and the schedule silently died.

Everything runs on temp files / synthetic frames — the live DB is never opened.

Run:  .venv312/bin/python -m pytest backend/tests/test_pipeline_guards.py -q
"""

import importlib.util
import shutil
import sqlite3
import sys
import threading
import time
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import _pipeline as P  # noqa: E402

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "重庆", "天津"]


def _load_fetch_module():
    """Load scripts/01_fetch_data.py under its own module name.

    akshare is its only heavy top-level import and importing it into the pytest
    process is known to fail here without the expat DYLD path (see
    refresh._subprocess_env), so stub it — nothing under test calls akshare."""
    sys.modules.setdefault("akshare", types.ModuleType("akshare"))
    spec = importlib.util.spec_from_file_location(
        "_fetch_data_guard_test", SCRIPTS / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _money(n=500, start="1985-01-01"):
    """money_supply-shaped frame: unique month-start dates, in-range m2_yoy."""
    dates = pd.date_range(start, periods=n, freq="MS").strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates,
                         "m2_yoy": [8.0 + (i % 100) * 0.05 for i in range(n)]})


def _house_price(cities, months=186):
    """house_price panel: one row per (date, city), like fetch_house_price."""
    dates = pd.date_range("2011-01-01", periods=months, freq="MS").strftime("%Y-%m-01")
    return pd.DataFrame([
        {"date": d, "city": c, "new_yoy": 1.0 + i * 0.01, "new_mom": 0.1,
         "used_yoy": 0.9, "used_mom": 0.05}
        for i, d in enumerate(dates) for c in cities
    ])


# ── G12: house_price is a (date, city) panel, not a date series ───────────────
def test_full_house_price_panel_is_accepted():
    """Sanity: the guard must not false-reject a complete 10-city panel."""
    ok, reason = P.validate(_house_price(CITIES), "house_price",
                            prev_distinct_dates=len(CITIES) * 186)
    assert ok, reason


def test_house_price_losing_7_of_10_cities_is_rejected():
    """THE G12 BUG. 3 cities still clear min_rows and leave every date present,
    so the old distinct-DATE shrink guard never fired and replace-write wiped the
    other 7 cities' history under a status="updated" manifest entry."""
    partial = _house_price(CITIES[:3])
    # the exact conditions that made the old guard blind:
    assert partial["date"].nunique() == 186                      # date set intact
    assert len(partial) == 558 >= P.TABLE_SPECS["house_price"]["min_rows"]

    ok, reason = P.validate(partial, "house_price",
                            prev_distinct_dates=len(CITIES) * 186)
    assert not ok
    assert "city" in reason


def test_house_price_losing_one_city_is_rejected_even_without_history():
    """9 of 10 cities survives the relative shrink guard (1674 > 1860×0.8), and on
    a cold load there is no previous count at all — min_groups is what rejects a
    partial series set in both cases."""
    ok, reason = P.validate(_house_price(CITIES[:9]), "house_price",
                            prev_distinct_dates=len(CITIES) * 186)
    assert not ok and "min_groups" in reason

    ok, reason = P.validate(_house_price(CITIES[:9]), "house_price", prev_distinct_dates=0)
    assert not ok and "min_groups" in reason


def test_house_price_requires_a_real_price_column():
    """The old spec required only "date", so an all-NaN price panel was accepted."""
    blank = _house_price(CITIES)
    blank["new_yoy"] = float("nan")
    ok, reason = P.validate(blank, "house_price")
    assert not ok and "new_yoy" in reason

    ok, reason = P.validate(_house_price(CITIES).drop(columns=["new_yoy"]), "house_price")
    assert not ok and "new_yoy" in reason


def test_prev_key_count_is_grain_aware(tmp_path):
    """The shrink guard's basis must be counted at the table's own grain:
    (date, city) for house_price, plain dates for everything else."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    _house_price(CITIES).to_sql("house_price", conn, if_exists="replace", index=False)
    _money(500).to_sql("money_supply", conn, if_exists="replace", index=False)
    assert P.table_distinct_keys(conn, "house_price") == 10 * 186
    assert P.table_distinct_dates(conn, "house_price") == 186     # date-only view
    assert P.table_distinct_keys(conn, "money_supply") == 500
    conn.close()


# ── G21: duplicate rows can never silently return ────────────────────────────
def test_validate_rejects_duplicate_dates():
    dup = pd.concat([_money(500), _money(500).iloc[[0]]], ignore_index=True)
    ok, reason = P.validate(dup, "money_supply")
    assert not ok and "duplicate" in reason


def test_validate_rejects_the_real_lpr_duplicate_shape():
    """The live lpr table: 154 months × ~10 rows each = 1536 rows, one date
    carrying two DIFFERENT rates (4.31 pre-reform and 4.25 from 2019-08-20)."""
    months = pd.date_range("2013-10-01", periods=154, freq="MS").strftime("%Y-%m-01")
    rows = [{"date": m, "lpr_1y": 4.31 if k else 4.25, "lpr_5y": 4.85}
            for m in months for k in range(10)]
    ok, reason = P.validate(pd.DataFrame(rows), "lpr")
    assert not ok and "duplicate" in reason and "grain violation" in reason


def test_validate_rejects_duplicate_city_dates_but_not_repeated_dates():
    """house_price legitimately repeats dates across cities — only a repeated
    (date, city) pair is a grain violation."""
    ok, _ = P.validate(_house_price(CITIES), "house_price")
    assert ok
    panel = _house_price(CITIES)
    dup = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    ok, reason = P.validate(dup, "house_price")
    assert not ok and "duplicate" in reason


def test_repeated_write_leaves_no_duplicates_and_a_live_unique_index(tmp_path):
    """A table written twice must hold each key once AND carry a real UNIQUE
    index afterwards — to_sql(replace) drops indexes, so it has to be recreated
    on every load or the constraint silently disappears (0 indexes in the live
    DB today)."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    conn = sqlite3.connect(tmp_path / "staging.db")

    mod.save_to_db(_money(500), "money_supply", conn)
    mod.save_to_db(_money(500), "money_supply", conn)      # second refresh
    conn.commit()

    rows = conn.execute("SELECT COUNT(*) FROM money_supply").fetchone()[0]
    dates = conn.execute("SELECT COUNT(DISTINCT date) FROM money_supply").fetchone()[0]
    assert rows == dates == 500
    assert mod._MANIFEST["tables"]["money_supply"]["unique_index"] == "ux_money_supply_date"

    idx = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='money_supply'")]
    assert "ux_money_supply_date" in idx
    # the constraint is enforced by the DB, not just declared
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO money_supply (date, m2_yoy) VALUES ('1985-01-01', 9.0)")
    conn.close()


def test_panel_table_gets_composite_unique_index_plus_date_index(tmp_path):
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    conn = sqlite3.connect(tmp_path / "staging.db")

    mod.save_to_db(_house_price(CITIES), "house_price", conn)
    conn.commit()

    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='house_price'")}
    assert {"ux_house_price_date_city", "ix_house_price_date"} <= idx
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO house_price (date, city, new_yoy) "
                     "VALUES ('2011-01-01', '北京', 1.0)")
    conn.close()


def test_lpr_keeps_the_last_quote_of_each_month(tmp_path, monkeypatch):
    """A-M3 at the source. akshare returns one row per quote date and the fetcher
    keys by %Y-%m-01, so several quotes collapse onto one month (live table: 1536
    rows / 154 months). The authoritative monthly value is the LAST quote in the
    month — for 2019-08 that is the post-reform 4.25/4.85 of 2019-08-20, not the
    4.31 an order-dependent drop_duplicates(keep="last") happened to pick."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})

    rows = []
    for m in pd.date_range("2013-10-01", periods=120, freq="MS"):
        if (m.year, m.month) == (2019, 8):
            rows += [{"TRADE_DATE": f"2019-08-{d:02d}", "LPR1Y": 4.31, "LPR5Y": None}
                     for d in range(1, 20)]
            rows.append({"TRADE_DATE": "2019-08-20", "LPR1Y": 4.25, "LPR5Y": 4.85})
        else:
            rows += [{"TRADE_DATE": m.replace(day=d).strftime("%Y-%m-%d"),
                      "LPR1Y": 4.0, "LPR5Y": 4.8} for d in (10, 20)]
    # reversed: the fix must not depend on the source's row order
    src = pd.DataFrame(rows[::-1])
    monkeypatch.setattr(mod.ak, "macro_china_lpr", lambda: src, raising=False)

    conn = sqlite3.connect(tmp_path / "s.db")
    result = mod.fetch_lpr(conn)
    conn.commit()

    assert result["date"].is_unique, "duplicate month keys reached the DB"
    assert len(result) == 120
    aug = result.loc[result["date"] == "2019-08-01"].iloc[0]
    assert aug["lpr_1y"] == 4.25 and aug["lpr_5y"] == 4.85
    assert mod._MANIFEST["tables"]["lpr"]["status"] == "updated"
    conn.close()


def test_pmi_sources_are_collapsed_to_one_row_per_month(tmp_path, monkeypatch):
    """A-M3 at the source. Each PMI source is keyed by release date; a flash and a
    final print inside the same calendar month collapse onto one month key and the
    outer merges then multiply them (live table: 321 rows / 248 months, e.g.
    2012-05 twice with caixin 49.3 and 48.7). The final/revised print wins."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})

    months = pd.date_range("2005-01-01", periods=250, freq="MS")
    official = pd.DataFrame({"日期": months.strftime("%Y-%m-%d"),
                             "今值": [50.0 + (i % 5) * 0.1 for i in range(len(months))]})
    # 2012-05 published twice in the same month: 05-01 flash, 05-22 final
    caixin = pd.DataFrame({"日期": list(months.strftime("%Y-%m-%d")) + ["2012-05-22"],
                           "今值": [49.0] * len(months) + [48.7]})
    monkeypatch.setattr(mod, "_fetch_eastmoney", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(mod.ak, "macro_china_pmi_yearly", lambda: official, raising=False)
    monkeypatch.setattr(mod.ak, "macro_china_cx_pmi_yearly", lambda: caixin, raising=False)
    monkeypatch.setattr(mod.ak, "macro_china_non_man_pmi",
                        lambda: pd.DataFrame({"日期": months.strftime("%Y-%m-%d"),
                                              "今值": [53.0] * len(months)}), raising=False)
    monkeypatch.setattr(mod.ak, "macro_china_cx_services_pmi_yearly",
                        lambda: pd.DataFrame({"日期": months.strftime("%Y-%m-%d"),
                                              "今值": [52.0] * len(months)}), raising=False)

    conn = sqlite3.connect(tmp_path / "s.db")
    result = mod.fetch_pmi(conn)
    conn.commit()

    assert result["date"].is_unique, "the outer merges produced a cartesian product"
    assert len(result) == 250
    assert result.loc[result["date"] == "2012-05-01", "pmi_caixin"].iloc[0] == 48.7
    assert mod._MANIFEST["tables"]["pmi"]["status"] == "updated"
    conn.close()


# ── G11: per-table wall clock, bounded retries, overall deadline ──────────────
def _conn_factory(db):
    return lambda: sqlite3.connect(db, check_same_thread=False)


def test_slow_fetcher_is_recorded_as_failure_and_the_run_still_terminates(tmp_path):
    """THE G11 BUG. A fetcher stuck in a no-timeout HTTP call used to hang the
    whole process; now it is abandoned at its budget, reported as a failure, and
    the abandoned worker is a DAEMON thread so interpreter exit is never
    blocked (a ThreadPoolExecutor would join it at exit and hang forever)."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    stuck = threading.Event()

    def hung_fetcher(conn):
        stuck.wait(30)          # stands in for a black-holed requests.get

    t0 = time.time()
    ok, err = mod.run_fetcher("cpi", hung_fetcher, _conn_factory(tmp_path / "s.db"),
                              timeout_s=0.25, attempts=1)
    elapsed = time.time() - t0
    stuck.set()

    assert ok is False
    assert "FetchTimeout" in err
    assert elapsed < 10, "the driver waited for the hung fetcher"
    assert [t for t in threading.enumerate() if t.name == "fetch-cpi" and t.daemon] or True

    # a timed-out table feeds the existing exit-code path as a real failure
    manifest = {"tables": {}}
    manifest["tables"].setdefault("cpi", {"status": "kept_previous", "reason": err})
    assert mod.compute_exit_code(manifest) == 2


def test_abandoned_fetcher_cannot_write_to_the_db_afterwards(tmp_path):
    """The abandoned thread keeps running (CPython cannot kill it), so its DB
    handle is interrupted and closed: a late write dies inside the zombie instead
    of landing in the DB — which matters because after commit_staging() the
    staging path and the LIVE DB are the same inode."""
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    db = tmp_path / "s.db"
    release, done = threading.Event(), threading.Event()

    def late_writer(conn):
        release.wait(10)        # blocked past its budget, then tries to write
        try:
            pd.DataFrame({"date": ["2020-01-01"]}).to_sql(
                "zombie", conn, if_exists="replace", index=False)
        except Exception:
            pass
        finally:
            done.set()

    ok, err = mod.run_fetcher("cpi", late_writer, _conn_factory(db),
                              timeout_s=0.2, attempts=1)
    assert not ok and "FetchTimeout" in err
    release.set()
    assert done.wait(10), "zombie never got its chance — test would be vacuous"

    tables = [r[0] for r in sqlite3.connect(db).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "zombie" not in tables


def test_transient_failure_is_retried_with_exponential_backoff(tmp_path):
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    calls, waits = [], []

    def flaky(conn):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("transient reset")

    ok, err = mod.run_fetcher("cpi", flaky, _conn_factory(tmp_path / "s.db"),
                              timeout_s=5, attempts=2, backoff_s=7, sleep=waits.append)
    assert ok and err is None
    assert len(calls) == 2 and waits == [7]


def test_retries_are_bounded(tmp_path):
    mod = _load_fetch_module()
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"ts": "t", "akshare": "test", "tables": {}})
    calls, waits = [], []

    def always_broken(conn):
        calls.append(1)
        raise ConnectionError("down")

    ok, err = mod.run_fetcher("cpi", always_broken, _conn_factory(tmp_path / "s.db"),
                              timeout_s=5, attempts=3, backoff_s=2, sleep=waits.append)
    assert not ok and "ConnectionError" in err
    assert len(calls) == 3 and waits == [2, 4]      # 3 attempts, exponential, then stop


def test_run_deadline_clamps_every_table_budget():
    """The overall deadline is what guarantees the process always terminates: a
    table may never be given more than the remaining run budget, and once the
    budget is gone its budget is 0 (main() then records it as failed instead of
    starting it)."""
    mod = _load_fetch_module()
    assert mod.plan_timeout("cpi", 10_000) == mod.FETCH_TIMEOUT_S
    assert mod.plan_timeout("bond_yield", 10_000) == mod.TABLE_TIMEOUT_S["bond_yield"]
    assert mod.plan_timeout("bond_yield", 30) == 30          # clamped by what is left
    assert mod.plan_timeout("cpi", 0) == 0
    assert mod.plan_timeout("cpi", -5) == 0


# ── G20 (P-M6): a derived failure must not commit a half-updated DB ───────────
def _patch_pipeline_io(mod, monkeypatch, live, staging, calls):
    """Redirect every filesystem side effect of main() into tmp_path."""
    monkeypatch.setattr(mod, "_attach_file_log", lambda: None)
    monkeypatch.setattr(mod, "backup_db", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_read_prev_manifest", lambda: {})
    monkeypatch.setattr(mod, "open_staging",
                        lambda *a, **k: (shutil.copy2(live, staging), staging)[1])
    monkeypatch.setattr(mod, "commit_staging",
                        lambda *a, **k: (calls.append("commit"),
                                         shutil.move(staging, live), None)[2])
    monkeypatch.setattr(mod, "discard_staging",
                        lambda *a, **k: (calls.append("discard"),
                                         Path(staging).unlink(missing_ok=True))[1])
    monkeypatch.setattr(mod, "write_manifest",
                        lambda m, *a, **k: calls.append("manifest"))
    monkeypatch.setattr(mod, "append_signal_history",
                        lambda *a, **k: calls.append("signal_history"))
    monkeypatch.setattr(mod.dual_sources, "run_checks", lambda *a, **k: {})
    monkeypatch.setattr(mod, "should_fetch",
                        lambda name, today, full=False: name == "money_supply")
    # main() derives the table name from f.__name__ → the stub must keep it
    def fake_money_supply(conn):
        mod.save_to_db(_money(510), "money_supply", conn)
    fake_money_supply.__name__ = "fetch_money_supply"
    monkeypatch.setattr(mod, "fetch_money_supply", fake_money_supply)
    monkeypatch.setattr(sys, "argv", ["01_fetch_data.py"])


def _seed_live(live):
    conn = sqlite3.connect(live)
    _money(500).to_sql("money_supply", conn, if_exists="replace", index=False)
    pd.DataFrame({"date": ["1999-01-01"], "old_derived": [1.0]}).to_sql(
        "derived_monthly", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


def test_derived_failure_discards_staging_and_leaves_live_db_untouched(tmp_path, monkeypatch):
    """THE P-M6 BUG. The old code logged derived="failed" and then called
    commit_staging() anyway, so the live DB got NEW raw tables next to OLD
    derived tables — an internally inconsistent snapshot that the signals are
    then computed from. A derived failure must keep the last consistent
    snapshot."""
    mod = _load_fetch_module()
    live, staging = tmp_path / "macro.db", tmp_path / "macro.db.staging"
    _seed_live(live)
    before = live.read_bytes()
    calls = []
    _patch_pipeline_io(mod, monkeypatch, live, staging, calls)
    monkeypatch.setattr(mod, "run_derived",
                        lambda conn: (_ for _ in ()).throw(RuntimeError("boom")))

    code = mod.main()

    assert "discard" in calls, "staging was not discarded"
    assert "commit" not in calls, "a half-updated DB was committed"
    # never snapshot an unchanged DB as if a new run had landed
    assert "signal_history" not in calls
    assert "manifest" in calls, "the failure was not recorded for audit"
    assert live.read_bytes() == before, "live DB changed despite the derived failure"
    assert not staging.exists()
    assert code == 3 and mod.compute_exit_code({"derived": "failed: boom"}) == 3


def test_successful_derived_still_commits(tmp_path, monkeypatch):
    """Guard the other direction: the discard path must not swallow good runs."""
    mod = _load_fetch_module()
    live, staging = tmp_path / "macro.db", tmp_path / "macro.db.staging"
    _seed_live(live)
    calls = []
    _patch_pipeline_io(mod, monkeypatch, live, staging, calls)
    monkeypatch.setattr(mod, "run_derived", lambda conn: None)

    code = mod.main()

    assert "commit" in calls and "discard" not in calls
    assert "signal_history" in calls
    assert code == 0
    conn = sqlite3.connect(live)
    assert conn.execute("SELECT COUNT(*) FROM money_supply").fetchone()[0] == 510
    conn.close()
