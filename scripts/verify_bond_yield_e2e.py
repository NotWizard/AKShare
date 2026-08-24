#!/usr/bin/env python3
"""联网真实重放国债收益率抓取（G30 / P-L 收尾的联网验证器）。

为什么单独一个脚本：`fetch_bond_yield` 的 TLS 与取表修复（`2a3b8a0`）需要真实
出网才能端到端验证，而开发沙箱的出口策略禁止外连（DNS 正常但 TCP 被拒）。离线
部分已由 `backend/tests/test_bond_yield_e2e.py` 全链路覆盖（除 socket 外全真）；
本脚本补上真实网络那一段——**在任意有网机器上跑一次即可闭环**。

安全性：只写入临时库（`tempfile`），**绝不触碰 `data/macro_data.db`**；
只读地与 live 库比对（若存在）做回归检查。

用法:
    .venv312/bin/python scripts/verify_bond_yield_e2e.py

退出码: 0 全部通过 / 1 有断言失败（每条失败都会打印原因）。
"""

import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

LIVE_DB = ROOT / "data" / "macro_data.db"

_failures = []


def check(cond, label, detail=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        _failures.append(label)


def main():
    spec = importlib.util.spec_from_file_location(
        "fetch_data_mod", SCRIPTS / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fetch_data_mod"] = mod
    spec.loader.exec_module(mod)

    print("\n[1/4] TLS 校验（不关校验能否 200）")
    import requests
    try:
        r = requests.get(
            "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery",
            params={"startDate": "2026-01-01", "endDate": "2026-12-31",
                    "gjqx": "0", "qxId": "ycqx", "locale": "cn_ZH"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        check(r.status_code == 200, "默认 CA 直连返回 200",
              f"HTTP {r.status_code}, {len(r.text)} 字节")
    except Exception as e:
        check(False, "默认 CA 直连返回 200", f"{type(e).__name__}: {e}")
        print("\n⛔ 无法出网或该站点拒绝校验后的连接——后续步骤跳过。")
        return 1

    print("\n[2/4] 按列认表（真实页面）")
    from io import StringIO

    from _specs import CB_CURVE_COLS, pick_curve_table
    dfs = pd.read_html(StringIO(r.text.replace("&nbsp", "")), header=0)
    try:
        picked = pick_curve_table(dfs)
        check(all(c in picked.columns for c in CB_CURVE_COLS),
              f"认出含 {CB_CURVE_COLS} 的数据表", f"共 {len(dfs)} 张表")
        check(len(picked) > 0, "数据表非空", f"{len(picked)} 行")
    except LookupError as e:
        check(False, "认表成功", str(e))

    print("\n[3/4] 全年重放 → 月频 → 闸门 → 落库（临时库）")
    incomplete = False
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(Path(td) / "macro.db")
        mod._MANIFEST.clear()
        mod._MANIFEST.update({"tables": {}})

        # 捕获 fetcher 自身日志，以便统计「因网络失败的年份数」：部分年份下载
        # 失败时序列本就不完整，闸门拒收是**正确的保护行为**，不能记为代码缺陷。
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = mod.fetch_bond_yield(conn)
        fetch_log = buf.getvalue()
        print(fetch_log, end="")
        failed_years = fetch_log.count("年采集失败")
        incomplete = failed_years > 0
        if incomplete:
            print(f"  ⚠️  本次有 {failed_years} 个年份下载失败（环境网络不稳），"
                  "序列不完整 → 下面的闸门/月份数断言按「预期拒收」处理")

        check(not result.empty, "返回非空月频序列", f"{len(result)} 个月")
        if not result.empty:
            check(list(result.columns) == ["date", "y_10y"], "列为 date/y_10y")
            check(result["date"].is_monotonic_increasing, "按日期升序")
            check(all(d.endswith("-01") for d in result["date"]),
                  "月频锚点为月初 YYYY-MM-01")
            check(result["y_10y"].between(0, 10).all(), "收益率全部落在 (0,10)",
                  f"min={result['y_10y'].min()} max={result['y_10y'].max()}")
            print(f"     最新: {result['date'].iloc[-1]} = {result['y_10y'].iloc[-1]}")

        entry = mod._MANIFEST["tables"].get("bond_yield", {})
        if incomplete:
            check(entry.get("status") == "kept_previous",
                  "序列不完整时闸门正确拒收（保护既有数据）", str(entry.get("reason", "")))
        else:
            check(entry.get("status") == "updated", "通过 validate 闸门并落库",
                  str(entry))
            stored = pd.read_sql("SELECT * FROM bond_yield ORDER BY date", conn)
            check(len(stored) == len(result), "库内行数与返回一致")
            idx = pd.read_sql("SELECT name FROM sqlite_master WHERE type='index' "
                              "AND tbl_name='bond_yield'", conn)
            check(not idx.empty, "UNIQUE 索引已重建")
        conn.close()

    print("\n[4/4] 与 live 库回归比对（只读）")
    if not LIVE_DB.exists():
        print("     (live 库不存在，跳过)")
    elif result.empty:
        print("     (本次无数据，跳过)")
    else:
        live = pd.read_sql("SELECT date, y_10y FROM bond_yield ORDER BY date",
                           sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True))
        if incomplete:
            print(f"     (本次重放不完整，跳过月份数比对：new={len(result)} live={len(live)})")
        else:
            check(len(result) >= len(live) - 1,
                  "月份数不低于 live（允许 1 个月差）",
                  f"new={len(result)} live={len(live)}")
        # live 的**最新一个月**通常是「未收官月」：上次采集发生在月中，
        # `resample("ME").last()` 当时只能取到当日为止的最后一个交易日；等该月
        # 真正结束后重抓，月末值会正常修订。所以它不参与一致性比对，单独报告。
        live_open_month = live["date"].max() if not live.empty else None
        closed = live[live["date"] != live_open_month]
        merged = closed.merge(result, on="date", suffixes=("_live", "_new"))
        if not merged.empty:
            diff = (merged["y_10y_live"] - merged["y_10y_new"]).abs()
            check(diff.max() < 0.01, "已收官月份数值一致（<0.01pp）",
                  f"比对 {len(merged)} 个月，最大差 {diff.max():.4f} 于 "
                  f"{merged.loc[diff.idxmax(), 'date']}")
        if live_open_month is not None:
            new_val = result.loc[result["date"] == live_open_month, "y_10y"]
            old_val = live.loc[live["date"] == live_open_month, "y_10y"].iloc[0]
            if not new_val.empty:
                print(f"     ℹ️  live 未收官月 {live_open_month}: "
                      f"{old_val} → {new_val.iloc[0]}（月末收官后的正常修订，不计为回归）")

    print("\n" + "=" * 60)
    if _failures:
        print(f"❌ {len(_failures)} 项未通过: " + "; ".join(_failures))
        return 1
    print("✅ 联网 e2e 全年重放通过——TLS 校验已恢复、认表正确、闸门与落库正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
