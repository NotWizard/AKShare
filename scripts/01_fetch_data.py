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
import threading
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
    enforce_indexes,
    table_distinct_keys,
    validate,
)
from release_calendar import TABLE_CALENDAR, should_fetch  # noqa: E402
import dual_sources  # noqa: E402
from signal_history import append_signal_history  # noqa: E402
from nifd_leverage import nifd_supplement_df  # noqa: E402
from _specs import DATE_PARSERS, FETCH_SPECS, to_num  # noqa: E402

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
    all-NaN, unique grain key, no series loss, no grain-key erosion) before it
    may replace the table. On any failure the previously-good staging table is
    kept and the outcome recorded in _MANIFEST — bad data never overwrites good
    data.

    After a successful load the table's grain is re-materialised as a UNIQUE
    index: ``to_sql(if_exists="replace")`` drops the table (and therefore every
    index on it), which is why the live DB had 0 indexes and no uniqueness
    constraint at all. The index is created BEFORE the manifest says "updated"
    so a constraint failure is reported as a fetch failure, never as success.
    """
    prev = table_distinct_keys(conn, table_name)
    ok, reason = validate(df, table_name, prev)
    if not ok:
        _MANIFEST["tables"][table_name] = {
            "status": "kept_previous",
            "reason": reason,
            "prev_distinct_dates": prev,
        }
        log(f"  ⏭️  {table_name}: kept previous (prev {prev} keys) — {reason}")
        return
    df.to_sql(table_name, conn, if_exists=if_exists, index=False)
    index = enforce_indexes(conn, table_name)
    _MANIFEST["tables"][table_name] = {
        "status": "updated",
        "new_rows": int(len(df)),
        "prev_distinct_dates": prev,
        "unique_index": index,
        "checks": "pass",
    }
    log(f"  ✅ {table_name}: {len(df)} rows → staging (prev {prev} keys)")


# ─────────────────────────────────────────────
# 0. 墙钟护栏（P-H1：每表硬超时 + 有界重试 + 整轮截止）
# ─────────────────────────────────────────────
# 为什么必须由调用方设界：ak.macro_china_* / ak.stock_us_daily 内部是裸
# requests.get(url)，没有任何 timeout 参数可传，一个被黑洞的主机能让整轮采集
# 永久挂住（launchd 因此不再启动下一次实例 → 调度静默死亡）。
# 单位秒；可用环境变量按机器/网络调整（默认值按现网单表耗时留足余量）。
FETCH_TIMEOUT_S = float(os.getenv("FETCH_TIMEOUT_S", "120"))
# 单表覆盖：内部还要串/并发多次 HTTP 的表给更宽预算
# （bond_yield 21 年×每年 30s、house_price 10 城、demographics 4 次 World Bank×60s）
TABLE_TIMEOUT_S = {
    "bond_yield": 240.0,
    "house_price": 240.0,
    "demographics": 300.0,
    "fiscal": 180.0,
    "household_income": 180.0,
    "external_demand": 180.0,
}
# 整轮墙钟上限：无论多少表挂住，进程一定会结束（API 侧另有 REFRESH_TIMEOUT_S=300
# 的父进程超时；这里是给 launchd/cron 无父进程场景的自守）
FETCH_RUN_BUDGET_S = float(os.getenv("FETCH_RUN_BUDGET_S", "1500"))
FETCH_ATTEMPTS = 2          # 首次 + 1 次重试（瞬时网络抖动/WAF 偶发 403）
FETCH_BACKOFF_S = 5.0       # 指数退避基数：5s → 10s → …
FETCH_GAP_S = 1.5           # 表间小停顿，避免连续 16 次请求触发 WAF 限流


class FetchTimeout(Exception):
    """A fetcher outlived its per-table wall-clock budget."""


def plan_timeout(name, remaining_s, default_s=None, overrides=None):
    """Per-table wall-clock budget, clamped by what is left of the run budget.
    Returns <= 0 when the overall deadline is already blown (caller must then
    record the table as failed instead of starting it)."""
    default_s = FETCH_TIMEOUT_S if default_s is None else default_s
    overrides = TABLE_TIMEOUT_S if overrides is None else overrides
    return min(overrides.get(name, default_s), max(0.0, remaining_s))


def _call_with_timeout(fn, timeout_s, name="fetch"):
    """Run fn() in a DAEMON thread and enforce a hard wall-clock ceiling.

    Why a thread: akshare exposes no timeout parameter, so "stop waiting for it"
    is the only bound a caller can enforce.

    Why a raw daemon thread and NOT ThreadPoolExecutor: the executor registers
    an atexit hook that JOINS its workers at interpreter shutdown, so a single
    hung fetcher would block process exit forever — re-creating the exact
    "process never ends, schedule dies" bug this guard exists to remove. Daemon
    threads are killed when the process exits.

    Documented ceiling: CPython cannot kill a thread. A hung fetcher keeps
    running (blocked in socket recv) until the process exits, holding one socket
    and its frame; the run does NOT wait for it. Its only dangerous side effect
    is a late write into the staging DB, which the caller disarms by interrupting
    and closing the sqlite handle it was given (see _close_conn).
    """
    box = {}

    def _target():
        try:
            box["value"] = fn()
        except BaseException as e:      # noqa: BLE001 — re-raised in the caller
            box["error"] = e

    th = threading.Thread(target=_target, name=f"fetch-{name}", daemon=True)
    th.start()
    th.join(timeout_s)
    if th.is_alive():
        raise FetchTimeout(f"exceeded {timeout_s:.0f}s wall clock (thread abandoned)")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _close_conn(conn, abandoned=False):
    """Close a per-table staging connection; never raise.

    When the fetcher was ABANDONED on timeout its thread may still be alive and
    still holding this handle. interrupt() (documented as safe to call from
    another thread) aborts any in-flight statement and close() invalidates the
    handle, so the zombie's later to_sql raises inside the dead thread instead of
    writing to the DB — which matters because after commit_staging() the staging
    path and the LIVE DB are the same inode.
    """
    try:
        conn.interrupt() if abandoned else conn.commit()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def _soft_empty(name):
    """True when the gate rejected this table because the fetcher handed it an
    EMPTY frame — i.e. the fetcher swallowed its own network error and raised
    nothing. That is the dominant transient failure (SSL / WAF / geo-block), so
    it is worth one retry. Deterministic rejections (min_rows / ranges / shrink /
    duplicate keys) are NOT retried: identical input fails identically."""
    entry = _MANIFEST.get("tables", {}).get(name) or {}
    return entry.get("status") == "kept_previous" and entry.get("reason") == "empty result"


def run_fetcher(name, f, conn_factory, timeout_s, attempts=FETCH_ATTEMPTS,
                backoff_s=FETCH_BACKOFF_S, sleep=time.sleep):
    """Run one fetcher under a hard timeout with bounded exponential backoff.

    Returns (ok, err) with the pre-existing meaning of ok: "no exception and no
    timeout reached the driver" (gate rejections stay ok=True and are reported
    through _MANIFEST['tables'][name], which the backend turns into a warning).

    Every attempt gets a FRESH sqlite connection so a timed-out attempt's
    abandoned thread can have its handle disarmed independently of the next one.
    """
    err = None
    for attempt in range(1, attempts + 1):
        conn = conn_factory()
        abandoned = False
        try:
            _call_with_timeout(lambda: f(conn), timeout_s, name)
        except FetchTimeout as e:
            abandoned, err = True, f"FetchTimeout: {e}"
            logger.error("table %s attempt %d/%d timed out (%.0fs budget)",
                         name, attempt, attempts, timeout_s)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            logger.warning("table %s attempt %d/%d failed: %s", name, attempt, attempts, err)
        else:
            if not _soft_empty(name):
                return True, None
            err = "gate: empty result (fetcher swallowed its own error)"
            logger.warning("table %s attempt %d/%d: %s", name, attempt, attempts, err)
        finally:
            _close_conn(conn, abandoned=abandoned)
        if attempt < attempts:
            wait = backoff_s * (2 ** (attempt - 1))
            log(f"  ⏳ {name}: 第 {attempt} 次失败，{wait:.0f}s 后重试 ({err})")
            sleep(wait)
    # last attempt was a soft gate rejection → keep the legacy ok=True contract
    # (the kept_previous entry already drives the exit code and the health lamp)
    return (True, None) if err and err.startswith("gate:") else (False, err)


# ─────────────────────────────────────────────
# 声明式采集器（P-M9）: 1.货币供应量 2.GDP 9.工业增加值 12.新增人民币贷款
# ─────────────────────────────────────────────
# 这四张表的抓取体此前逐字重复（call ak → 中文列名 rename + to_numeric coerce →
# 解析日期 → dropna/sort/reset → save_to_db）。现由 scripts/_specs.py 的
# FETCH_SPECS 声明式描述 + 下面这一个通用循环驱动；生成出的 fetch_* 仍是模块级
# 函数（__name__ 保持 fetch_<table>），故 main() 的 fetchers 列表与测试对它们的
# 引用/替身完全不变。真正不规则的采集器（cpi/ppi/pmi/bond/leverage/lpr/
# social_finance/household_income/demographics/fiscal/external_demand）仍各自成
# 函数，只复用 DATE_PARSERS / to_num。
def _build_spec_frame(df, spec):
    """Raw akshare frame → standardized (date + English numeric cols) frame.

    Reproduces the old inline bodies exactly: date via the named DATE_PARSERS
    entry, every value column via to_num, optional columns via ``df.get`` (a
    missing optional column raises the same length-mismatch the old
    ``df.get(src, pd.Series())`` idiom did), then dropna(date)/sort/reset."""
    date_col, parser_key = spec["date"]
    parser = DATE_PARSERS[parser_key]
    data = {"date": [parser(x) for x in df[date_col]]}
    for dest, src, optional in spec["cols"]:
        series = df.get(src, pd.Series(dtype="float64")) if optional else df[src]
        data[dest] = to_num(series)
    out = pd.DataFrame(data)
    return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _run_spec(conn, name):
    """Generic fetch/rename/coerce/persist for one FETCH_SPECS table."""
    spec = FETCH_SPECS[name]
    log(f"采集: {spec['label']} ...")
    fn = getattr(ak, spec["api"])
    if spec.get("swallow_errors"):
        # 保持 fetch_new_credit 历史行为：网络异常吞成空表 → 闸门记 kept_previous
        # （可重试），而非把异常上抛给 run_fetcher。
        try:
            result = _build_spec_frame(fn(), spec)
        except Exception as e:
            log(f"  ⚠️ {spec.get('fail_log', spec['label'] + '采集失败')}: {e}")
            result = pd.DataFrame()
    else:
        result = _build_spec_frame(fn(), spec)
    save_to_db(result, name, conn)
    return result


def _make_spec_fetcher(name):
    """Build a module-level ``fetch_<name>(conn)`` that runs the declarative spec.
    The returned function keeps the ``fetch_<name>`` identity main()/tests rely on."""
    def _f(conn):
        return _run_spec(conn, name)
    _f.__name__ = _f.__qualname__ = f"fetch_{name}"
    _f.__doc__ = f"Declarative fetcher for {name!r} (see scripts/_specs.py FETCH_SPECS)."
    return _f


fetch_money_supply = _make_spec_fetcher("money_supply")   # 1. 货币供应量 (M0/M1/M2)
fetch_gdp = _make_spec_fetcher("gdp")                      # 2. GDP (绝对值 + 同比增速)
fetch_industrial = _make_spec_fetcher("industrial")       # 9. 工业增加值
fetch_new_credit = _make_spec_fetcher("new_credit")       # 12. 新增人民币贷款


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
    em["cpi_yoy"] = to_num(em["cpi_yoy"])
    em["cpi_mom"] = to_num(em["cpi_mom"])
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
    em["ppi_yoy"] = to_num(em["ppi_yoy"])
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
def _pmi_monthly(release_dates, values, col):
    """One row per month for one PMI source, keeping the LAST release in that month.

    每个源都是「发布日一行」：同一个月内可能有初值+终值两次发布（财新/Markit
    flash & final），%Y-%m-01 把它们压成同一个 date。直接 outer merge 会做笛卡尔
    积——现网 pmi 表 321 行 / 248 个月（2012-05 两行、caixin 49.3 与 48.7），读侧
    只能靠顺序相关的 drop_duplicates 兜。按真实发布日排序后取当月最后一次发布
    （终值/修订值）为权威值，结果与源顺序无关。
    """
    release = pd.to_datetime(release_dates)
    out = pd.DataFrame({
        "date": release.dt.strftime("%Y-%m-01"),
        "_release": release,
        col: to_num(values),
    }).dropna(subset=[col])
    return (out.sort_values("_release")
               .drop_duplicates(subset=["date"], keep="last")
               .drop(columns=["_release"])
               .sort_values("date").reset_index(drop=True))


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
    off_ak = _pmi_monthly(df_off["日期"], df_off["今值"], "pmi_official")
    try:
        df_non = ak.macro_china_non_man_pmi()
        non_ak = _pmi_monthly(df_non["日期"], df_non["今值"], "pmi_non_mfg")
    except Exception:
        non_ak = pd.DataFrame(columns=["date", "pmi_non_mfg"])

    if em.empty:
        log("  ⚠️ 东财 PMI 无数据，官方/非制造业仅用 akshare")
        off, non = off_ak, non_ak
    else:
        em2 = em.assign(pmi_official=to_num(em["pmi_official"])) \
                .dropna(subset=["pmi_official"])
        em_off = _pmi_monthly(em2["date"], em2["pmi_official"], "pmi_official")
        em_non = _pmi_monthly(em2["date"], em2["pmi_non_mfg"], "pmi_non_mfg")
        # 东财优先(更当前), akshare 补东财没有的早期月份
        off = em_off.merge(off_ak, on="date", how="outer", suffixes=("_em", "_ak"))
        off["pmi_official"] = off["pmi_official_em"].combine_first(off["pmi_official_ak"])
        off = off[["date", "pmi_official"]].dropna(subset=["pmi_official"])
        non = em_non.merge(non_ak, on="date", how="outer", suffixes=("_em", "_ak"))
        non["pmi_non_mfg"] = non["pmi_non_mfg_em"].combine_first(non["pmi_non_mfg_ak"])
        non = non[["date", "pmi_non_mfg"]].dropna(subset=["pmi_non_mfg"])

    cx = _pmi_monthly(df_cx["日期"], df_cx["今值"], "pmi_caixin")

    # 财新服务业 PMI（东财无财新口径，仍用 akshare）
    try:
        df_svc = ak.macro_china_cx_services_pmi_yearly()
        svc = _pmi_monthly(df_svc["日期"], df_svc["今值"], "pmi_caixin_svc")
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
# NIFD 季度杠杆率补充值（官方发布、非自算）已抽到 scripts/nifd_leverage.py 作为
# 单一真相源（此前 01 与 03 各存一份、易漂移，即 P-M8）。macro_cnbs 滞后时补齐。


def fetch_leverage(conn):
    log("采集: 宏观杠杆率 ...")
    df = ak.macro_cnbs()

    # 解析季度日期: "1992-12" → "1992-12-01" (Q4), "1993-03" → "1993-03-01" (Q1)
    parse_cnbs_date = DATE_PARSERS["cnbs_dash"]

    result = pd.DataFrame({
        "date": [parse_cnbs_date(x) for x in df["年份"]],
        "household": to_num(df["居民部门"]),
        "non_fin_corp": to_num(df["非金融企业部门"]),
        "gov_total": to_num(df["政府部门"]),
        "gov_central": to_num(df["中央政府"]),
        "gov_local": to_num(df["地方政府"]),
        "real_economy": to_num(df["实体经济部门"]),
        "fin_asset": to_num(df["金融部门资产方"]),
        "fin_liability": to_num(df["金融部门负债方"]),
    })
    result = result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # Fold NIFD official quarterly leverage (report-extracted, not self-computed)
    # for dates newer than what ak.macro_cnbs() provides; goes through the same
    # gated save_to_db. date>cnbs_max filter means once AKShare catches up, the
    # NIFD rows for those dates drop out and fresher CNBS data supersedes them.
    cnbs_max = result["date"].max()
    nifd_new = nifd_supplement_df()
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
                v = to_num(xls.iloc[i, j])
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
            "total": to_num(df["社会融资规模增量"]),
            "rmb_loan": to_num(df["其中-人民币贷款"]),
            "entrusted_loan": to_num(df["其中-委托贷款"]),
            "trust_loan": to_num(df["其中-信托贷款"]),
            "acceptance_bill": to_num(df["其中-未贴现银行承兑汇票"]),
            "corp_bond": to_num(df["其中-企业债券"]),
            "equity": to_num(df["其中-非金融企业境内股票融资"]),
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
        trade_date = pd.to_datetime(df["TRADE_DATE"])
        result = pd.DataFrame({
            "trade_date": trade_date,
            "date": trade_date.dt.strftime("%Y-%m-01"),
            "lpr_1y": to_num(df["LPR1Y"]),
            "lpr_5y": to_num(df["LPR5Y"]),
        })
        # 只保留有 LPR 数据的行 (2019年8月起)
        result = result.dropna(subset=["lpr_1y"])
        # 源是「每个报价日一行」，%Y-%m-01 会把同月多个报价日压成同一个 date：
        # 旧代码因此写出 1536 行 / 154 个月（2019-08 一个月 13 行），读侧只能靠
        # 顺序相关的 drop_duplicates(keep="last") 兜，且会挑中改革前的 4.31 而不是
        # 8/20 新报价 4.25。按真实报价日排序后取当月最后一次报价（月末实际生效值）
        # 才是权威值，且结果与源顺序无关。
        result = (result.sort_values("trade_date")
                        .drop_duplicates(subset=["date"], keep="last")
                        .drop(columns=["trade_date"])
                        .sort_values("date").reset_index(drop=True))
    except Exception as e:
        log(f"  ⚠️ LPR 数据采集失败 (SSL问题): {e}")
        result = pd.DataFrame()

    save_to_db(result, "lpr", conn)
    return result


# ─────────────────────────────────────────────
# 9. 工业增加值 → 声明式 fetch_industrial（见上方 P-M9 块 + scripts/_specs.py）
# ─────────────────────────────────────────────


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
            "new_yoy": to_num(combined["新建商品住宅价格指数-同比"]),
            "new_mom": to_num(combined["新建商品住宅价格指数-环比"]),
            "new_base": to_num(combined["新建商品住宅价格指数-定基"]),
            "used_yoy": to_num(combined["二手住宅价格指数-同比"]),
            "used_mom": to_num(combined["二手住宅价格指数-环比"]),
            "used_base": to_num(combined["二手住宅价格指数-定基"]),
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

    _parse_year_col = DATE_PARSERS["cn_year"]

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
                    records.append({"date": d, "income_per_capita": to_num(val)})
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
                    records.append({"date": d, "population_10k": to_num(val)})
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
        # 可得日期（防前视）：date 是「参考年」，但参考年 Y 的年度居民收入/人口要到
        # 次年 1 月《国民经济运行情况》才发布。若下游按 date 做 backward merge_asof，
        # 会把还没发布的值回填进参考年当年各季度（约 12 个月前视，直接污染
        # hh_debt_to_income / hh_income_share）。这里显式标注最早可得日 = Y+1-01-01
        # （季度锚点最早为 Y+1-03-01，故按月初标注已足够消除前视）。
        merged["available_from"] = (merged["date"].str[:4].astype(int) + 1).astype(str) + "-01-01"
    save_to_db(merged, "household_income", conn)
    return merged


# ─────────────────────────────────────────────
# 12. 新增人民币贷款 → 声明式 fetch_new_credit（见上方 P-M9 块 + scripts/_specs.py）
# ─────────────────────────────────────────────


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
            gz["10年"] = to_num(gz["10年"])
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
    # NBS 月份标签（"2026年5月"）解析，与 industrial/new_credit 同款
    return DATE_PARSERS["cn_month"](s)


def _nbs_long(df):
    """NBS 指标×月份宽表（指标为行、月份为列）→ (date, indicator, value) 长表。"""
    records = []
    for ind in df.index:
        for col, val in df.loc[ind].items():
            d = _parse_nbs_month(col)
            if d:
                records.append({"date": d, "indicator": str(ind),
                                "value": to_num(val)})
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
            "us_ism_pmi": to_num(df_ism["今值"]),
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

    Returns 3 when the derived recompute failed (the run was DISCARDED — the live
    DB still holds the previous consistent snapshot, so nothing landed at all),
    2 (partial failure) when any attempted table ended ``kept_previous``,
    else 0 (fully clean)."""
    derived = manifest.get("derived")
    if isinstance(derived, str) and derived.startswith("failed"):
        return 3
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

    def _staging_conn():
        # check_same_thread=False: the fetcher body runs inside the per-table
        # timeout worker thread (see _call_with_timeout). Each attempt gets its
        # OWN handle so an abandoned attempt can be disarmed independently.
        return sqlite3.connect(staging, check_same_thread=False)

    ts = iso_ts()
    _MANIFEST = {"ts": ts, "akshare": getattr(ak, "__version__", "?"), "tables": {}, "sources": []}

    run_deadline = time.time() + FETCH_RUN_BUDGET_S
    for i, (name, f) in enumerate(selected):
        t0 = time.time()
        budget = plan_timeout(name, run_deadline - t0)
        if budget <= 0:
            # 整轮墙钟耗尽：剩余表记为失败并停止，进程一定结束，且退出码反映缺口
            ok, err = False, f"run budget {FETCH_RUN_BUDGET_S:.0f}s exhausted before start"
            log(f"  ⛔ {name}: {err}")
            logger.error("run budget exhausted, skipping table %s", name)
        else:
            ok, err = run_fetcher(name, f, _staging_conn, budget)
        if not ok:
            log(f"  ❌ fetch_{name} 失败: {err}")
            _MANIFEST["tables"].setdefault(name, {"status": "kept_previous", "reason": err})
        # ok 仅表示 fetcher 是否抛异常/超时；验证闸门拒收走 kept_previous warning（后端推导）
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
        # 表间小停顿：连续 16 次抓取容易触发源站 WAF 限流（最后一张表不必等）
        if i < len(selected) - 1 and time.time() < run_deadline:
            time.sleep(FETCH_GAP_S)

    conn = sqlite3.connect(staging)

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
        # 衍生失败绝不能提交：raw 已更新而 derived 仍是旧的 → 库内自相矛盾的快照，
        # 而信号/相位正是从 derived 算出来的。丢弃 staging，保留上一份一致快照。
        log(f"  ❌ 衍生计算失败，丢弃本轮 staging（保留上一份一致快照）: {e}")
        logger.error("derived recompute failed, staging DISCARDED (live DB unchanged): %s", e)
        _MANIFEST["derived"] = f"failed: {e}"
        conn.close()
        discard_staging()
        write_manifest(_MANIFEST)     # 审计留痕：本轮为何没有落库
        log("=" * 50)
        log("采集中止 (staging discarded): live DB 未改动")
        log("=" * 50)
        return compute_exit_code(_MANIFEST)

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

