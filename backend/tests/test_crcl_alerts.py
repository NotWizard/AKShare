"""CRCL 告警规则 fixture 测试 — 黄色与红色触发条件各验证通过。

运行：.venv312/bin/python -m pytest backend/tests/test_crcl_alerts.py -v
（无 pytest 时：.venv312/bin/python backend/tests/test_crcl_alerts.py）
"""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import date

from backend.app.core import crcl_alerts, crcl_db


def _tmp_db(monkey):
    """把 crcl_db 指向临时库，返回路径。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    monkey.setattr(crcl_db, "CRCL_DB_PATH", Path(tmp.name))
    crcl_db.ensure_schema()
    return Path(tmp.name)


def _usdc_series(yoy_pct: float) -> list[tuple[str, float]]:
    """400 天合成序列，末值相对 365 天前为 yoy_pct。"""
    from datetime import timedelta

    base = date(2026, 8, 20)
    pts = []
    for i in range(400):
        d = base - timedelta(days=399 - i)
        if i < 335:
            v = 67.0e9
        else:
            v = 67.0e9 * (1 + yoy_pct / 100) * (i - 334) / 65 + 67.0e9 * (1 - (i - 334) / 65)
        pts.append((d.isoformat(), v))
    # 保证 365 天前恰为 67e9：线性插值段覆盖最后 65 天
    return pts


class _Monkey:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, val):
        old = getattr(obj, name)
        setattr(obj, name, val)
        self._undo.append((obj, name, old))

    def undo(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)
        self._undo.clear()


def _run(rule):
    return crcl_alerts._EVALUATORS[rule]()


def test_yellow_usdc_growth():
    m = _Monkey()
    try:
        _tmp_db(m)
        crcl_db.upsert_points("usdc_circ", _usdc_series(7.0))
        status, msg = _run("y_usdc_growth")
        assert status == "triggered", msg
        crcl_db.upsert_points("usdc_circ", _usdc_series(20.0))
        status, msg = _run("y_usdc_growth")
        assert status == "ok", msg
        print("PASS yellow y_usdc_growth: 7% → triggered, 20% → ok")
    finally:
        m.undo()


def _write_fundamentals(monkey, quarters, annual=None, flags=None):
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump(
        {"quarters": quarters, "annual": annual or [], "flags": flags or {}},
        tmp, ensure_ascii=False,
    )
    tmp.close()
    monkey.setattr(crcl_alerts, "FUNDAMENTALS_PATH", Path(tmp.name))


def test_yellow_nonreserve_stagnant():
    m = _Monkey()
    try:
        _tmp_db(m)
        _write_fundamentals(m, [
            {"period": "2026Q1", "nonreserve_share_pct": 4.7},
            {"period": "2026Q2", "nonreserve_share_pct": 4.8},
        ])
        status, msg = _run("y_nonreserve_stagnant")
        assert status == "triggered", msg
        _write_fundamentals(m, [
            {"period": "2026Q1", "nonreserve_share_pct": 4.7},
            {"period": "2026Q2", "nonreserve_share_pct": 7.2},
        ])
        status, msg = _run("y_nonreserve_stagnant")
        assert status == "ok", msg
        print("PASS yellow y_nonreserve_stagnant: 停滞 → triggered, +2.5pp → ok")
    finally:
        m.undo()


def test_yellow_distribution_cost():
    m = _Monkey()
    try:
        _tmp_db(m)
        _write_fundamentals(m, [], annual=[{"period": "2024", "distribution_cost_ratio_pct": 62.0}])
        status, msg = _run("y_distribution_cost")
        assert status == "triggered", msg
        _write_fundamentals(m, [], annual=[{"period": "2024", "distribution_cost_ratio_pct": 55.0}])
        status, msg = _run("y_distribution_cost")
        assert status == "ok", msg
        print("PASS yellow y_distribution_cost: 62% → triggered, 55% → ok")
    finally:
        m.undo()


def test_red_thesis_falsified():
    m = _Monkey()
    try:
        _tmp_db(m)
        crcl_db.upsert_points("usdc_circ", _usdc_series(8.0))
        _write_fundamentals(
            m,
            [{"period": "2026Q2", "nonreserve_share_pct": 6.0}],
            flags={"fed_cutting": True},
        )
        # 检查点之前 → ok
        m.setattr(crcl_alerts, "_today", lambda: date(2026, 8, 20))
        status, msg = _run("r_thesis_falsified")
        assert status == "ok", msg
        # 检查点之后且组合条件满足 → triggered
        m.setattr(crcl_alerts, "_today", lambda: date(2027, 7, 1))
        status, msg = _run("r_thesis_falsified")
        assert status == "triggered", msg
        print("PASS red r_thesis_falsified: 检查点前 ok, 检查点后组合满足 → triggered")
    finally:
        m.undo()


def test_confirm_thesis_confirmed():
    m = _Monkey()
    try:
        _tmp_db(m)
        crcl_db.upsert_points("usdc_circ", _usdc_series(22.0))
        _write_fundamentals(
            m,
            [{"period": "2026Q2", "nonreserve_share_pct": 16.5}],
            flags={"clarity_act_passed": True},
        )
        status, msg = _run("c_thesis_confirmed")
        assert status == "triggered", msg
        print("PASS confirm c_thesis_confirmed: 组合满足 → triggered")
    finally:
        m.undo()


if __name__ == "__main__":
    test_yellow_usdc_growth()
    test_yellow_nonreserve_stagnant()
    test_yellow_distribution_cost()
    test_red_thesis_falsified()
    test_confirm_thesis_confirmed()
    print("ALL CRCL ALERT TESTS PASSED")
