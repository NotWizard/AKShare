#!/usr/bin/env python3
"""
补充宏观杠杆率数据（NIFD 季度报告）

ak.macro_cnbs() (AKShare) 数据滞后至 2024-Q4。
NIFD（国家金融与发展实验室）按季度发布宏观杠杆率报告，
包含居民/非金融企业/政府部门（中央+地方）完整分项数据。

本脚本从 NIFD 季度报告中提取的数据，补充至 leverage 表。

数据来源：
  - NIFD 2025Q1 报告 (2025-04-29): http://www.nifd.cn/SeriesReport/Details/4712
  - NIFD 2025Q2 报告 (2025-07-30): http://www.nifd.cn/SeriesReport/Details/4728
  - NIFD 2025Q3 报告 (2025-10-24): http://www.nifd.cn/SeriesReport/Details/4800
  - NIFD 2025Q4 报告 (2026-01-26): http://www.nifd.cn/SeriesReport/Details/4851
  - NIFD 2026Q1 报告 (2026-04-21): http://www.nifd.cn/SeriesReport/Details/4896

当 ak.macro_cnbs() 更新至 2025+ 数据后，fetch_leverage 会自动覆盖，
本脚本可保留作为手动补充参考。
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "macro_data.db")

# NIFD 季度报告提取的杠杆率数据
# 各季度数值已通过报告间交叉验证（季度变化之和 = 全年涨幅）
# 微小差异（≤0.1pp）来自 NIFD 报告四舍五入，脚注已说明
NIFD_DATA = [
    # date, household, non_fin_corp, gov_total, gov_central, gov_local,
    #   real_economy, fin_asset, fin_liability
    ("2025-03-01", 61.5, 173.7, 63.2, 26.4, 36.8, 298.4, 50.3, 69.4),
    ("2025-06-01", 61.1, 174.0, 65.3, 27.6, 37.8, 300.4, 51.7, 71.8),
    ("2025-09-01", 60.4, 174.4, 67.5, 28.8, 38.7, 302.3, 51.3, 73.4),
    ("2025-12-01", 59.4, 174.6, 68.4, 29.4, 39.1, 302.4, 50.5, 73.5),
    ("2026-03-01", 59.0, 180.0, 70.3, 29.9, 40.4, 309.3, None, None),
]

COLUMNS = [
    "date", "household", "non_fin_corp", "gov_total",
    "gov_central", "gov_local", "real_economy",
    "fin_asset", "fin_liability",
]


def supplement():
    conn = sqlite3.connect(DB_PATH)

    # Check existing data to avoid duplicate inserts
    existing = {row[0] for row in conn.execute("SELECT date FROM leverage")}
    inserted = 0
    skipped = 0

    for row in NIFD_DATA:
        if row[0] in existing:
            print(f"  ⏭️  {row[0]}: already exists, skipping")
            skipped += 1
            continue

        placeholders = ", ".join(["?"] * len(COLUMNS))
        col_list = ", ".join(COLUMNS)
        conn.execute(
            f"INSERT INTO leverage ({col_list}) VALUES ({placeholders})",
            row,
        )
        print(f"  ✅ {row[0]}: inserted (household={row[1]}, non_fin={row[2]}, gov={row[3]}, central={row[4]}, local={row[5]})")
        inserted += 1

    conn.commit()

    # Verify
    result = conn.execute(
        "SELECT date, household, non_fin_corp, gov_total, gov_central, gov_local "
        "FROM leverage ORDER BY date DESC LIMIT 10"
    ).fetchall()
    print(f"\nLatest 10 rows in leverage table:")
    for r in result:
        print(f"  {r[0]} | household={r[1]} | non_fin={r[2]} | gov={r[3]} | central={r[4]} | local={r[5]}")

    print(f"\nInserted: {inserted}, Skipped: {skipped}")
    conn.close()


if __name__ == "__main__":
    print("补充宏观杠杆率数据（NIFD 季度报告）...")
    supplement()
    print("完成")
