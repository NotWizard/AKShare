"""Declarative fetch specs + shared parsers for the collector (G26 / P-M9).

`scripts/01_fetch_data.py` had ~7 structurally identical fetcher bodies (call
``ak.xxx()`` → rename hardcoded Chinese columns to English + ``pd.to_numeric``
coerce → parse the date label → ``dropna/sort/reset`` → ``save_to_db``), ~8
near-duplicate date parsers, and 50+ copies of ``pd.to_numeric(..., errors=
"coerce")``. This module collapses the mechanical parts:

  * ``DATE_PARSERS`` — one registry for every raw→ISO date label parser. Bespoke
    fetchers that keep their own body still reuse these instead of re-declaring.
  * ``to_num`` — the single numeric-coercion helper.
  * ``FETCH_SPECS`` — the fetchers whose ENTIRE body was the pattern above,
    described as data. The generic loop that consumes them lives in
    01_fetch_data.py (it needs akshare + save_to_db); this module stays
    dependency-light (pandas only) so the test harness can import it with a
    stubbed akshare.

Deliberately NOT here: the NIFD leverage constant (that is P-M8, and lives in
``scripts/nifd_leverage.py``), and the genuinely irregular fetchers
(cpi/ppi/pmi/bond/leverage/lpr/social_finance/household_income/demographics/
fiscal/external_demand) which stay bespoke — they only borrow DATE_PARSERS/to_num.
"""

import re

import pandas as pd


# ── numeric coercion helper (replaces 50+ inline pd.to_numeric calls) ─────────
def to_num(series):
    """``pd.to_numeric(series, errors="coerce")`` — the collector's ONLY numeric
    coercion. A source that starts returning junk turns into NaN uniformly, which
    the validate() dtype/all-NaN gate then rejects."""
    return pd.to_numeric(series, errors="coerce")


# ── date parsers (one registry; see P-M9) ─────────────────────────────────────
def parse_dot_month(s):
    """money_supply: ``"2026.5"`` → ``"2026-05-01"``."""
    parts = str(s).split(".")
    if len(parts) == 2:
        return f"{parts[0]}-{int(parts[1]):02d}-01"
    return None


def parse_cn_quarter(s):
    """gdp: ``"2024年第1季度"`` → ``"2024-01-01"``; cumulative ``"2026年第1-2季度"``
    → last quarter ``"2026-04-01"``."""
    m = re.match(r"(\d{4})年第(\d)(?:-(\d))?季度", str(s))
    if m:
        year = int(m.group(1))
        q = int(m.group(3) or m.group(2))   # 累计取末季
        month = (q - 1) * 3 + 1
        return f"{year}-{month:02d}-01"
    return None


def parse_cn_month(s):
    """Monthly NBS/PBoC labels: ``"2026年5月份"`` / ``"2026年5月"`` /
    ``"2008年02月份"`` → ``"2026-05-01"`` / ``"2008-02-01"``.

    Unifies the old ``parse_month`` (industrial, ``(\\d{4})年(\\d{2})月份``),
    ``parse_month`` (new_credit, ``(\\d{4})年(\\d{1,2})月``) and ``_parse_nbs_month``
    (fiscal/external_demand, same regex). The ``\\d{1,2}`` form is a superset of
    the industrial ``\\d{2}`` form and yields an identical ISO string for every
    two-digit label the source actually emits."""
    m = re.match(r"(\d{4})年(\d{1,2})月", str(s))
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    return None


def parse_cnbs_dash(s):
    """leverage (CNBS): ``"1992-12"`` → ``"1992-12-01"``."""
    parts = str(s).split("-")
    if len(parts) == 2:
        return f"{parts[0]}-{parts[1]}-01"
    return None


def parse_cn_year(s):
    """Annual NBS labels: ``"2024年"`` → ``"2024-01-01"``."""
    m = re.match(r"(\d{4})年", str(s))
    if m:
        return f"{m.group(1)}-01-01"
    return None


DATE_PARSERS = {
    "dot_month": parse_dot_month,
    "cn_quarter": parse_cn_quarter,
    "cn_month": parse_cn_month,
    "cnbs_dash": parse_cnbs_dash,
    "cn_year": parse_cn_year,
}


# ── declarative fetchers (P-M9) ───────────────────────────────────────────────
# Only the fetchers whose entire body was "call ak → rename+coerce → parse date
# → dropna/sort → save" live here. Each column is (dest, source, optional):
# optional columns are read via df.get() (missing → all-NaN, matching the old
# ``df.get(src, pd.Series())`` idiom); required columns via df[src] (a missing
# source column raises, exactly as before, so run_fetcher retries/records it).
FETCH_SPECS = {
    "money_supply": dict(
        label="货币供应量 M0/M1/M2",
        api="macro_china_supply_of_money",
        date=("统计时间", "dot_month"),
        cols=[
            ("m2", "货币和准货币（广义货币M2）", False),
            ("m2_yoy", "货币和准货币（广义货币M2）同比增长", False),
            ("m1", "货币(狭义货币M1)", False),
            ("m1_yoy", "货币(狭义货币M1)同比增长", False),
            ("m0", "流通中现金(M0)", False),
            ("m0_yoy", "流通中现金(M0)同比增长", False),
            ("demand_deposit", "活期存款", True),
            ("time_deposit", "定期存款", True),
            ("savings", "储蓄存款", True),
        ],
    ),
    "gdp": dict(
        label="GDP",
        api="macro_china_gdp",
        date=("季度", "cn_quarter"),
        cols=[
            ("gdp_abs", "国内生产总值-绝对值", False),
            ("gdp_yoy", "国内生产总值-同比增长", False),
            ("gdp_primary", "第一产业-绝对值", True),
            ("gdp_secondary", "第二产业-绝对值", True),
            ("gdp_tertiary", "第三产业-绝对值", True),
        ],
    ),
    "industrial": dict(
        label="工业增加值",
        api="macro_china_gyzjz",
        date=("月份", "cn_month"),
        cols=[
            ("ip_yoy", "同比增长", False),
            ("ip_cumulative", "累计增长", False),
        ],
    ),
    "new_credit": dict(
        label="新增人民币贷款",
        api="macro_china_new_financial_credit",
        date=("月份", "cn_month"),
        cols=[
            ("new_rmb_loan", "当月", False),
        ],
        # 原 fetch_new_credit 把网络异常吞成空表（走闸门 kept_previous），与
        # money_supply/gdp（异常上抛给 run_fetcher 重试）不同，保持一致行为。
        swallow_errors=True,
        fail_log="新增信贷数据采集失败",   # 保持原始告警文案
    ),
}


# ── 中债收益率页：按列特征认表（替代位置式 dfs[1]）────────────────────────────
# 该页 read_html 出两张表：第 0 张是查询表单、第 1 张才是数据。表单**同样带
# 「曲线名称」列**，所以只能靠三列同时存在来区分；上游一旦多插一张表，位置式
# 索引就会静默取错表、再被 fetcher 的 except 吞掉，表现为「收益率永远不更新」。
CB_CURVE_COLS = ("曲线名称", "日期", "10年")


def pick_curve_table(dfs):
    """从 `read_html` 结果中选出中债收益率数据表。

    认不出就抛 `LookupError`——让调用方把「页面改版」记成失败，而不是当作
    「本年无数据」静默返回空表。"""
    for df in dfs:
        if all(col in df.columns for col in CB_CURVE_COLS):
            return df
    raise LookupError(
        f"未找到含 {CB_CURVE_COLS} 的中债收益率表（read_html 共 {len(dfs)} 张表）")
