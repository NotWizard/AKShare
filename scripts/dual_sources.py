"""核心序列双源比对 — primary（staging 表）vs 独立次源，只读、永不覆盖 primary。

跑点：01_fetch_data.py fetch 循环之后、run_derived 之前，仅对本次抓取成功的表
跑对应序列（primary 未更新时比对无意义）。结果合并进 manifest.sources[].dual；
divergence 由后端 sources_health 转黄灯（检查器自身故障只记录，不红不黄）。

容差（任务给定）：
    rate （同比 %、PMI 点）：绝对差 ≤0.3 或 相对差 ≤2%（任一满足即通过——
         低基数序列相对差易爆，绝对差兜底；高基数反之）
    level（10Y 收益率水平）：相对差 ≤2%

social_finance 无次源：东财 RPT_ECONOMY_SHRZGM 及 4 个变体名探针实测全 EMPTY。
"""

import re

import pandas as pd

_EPS = 1e-9

# table → 序列/次源/容差类型；fetch 返回 date×value 两列（date 为 YYYY-MM-DD 字符串）
DUAL_SERIES = [
    dict(table="money_supply", series="m2_yoy", kind="rate",
         source="ak.macro_china_money_supply"),
    dict(table="cpi", series="cpi_yoy", kind="rate",
         source="ak.macro_china_cpi_yearly"),
    dict(table="ppi", series="ppi_yoy", kind="rate",
         source="ak.macro_china_ppi_yearly"),
    dict(table="gdp", series="gdp_yoy", kind="rate",
         source="eastmoney RPT_ECONOMY_GDP"),
    dict(table="pmi", series="pmi_official", kind="rate",
         source="ak.macro_china_pmi_yearly"),
    dict(table="bond_yield", series="y_10y", kind="level",
         source="ak.bond_zh_us_rate"),
]


def _norm_jin10_date(d):
    """Jin10 日期归一：历史行日期为数据月首日，近期行为发布日（如 2025-08-09
    发布 7 月 CPI）。day==1 保留；day>1 → 归一到上个月 1 日（1 月发布 → 上年 12 月）。
    返回 YYYY-MM-DD 字符串。"""
    t = pd.Timestamp(d)
    if t.day > 1:
        t = t.replace(day=1) - pd.DateOffset(months=1)
    return t.strftime("%Y-%m-01")


def _norm_ism_date(d):
    """ISM 归一：jin10 ISM 的日期恒为发布日（月初首个工作日，含 1 日），没有
    「数据月首日」型历史行 → 数据月永远是上一个月（与 _norm_jin10_date 的
    day==1 保留规则不同）。如 2025-08-01 发布 → 7 月数据。"""
    t = pd.Timestamp(d).replace(day=1) - pd.DateOffset(months=1)
    return t.strftime("%Y-%m-01")


def _gdp_q1_date(time_str):
    """东财 RPT_ECONOMY_GDP TIME → 日期；只匹配「第1季度」行（Q1 累计==当季同比）。"""
    m = re.match(r"^(\d{4})年第1季度$", str(time_str))
    return f"{m.group(1)}-01-01" if m else None


def within_tolerance(primary, secondary, kind="rate"):
    """rate: 绝对差 ≤0.3 或 相对差 ≤2%；level: 相对差 ≤2%。
    _EPS 吸收浮点边界噪声（如 1.3−1.0=0.30000000000000004）。"""
    diff = abs(primary - secondary)
    denom = max(abs(primary), abs(secondary))
    if kind == "level":
        return denom == 0 or diff / denom <= 0.02 + _EPS
    if diff <= 0.3 + _EPS:
        return True
    return denom > 0 and diff / denom <= 0.02 + _EPS


# ── 次源抓取（各自返回 date/value 两列；akshare 惰性导入保持本模块可离线导入） ──
def _fetch_money():
    import akshare as ak
    df = ak.macro_china_money_supply()

    def _d(s):
        m = re.match(r"(\d{4})年(\d{1,2})月", str(s))
        return f"{m.group(1)}-{int(m.group(2)):02d}-01" if m else None

    out = pd.DataFrame({
        "date": [_d(x) for x in df["月份"]],
        "value": pd.to_numeric(df["货币和准货币(M2)-同比增长"], errors="coerce"),
    })
    return out.dropna()


