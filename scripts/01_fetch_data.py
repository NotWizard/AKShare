#!/usr/bin/env python3
"""
中国宏观经济数据采集脚本
从 AKShare 拉取所有宏观指标数据，清洗后存入 SQLite
"""

import sqlite3
import os
import sys
import time
import warnings
from datetime import datetime

import akshare as ak
import pandas as pd
import numpy as np
import requests

warnings.filterwarnings("ignore")

# allow `import _pipeline` whether run as a script or imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pipeline import (  # noqa: E402
    DB_PATH as _LIVE_DB,
    STAGING_PATH as _STAGING,
    iso_ts,
    backup_db,
    open_staging,
    commit_staging,
    discard_staging,
    write_manifest,
    run_derived,
    table_distinct_dates,
    validate,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "macro_data.db")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# Per-run audit manifest, populated by save_to_db and flushed by main().
_MANIFEST = {"ts": None, "akshare": None, "tables": {}}


def save_to_db(df, table_name, conn, if_exists="replace"):
    """Validation-gated write to the STAGING connection.

    A fetched df must clear validate() (non-empty, min_rows, required cols not
    all-NaN, no distinct-date erosion) before it may replace the table. On any
    failure the previously-good staging table is kept and the outcome recorded
    in _MANIFEST — bad data never overwrites good data.
    """
    prev = table_distinct_dates(conn, table_name)
    ok, reason = validate(df, table_name, prev)
    if not ok:
        _MANIFEST["tables"][table_name] = {
            "status": "kept_previous",
            "reason": reason,
            "prev_distinct_dates": prev,
        }
        log(f"  ⏭️  {table_name}: kept previous (prev {prev} dates) — {reason}")
        return
    df.to_sql(table_name, conn, if_exists=if_exists, index=False)
    _MANIFEST["tables"][table_name] = {
        "status": "updated",
        "new_rows": int(len(df)),
        "prev_distinct_dates": prev,
        "checks": "pass",
    }
    log(f"  ✅ {table_name}: {len(df)} rows → staging (prev {prev} dates)")


# ─────────────────────────────────────────────
# 1. 货币供应量 (M0/M1/M2)
# ─────────────────────────────────────────────
def fetch_money_supply(conn):
    log("采集: 货币供应量 M0/M1/M2 ...")
    df = ak.macro_china_supply_of_money()

    # 解析日期: "2026.5" → "2026-05-01"
    def parse_date(s):
        parts = str(s).split(".")
        if len(parts) == 2:
            return f"{parts[0]}-{int(parts[1]):02d}-01"
        return None

    result = pd.DataFrame({
        "date": [parse_date(x) for x in df["统计时间"]],
        "m2": pd.to_numeric(df["货币和准货币（广义货币M2）"], errors="coerce"),
        "m2_yoy": pd.to_numeric(df["货币和准货币（广义货币M2）同比增长"], errors="coerce"),
        "m1": pd.to_numeric(df["货币(狭义货币M1)"], errors="coerce"),
        "m1_yoy": pd.to_numeric(df["货币(狭义货币M1)同比增长"], errors="coerce"),
        "m0": pd.to_numeric(df["流通中现金(M0)"], errors="coerce"),
        "m0_yoy": pd.to_numeric(df["流通中现金(M0)同比增长"], errors="coerce"),
        "demand_deposit": pd.to_numeric(df.get("活期存款", pd.Series()), errors="coerce"),
        "time_deposit": pd.to_numeric(df.get("定期存款", pd.Series()), errors="coerce"),
        "savings": pd.to_numeric(df.get("储蓄存款", pd.Series()), errors="coerce"),
    })
    result = result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    save_to_db(result, "money_supply", conn)
    return result


