#!/usr/bin/env python3
"""Vintage diff — live vs 最近一份 vintage，回答"这次刷新到底改了什么"。

默认比对 data/macro_data.db 与 data/vintages/ 内按名排序最新的一份快照
（--vintage 指定基线，--json 输出 JSON）。逐表行数差 + CORE_SERIES 最新值差；
无差异（所有 delta=0 且同日期序列值差为 0/NaN）exit 0，否则 1——
便于 cron/人工一眼判断"这次刷新有没有真的改数据"。

Run:  .venv312/bin/python scripts/diff_vintage.py [--vintage PATH] [--json]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "macro_data.db"
VINTAGE_DIR = PROJECT_ROOT / "data" / "vintages"

# 核心序列（表, 列）：最新值差是刷新内容的最直接信号
CORE_SERIES = [
    ("money_supply", "m2_yoy"), ("cpi", "cpi_yoy"), ("ppi", "ppi_yoy"),
    ("gdp", "gdp_yoy"), ("pmi", "pmi_official"), ("social_finance", "total"),
    ("bond_yield", "y_10y"), ("leverage", "household"),
    ("fiscal", "revenue_cum"), ("external_demand", "exports_yoy"),
]

_EPS = 1e-9  # 浮点噪声容差（同库复制本应逐位相等）


def _tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")} - {"sqlite_sequence"}


def _row_count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    except sqlite3.Error:
        return 0


def _last_value(conn, table, col):
    """date 列定位，取 col 最后一个非空值 → (date, value)；表/列缺失返回 (None, None)。"""
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
    except sqlite3.Error:
        return None, None
    date_col = next((c for c in cols if c.lower() == "date"), None)
    if not date_col or col not in cols:
        return None, None
    row = conn.execute(
        f"SELECT [{date_col}], [{col}] FROM [{table}] "
        f"WHERE [{col}] IS NOT NULL ORDER BY [{date_col}] DESC LIMIT 1"
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def build_report(live_path, vintage_path):
    live = sqlite3.connect(f"file:{live_path}?mode=ro", uri=True)
    vint = sqlite3.connect(f"file:{vintage_path}?mode=ro", uri=True)
    try:
        tables = {}
        for t in sorted(_tables(live) | _tables(vint)):
            if t.startswith("sqlite_"):
                continue
            lr, vr = _row_count(live, t), _row_count(vint, t)
            tables[t] = {"live_rows": lr, "vintage_rows": vr, "delta": lr - vr}

        series = {}
        for t, col in CORE_SERIES:
            ld, lv = _last_value(live, t, col)
            vd, vv = _last_value(vint, t, col)
            if ld is None and vd is None:
                continue
            # diff = 同日期时 live−vintage；日期不同为 null（新旧月交替不算差异）
            diff = None
            if ld == vd and lv is not None and vv is not None:
                diff = round(lv - vv, 6)
            series[f"{t}.{col}"] = {
                "live_date": ld, "live_value": lv,
                "vintage_date": vd, "vintage_value": vv, "diff": diff,
            }
    finally:
        live.close()
        vint.close()

    changed = any(v["delta"] != 0 for v in tables.values())
    for s in series.values():
        if s["live_date"] != s["vintage_date"]:
            changed = True                      # 新增/回退月份 = 数据变了
        elif s["diff"] is not None and abs(s["diff"]) > _EPS:
            changed = True                      # 同日期值被修订
    return {"live": str(live_path), "vintage": str(vintage_path),
            "identical": not changed, "tables": tables, "series": series}


def main():
    parser = argparse.ArgumentParser(description="live vs vintage 差异比对")
    parser.add_argument("--vintage", help="基线 vintage 路径（默认取 vintages/ 最新一份）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认人类可读）")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"live DB 不存在: {DB_PATH}")
        return 0
    if args.vintage:
        vintage_path = Path(args.vintage)
        if not vintage_path.exists():
            print(f"vintage 路径不存在: {vintage_path}")
            return 0
    else:
        vintages = sorted(VINTAGE_DIR.glob("macro_data_*.db")) if VINTAGE_DIR.exists() else []
        if not vintages:
            print(f"无 vintage 快照（{VINTAGE_DIR} 为空）——首次运行后才有比对基线")
            return 0
        vintage_path = vintages[-1]

    report = build_report(DB_PATH, vintage_path)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"live:    {report['live']}")
        print(f"vintage: {report['vintage']}")
        print("\n表行数:")
        for t, v in report["tables"].items():
            print(f"  {t}: {v['vintage_rows']}→{v['live_rows']} ({v['delta']:+d})")
        if report["series"]:
            print("\n核心序列最新值:")
            for name, s in report["series"].items():
                print(f"  {name}: {s['vintage_value']} @{s['vintage_date']} "
                      f"→ {s['live_value']} @{s['live_date']}")
        print(f"\n{'无差异' if report['identical'] else '有差异'}")
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
