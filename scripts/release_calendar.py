"""发布日历驱动的增量抓取 — 纯函数，零依赖。

哪张表今天该不该抓，取决于官方发布节奏：release 型表只在发布窗口内抓
（窗口宁宽勿窄：误报成本是一次廉价抓取，验证闸门兜底；漏报成本是数据陈旧）；
market 型表（bond_yield）是日频市场数据，永远抓；未知表 fail-open，
新表永不被日历静默饿死。
"""

import datetime

# 每表：kind=release/market；months=发布月份；days=(起始日, 结束日) 窗口列表；
# channel=数据通道短名（健康灯 popover 展示用）。
TABLE_CALENDAR = {
    # 央行上月金融统计数据约每月 10–15 日发布；春节月偏移，窗口放宽自 9 日
    "money_supply": dict(kind="release", months=tuple(range(1, 13)), days=[(9, 17)], channel="pbc-akshare"),
    # NBS 季度 GDP 初值于季后月 15–18 日左右发布
    "gdp": dict(kind="release", months=(1, 4, 7, 10), days=[(10, 22)], channel="nbs-akshare"),
    # NBS 每月 9 日左右发布 CPI；东财数据中心镜像同步
    "cpi": dict(kind="release", months=tuple(range(1, 13)), days=[(8, 12)], channel="eastmoney"),
    # 与 CPI 同日发布
    "ppi": dict(kind="release", months=tuple(range(1, 13)), days=[(8, 12)], channel="eastmoney"),
    # 官方 PMI 当月最后一天、财新次月首个工作日，跨月 → 双窗口
    "pmi": dict(kind="release", months=tuple(range(1, 13)), days=[(1, 5), (25, 31)], channel="nbs-akshare"),
    # NIFD 季报约季后月 20–30 日；CNBS 经 AKShare 滞后且不定期 → 宽窗口兜底
    "leverage": dict(kind="release", months=(1, 4, 7, 10), days=[(10, 31)], channel="cnbs-akshare"),
    # 央行社融初值与金融统计同批（每月 10–15 日）
    "social_finance": dict(kind="release", months=tuple(range(1, 13)), days=[(9, 17)], channel="pbc-akshare"),
    # LPR 每月 20 日公布，遇节假日顺延
    "lpr": dict(kind="release", months=tuple(range(1, 13)), days=[(19, 22)], channel="pbc-akshare"),
    # NBS 规上工业增加值每月 15–16 日；1–2 月合并值 3 月中旬发布，窗口天然覆盖
    "industrial": dict(kind="release", months=tuple(range(1, 13)), days=[(12, 20)], channel="nbs-akshare"),
    # NBS 70 城房价每月 15–18 日；1、2 月照常单独发布
    "house_price": dict(kind="release", months=tuple(range(1, 13)), days=[(12, 20)], channel="nbs-akshare"),
    # NBS 年度数据/公报一季度发布；源现被 NBS WAF 封锁，窗口按真实节奏保留，失败经探针可见
    "household_income": dict(kind="release", months=(1, 2, 3), days=[(1, 31)], channel="nbs-akshare"),
    # 新增人民币贷款与社融同批金融统计数据
    "new_credit": dict(kind="release", months=tuple(range(1, 13)), days=[(9, 17)], channel="pbc-akshare"),
    # 中债信息网收益率曲线为日频市场数据，永远抓
    "bond_yield": dict(kind="market", months=(), days=[], channel="chinabond"),
    # World Bank WDI 年度指标约每年 9–10 月更新一次
    "demographics": dict(kind="release", months=(9, 10), days=[(1, 31)], channel="worldbank"),
    # 财政部约每月中旬发布上月财政收支数据（与 NBS 同步）
    "fiscal": dict(kind="release", months=tuple(range(1, 13)), days=[(10, 25)], channel="nbs-akshare"),
    # 海关总署约每月 7–14 日发布上月进出口（美元口径）
    "external_demand": dict(kind="release", months=tuple(range(1, 13)), days=[(7, 18)], channel="nbs-akshare"),
}


def should_fetch(table: str, today: datetime.date, force: bool = False) -> bool:
    """该表今天是否该抓。force/未知表/market 型恒 True（fail-open）。"""
    meta = TABLE_CALENDAR.get(table)
    if force or meta is None or meta["kind"] == "market":
        return True
    if today.month not in meta["months"]:
        return False
    return any(lo <= today.day <= hi for lo, hi in meta["days"])
