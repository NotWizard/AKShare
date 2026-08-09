"""Dual-source checks — run_checks on constructed primary/secondary samples.

覆盖任务三口径：divergence→warning（转黄灯）、容差边界、次源失败降级。
次源抓取以假 fetcher 替换（monkeypatch _FETCHERS），零网络。

Run:  .venv312/bin/python -m pytest backend/tests/test_dual_sources.py -q
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import dual_sources  # noqa: E402
from backend.app.core.refresh import sources_health  # noqa: E402

CPI_SOURCE = "ak.macro_china_cpi_yearly"

# primary 样本：3 个月，末点 2026-07-01 = 2.0
PRIMARY = pd.DataFrame({"date": ["2026-05-01", "2026-06-01", "2026-07-01"],
                        "cpi_yoy": [1.0, 0.5, 2.0]})


def _conn():
    conn = sqlite3.connect(":memory:")
    PRIMARY.to_sql("cpi", conn, index=False)
    return conn


def _run(monkeypatch, secondary=None, raises=None, ok_tables=("cpi",)):
    if raises is not None:
        fake = raises
    else:
        fake = lambda: secondary  # noqa: E731
    monkeypatch.setitem(dual_sources._FETCHERS, CPI_SOURCE, fake)
    return dual_sources.run_checks(_conn(), set(ok_tables))


def test_match_within_tolerance(monkeypatch):
    # 次源含 primary 没有的新月 → 比对点仍是最后公共日期
    sec = pd.DataFrame({"date": ["2026-06-01", "2026-07-01", "2026-08-01"],
                        "value": [0.55, 2.05, 9.9]})
    out = _run(monkeypatch, secondary=sec)
    rec = out["cpi"]
    assert rec["date"] == "2026-07-01"
    assert rec["primary"] == 2.0 and rec["secondary"] == 2.05
    assert rec["diff"] == -0.05
    assert rec["divergent"] is False and rec["error"] is None


def test_tolerance_boundary_abs_03(monkeypatch):
    # Δ 恰 0.3 → 绝对差支路通过（_EPS 吸收浮点噪声）；Δ0.31 且相对差 >2% → 拒
    ok = _run(monkeypatch, secondary=pd.DataFrame(
        {"date": ["2026-07-01"], "value": [2.3]}))
    assert ok["cpi"]["divergent"] is False
    bad = _run(monkeypatch, secondary=pd.DataFrame(
        {"date": ["2026-07-01"], "value": [2.31]}))
    assert bad["cpi"]["divergent"] is True


def test_divergence_flagged(monkeypatch):
    sec = pd.DataFrame({"date": ["2026-07-01"], "value": [5.0]})
    rec = _run(monkeypatch, secondary=sec)["cpi"]
    assert rec["divergent"] is True
    assert rec["diff"] == -3.0


def test_secondary_failure_degrades(monkeypatch):
    def boom():
        raise ConnectionError("upstream down")
    rec = _run(monkeypatch, raises=boom)["cpi"]
    assert rec["error"] == "ConnectionError: upstream down"
    # 检查器自身故障只记录：不判分歧、日期/值留空
    assert rec["divergent"] is False
    assert rec["date"] is None and rec["primary"] is None


def test_skips_tables_not_ok(monkeypatch):
    assert _run(monkeypatch, ok_tables=()) == {}
    # cpi 未抓成功（不在 ok_tables）→ 不比；无双源规格的表也不产生条目
    assert _run(monkeypatch, ok_tables=("fiscal",)) == {}


def test_primary_never_written(monkeypatch):
    conn = _conn()
    before = conn.execute("SELECT * FROM cpi ORDER BY date").fetchall()
    sec = pd.DataFrame({"date": ["2026-07-01"], "value": [5.0]})
    monkeypatch.setitem(dual_sources._FETCHERS, CPI_SOURCE, lambda: sec)
    dual_sources.run_checks(conn, {"cpi"})
    assert conn.execute("SELECT * FROM cpi ORDER BY date").fetchall() == before


def test_divergence_yellows_health(monkeypatch):
    # run_checks 分歧记录 → manifest 接线 → sources_health 转黄
    rec = _run(monkeypatch, secondary=pd.DataFrame(
        {"date": ["2026-07-01"], "value": [5.0]}))["cpi"]
    src = {"table": "cpi", "channel": "test", "ok": True, "elapsed_s": 0.1,
           "error": None, "consecutive_failures": 0, "last_success": None,
           "dual": rec}
    h = sources_health({"ts": "t", "tables": {"cpi": {"status": "updated"}},
                        "sources": [src]})
    assert h["status"] == "yellow"
    assert "dual-source divergence" in h["sources"][0]["warning"]