def _fetch_jin10(attr):
    """Jin10 系（cpi_yearly/ppi_yearly）：今值 dropna 去待发布行，日期按发布日归一。"""
    import akshare as ak
    df = getattr(ak, attr)()
    out = pd.DataFrame({
        "date": [_norm_jin10_date(x) for x in df["日期"]],
        "value": pd.to_numeric(df["今值"], errors="coerce"),
    })
    return out.dropna()


def _fetch_gdp():
    import requests
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    page, rows_out = 1, []
    while True:
        params = {
            "reportName": "RPT_ECONOMY_GDP", "columns": "TIME,SUM_SAME",
            "pageNumber": str(page), "pageSize": "500",
            "sortColumns": "REPORT_DATE", "sortTypes": "-1",
            "source": "WEB", "client": "WEB",
        }
        r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        rows = (r.json().get("result") or {}).get("data") or []
        for x in rows:
            d = _gdp_q1_date(x.get("TIME"))
            if d:
                rows_out.append({"date": d, "value": pd.to_numeric(x.get("SUM_SAME"))})
        if len(rows) < 500:
            break
        page += 1
    return pd.DataFrame(rows_out).dropna()


def _fetch_pmi():
    """NBS 口径官方 PMI（日期=数据月末，非 Jin10 发布日，不做归一）。"""
    import akshare as ak
    df = ak.macro_china_pmi_yearly()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-01"),
        "value": pd.to_numeric(df["今值"], errors="coerce"),
    })
    return out.dropna()


def _fetch_bond():
    import akshare as ak
    df = ak.bond_zh_us_rate()
    s = pd.Series(pd.to_numeric(df["中国国债收益率10年"], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df["日期"]))
    monthly = s.dropna().resample("ME").last().dropna()
    return pd.DataFrame({"date": monthly.index.strftime("%Y-%m-01"), "value": monthly.to_numpy()})


_FETCHERS = {
    "ak.macro_china_money_supply": _fetch_money,
    "ak.macro_china_cpi_yearly": lambda: _fetch_jin10("macro_china_cpi_yearly"),
    "ak.macro_china_ppi_yearly": lambda: _fetch_jin10("macro_china_ppi_yearly"),
    "eastmoney RPT_ECONOMY_GDP": _fetch_gdp,
    "ak.macro_china_pmi_yearly": _fetch_pmi,
    "ak.bond_zh_us_rate": _fetch_bond,
}


def _last_common(primary, secondary):
    """两源最后公共日期（双方均非空）→ (date, p, s)；无公共点返回 None。"""
    m = primary.merge(secondary, on="date", suffixes=("_p", "_s"))
    m = m.dropna(subset=["value_p", "value_s"]).sort_values("date")
    if m.empty:
        return None
    r = m.iloc[-1]
    return str(r["date"]), float(r["value_p"]), float(r["value_s"])


def run_checks(conn, ok_tables):
    """对本次抓取成功（ok=True）的表逐序列比对。只读 staging + 拉次源，不写任何表。
    返回 {table: dual 记录}，供 01 合并进 manifest.sources[]。"""
    out = {}
    for spec in DUAL_SERIES:
        table = spec["table"]
        if table not in ok_tables:
            continue
        rec = {"series": spec["series"], "source": spec["source"],
               "date": None, "primary": None, "secondary": None,
               "diff": None, "divergent": False, "error": None}
        try:
            primary = pd.read_sql(
                f"SELECT date, [{spec['series']}] AS value FROM [{table}]", conn)
            secondary = _FETCHERS[spec["source"]]()
        except Exception as e:  # 检查器自身故障只记录，不等于数据有问题
            rec["error"] = f"{type(e).__name__}: {e}"[:200]
            out[table] = rec
            continue
        hit = _last_common(primary, secondary)
        if hit is None:
            rec["error"] = "no common dates"
        else:
            date, p, s = hit
            rec.update(date=date, primary=p, secondary=s, diff=round(p - s, 6),
                       divergent=not within_tolerance(p, s, spec["kind"]))
        out[table] = rec
    return out
