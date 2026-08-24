"""04_supplement_social_finance — PBoC 社融补充经暂存闸门原子提交，与 03 同构。

akshare ``macro_china_shrzgm`` 常滞后 3-4 个月；PBoC 官方 XLSX 有更新月份。主管线里
social_finance 排在 leverage（CNBS 线程超时）之后，一旦 CNBS 超时的被弃线程损坏进程
socket fd（Errno 9 级联），紧随其后的 PBoC requests 也被静默吞空 → 社融永远补不进。本
脚本脱离该级联单独补齐，其正确性在此锁定：

  * 只追加「日期 > 现有最大月」且 total 非空的 PBoC 行（未发布月为 NaN，不得追加）。
  * 经 validate() 闸门；拒收 → 抛错、live 逐字节不动。
  * 走 backup → staging → enforce_indexes + run_derived → 原子交换；任何失败丢弃暂存。
  * 无新增 → 不写快照（不把未变的库当作一次落地）。

全部跑在临时文件上；run_derived 被替身（其输入另有测试）——不触碰 live 库。

Run:  .venv312/bin/python -m pytest backend/tests/test_social_finance_supplement.py -q
"""

import datetime
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

SF_COLS = ["date", "total", "rmb_loan", "entrusted_loan", "trust_loan",
           "acceptance_bill", "corp_bond", "equity"]


