"""NIFD 季度宏观杠杆率 —— 单一真相源 (G26 / P-M8)。

NIFD（国家金融与发展实验室）按季度发布宏观杠杆率报告，含居民 / 非金融企业 /
政府（中央+地方）完整分项。`ak.macro_cnbs()` 滞后时用于补齐（见
`01_fetch_data.fetch_leverage` 与 `03_supplement_leverage`）。

此前这份数据在 `01_fetch_data.py` 与 `03_supplement_leverage.py` 各存一份、
靠人工同步——两处极易漂移。现抽到本模块，二者都从这里取，改一处即可。

数据来源（NIFD 季度报告，官方发布、非自算；季度变化之和 = 全年涨幅，微小差异
≤0.1pp 来自报告四舍五入）：
  - NIFD 2025Q1 (2025-04-29): http://www.nifd.cn/SeriesReport/Details/4712
  - NIFD 2025Q2 (2025-07-30): http://www.nifd.cn/SeriesReport/Details/4728
  - NIFD 2025Q3 (2025-10-24): http://www.nifd.cn/SeriesReport/Details/4800
  - NIFD 2025Q4 (2026-01-26): http://www.nifd.cn/SeriesReport/Details/4851
  - NIFD 2026Q1 (2026-04-21): http://www.nifd.cn/SeriesReport/Details/4896
  - NIFD 2026Q2 (2026-07-30): 双源交叉验证
"""

import pandas as pd

# date, household, non_fin_corp, gov_total, gov_central, gov_local,
#   real_economy, fin_asset, fin_liability
NIFD_DATA = [
    ("2025-03-01", 61.5, 173.7, 63.2, 26.4, 36.8, 298.4, 50.3, 69.4),
    ("2025-06-01", 61.1, 174.0, 65.3, 27.6, 37.8, 300.4, 51.7, 71.8),
    ("2025-09-01", 60.4, 174.4, 67.5, 28.8, 38.7, 302.3, 51.3, 73.4),
    ("2025-12-01", 59.4, 174.6, 68.4, 29.4, 39.1, 302.4, 50.5, 73.5),
    ("2026-03-01", 59.0, 180.0, 70.3, 29.9, 40.4, 309.3, None, None),
    ("2026-06-01", 57.7, 179.5, 71.0, 30.5, 40.4, 308.2, None, None),
]

COLUMNS = [
    "date", "household", "non_fin_corp", "gov_total",
    "gov_central", "gov_local", "real_economy", "fin_asset", "fin_liability",
]


def nifd_supplement_df() -> pd.DataFrame:
    """NIFD 补充值 → DataFrame（列见 COLUMNS）。"""
    return pd.DataFrame(NIFD_DATA, columns=COLUMNS)