# ─────────────────────────────────────────────
# 2. GDP (绝对值 + 同比增速)
# ─────────────────────────────────────────────
def fetch_gdp(conn):
    log("采集: GDP ...")
    df = ak.macro_china_gdp()

    # 解析季度日期: "2024年第1季度" → "2024-01-01"
    def parse_quarter(s):
        import re
        m = re.match(r"(\d{4})年第(\d)季度", str(s))
        if m:
            year, q = int(m.group(1)), int(m.group(2))
            month = (q - 1) * 3 + 1
            return f"{year}-{month:02d}-01"
        return None

    result = pd.DataFrame({
        "date": [parse_quarter(x) for x in df["季度"]],
        "gdp_abs": pd.to_numeric(df["国内生产总值-绝对值"], errors="coerce"),
        "gdp_yoy": pd.to_numeric(df["国内生产总值-同比增长"], errors="coerce"),
        "gdp_primary": pd.to_numeric(df.get("第一产业-绝对值", pd.Series()), errors="coerce"),
        "gdp_secondary": pd.to_numeric(df.get("第二产业-绝对值", pd.Series()), errors="coerce"),
        "gdp_tertiary": pd.to_numeric(df.get("第三产业-绝对值", pd.Series()), errors="coerce"),
    })
    result = result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    save_to_db(result, "gdp", conn)
    return result