def _load_04():
    spec = importlib.util.spec_from_file_location(
        "_supp_sf_test", SCRIPTS / "04_supplement_social_finance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _month_first(d: datetime.date, delta_months: int) -> str:
    """First-of-month string `delta_months` away from d's month (delta<0 = past)."""
    m = d.year * 12 + (d.month - 1) + delta_months
    return f"{m // 12}-{m % 12 + 1:02d}-01"


# Anchor everything to real today so the freshness gate (max_date_lag=200) always
# passes — a hardcoded 2026 date would eventually go stale and break this test.
_TODAY = datetime.date.today()


def _recent_monthly_dates(n: int, end_delta: int):
    """n consecutive month-firsts ending `end_delta` months from today."""
    return [_month_first(_TODAY, end_delta - (n - 1 - i)) for i in range(n)]


def _seed_live(path, dates):
    conn = sqlite3.connect(path)
    pd.DataFrame({
        "date": list(dates), "total": [10000.0] * len(dates),
        "rmb_loan": [7000.0] * len(dates), "entrusted_loan": [10.0] * len(dates),
        "trust_loan": [10.0] * len(dates), "acceptance_bill": [10.0] * len(dates),
        "corp_bond": [500.0] * len(dates), "equity": [50.0] * len(dates),
    }).to_sql("social_finance", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


def _paths(tmp_path):
    return dict(db_path=tmp_path / "macro.db", staging_path=tmp_path / "macro.db.staging",
                backup_dir=tmp_path / "backups", vintage_dir=tmp_path / "vintages")


def _supplement_frame(newest_present):
    """PBoC-shaped frame: two publishable months after the live max, then one
    unpublished (NaN total) month — the exact fold/drop the code must get right."""
    m1, m2, m3 = (_month_first(datetime.date.fromisoformat(newest_present), k) for k in (1, 2, 3))
    return pd.DataFrame([
        {"date": m1, "total": 20293.0, "rmb_loan": 4965.0, "entrusted_loan": 0.0,
         "trust_loan": 0.0, "acceptance_bill": 0.0, "corp_bond": 1000.0, "equity": 100.0},
        {"date": m2, "total": 33671.0, "rmb_loan": 17650.0, "entrusted_loan": 0.0,
         "trust_loan": 0.0, "acceptance_bill": 0.0, "corp_bond": 2000.0, "equity": 200.0},
        # unpublished month: NaN total → MUST NOT be appended
        {"date": m3, "total": None, "rmb_loan": None, "entrusted_loan": None,
         "trust_loan": None, "acceptance_bill": None, "corp_bond": None, "equity": None},
    ], columns=SF_COLS)


def test_folds_only_newer_nonnull_months_through_staging(tmp_path, monkeypatch):
    """THE fold contract: append PBoC months strictly after the live max AND with a
    non-null total; the NaN (unpublished) month is dropped. Rides the atomic swap
    with a rebuilt UNIQUE index and an atomic derived recompute."""
    mod = _load_04()
    p = _paths(tmp_path)
    dates = _recent_monthly_dates(60, end_delta=-3)   # 60 months ending 3mo ago
    _seed_live(p["db_path"], dates)
    newest = dates[-1]

    monkeypatch.setattr(mod, "pbc_shrzgm_supplement_df", lambda: _supplement_frame(newest))
    calls = []

    def spy_derived(conn):
        calls.append("derived")
        pd.DataFrame({"date": ["2099-01-01"], "sentinel": [1.0]}).to_sql(
            "derived_monthly", conn, if_exists="replace", index=False)
    monkeypatch.setattr(mod, "run_derived", spy_derived)

    n = mod.supplement(**p)

    assert n == 2                       # two publishable months; NaN month dropped
    assert calls == ["derived"]         # raw+derived stayed atomic on staging
    assert not p["staging_path"].exists()

    conn = sqlite3.connect(p["db_path"])
    got = pd.read_sql("SELECT date, total FROM social_finance ORDER BY date", conn)
    assert len(got) == 62
    m1 = _month_first(datetime.date.fromisoformat(newest), 1)
    m2 = _month_first(datetime.date.fromisoformat(newest), 2)
    m3 = _month_first(datetime.date.fromisoformat(newest), 3)
    assert {m1, m2} <= set(got["date"])
    assert m3 not in set(got["date"])   # NaN month never landed
    # unique index rebuilt after the replace → duplicate date now an IntegrityError
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='social_finance'")}
    assert "ux_social_finance_date" in idx
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO social_finance (date, total) VALUES (?, 1.0)", (m1,))
    assert pd.read_sql("SELECT * FROM derived_monthly", conn)["sentinel"].iloc[0] == 1.0
    conn.close()


def test_noop_when_supplement_has_nothing_newer(tmp_path, monkeypatch):
    """Supplement only offers months already present (or NaN) → 0 rows, no swap,
    no derived recompute, live byte-identical."""
    mod = _load_04()
    p = _paths(tmp_path)
    dates = _recent_monthly_dates(60, end_delta=-3)
    _seed_live(p["db_path"], dates)
    before = Path(p["db_path"]).read_bytes()

    # everything the supplement offers is <= live max → filtered out
    stale = pd.DataFrame([{"date": dates[-1], "total": 999.0, "rmb_loan": 1.0,
                           "entrusted_loan": 0.0, "trust_loan": 0.0, "acceptance_bill": 0.0,
                           "corp_bond": 0.0, "equity": 0.0}], columns=SF_COLS)
    monkeypatch.setattr(mod, "pbc_shrzgm_supplement_df", lambda: stale)
    monkeypatch.setattr(mod, "run_derived", lambda conn: pytest.fail("must not recompute"))

    n = mod.supplement(**p)

    assert n == 0
    assert Path(p["db_path"]).read_bytes() == before
    assert not p["staging_path"].exists()


def test_gate_rejection_leaves_live_untouched(tmp_path, monkeypatch):
    """A validate() rejection must raise and leave live byte-identical — nothing
    enters the live DB except through the gate."""
    mod = _load_04()
    p = _paths(tmp_path)
    dates = _recent_monthly_dates(60, end_delta=-3)
    _seed_live(p["db_path"], dates)
    before = Path(p["db_path"]).read_bytes()

    monkeypatch.setattr(mod, "pbc_shrzgm_supplement_df",
                        lambda: _supplement_frame(dates[-1]))
    monkeypatch.setattr(mod, "validate", lambda *a, **k: (False, "forced test reject"))
    monkeypatch.setattr(mod, "run_derived", lambda conn: pytest.fail("must not recompute"))

    with pytest.raises(ValueError, match="拒收"):
        mod.supplement(**p)

    assert Path(p["db_path"]).read_bytes() == before
    assert not p["staging_path"].exists()


def test_missing_live_db_raises_clearly(tmp_path):
    mod = _load_04()
    with pytest.raises(FileNotFoundError):
        mod.supplement(**_paths(tmp_path))
