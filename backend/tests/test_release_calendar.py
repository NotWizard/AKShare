"""Release calendar — should_fetch window boundaries (pure date logic, no network).

Run:  .venv312/bin/python -m pytest backend/tests -q
"""

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from release_calendar import TABLE_CALENDAR, should_fetch  # noqa: E402

D = datetime.date

# 14 表全集 = 01_fetch_data.py main() fetchers 列表
TABLES = [
    "money_supply", "gdp", "cpi", "ppi", "pmi", "leverage", "social_finance",
    "lpr", "industrial", "house_price", "household_income", "new_credit",
    "bond_yield", "demographics",
]


def test_calendar_covers_all_fetched_tables():
    assert set(TABLE_CALENDAR) >= set(TABLES)


# ── 窗内 / 窗外（含窗口两端边界日）──────────────────────────────────────────

def test_lpr_window_boundaries():
    assert should_fetch("lpr", D(2026, 8, 19))       # 窗口首日
    assert should_fetch("lpr", D(2026, 8, 22))       # 窗口末日
    assert not should_fetch("lpr", D(2026, 8, 18))   # 窗前一日
    assert not should_fetch("lpr", D(2026, 8, 23))   # 窗后一日


def test_money_supply_window():
    assert should_fetch("money_supply", D(2026, 8, 9))
    assert should_fetch("money_supply", D(2026, 8, 17))
    assert not should_fetch("money_supply", D(2026, 8, 8))


def test_pmi_dual_window():
    # 官方 PMI 当月最后一天 + 财新次月首个工作日 → (1,5) 与 (25,31) 双窗口
    assert should_fetch("pmi", D(2026, 8, 1))
    assert should_fetch("pmi", D(2026, 8, 5))
    assert not should_fetch("pmi", D(2026, 8, 6))    # 两窗之间的空档
    assert not should_fetch("pmi", D(2026, 8, 24))
    assert should_fetch("pmi", D(2026, 8, 25))
    assert should_fetch("pmi", D(2026, 8, 31))


def test_gdp_month_gate():
    assert not should_fetch("gdp", D(2026, 2, 15))   # 非季度发布月，窗内也不抓
    assert should_fetch("gdp", D(2026, 4, 15))


def test_demographics_yearly_window():
    assert not should_fetch("demographics", D(2026, 8, 31))
    assert should_fetch("demographics", D(2026, 9, 1))
    assert should_fetch("demographics", D(2026, 10, 31))
    assert not should_fetch("demographics", D(2026, 11, 1))


# ── force 恒真 ──────────────────────────────────────────────────────────────

def test_force_overrides_window():
    assert should_fetch("lpr", D(2026, 8, 23), force=True)
    assert should_fetch("gdp", D(2026, 2, 15), force=True)


def test_force_true_for_all_tables_on_dead_date():
    # 2026-08-23：lpr/gdp/demographics 均在窗外 → 无 force 时非全真
    assert not all(should_fetch(t, D(2026, 8, 23)) for t in TABLES)
    assert all(should_fetch(t, D(2026, 8, 23), force=True) for t in TABLES)


# ── 1–2 月合并（industrial）─────────────────────────────────────────────────

def test_industrial_jan_feb_combined_release():
    # 1–2 月合并值 3 月中旬发布 → 3 月窗口天然覆盖
    assert should_fetch("industrial", D(2026, 3, 15))
    # 窗口宁宽勿窄：1、2 月照常开窗（即便数据并入 3 月发布，误报仅一次廉价抓取）
    assert should_fetch("industrial", D(2026, 1, 15))
    assert should_fetch("industrial", D(2026, 2, 15))
    assert not should_fetch("industrial", D(2026, 3, 21))


# ── market 型恒真 / 未知表 fail-open ────────────────────────────────────────

def test_market_kind_always_true():
    for d in (D(2026, 1, 1), D(2026, 8, 9), D(2026, 12, 31), D(2028, 2, 29)):
        assert should_fetch("bond_yield", d)


def test_unknown_table_fails_open():
    assert should_fetch("future_table", D(2026, 8, 9))
