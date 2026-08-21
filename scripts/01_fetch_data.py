#!/usr/bin/env python3
"""
中国宏观经济数据采集脚本
从 AKShare 拉取所有宏观指标数据，清洗后存入 SQLite
"""

import argparse
import json
import logging
import sqlite3
import os
import sys
import time
import warnings
from datetime import date, datetime
from logging.handlers import RotatingFileHandler

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
    MANIFEST_PATH,
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
from release_calendar import TABLE_CALENDAR, should_fetch  # noqa: E402
import dual_sources  # noqa: E402
from signal_history import append_signal_history  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "macro_data.db")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# Structured run logger, separate from the human-facing stdout `log()` above
# (which the refresh driver parses for ✅ progress). Emits to stderr so a failed
# run leaves a record even when stdout is discarded; a partial failure logs an
# ERROR line. Messages stay plain ASCII so they never trip the driver's stdout
# parsing (no ✅, no "计划抓取 N/").
logger = logging.getLogger("fetch_data")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _sh = logging.StreamHandler(sys.stderr)
    _sh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(_sh)
    logger.propagate = False


def _attach_file_log():
    """Best-effort: also persist run logs to data/logs/fetch.log (rotating) so a
    scheduled run whose stderr is discarded still leaves a durable record. A
    logging-setup failure must never abort a data run."""
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(os.path.join(log_dir, "fetch.log"),
                                 maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    except Exception:
        pass


# Per-run audit manifest, populated by save_to_db and flushed by main().
_MANIFEST = {"ts": None, "akshare": None, "tables": {}, "sources": []}


def _read_prev_manifest():
    """读上次 data/last_run.json（任何读取失败视为空），用于沿用 sources 的
    consecutive_failures / last_success。模式同 core/refresh.read_manifest_summary。"""
    try:
        m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return m if isinstance(m, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


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

    # 解析季度日期: "2024年第1季度" → "2024-01-01"; 累计 "2026年第1-2季度" → 末季 "2026-04-01"
    def parse_quarter(s):
        import re
        m = re.match(r"(\d{4})年第(\d)(?:-(\d))?季度", str(s))
        if m:
            year = int(m.group(1))
            q = int(m.group(3) or m.group(2))   # 累计取末季
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
        save_to_db(pd.DataFrame(), "cpi", conn)  # 记 kept_previous → 计入退出码/健康灯
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
def _derive_ppi_mom(df: pd.DataFrame) -> pd.DataFrame:
    """由 PPI 同比重建定基指数、再求环比(%)。

    东财/akshare 均无免费 PPI 环比源（东财只有同比 BASE_SAME），
    此为行业标准的同比→定基→环比推导（P_t = P_{t-12}×(1+同比)），
    用户确认接受推导；前端图注标明"推导值"。
    """
    level, rows = {}, []
    prev_dt = None
    for _, r in df.sort_values("date").iterrows():
        dt = pd.to_datetime(r["date"]); yoy = r["ppi_yoy"]
        y12 = dt - pd.DateOffset(months=12)
        if pd.notna(yoy) and y12 in level:
            lv = level[y12] * (1 + yoy / 100)
        elif pd.notna(yoy):
            lv = 100.0                      # 种子月
        else:
            lv = level.get(prev_dt)         # 同比缺失→沿用上期水平
        if lv is not None:
            level[dt] = lv
            if prev_dt is not None and prev_dt in level and level[prev_dt]:
                rows.append((r["date"], (lv / level[prev_dt] - 1) * 100))
        prev_dt = dt
    return pd.DataFrame(rows, columns=["date", "ppi_mom"])


def fetch_ppi(conn):
    log("采集: PPI 年率 ...")
    em = _fetch_eastmoney("RPT_ECONOMY_PPI", {
        "REPORT_DATE": "date",
        "BASE_SAME": "ppi_yoy",
    })
    if em.empty:
        log("  ⚠️ 东方财富 PPI 无数据，保留旧表")
        save_to_db(pd.DataFrame(), "ppi", conn)  # 记 kept_previous → 计入退出码/健康灯
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
    # PPI 环比(推导值): 无免费直接源, 由同比重建定基指数再求环比, 图注标明推导值
    result = result.merge(_derive_ppi_mom(result), on="date", how="left")
    save_to_db(result, "ppi", conn)
    return result


# ─────────────────────────────────────────────
# 5. PMI (官方 + 财新 + 非制造业)
# ─────────────────────────────────────────────
def fetch_pmi(conn):
    log("采集: PMI (官方/非制造业=东财, 财新/财新服务=akshare) ...")
    # 官方 + 非制造业 PMI: 东财 RPT_ECONOMY_PMI（当前；akshare macro_china_pmi_yearly
    # 滞后约一年，同杠杆率同款"源滞后"）。东财无数据时回退 akshare。
    em = _fetch_eastmoney("RPT_ECONOMY_PMI", {
        "REPORT_DATE": "date", "MAKE_INDEX": "pmi_official", "NMAKE_INDEX": "pmi_non_mfg",
    })
    df_cx = ak.macro_china_cx_pmi_yearly()

    # akshare 官方/非制造业 = 全历史(2005+)底；东财(2008+ 更当前) 覆盖近期，
    # 合并避免切源丢掉 2008 前历史（审查发现的回归）。
    df_off = ak.macro_china_pmi_yearly()
    off_ak = pd.DataFrame({
        "date": pd.to_datetime(df_off["日期"]).dt.strftime("%Y-%m-01"),
        "pmi_official": pd.to_numeric(df_off["今值"], errors="coerce"),
    }).dropna(subset=["pmi_official"])
    try:
        df_non = ak.macro_china_non_man_pmi()
        non_ak = pd.DataFrame({
            "date": pd.to_datetime(df_non["日期"]).dt.strftime("%Y-%m-01"),
            "pmi_non_mfg": pd.to_numeric(df_non["今值"], errors="coerce"),
        }).dropna(subset=["pmi_non_mfg"])
    except Exception:
        non_ak = pd.DataFrame(columns=["date", "pmi_non_mfg"])

    if em.empty:
        log("  ⚠️ 东财 PMI 无数据，官方/非制造业仅用 akshare")
        off, non = off_ak, non_ak
    else:
        em2 = pd.DataFrame({
            "date": pd.to_datetime(em["date"]).dt.strftime("%Y-%m-01"),
            "pmi_official": pd.to_numeric(em["pmi_official"], errors="coerce"),
            "pmi_non_mfg": pd.to_numeric(em["pmi_non_mfg"], errors="coerce"),
        }).dropna(subset=["pmi_official"])
        # 东财优先(更当前), akshare 补东财没有的早期月份
        off = em2[["date", "pmi_official"]].merge(off_ak, on="date", how="outer", suffixes=("_em", "_ak"))
        off["pmi_official"] = off["pmi_official_em"].combine_first(off["pmi_official_ak"])
        off = off[["date", "pmi_official"]].dropna(subset=["pmi_official"])
        non = em2[["date", "pmi_non_mfg"]].dropna(subset=["pmi_non_mfg"]).merge(
            non_ak, on="date", how="outer", suffixes=("_em", "_ak"))
        non["pmi_non_mfg"] = non["pmi_non_mfg_em"].combine_first(non["pmi_non_mfg_ak"])
        non = non[["date", "pmi_non_mfg"]].dropna(subset=["pmi_non_mfg"])

    cx = pd.DataFrame({
        "date": pd.to_datetime(df_cx["日期"]).dt.strftime("%Y-%m-01"),
        "pmi_caixin": pd.to_numeric(df_cx["今值"], errors="coerce"),
    }).dropna(subset=["pmi_caixin"])

    # 财新服务业 PMI（东财无财新口径，仍用 akshare）
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
    ("2026-06-01", 57.7, 179.5, 71.0, 30.5, 40.4, 308.2, None, None),  # NIFD 2026Q2 (2026-07-30 发布, 双源交叉验证)
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
def _pbc_shrzgm_supplement_df() -> pd.DataFrame:
    """PBoC 调查统计司 社融增量 XLSX 备用源（akshare shrzgm 滞后时补齐）。解析失败返回空。"""
    import re, io, requests
    try:
        import datetime
        yr = datetime.date.today().year
        hrefs = []
        for y in (yr, yr - 1):
            lu = f"http://www.pbc.gov.cn/diaochatongjisi/116219/116319/{y}ntjsj/shrzgm/index.html"
            try:
                r = requests.get(lu, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
                hrefs = re.findall(r'(attachDir/[^"\'\s]+\.xlsx)', r.text)
                if hrefs:
                    break
            except Exception:
                continue
        if not hrefs:
            return pd.DataFrame()
        xls = None; hdr = None
        for h in hrefs[:4]:   # 选增量表(title 含"增量")且有列头行(含"人民币贷款")
            try:
                xr = requests.get("http://www.pbc.gov.cn/diaochatongjisi/" + h,
                                  headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                x = pd.read_excel(io.BytesIO(xr.content), header=None)
                if not any("增量" in str(v) for v in x.iloc[0]):
                    continue
                hd = next((i for i in range(min(20, len(x)))
                           if any("人民币贷款" in str(v) for v in x.iloc[i])), None)
                if hd is not None:
                    xls, hdr = x, hd; break
            except Exception:
                continue
        if xls is None or hdr is None:
            return pd.DataFrame()
        cols = [str(v) for v in xls.iloc[hdr]]
        def colidx(*names):
            for n in names:
                for j, c in enumerate(cols):
                    if n in c:
                        return j
            return None
        idx = {k: colidx(*ns) for k, ns in {
            "total": ("社会融资规模增量", "社会融资规模"), "rmb_loan": ("人民币贷款",), "entrusted_loan": ("委托贷款",),
            "trust_loan": ("信托贷款",), "acceptance_bill": ("未贴现",), "corp_bond": ("企业债券",),
            "equity": ("股票",)}.items()}
        rows = []
        for i in range(hdr + 1, len(xls)):
            mo = xls.iloc[i, 0]
            try:
                y = int(mo); month = round((float(mo) - y) * 100)   # 2026.05→5; 2026.1→10
            except Exception:
                continue
            if not (1 <= month <= 12):
                continue
            def gv(j):
                if j is None:
                    return None
                v = pd.to_numeric(xls.iloc[i, j], errors="coerce")
                return None if pd.isna(v) else float(v)
            rows.append({"date": f"{y}-{month:02d}-01", **{k: gv(j) for k, j in idx.items()}})
        return pd.DataFrame(rows)
    except Exception as e:
        log(f"  ⚠️ PBoC 社融补充失败, 保留主源: {type(e).__name__}")
        return pd.DataFrame()


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

    # PBoC 官方 XLSX 备用源: 仅追加比主源更新的月份(如主源滞后时的 2026-05/06)
    sup = _pbc_shrzgm_supplement_df()
    if not sup.empty:
        base_max = result["date"].max() if not result.empty else None
        if base_max is not None:
            sup = sup[sup["date"] > base_max]
        sup = sup.dropna(subset=["total"])   # 不追加未发布月份(NaN)
        if not sup.empty:
            result = pd.concat([result, sup], ignore_index=True).sort_values("date").reset_index(drop=True)
            log(f"  ℹ️ 社融 PBoC 补充 {len(sup)} 行 (>{base_max})")

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
def _nbs_population() -> "pd.DataFrame | None":
    """NBS 官方总人口/城镇化率。返回表以指标名为行(年末总人口/城镇人口/…)、年份为列。失败返回 None。"""
    try:
        d = ak.macro_china_nbs_nation(kind="年度数据", path="人口 > 总人口", period="LAST30")
        def row_of(key):
            for idx in d.index:
                if key in str(idx):
                    return d.loc[idx]
            return None
        total_r, urban_r = row_of("年末总人口"), row_of("城镇人口")
        if total_r is None or urban_r is None:
            return None
        years = [c for c in d.columns if "年" in str(c)]
        rows = []
        for y in years:
            t, u = float(total_r[y]), float(urban_r[y])
            rows.append({"date": f"{str(y).replace('年', '')}-01-01",
                         "population": t, "urbanization_rate": u / t * 100})
        return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    except Exception as e:
        log(f"  ⚠️ NBS 人口失败, 回退 World Bank: {type(e).__name__}")
        return None


def fetch_demographics(conn):
    """年度人口指标：城镇化率 / 总人口 / 出生率 / 自然增长率。

    人口/城镇化率优先 NBS 官方（与统计局公报一致），World Bank 回退；
    出生率/自然增长率用 World Bank（NBS 经 akshare 无可用 path）。
    """
    log("采集: 人口与城镇化（NBS 优先, World Bank 回退） ...")

    def _fetch_wb(indicator_code, col_name):
        try:
            url = f"https://api.worldbank.org/v2/country/CHN/indicator/{indicator_code}"
            r = requests.get(url, params={"format": "json", "per_page": 100}, timeout=60)
            r.raise_for_status()
            rows = [{"date": f"{rec['date']}-01-01", col_name: float(rec["value"])}
                    for rec in r.json()[1] if rec["value"] is not None]
            out = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
            log(f"  ✅ {col_name}: {len(out)} 年")
            return out
        except Exception as e:
            log(f"  ⚠️ {col_name} 采集失败: {e}")
            return pd.DataFrame()

    wp = _fetch_wb("SP.POP.TOTL", "population")
    wu = _fetch_wb("SP.URB.TOTL.IN.ZS", "urbanization_rate")
    base = wp.merge(wu, on="date", how="outer")
    base["population"] = base["population"] / 10000  # 人 → 万人
    nbs = _nbs_population()
    if nbs is not None:
        # NBS 官方值覆盖近年, WB 补长历史 → 年份数不缩水(过闸门)且近年值准确
        pop_urb = nbs.set_index("date").combine_first(base.set_index("date")).reset_index()
        log(f"  ✅ population/urbanization: NBS 覆盖近年 + WB 长历史, {len(pop_urb)} 年")
    else:
        pop_urb = base

    birth = _fetch_wb("SP.DYN.CBRT.IN", "birth_rate")
    death = _fetch_wb("SP.DYN.CDRT.IN", "death_rate")
    merged = pop_urb
    for d in (birth, death):
        if not d.empty:
            merged = merged.merge(d, on="date", how="left")
    if "birth_rate" in merged.columns and "death_rate" in merged.columns:
        merged["natural_growth_rate"] = merged["birth_rate"] - merged["death_rate"]
        merged = merged.drop(columns=["death_rate"])

    # NBS 统计公报官方出生率/自然增长率（NBS API 被 WAF 封禁、akshare 无可用 path，手工补官方值）。
    # 来源：《中华人民共和国2025年国民经济和社会发展统计公报》(2026-02-28)。
    _NBS_BIRTH_NATURAL = {
        "2025-01-01": (5.63, -2.41),
    }
    for d, (b, n) in _NBS_BIRTH_NATURAL.items():
        m = merged["date"] == d
        if m.any():
            merged.loc[m, "birth_rate"] = b
            merged.loc[m, "natural_growth_rate"] = n

    if merged.empty:
        log("  ⚠️ 人口数据全部不可用，跳过保存")
    save_to_db(merged, "demographics", conn)
    return merged


# ─────────────────────────────────────────────
# 15. 财政收支（NBS 月度预算收入/支出，2015- 起）
# ─────────────────────────────────────────────
def _parse_nbs_month(s):
    import re
    m = re.match(r"(\d{4})年(\d{1,2})月", str(s))
    return f"{m.group(1)}-{int(m.group(2)):02d}-01" if m else None


def _nbs_long(df):
    """NBS 指标×月份宽表（指标为行、月份为列）→ (date, indicator, value) 长表。"""
    records = []
    for ind in df.index:
        for col, val in df.loc[ind].items():
            d = _parse_nbs_month(col)
            if d:
                records.append({"date": d, "indicator": str(ind),
                                "value": pd.to_numeric(val, errors="coerce")})
    return pd.DataFrame(records)


def _nbs_cum_yoy(df, cum_col, yoy_col):
    """NBS 两指标行（…累计值 / …累计增长）→ date×两列。指标名按子串匹配（容忍单位后缀）。"""
    long = _nbs_long(df)
    out = pd.DataFrame({"date": sorted(set(long["date"]))})
    for kw, col in [("累计值", cum_col), ("增长", yoy_col)]:
        sub = long[long["indicator"].str.contains(kw)].groupby("date")["value"].last().reset_index()
        if not sub.empty:
            out = out.merge(sub.rename(columns={"value": col}), on="date", how="left")
    return out


def fetch_fiscal(conn):
    """国家财政预算收入/支出（NBS 月度）。两路径各自长表化后按月外连接。
    NBS 不可达 → 空 df → 闸门记 kept_previous（与 household_income 同款降级）。"""
    log("采集: 财政收支（NBS 月度） ...")
    wides = []
    for path, cum_col, yoy_col in [
        ("财政 > 国家财政预算收入", "revenue_cum", "revenue_cum_yoy"),
        ("财政 > 国家财政预算支出", "expenditure_cum", "expenditure_cum_yoy"),
    ]:
        try:
            df = ak.macro_china_nbs_nation(kind="月度数据", path=path, period="2015-")
            wides.append(_nbs_cum_yoy(df, cum_col, yoy_col))
        except Exception as e:
            log(f"  ⚠️ {path} 采集失败: {e}")

    if not wides:
        save_to_db(pd.DataFrame(), "fiscal", conn)
        return pd.DataFrame()
    result = wides[0]
    for w in wides[1:]:
        result = result.merge(w, on="date", how="outer")
    result = result.sort_values("date").reset_index(drop=True)
    save_to_db(result, "fiscal", conn)
    return result


# ─────────────────────────────────────────────
# 16. 外需（NBS 货物进出口美元口径 + 美国 ISM 制造业 PMI）
# ─────────────────────────────────────────────
def fetch_external_demand(conn):
    """NBS「对外经济 > 货物进出口总额」（千美元 → fetcher 内 ÷1e5 亿美元）+
    ISM PMI（外需景气代理，Jin10 源冻结于 2025-08 数据月，近期自然为 NaN）。"""
    log("采集: 外需（NBS 货物进出口 + 美国 ISM PMI） ...")
    # NBS 指标名带单位后缀（千美元)/(%)）→ 按前缀匹配
    trade_map = {
        "出口总值_当期值": ("exports", 1e5),
        "出口总值_同比增长": ("exports_yoy", 1),
        "进口总值_当期值": ("imports", 1e5),
        "进口总值_同比增长": ("imports_yoy", 1),
        "进出口总值_同比增长": ("trade_total_yoy", 1),
        "进出口差额_当期值": ("trade_balance", 1e5),
    }
    try:
        df = ak.macro_china_nbs_nation(kind="月度数据", path="对外经济 > 货物进出口总额", period="2015-")
        long = _nbs_long(df)
    except Exception as e:
        log(f"  ⚠️ NBS 货物进出口采集失败: {e}")
        long = pd.DataFrame()

    if long.empty:
        save_to_db(pd.DataFrame(), "external_demand", conn)
        return pd.DataFrame()

    result = pd.DataFrame({"date": sorted(set(long["date"]))})
    for kw, (col, scale) in trade_map.items():
        sub = long[long["indicator"].str.startswith(kw)].groupby("date")["value"].last().reset_index()
        if not sub.empty:
            sub["value"] = (sub["value"] / scale).round(2)
            result = result.merge(sub.rename(columns={"value": col}), on="date", how="left")

    trade_start = result["date"].iloc[0]  # 贸易块日期域下界（裁 ISM 全史用）

    # ISM 失败仅丢该列，不影响贸易块。ISM 日期恒为发布日（含 1 日）→ 数据月
    # 永远是上月（_norm_ism_date）；若误用 day==1 保留规则会把「8月1日发布」
    # 留在 8 月并与「9月2日发布→8月」撞成重复日期
    try:
        df_ism = ak.macro_usa_ism_pmi()
        ism = pd.DataFrame({
            "date": [dual_sources._norm_ism_date(x) for x in df_ism["日期"]],
            "us_ism_pmi": pd.to_numeric(df_ism["今值"], errors="coerce"),
        }).dropna(subset=["us_ism_pmi"])
        ism = ism.drop_duplicates(subset=["date"], keep="last")
        result = result.merge(ism, on="date", how="outer")
    except Exception as e:
        log(f"  ⚠️ 美国 ISM PMI 采集失败: {e}")

    # ISM 官方补充：akshare 的 Jin10 源冻结于 2025-08；以下为 ISM 官方
    # （PR Newswire 月度发布）值，手工/Agent 按月维护（见 data-supplement-runbook）。
    _ISM_SUPPLEMENT = {
        "2025-09-01": 49.1, "2025-10-01": 48.7, "2025-11-01": 48.2, "2025-12-01": 47.9,
        "2026-01-01": 52.6, "2026-02-01": 52.4, "2026-03-01": 52.7, "2026-04-01": 52.7,
        "2026-05-01": 54.0, "2026-06-01": 53.3, "2026-07-01": 55.6,
    }
    have = set(result["date"])
    for d, v in _ISM_SUPPLEMENT.items():
        if d in have:
            result.loc[result["date"] == d, "us_ism_pmi"] = v
        else:
            result = pd.concat([result, pd.DataFrame([{"date": d, "us_ism_pmi": v}])],
                               ignore_index=True)

    result = result.sort_values("date").reset_index(drop=True)
    # ISM 外连接带入 1970 起全史（~540 行冗余）→ 裁到贸易日期域，
    # ISM 保留与贸易重叠段（2015+），外需页语境足够
    result = result[result["date"] >= trade_start].reset_index(drop=True)
    save_to_db(result, "external_demand", conn)
    return result


# ─────────────────────────────────────────────
# 退出码汇总
# ─────────────────────────────────────────────
def compute_exit_code(manifest: dict) -> int:
    """Aggregate the process exit code from the run manifest.

    A table appears in ``manifest['tables']`` ONLY if it was actually attempted
    this run — written by ``save_to_db`` (updated / kept_previous) or by main()'s
    fetcher-exception handler (kept_previous). A table skipped because it's
    outside its release window is never added there; it is only carried over in
    ``manifest['sources']``. Therefore a ``kept_previous`` entry in
    ``manifest['tables']`` is unambiguously a REAL fetch/validate failure this
    run — never an in-window skip.

    Returns 2 (partial failure) when any attempted table ended ``kept_previous``,
    else 0 (fully clean)."""
    tables = manifest.get("tables", {}) or {}
    failed = [t for t, v in tables.items()
              if isinstance(v, dict) and v.get("status") == "kept_previous"]
    return 2 if failed else 0


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="中国宏观经济数据采集（默认按发布日历增量，--full 全量）")
    parser.add_argument("--full", action="store_true", help="跳过发布日历，抓取全部表")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    _attach_file_log()
    global _MANIFEST

    log("=" * 50)
    log("中国宏观经济数据采集开始 (staged + atomic)")
    log("=" * 50)

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
        fetch_fiscal,
        fetch_external_demand,
    ]

    # 抓取计划：release 型表只在发布窗口内抓，market/未知表恒抓（见 release_calendar）
    today = date.today()
    selected = [(f.__name__.replace("fetch_", ""), f) for f in fetchers
                if should_fetch(f.__name__.replace("fetch_", ""), today, args.full)]
    log(f"📋 计划抓取 {len(selected)}/{len(fetchers)} 表（{'全量' if args.full else '增量'}）")
    if not selected:
        log("窗口内无表，跳过")
        return 0

    # 上次运行的 sources（窗口外跳过的表整条沿用：不增不减，last_success 保持真实）
    prev_sources = {s.get("table"): s for s in _read_prev_manifest().get("sources", [])
                     if isinstance(s, dict)}

    # ① backup the live DB (recoverable)
    backup_db()
    # ② copy live → staging (old good data already present inside staging)
    staging = open_staging()
    conn = sqlite3.connect(staging)

    ts = iso_ts()
    _MANIFEST = {"ts": ts, "akshare": getattr(ak, "__version__", "?"), "tables": {}, "sources": []}

    for name, f in selected:
        t0 = time.time()
        ok, err = True, None
        try:
            f(conn)
        except Exception as e:
            ok, err = False, f"{type(e).__name__}: {e}"
            log(f"  ❌ {f.__name__} 异常: {e}")
            _MANIFEST["tables"].setdefault(
                name, {"status": "kept_previous", "reason": f"{type(e).__name__}: {e}"}
            )
        # ok 仅表示 fetcher 是否抛异常；验证闸门拒收走 kept_previous warning（后端推导）
        prev = prev_sources.get(name, {})
        _MANIFEST["sources"].append({
            "table": name,
            "channel": TABLE_CALENDAR.get(name, {}).get("channel", ""),
            "ok": ok,
            "elapsed_s": round(time.time() - t0, 2),
            "error": err[:200] if err else None,  # 截断防膨胀
            "consecutive_failures": 0 if ok else prev.get("consecutive_failures", 0) + 1,
            "last_success": ts if ok else prev.get("last_success"),
        })

    # sources 最终按 fetchers 顺序：本次抓取的 + 窗口外沿用上次整条的
    fetched = {s["table"]: s for s in _MANIFEST["sources"]}
    ordered = []
    for f in fetchers:
        entry = fetched.get(f.__name__.replace("fetch_", "")) or prev_sources.get(f.__name__.replace("fetch_", ""))
        if entry:
            ordered.append(entry)
    _MANIFEST["sources"] = ordered

    # 双源比对：只对本次抓取成功（primary 有更新）的表跑；只读 staging，
    # 永不覆盖 primary；结果并入 sources[].dual（divergence 由后端转黄灯）
    try:
        fetched_ok = {t for t, s in fetched.items() if s.get("ok")}
        duals = dual_sources.run_checks(conn, fetched_ok)
        for s in _MANIFEST["sources"]:
            if s["table"] in duals:
                s["dual"] = duals[s["table"]]
    except Exception as e:
        log(f"  ⚠️ 双源比对失败（不影响数据）: {e}")

    # ③ recompute derived tables ON staging (raw + derived atomic together)
    try:
        run_derived(conn)
        _MANIFEST["derived"] = "recomputed"
    except Exception as e:
        log(f"  ⚠️ 衍生计算失败 (保留旧衍生表): {e}")
        _MANIFEST["derived"] = f"failed: {e}"

    conn.commit()
    conn.close()

    # ④ atomic promote staging → live (production DB touched exactly once);
    # commit 前把旧 live 复制为 vintage（审计快照，供 diff_vintage 比对）
    vintage = commit_staging()
    if vintage:
        _MANIFEST["vintage"] = f"data/vintages/{vintage.name}"
    # ⑤ audit trail
    write_manifest(_MANIFEST)

    # ⑥ 信号历史快照：commit 后追加，失败仅告警不影响已提交数据
    # （日志行不含 ✅——refresh.py 进度计数依赖 ✅ 行数）
    try:
        append_signal_history(DB_PATH, ts)
        log("📈 signal_history: +1 行（composite+四相位）")
    except Exception as e:
        log(f"  ⚠️ signal_history 写入失败（不影响数据）: {e}")

    log("=" * 50)
    log("采集完成 (atomic commit): " + os.path.abspath(DB_PATH))
    updated = [t for t, v in _MANIFEST["tables"].items() if v.get("status") == "updated"]
    kept = [t for t, v in _MANIFEST["tables"].items() if v.get("status") == "kept_previous"]
    log(f"  updated {len(updated)}: {', '.join(updated) or '-'}")
    log(f"  kept_previous {len(kept)}: {', '.join(kept) or '-'}")
    log("=" * 50)

    # Aggregate exit code: any kept_previous table this run = real fetch/validate
    # failure → nonzero, so run_refresh / cron / launchd actually see the failure
    # (previously main() always fell through to exit 0, hiding partial failures).
    code = compute_exit_code(_MANIFEST)
    if code:
        logger.error("partial failure: %d table(s) kept previous due to "
                     "fetch/validate failure: %s", len(kept), ", ".join(kept) or "-")
    else:
        logger.info("clean run: %d table(s) updated, no real failures", len(updated))
    return code


if __name__ == "__main__":
    # Share the SAME flock as the API refresh driver so a manual run and an
    # API-triggered refresh can never race on the shared staging DB.
    # When run_refresh spawns this script it already holds the lock in the parent
    # and sets REFRESH_LOCK_HELD=1, so we skip re-acquiring (would self-conflict);
    # a standalone `python scripts/01_fetch_data.py` acquires it here and exits
    # non-zero if another refresh already holds it.
    from contextlib import nullcontext

    if os.getenv("REFRESH_LOCK_HELD") == "1":
        _guard = nullcontext()
    else:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.app.core.locking import refresh_lock
        _guard = refresh_lock()

    try:
        with _guard:
            sys.exit(main())
    except BlockingIOError:
        log("⛔ 已有刷新在进行中（另一进程持有刷新锁），本次退出")
        sys.exit(1)

