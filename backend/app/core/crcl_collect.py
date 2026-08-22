"""CRCL monitor collectors.

Each source is isolated: failures are logged to collect_log and never raised,
so one dead source does not block the others. No fabricated data — a failed
source simply produces no points and an error log row.

Sources (all free, no API key):
- DefiLlama   stablecoins.llama.fi        USDC 流通量历史 + 稳定币总盘历史
- Treasury    home.treasury.gov CSV       3M/6M/1Y 美债收益率曲线（日频）
- AKShare     stock_us_daily('CRCL')      CRCL 日线 OHLCV
- yfinance    Ticker('CRCL').info         市值 / TTM P/E / 前瞻 P/E / P/S 快照

Two concurrency guarantees (F6), both enforced in ``collect_all``:
* SINGLE-FLIGHT — an OS ``flock`` on ``data/.crcl_collect.lock`` (a different
  file from the macro refresh lock). N clicks used to start N concurrent full
  collections all writing crcl_monitor.db; now the loser returns "busy"
  immediately and the startup collection can never stampede a user-triggered one.
* ENFORCEABLE TIMEOUT — the httpx sources already pass ``timeout=30``, but
  ``ak.stock_us_daily`` goes through akshare's internal *bare* ``requests.get``
  (no timeout) and yfinance is equally uncontrolled, so a black-holed host used
  to pin the calling thread forever. Those three calls now run behind
  ``_call_with_timeout``.
"""

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import httpx

from backend.app.core import crcl_db
from backend.app.core.locking import crcl_collect_lock

logger = logging.getLogger(__name__)

DEFILLAMA_TIMEOUT = 30
TREASURY_YEARS = 2  # 当年 + 上一年，用于回填与跨年连续

# Wall-clock ceiling for ONE uncontrollable third-party blocking call
# (akshare / yfinance). Env-overridable, same pattern as REFRESH_TIMEOUT_S.
THIRD_PARTY_TIMEOUT_S = int(os.getenv("CRCL_STEP_TIMEOUT_S", "60"))


def _call_with_timeout(fn, timeout: int | None = None):
    """Call ``fn()`` with an enforceable wall-clock ceiling.

    Python cannot interrupt a thread blocked in a socket read, so the ceiling is
    enforced by *waiting* on a DAEMON worker and giving up on it: on timeout a
    ``TimeoutError`` is raised to the caller (which logs it as a failed source
    and moves on) while the hung thread is ABANDONED. That leak is deliberate
    and bounded — it is one daemon thread per hung call, it holds no lock and no
    DB connection, it dies with the process, and being daemon it never delays
    interpreter shutdown. The alternative (a subprocess per call) buys real
    cancellation at the cost of re-importing akshare/yfinance every time.
    """
    box: dict = {}
    limit = THIRD_PARTY_TIMEOUT_S if timeout is None else timeout

    def _run():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — re-raised in the caller
            box["error"] = e

    t = threading.Thread(target=_run, daemon=True, name="crcl-thirdparty")
    t.start()
    t.join(limit)
    if t.is_alive():
        raise TimeoutError(f"第三方调用超时（>{limit} 秒）")
    if "error" in box:
        raise box["error"]
    return box["value"]


METRIC_LABELS = {
    "usdc_circ": ("USDC 流通量", "美元", "DefiLlama /stablecoin/2", "日"),
    "stablecoin_total": ("稳定币总市值", "美元", "DefiLlama /stablecoincharts/all", "日"),
    "treasury_3m": ("美债收益率 3M", "%", "Treasury.gov 年度 CSV", "日"),
    "treasury_6m": ("美债收益率 6M", "%", "Treasury.gov 年度 CSV", "日"),
    "treasury_1y": ("美债收益率 1Y", "%", "Treasury.gov 年度 CSV", "日"),
    "crcl_close": ("CRCL 收盘价", "美元", "AKShare stock_us_daily", "日"),
    "eurc_circ": ("EURC 流通量", "欧元", "DefiLlama /stablecoincharts/all?stablecoin=50", "日"),
    "crcl_volume": ("CRCL 成交量", "股", "AKShare stock_us_daily", "日"),
}


