"""Offline, deterministic verification of the release calendar.

No network — pure date logic. Run:  .venv312/bin/python scripts/release_calendar_test.py
"""

import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from release_calendar import TABLE_CALENDAR, should_fetch  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


# 16 表全集 = 01_fetch_data.py main() fetchers 列表
TABLES = [
    "money_supply", "gdp", "cpi", "ppi", "pmi", "leverage", "social_finance",
    "lpr", "industrial", "house_price", "household_income", "new_credit",
    "bond_yield", "demographics", "fiscal", "external_demand",
]

print("\n=== 1. calendar coverage ===")
check("TABLE_CALENDAR covers all 16 tables", set(TABLE_CALENDAR) >= set(TABLES))

print("\n=== 2. window logic ===")
check("lpr on 20th True", should_fetch("lpr", datetime.date(2026, 8, 20)))
check("lpr on 23rd False", not should_fetch("lpr", datetime.date(2026, 8, 23)))
check("pmi on Jan 2 True", should_fetch("pmi", datetime.date(2026, 1, 2)))
check("pmi on Jan 15 False", not should_fetch("pmi", datetime.date(2026, 1, 15)))
check("pmi on 28th True (month-end window)", should_fetch("pmi", datetime.date(2026, 8, 28)))
check("gdp in Feb False (quarter months only)", not should_fetch("gdp", datetime.date(2026, 2, 15)))
check("gdp in Jan window True", should_fetch("gdp", datetime.date(2026, 1, 16)))
check("industrial on Mar 15 True", should_fetch("industrial", datetime.date(2026, 3, 15)))
check("demographics in Aug False", not should_fetch("demographics", datetime.date(2026, 8, 9)))
check("demographics in Sep True", should_fetch("demographics", datetime.date(2026, 9, 9)))
check("fiscal mid-month True", should_fetch("fiscal", datetime.date(2026, 8, 15)))
check("fiscal before window False", not should_fetch("fiscal", datetime.date(2026, 8, 8)))
check("external_demand in window True", should_fetch("external_demand", datetime.date(2026, 8, 10)))
check("external_demand after window False", not should_fetch("external_demand", datetime.date(2026, 8, 20)))

print("\n=== 3. fail-open rules ===")
check("bond_yield always True (market)", should_fetch("bond_yield", datetime.date(2026, 8, 9)))
check("bond_yield True even with force=False", should_fetch("bond_yield", datetime.date(2026, 1, 23)))
check("force=True always True", all(should_fetch(t, datetime.date(2026, 8, 9), force=True) for t in TABLES))
check("lpr outside window but forced True", should_fetch("lpr", datetime.date(2026, 8, 23), force=True))
check("unknown table True (fail-open)", should_fetch("future_table", datetime.date(2026, 8, 9)))

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== RESULT ===")
if _failures:
    print(f"❌ {len(_failures)} FAILED: {_failures}")
    sys.exit(1)
print("✅ ALL CHECKS PASSED — release calendar gates incremental fetches")
