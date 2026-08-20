"""CRCL monitor collectors.

Each source is isolated: failures are logged to collect_log and never raised,
so one dead source does not block the others. No fabricated data — a failed
source simply produces no points and an error log row.

Sources (all free, no API key):
- DefiLlama   stablecoins.llama.fi        USDC 流通量历史 + 稳定币总盘历史
- Treasury    home.treasury.gov CSV       3M/6M/1Y 美债收益率曲线（日频）
- AKShare     stock_us_daily('CRCL')      CRCL 日线 OHLCV
- yfinance    Ticker('CRCL').info         市值 / TTM P/E / 前瞻 P/E / P/S 快照
"""

import time
import uuid
from datetime import datetime, timezone

import httpx

from backend.app.core import crcl_db

DEFILLAMA_TIMEOUT = 30
TREASURY_YEARS = 2  # 当年 + 上一年，用于回填与跨年连续

METRIC_LABELS = {
    "usdc_circ": ("USDC 流通量", "美元", "DefiLlama /stablecoin/2", "日"),
    "stablecoin_total": ("稳定币总市值", "美元", "DefiLlama /stablecoincharts/all", "日"),
    "treasury_3m": ("美债收益率 3M", "%", "Treasury.gov 年度 CSV", "日"),
    "treasury_6m": ("美债收益率 6M", "%", "Treasury.gov 年度 CSV", "日"),
    "treasury_1y": ("美债收益率 1Y", "%", "Treasury.gov 年度 CSV", "日"),
    "crcl_close": ("CRCL 收盘价", "美元", "AKShare stock_us_daily", "日"),
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

        df = ak.stock_us_daily(symbol="CRCL")
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

        h = yf.Ticker("CRCL").history(period="max")
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

        info = yf.Ticker("CRCL").info
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
        if snap:
            crcl_db.set_snapshot("stablecoins", snap)
            _log(run_id, "snapshot_stablecoins", "ok", "流通量快照已更新", t0)
    except Exception as e:  # noqa: BLE001
        _log(run_id, "snapshot_stablecoins", "error", f"{type(e).__name__}: {e}", t0)


def collect_all(progress_cb=None) -> dict:
    """Run all collectors + alert evaluation. Returns a summary dict."""
    from backend.app.core import crcl_alerts

    crcl_db.ensure_schema()
    run_id = uuid.uuid4().hex[:8]
    steps = [
        ("USDC 流通量历史", collect_usdc_circ),
        ("稳定币总盘历史", collect_stablecoin_total),
        ("美债收益率", collect_treasury),
        ("CRCL 日线", collect_crcl_stock),
    ]
    summary = {"run_id": run_id, "steps": []}
    for i, (name, fn) in enumerate(steps):
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

    Skippable via CRCL_STARTUP_COLLECT=0 (used by tests).
    """
    import os
    import threading

    if os.getenv("CRCL_STARTUP_COLLECT", "1") == "0":
        return

    def _bg():
        try:
            collect_all()
        except Exception:  # noqa: BLE001 — startup must never crash
            pass

    threading.Thread(target=_bg, daemon=True).start()
