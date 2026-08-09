"""Offline, deterministic verification of the dual-source comparison logic.

No network — pure tolerance/date-normalization logic.
Run:  .venv312/bin/python scripts/dual_sources_test.py
"""

import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dual_sources import (  # noqa: E402
    within_tolerance, _norm_jin10_date, _norm_ism_date, _gdp_q1_date,
)

_failures = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


print("\n=== 1. tolerance: rate (abs ≤0.3 OR rel ≤2%) ===")
check("abs branch: 1.0 vs 1.25 pass (Δ0.25)", within_tolerance(1.0, 1.25, "rate"))
check("abs boundary: 1.0 vs 1.3 pass (Δ0.3)", within_tolerance(1.0, 1.3, "rate"))
check("rel branch: 50 vs 51 pass (Δ1, rel 1.96%)", within_tolerance(50.0, 51.0, "rate"))
check("both fail: 1.0 vs 2.0 reject", not within_tolerance(1.0, 2.0, "rate"))
check("rel boundary out: 50 vs 51.2 reject (rel 2.33%)", not within_tolerance(50.0, 51.2, "rate"))
check("zeros: 0 vs 0 pass", within_tolerance(0.0, 0.0, "rate"))

print("\n=== 2. tolerance: level (rel ≤2%) ===")
check("2.0 vs 2.03 pass (rel 1.48%)", within_tolerance(2.0, 2.03, "level"))
check("2.0 vs 2.1 reject (rel 4.76%)", not within_tolerance(2.0, 2.1, "level"))
check("zeros: 0 vs 0 pass", within_tolerance(0.0, 0.0, "level"))

print("\n=== 3. Jin10 date normalization ===")
check("day=1 kept", _norm_jin10_date("2025-07-01") == "2025-07-01")
check("pub day → prev data month", _norm_jin10_date("2025-08-09") == "2025-07-01")
check("Jan publish → prev year Dec", _norm_jin10_date("2025-01-10") == "2024-12-01")
check("datetime.date input ok", _norm_jin10_date(datetime.date(2025, 9, 10)) == "2025-08-01")

print("\n=== 4. ISM date normalization (every row is a release date) ===")
check("pub on the 1st → prev month", _norm_ism_date("2025-08-01") == "2025-07-01")
check("pub on the 2nd → prev month", _norm_ism_date("2025-09-02") == "2025-08-01")
check("Jan release → prev year Dec", _norm_ism_date("1970-01-01") == "1969-12-01")

print("\n=== 5. GDP TIME only matches 第1季度 rows ===")
check("Q1 row matched", _gdp_q1_date("2026年第1季度") == "2026-01-01")
check("cumulative Q1-2 rejected", _gdp_q1_date("2026年第1-2季度") is None)
check("Q2 rejected", _gdp_q1_date("2025年第2季度") is None)
check("full-year rejected", _gdp_q1_date("2025年第1-4季度") is None)

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== RESULT ===")
if _failures:
    print(f"❌ {len(_failures)} FAILED: {_failures}")
    sys.exit(1)
print("✅ ALL CHECKS PASSED — dual-source comparison logic holds")