def _log(run_id: str, source: str, status: str, message: str, started: float) -> None:
    crcl_db.add_log(run_id, source, status, message, int((time.time() - started) * 1000))


def _iso_from_ts(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def collect_usdc_circ(run_id: str) -> int:
    """USDC 流通量历史（DefiLlama 聚合端点，stablecoin=2，已去跨链桥重复）。"""
    t0 = time.time()
    try:
        r = httpx.get(
            "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=2",
            timeout=DEFILLAMA_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        points = []
        for row in r.json():
            v = (row.get("totalCirculatingUSD") or {}).get("peggedUSD")
            if v is not None:
                points.append((_iso_from_ts(row["date"]), float(v)))
        n = crcl_db.upsert_points("usdc_circ", points)
        _log(run_id, "defillama_usdc", "ok", f"{n} 个数据点", t0)
        return n
    except Exception as e:  # noqa: BLE001 — collector must never raise
        _log(run_id, "defillama_usdc", "error", f"{type(e).__name__}: {e}", t0)
        return 0


def collect_eurc_circ(run_id: str) -> int:
    """EURC 流通量历史（DefiLlama 聚合端点，stablecoin=50，欧元计价）。"""
    t0 = time.time()
    try:
        r = httpx.get(
            "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=50",
            timeout=DEFILLAMA_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        points = []
        for row in r.json():
            v = (row.get("totalCirculating") or {}).get("peggedEUR")
            if v is not None:
                points.append((_iso_from_ts(row["date"]), float(v)))
        n = crcl_db.upsert_points("eurc_circ", points)
        _log(run_id, "defillama_eurc", "ok", f"{n} 个数据点", t0)
        return n
    except Exception as e:  # noqa: BLE001
        _log(run_id, "defillama_eurc", "error", f"{type(e).__name__}: {e}", t0)
        return 0


def collect_stablecoin_total(run_id: str) -> int:
    """稳定币总盘历史（DefiLlama charts/all，全链合计）。"""
    t0 = time.time()
    try:
        r = httpx.get(
            "https://stablecoins.llama.fi/stablecoincharts/all",
            timeout=DEFILLAMA_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        points = []
        for row in r.json():
            v = (row.get("totalCirculatingUSD") or {}).get("peggedUSD")
            if v is not None:
                points.append((_iso_from_ts(row["date"]), float(v)))
        n = crcl_db.upsert_points("stablecoin_total", points)
        _log(run_id, "defillama_total", "ok", f"{n} 个数据点", t0)
        return n
    except Exception as e:  # noqa: BLE001
        _log(run_id, "defillama_total", "error", f"{type(e).__name__}: {e}", t0)
        return 0


def collect_treasury(run_id: str) -> int:
    """短端美债收益率（Treasury.gov 年度 CSV，取 3M/6M/1Y 三列）。"""
    t0 = time.time()
    import io

    import pandas as pd

    year_now = datetime.now(timezone.utc).year
    cols = {"3 Mo": "treasury_3m", "6 Mo": "treasury_6m", "1 Yr": "treasury_1y"}
    total = 0
    try:
        for year in range(year_now - TREASURY_YEARS + 1, year_now + 1):
            url = (
                "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                f"daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
                f"&field_tdr_date_value={year}&page&_format=csv"
            )
            r = httpx.get(url, timeout=DEFILLAMA_TIMEOUT, follow_redirects=True)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df["date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
            for src, metric in cols.items():
                if src not in df.columns:
                    continue
                sub = df[["date", src]].dropna()
                points = [(d, float(v)) for d, v in zip(sub["date"], sub[src])]
                total += crcl_db.upsert_points(metric, points)
        _log(run_id, "treasury_csv", "ok", f"{total} 个数据点（{TREASURY_YEARS} 年）", t0)
        return total
    except Exception as e:  # noqa: BLE001
        _log(run_id, "treasury_csv", "error", f"{type(e).__name__}: {e}", t0)
        return total


def collect_crcl_stock(run_id: str) -> int:
    """CRCL 日线。主源 AKShare（新浪端点偶发不可达），备用 yfinance。"""
    t0 = time.time()
    try:
        import akshare as ak

        # akshare's stock_us_daily uses a BARE requests.get (no timeout) → an
        # unreachable Sina endpoint would block this thread forever.
        df = _call_with_timeout(lambda: ak.stock_us_daily(symbol="CRCL"))
        points_close = [
            (d.strftime("%Y-%m-%d"), float(c))
            for d, c in zip(df["date"], df["close"])
        ]
        points_vol = [
            (d.strftime("%Y-%m-%d"), float(v))
            for d, v in zip(df["date"], df["volume"])
        ]
        n = crcl_db.upsert_points("crcl_close", points_close)
        n += crcl_db.upsert_points("crcl_volume", points_vol)
        _log(run_id, "akshare_crcl", "ok", f"{n} 个数据点（AKShare）", t0)
        return n
    except Exception as e:  # noqa: BLE001
        _log(run_id, "akshare_crcl", "error", f"主源失败，转备用源 {type(e).__name__}", t0)
    # 备用源：yfinance
    t1 = time.time()
    try:
        import yfinance as yf

        h = _call_with_timeout(lambda: yf.Ticker("CRCL").history(period="max"))
        points_close = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(h.index, h["Close"])]
        points_vol = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(h.index, h["Volume"])]
        n = crcl_db.upsert_points("crcl_close", points_close)
        n += crcl_db.upsert_points("crcl_volume", points_vol)
        _log(run_id, "yfinance_crcl", "ok", f"{n} 个数据点（备用源）", t1)
        return n
    except Exception as e:  # noqa: BLE001
        _log(run_id, "yfinance_crcl", "error", f"{type(e).__name__}: {e}", t1)
        return 0


def collect_valuation_snapshot(run_id: str) -> bool:
    """CRCL 估值快照（yfinance：市值/TTM P/E/前瞻 P/E/P-S/52 周区间）。"""
    t0 = time.time()
    try:
        import yfinance as yf

        info = _call_with_timeout(lambda: yf.Ticker("CRCL").info)
        snap = {
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "ps_ttm": info.get("priceToSalesTrailing12Months"),
            "week52_low": info.get("fiftyTwoWeekLow"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "pe_note": "Yahoo Finance 口径；trailingPE 受一次性项目影响，与 WSJ 等口径存在差异",
        }
        crcl_db.set_snapshot("valuation", snap)
        _log(run_id, "yfinance_valuation", "ok", "估值快照已更新", t0)
        return True
    except Exception as e:  # noqa: BLE001
        _log(run_id, "yfinance_valuation", "error", f"{type(e).__name__}: {e}", t0)
        return False


def update_circ_snapshot(run_id: str) -> None:
    """把流通量/总盘最新值写入 snapshot，供 KPI 区直接读取。"""
    t0 = time.time()
    try:
        snap = {}
        usdc = crcl_db.get_series("usdc_circ")
        if usdc:
            snap["usdc_circ"] = usdc[-1]["value"]
            snap["usdc_circ_date"] = usdc[-1]["date"]
        total = crcl_db.get_series("stablecoin_total")
        if total:
            snap["stablecoin_total"] = total[-1]["value"]
            snap["stablecoin_total_date"] = total[-1]["date"]
        eurc = crcl_db.get_series("eurc_circ")
        if eurc:
            snap["eurc_circ"] = eurc[-1]["value"]
            snap["eurc_circ_date"] = eurc[-1]["date"]
        if snap:
            crcl_db.set_snapshot("stablecoins", snap)
            _log(run_id, "snapshot_stablecoins", "ok", "流通量快照已更新", t0)
    except Exception as e:  # noqa: BLE001
        _log(run_id, "snapshot_stablecoins", "error", f"{type(e).__name__}: {e}", t0)


def collect_all(progress_cb=None, stop_event=None) -> dict:
    """Run all collectors + alert evaluation. Returns a summary dict.

    SINGLE-FLIGHT (F6): the whole collection is wrapped in an OS ``flock`` on
    ``data/.crcl_collect.lock``, so a second caller — another click, another tab,
    or the startup collection racing a user-triggered one — returns
    ``status="busy"`` INSTEAD of starting a second full network collection
    against the same DB. Acquisition is atomic and non-blocking (no
    check-then-act window), and the kernel drops the lock if the process dies.
    ``stop_event`` (threading.Event) is checked between steps for cooperative
    cancellation when the SSE client disconnects.
    """
    try:
        with crcl_collect_lock():
            return _collect_all_locked(progress_cb, stop_event)
    except BlockingIOError:
        logger.info("[crcl] 采集已在进行中，本次请求返回 busy")
        return {"status": "busy", "msg": "已有采集在进行中，请稍候…",
                "run_id": None, "steps": [], "alerts_changed": []}


def _collect_all_locked(progress_cb, stop_event) -> dict:
    """Body of collect_all, executed while holding the CRCL collect lock."""
    from backend.app.core import crcl_alerts

    crcl_db.ensure_schema()
    run_id = uuid.uuid4().hex[:8]
    steps = [
        ("USDC 流通量历史", collect_usdc_circ),
        ("稳定币总盘历史", collect_stablecoin_total),
        ("EURC 流通量历史", collect_eurc_circ),
        ("美债收益率", collect_treasury),
        ("CRCL 日线", collect_crcl_stock),
    ]
    summary = {"status": "ok", "run_id": run_id, "steps": []}
    for i, (name, fn) in enumerate(steps):
        # Cancellation is BETWEEN steps: a thread blocked in a socket read cannot
        # be interrupted (the per-call ceiling in _call_with_timeout bounds it).
        if stop_event is not None and stop_event.is_set():
            return {"status": "cancelled", "msg": "采集已取消（客户端断开）",
                    "run_id": run_id, "steps": [], "alerts_changed": []}
        fn(run_id)
        if progress_cb:
            progress_cb((i + 1) / (len(steps) + 2))
    collect_valuation_snapshot(run_id)
    if progress_cb:
        progress_cb((len(steps) + 1) / (len(steps) + 2))
    update_circ_snapshot(run_id)
    changed = crcl_alerts.evaluate(run_id)
    summary["alerts_changed"] = changed
    logs = crcl_db.get_logs(limit=len(steps) + 2)
    summary["steps"] = [
        {"source": l["source"], "status": l["status"], "message": l["message"]}
        for l in logs
        if l["run_id"] == run_id
    ]
    if progress_cb:
        progress_cb(1.0)
    return summary


def schedule_startup_collection() -> None:
    """Non-blocking startup hook (called from FastAPI lifespan).

    Cannot stampede a user-triggered collect: it goes through the SAME
    single-flight lock, so whichever starts second simply returns "busy"
    (and this thread exits) instead of running a duplicate collection.
    Skippable via CRCL_STARTUP_COLLECT=0 (used by tests).
    """
    if os.getenv("CRCL_STARTUP_COLLECT", "1") == "0":
        return

    def _bg():
        try:
            result = collect_all()
            if result.get("status") == "busy":
                logger.info("[crcl] 启动采集跳过：已有采集在进行中")
        except Exception:  # noqa: BLE001 — startup must never crash
            logger.exception("[crcl] 启动采集异常")

    threading.Thread(target=_bg, daemon=True, name="crcl-startup").start()