# ─────────────────────────────────────────────
# 3. CPI 年率 + 月率 (东方财富)
# ─────────────────────────────────────────────
def _fetch_eastmoney(report_name: str, col_map: dict) -> pd.DataFrame:
    """Paginated fetch from eastmoney datacenter API."""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    headers = {"User-Agent": "Mozilla/5.0"}
    cols = ",".join(col_map.keys())
    page, frames = 1, []
    while True:
        params = {
            "reportName": report_name,
            "columns": cols,
            "pageNumber": str(page),
            "pageSize": "500",
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        r = requests.get(url, params=params, headers=headers, timeout=15)
        body = r.json()
        rows = (body.get("result") or {}).get("data")
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < 500:
            break
        page += 1
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df.rename(columns=col_map)


def fetch_cpi(conn):
    log("采集: CPI 年率 + 月率 ...")
    em = _fetch_eastmoney("RPT_ECONOMY_CPI", {
        "REPORT_DATE": "date",
        "NATIONAL_SAME": "cpi_yoy",
        "NATIONAL_SEQUENTIAL": "cpi_mom",
    })
    if em.empty:
        log("  ⚠️ 东方财富 CPI 无数据，保留旧表")
        return pd.DataFrame()
    em["date"] = pd.to_datetime(em["date"]).dt.strftime("%Y-%m-01")
    em["cpi_yoy"] = pd.to_numeric(em["cpi_yoy"], errors="coerce")
    em["cpi_mom"] = pd.to_numeric(em["cpi_mom"], errors="coerce")
    em = em.dropna(subset=["cpi_yoy"])

    # Keep old data for dates before eastmoney coverage
    em_min = em["date"].min()
    try:
        old = pd.read_sql(f"SELECT date, cpi_yoy, cpi_mom FROM cpi WHERE date < '{em_min}'", conn)
    except Exception:
        old = pd.DataFrame()

    result = pd.concat([old, em], ignore_index=True)
    result = result.drop_duplicates(subset=["date"], keep="last")
    result = result.sort_values("date").reset_index(drop=True)
    save_to_db(result, "cpi", conn)
    return result


# ─────────────────────────────────────────────
# 4. PPI 年率 (东方财富)
# ─────────────────────────────────────────────
def fetch_ppi(conn):
    log("采集: PPI 年率 ...")
    em = _fetch_eastmoney("RPT_ECONOMY_PPI", {
        "REPORT_DATE": "date",
        "BASE_SAME": "ppi_yoy",
    })
    if em.empty:
        log("  ⚠️ 东方财富 PPI 无数据，保留旧表")
        return pd.DataFrame()
    em["date"] = pd.to_datetime(em["date"]).dt.strftime("%Y-%m-01")
    em["ppi_yoy"] = pd.to_numeric(em["ppi_yoy"], errors="coerce")
    em = em.dropna(subset=["ppi_yoy"])

    em_min = em["date"].min()
    try:
        old = pd.read_sql(f"SELECT date, ppi_yoy FROM ppi WHERE date < '{em_min}'", conn)
    except Exception:
        old = pd.DataFrame()

    result = pd.concat([old, em], ignore_index=True)
    result = result.drop_duplicates(subset=["date"], keep="last")
    result = result.sort_values("date").reset_index(drop=True)
    save_to_db(result, "ppi", conn)
    return result


# ─────────────────────────────────────────────
# 5. PMI (官方 + 财新 + 非制造业)
# ─────────────────────────────────────────────
def fetch_pmi(conn):
    log("采集: PMI (官方 + 财新) ...")
    df_off = ak.macro_china_pmi_yearly()
    df_cx = ak.macro_china_cx_pmi_yearly()

    off = pd.DataFrame({
        "date": pd.to_datetime(df_off["日期"]).dt.strftime("%Y-%m-01"),
        "pmi_official": pd.to_numeric(df_off["今值"], errors="coerce"),
    }).dropna(subset=["pmi_official"])

    cx = pd.DataFrame({
        "date": pd.to_datetime(df_cx["日期"]).dt.strftime("%Y-%m-01"),
        "pmi_caixin": pd.to_numeric(df_cx["今值"], errors="coerce"),
    }).dropna(subset=["pmi_caixin"])

    # 非制造业 PMI
    try:
        df_non = ak.macro_china_non_man_pmi()
        non = pd.DataFrame({
            "date": pd.to_datetime(df_non["日期"]).dt.strftime("%Y-%m-01"),
            "pmi_non_mfg": pd.to_numeric(df_non["今值"], errors="coerce"),
        }).dropna(subset=["pmi_non_mfg"])
    except Exception:
        non = pd.DataFrame(columns=["date", "pmi_non_mfg"])

    # 财新服务业 PMI
    try:
        df_svc = ak.macro_china_cx_services_pmi_yearly()
        svc = pd.DataFrame({
            "date": pd.to_datetime(df_svc["日期"]).dt.strftime("%Y-%m-01"),
            "pmi_caixin_svc": pd.to_numeric(df_svc["今值"], errors="coerce"),
        }).dropna(subset=["pmi_caixin_svc"])
    except Exception:
        svc = pd.DataFrame(columns=["date", "pmi_caixin_svc"])

    result = off.merge(cx, on="date", how="outer") \
                .merge(non, on="date", how="outer") \
                .merge(svc, on="date", how="outer") \
                .sort_values("date").reset_index(drop=True)
    save_to_db(result, "pmi", conn)
    return result


# ─────────────────────────────────────────────
# 6. 宏观杠杆率 (CNBS)
# ─────────────────────────────────────────────
# NIFD（国家金融与发展实验室）季度杠杆率报告提取值（官方发布，非自算）。
# 出处见 scripts/03_supplement_leverage.py 头部报告链接；AKShare macro_cnbs 滞后时补齐。
_NIFD_DATA = [
    # date, household, non_fin_corp, gov_total,
    #   gov_central, gov_local, real_economy, fin_asset, fin_liability
    ("2025-03-01", 61.5, 173.7, 63.2, 26.4, 36.8, 298.4, 50.3, 69.4),
    ("2025-06-01", 61.1, 174.0, 65.3, 27.6, 37.8, 300.4, 51.7, 71.8),
    ("2025-09-01", 60.4, 174.4, 67.5, 28.8, 38.7, 302.3, 51.3, 73.4),
    ("2025-12-01", 59.4, 174.6, 68.4, 29.4, 39.1, 302.4, 50.5, 73.5),
    ("2026-03-01", 59.0, 180.0, 70.3, 29.9, 40.4, 309.3, None, None),
]
_NIFD_COLUMNS = [
    "date", "household", "non_fin_corp", "gov_total",
    "gov_central", "gov_local", "real_economy", "fin_asset", "fin_liability",
]


def _nifd_supplement_df() -> pd.DataFrame:
    return pd.DataFrame(_NIFD_DATA, columns=_NIFD_COLUMNS)


def fetch_leverage(conn):
    log("采集: 宏观杠杆率 ...")
    df = ak.macro_cnbs()

    # 解析季度日期: "1992-12" → "1992-12-01" (Q4), "1993-03" → "1993-03-01" (Q1)
    def parse_cnbs_date(s):
        parts = str(s).split("-")
        if len(parts) == 2:
            return f"{parts[0]}-{parts[1]}-01"
        return None

    result = pd.DataFrame({
        "date": [parse_cnbs_date(x) for x in df["年份"]],
        "household": pd.to_numeric(df["居民部门"], errors="coerce"),
        "non_fin_corp": pd.to_numeric(df["非金融企业部门"], errors="coerce"),
        "gov_total": pd.to_numeric(df["政府部门"], errors="coerce"),
        "gov_central": pd.to_numeric(df["中央政府"], errors="coerce"),
        "gov_local": pd.to_numeric(df["地方政府"], errors="coerce"),
        "real_economy": pd.to_numeric(df["实体经济部门"], errors="coerce"),
        "fin_asset": pd.to_numeric(df["金融部门资产方"], errors="coerce"),
        "fin_liability": pd.to_numeric(df["金融部门负债方"], errors="coerce"),
    })
    result = result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # Fold NIFD official quarterly leverage (report-extracted, not self-computed)
    # for dates newer than what ak.macro_cnbs() provides; goes through the same
    # gated save_to_db. date>cnbs_max filter means once AKShare catches up, the
    # NIFD rows for those dates drop out and fresher CNBS data supersedes them.
    cnbs_max = result["date"].max()
    nifd_new = _nifd_supplement_df()
    nifd_new = nifd_new[nifd_new["date"] > cnbs_max]
    if not nifd_new.empty:
        result = pd.concat([result, nifd_new], ignore_index=True)
        log(f"  ℹ️  leverage: +{len(nifd_new)} NIFD rows after CNBS max ({cnbs_max})")
    result = result.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    save_to_db(result, "leverage", conn)
    return result


# ─────────────────────────────────────────────
# 7. 社会融资规模增量
# ─────────────────────────────────────────────
def fetch_social_finance(conn):
    log("采集: 社会融资规模增量 ...")
    try:
        df = ak.macro_china_shrzgm()
        result = pd.DataFrame({
            "date": [f"{str(x)[:4]}-{str(x)[4:6]}-01" for x in df["月份"]],
            "total": pd.to_numeric(df["社会融资规模增量"], errors="coerce"),
            "rmb_loan": pd.to_numeric(df["其中-人民币贷款"], errors="coerce"),
            "entrusted_loan": pd.to_numeric(df["其中-委托贷款"], errors="coerce"),
            "trust_loan": pd.to_numeric(df["其中-信托贷款"], errors="coerce"),
            "acceptance_bill": pd.to_numeric(df["其中-未贴现银行承兑汇票"], errors="coerce"),
            "corp_bond": pd.to_numeric(df["其中-企业债券"], errors="coerce"),
            "equity": pd.to_numeric(df["其中-非金融企业境内股票融资"], errors="coerce"),
        })
        result = result.sort_values("date").reset_index(drop=True)
    except Exception as e:
        log(f"  ⚠️ 社融数据采集失败 (SSL问题): {e}")
        log(f"  → 请在正式 Python 环境中重新运行")
        result = pd.DataFrame()

    save_to_db(result, "social_finance", conn)
    return result


# ─────────────────────────────────────────────
# 8. LPR 利率
# ─────────────────────────────────────────────
def fetch_lpr(conn):
    log("采集: LPR 利率 ...")
    try:
        df = ak.macro_china_lpr()
        result = pd.DataFrame({
            "date": pd.to_datetime(df["TRADE_DATE"]).dt.strftime("%Y-%m-01"),
            "lpr_1y": pd.to_numeric(df["LPR1Y"], errors="coerce"),
            "lpr_5y": pd.to_numeric(df["LPR5Y"], errors="coerce"),
        })
        # 只保留有 LPR 数据的行 (2019年8月起)
        result = result.dropna(subset=["lpr_1y"]).sort_values("date").reset_index(drop=True)
    except Exception as e:
        log(f"  ⚠️ LPR 数据采集失败 (SSL问题): {e}")
        result = pd.DataFrame()

    save_to_db(result, "lpr", conn)
    return result


# ─────────────────────────────────────────────
# 9. 工业增加值
# ─────────────────────────────────────────────
def fetch_industrial(conn):
    log("采集: 工业增加值 ...")
    df = ak.macro_china_gyzjz()

    # 解析月份: "2008年02月份" → "2008-02-01"
    def parse_month(s):
        import re
        m = re.match(r"(\d{4})年(\d{2})月份", str(s))
        if m:
            return f"{m.group(1)}-{m.group(2)}-01"
        return None

    result = pd.DataFrame({
        "date": [parse_month(x) for x in df["月份"]],
        "ip_yoy": pd.to_numeric(df["同比增长"], errors="coerce"),
        "ip_cumulative": pd.to_numeric(df["累计增长"], errors="coerce"),
    })
    result = result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    save_to_db(result, "industrial", conn)
    return result


# ─────────────────────────────────────────────
# 10. 房价指数 (多城市)
# ─────────────────────────────────────────────
def fetch_house_price(conn):
    log("采集: 房价指数 (多城市) ...")
    cities = [
        ("北京", "上海"), ("广州", "深圳"),
        ("杭州", "成都"), ("南京", "武汉"),
        ("重庆", "天津"),
    ]
    all_dfs = []
    for c1, c2 in cities:
        try:
            df = ak.macro_china_new_house_price(city_first=c1, city_second=c2)
            all_dfs.append(df)
        except Exception as e:
            log(f"  ⚠️ {c1}/{c2} 失败: {e}")

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        result = pd.DataFrame({
            "date": pd.to_datetime(combined["日期"]).dt.strftime("%Y-%m-01"),
            "city": combined["城市"],
            "new_yoy": pd.to_numeric(combined["新建商品住宅价格指数-同比"], errors="coerce"),
            "new_mom": pd.to_numeric(combined["新建商品住宅价格指数-环比"], errors="coerce"),
            "new_base": pd.to_numeric(combined["新建商品住宅价格指数-定基"], errors="coerce"),
            "used_yoy": pd.to_numeric(combined["二手住宅价格指数-同比"], errors="coerce"),
            "used_mom": pd.to_numeric(combined["二手住宅价格指数-环比"], errors="coerce"),
            "used_base": pd.to_numeric(combined["二手住宅价格指数-定基"], errors="coerce"),
        })
        result = result.sort_values(["date", "city"]).reset_index(drop=True)
    else:
        result = pd.DataFrame()

    save_to_db(result, "house_price", conn)
    return result


# ─────────────────────────────────────────────
# 11. 居民人均可支配收入 / 人口（用于计算居民真实杠杆率）
# ─────────────────────────────────────────────
def fetch_household_income(conn):
    """Fetch national household disposable income (per capita) and population.

    Computes aggregate household disposable income (亿元) from NBS data.
    Falls back to an empty DataFrame if NBS is unreachable (common in some
    network environments due to SSL/geo-blocking).
    """
    log("采集: 居民可支配收入与人口 ...")

    def _parse_year_col(col):
        import re
        m = re.match(r"(\d{4})年", str(col))
        if m:
            return f"{m.group(1)}-01-01"
        return None

    income_df = pd.DataFrame()
    pop_df = pd.DataFrame()

    # 1) 居民人均可支配收入（元/人）
    try:
        df = ak.macro_china_nbs_nation(
            kind="年度数据",
            # NBS 目录树改版：收入指标收入「全国居民人均收入情况」三级分类下（原二级节点已不存在）
            path="人民生活 > 全国居民人均收入情况",
            period="LAST30",
        )
        # Find absolute-value per-capita row（排除中位数/增速/累计变体，新路径一次返回 12 个指标行）
        idx = [i for i in df.index if "居民人均可支配收入" in str(i) and "中位数" not in str(i) and "增长" not in str(i) and "累计" not in str(i)]
        if idx:
            row = df.loc[idx[0]]
            records = []
            for col, val in row.items():
                d = _parse_year_col(col)
                if d:
                    records.append({"date": d, "income_per_capita": pd.to_numeric(val, errors="coerce")})
            income_df = pd.DataFrame(records).dropna().sort_values("date").reset_index(drop=True)
            log(f"  ✅ 人均可支配收入: {len(income_df)} 年")
        else:
            log("  ⚠️ 未找到居民人均可支配收入指标行")
    except Exception as e:
        log(f"  ⚠️ 人均可支配收入采集失败: {e}")

    # 2) 总人口（万人）
    try:
        df = ak.macro_china_nbs_nation(
            kind="年度数据",
            path="人口 > 总人口",
            period="LAST30",
        )
        idx = [i for i in df.index if "总人口" in str(i)]
        if idx:
            row = df.loc[idx[0]]
            records = []
            for col, val in row.items():
                d = _parse_year_col(col)
                if d:
                    records.append({"date": d, "population_10k": pd.to_numeric(val, errors="coerce")})
            pop_df = pd.DataFrame(records).dropna().sort_values("date").reset_index(drop=True)
            log(f"  ✅ 总人口: {len(pop_df)} 年")
        else:
            log("  ⚠️ 未找到总人口指标行")
    except Exception as e:
        log(f"  ⚠️ 总人口采集失败: {e}")

    # 3) Merge and compute aggregate income (亿元).
    # Merge only when both sub-fetches returned data — a schema-less empty
    # DataFrame has no columns, so operating on it would raise KeyError. Empty
    # either way still flows through save_to_db, where the gate records it.
    merged = pd.DataFrame()
    if not income_df.empty and not pop_df.empty:
        merged = income_df.merge(pop_df, on="date", how="outer").sort_values("date")
        # income_per_capita(元) * population_10k(万人) / 10000 = 亿元
        merged["income_abs"] = merged["income_per_capita"] * merged["population_10k"] / 10000.0
        merged = merged.dropna(subset=["income_abs"]).reset_index(drop=True)
    save_to_db(merged, "household_income", conn)
    return merged


# ─────────────────────────────────────────────
# 12. 新增人民币贷款（社融数据的信用替代指标）
# ─────────────────────────────────────────────
def fetch_new_credit(conn):
    log("采集: 新增人民币贷款 ...")
    try:
        df = ak.macro_china_new_financial_credit()
        # 解析月份: "2026年5月份" → "2026-05-01"
        def parse_month(s):
            import re
            m = re.match(r"(\d{4})年(\d{1,2})月", str(s))
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-01"
            return None
        result = pd.DataFrame({
            "date": [parse_month(x) for x in df["月份"]],
            "new_rmb_loan": pd.to_numeric(df["当月"], errors="coerce"),
        })
        result = result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    except Exception as e:
        log(f"  ⚠️ 新增信贷数据采集失败: {e}")
        result = pd.DataFrame()

    save_to_db(result, "new_credit", conn)
    return result


# ─────────────────────────────────────────────
# 13. 10 年期国债收益率（中债信息网，并行年频采集 → 月频重采样）
# ─────────────────────────────────────────────
def fetch_bond_yield(conn):
    log("采集: 10 年期国债收益率 ...")
    from concurrent.futures import ThreadPoolExecutor
    from io import StringIO

    _CB_URL = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"
    _CB_HEADERS = {"User-Agent": "Mozilla/5.0"}

    def _fetch_year(year):
        params = {
            "startDate": f"{year}-01-01",
            "endDate": f"{year}-12-31",
            "gjqx": "0",
            "qxId": "ycqx",
            "locale": "cn_ZH",
        }
        try:
            r = requests.get(_CB_URL, params=params, headers=_CB_HEADERS,
                             verify=False, timeout=30)
            text = r.text.replace("&nbsp", "")
            dfs = pd.read_html(StringIO(text), header=0)
            df = dfs[1]
            gz = df[df["曲线名称"] == "中债国债收益率曲线"][["日期", "10年"]].copy()
            gz["10年"] = pd.to_numeric(gz["10年"], errors="coerce")
            return gz.dropna(subset=["10年"])
        except Exception:
            return pd.DataFrame()

    from datetime import datetime
    current_year = datetime.now().year
    years = list(range(2006, current_year + 1))

    with ThreadPoolExecutor(max_workers=6) as ex:
        frames = list(ex.map(_fetch_year, years))

    all_daily = pd.concat(frames, ignore_index=True)
    if all_daily.empty:
        log("  ⚠️ 国债收益率采集失败: 无数据")
        save_to_db(pd.DataFrame(), "bond_yield", conn)
        return pd.DataFrame()

    all_daily["date"] = pd.to_datetime(all_daily["日期"])
    all_daily["y_10y"] = all_daily["10年"]
    monthly = (
        all_daily.set_index("date")["y_10y"]
        .resample("ME").last().dropna()
        .reset_index()
    )
    monthly["date"] = monthly["date"].dt.strftime("%Y-%m-01")
    result = monthly[["date", "y_10y"]].sort_values("date").reset_index(drop=True)

    save_to_db(result, "bond_yield", conn)
    return result


# ─────────────────────────────────────────────
# 14. 人口与城镇化（NBS 年度数据）
# ─────────────────────────────────────────────
def fetch_demographics(conn):
    """年度人口指标：城镇化率 / 总人口 / 出生率 / 自然增长率。

    数据源：World Bank API（NBS data.stats.gov.cn 被 WAF 封禁 403）。
    指标映射：
        SP.POP.TOTL        → population（人 → 万人）
        SP.URB.TOTL.IN.ZS  → urbanization_rate（%）
        SP.DYN.CBRT.IN     → birth_rate（‰）
        SP.DYN.CDRT.IN     → death_rate（‰，用于计算 natural_growth_rate）
    """
    log("采集: 人口与城镇化（World Bank） ...")

    _WB_INDICATORS = {
        "SP.POP.TOTL":       "population",
        "SP.URB.TOTL.IN.ZS": "urbanization_rate",
        "SP.DYN.CBRT.IN":    "birth_rate",
        "SP.DYN.CDRT.IN":    "death_rate",
    }

    def _fetch_wb(indicator_code, col_name):
        try:
            url = f"https://api.worldbank.org/v2/country/CHN/indicator/{indicator_code}"
            r = requests.get(url, params={"format": "json", "per_page": 100}, timeout=60)
            r.raise_for_status()
            records = r.json()[1]
            rows = []
            for rec in records:
                if rec["value"] is not None:
                    rows.append({"date": f"{rec['date']}-01-01", col_name: float(rec["value"])})
            out = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
            log(f"  ✅ {col_name}: {len(out)} 年")
            return out
        except Exception as e:
            log(f"  ⚠️ {col_name} 采集失败: {e}")
            return pd.DataFrame()

    dfs = [_fetch_wb(code, col) for code, col in _WB_INDICATORS.items()]
    merged = pd.DataFrame({"date": sorted(set().union(*[d["date"].tolist() for d in dfs if not d.empty]))}) \
        if any(not d.empty for d in dfs) else pd.DataFrame()
    for d in dfs:
        if not d.empty:
            merged = merged.merge(d, on="date", how="left")

    if not merged.empty:
        merged["population"] = merged["population"] / 10000  # 人 → 万人
        merged["natural_growth_rate"] = merged["birth_rate"] - merged["death_rate"]
        merged = merged.drop(columns=["death_rate"])

    if merged.empty:
        log("  ⚠️ 人口数据全部不可用，跳过保存")
    save_to_db(merged, "demographics", conn)
    return merged


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    global _MANIFEST

    log("=" * 50)
    log("中国宏观经济数据采集开始 (staged + atomic)")
    log("=" * 50)

    # ① backup the live DB (recoverable)
    backup_db()
    # ② copy live → staging (old good data already present inside staging)
    staging = open_staging()
    conn = sqlite3.connect(staging)

    _MANIFEST = {"ts": iso_ts(), "akshare": getattr(ak, "__version__", "?"), "tables": {}}

    fetchers = [
        fetch_money_supply,
        fetch_gdp,
        fetch_cpi,
        fetch_ppi,
        fetch_pmi,
        fetch_leverage,
        fetch_social_finance,
        fetch_lpr,
        fetch_industrial,
        fetch_house_price,
        fetch_household_income,
        fetch_new_credit,
        fetch_bond_yield,
        fetch_demographics,
    ]

    for f in fetchers:
        name = f.__name__.replace("fetch_", "")
        try:
            f(conn)
        except Exception as e:
            log(f"  ❌ {f.__name__} 异常: {e}")
            _MANIFEST["tables"].setdefault(
                name, {"status": "kept_previous", "reason": f"{type(e).__name__}: {e}"}
            )

    # ③ recompute derived tables ON staging (raw + derived atomic together)
    try:
        run_derived(conn)
        _MANIFEST["derived"] = "recomputed"
    except Exception as e:
        log(f"  ⚠️ 衍生计算失败 (保留旧衍生表): {e}")
        _MANIFEST["derived"] = f"failed: {e}"

    conn.commit()
    conn.close()

    # ④ atomic promote staging → live (production DB touched exactly once)
    commit_staging()
    # ⑤ audit trail
    write_manifest(_MANIFEST)

    log("=" * 50)
    log("采集完成 (atomic commit): " + os.path.abspath(DB_PATH))
    updated = [t for t, v in _MANIFEST["tables"].items() if v.get("status") == "updated"]
    kept = [t for t, v in _MANIFEST["tables"].items() if v.get("status") == "kept_previous"]
    log(f"  updated {len(updated)}: {', '.join(updated) or '-'}")
    log(f"  kept_previous {len(kept)}: {', '.join(kept) or '-'}")
    log("=" * 50)


if __name__ == "__main__":
    main()
