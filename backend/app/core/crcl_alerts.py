"""CRCL alert engine — evaluates spec rules against collected data.

Rules come from docs/CRCL监控体系.md 决策规则. Each evaluate() returns
(status, message) with status ∈ {ok, triggered, insufficient_data}.
Only status *changes* are written to the alerts table (no log spam).

Data-driven rules use metric_points (auto-collected); judgment rules use
data/crcl_fundamentals.json (human-maintained quarters + flags).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core import crcl_db

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FUNDAMENTALS_PATH = PROJECT_ROOT / "data" / "crcl_fundamentals.json"

RULES = {
    "y_usdc_growth": ("yellow", "USDC 流通量同比增速 <15%（跑不赢降息）"),
    "y_nonreserve_stagnant": ("yellow", "非储备收入占比连续两季停滞（变化 <1pp）"),
    "y_distribution_cost": ("yellow", "分发成本率 >60% 且无下降趋势"),
    "r_thesis_falsified": ("red", "论点证伪：2027 年中 非储备占比 <10% + 流通增速 <10% + 降息持续"),
    "c_thesis_confirmed": ("confirm", "论点确认：非储备占比 >15% + 流通增速 ≥20% + Clarity Act 通过"),
}


def _today():
    return datetime.now(timezone.utc).date()


def _load_fundamentals() -> dict:
    try:
        return json.loads(FUNDAMENTALS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _usdc_yoy() -> float | None:
    """USDC 流通量同比（%）：最新值 vs ~365 天前的值。"""
    series = crcl_db.get_series("usdc_circ")
    if len(series) < 300:
        return None
    latest = series[-1]
    target = datetime.strptime(latest["date"], "%Y-%m-%d").timestamp() - 365 * 86400
    past = min(series, key=lambda p: abs(datetime.strptime(p["date"], "%Y-%m-%d").timestamp() - target))
    if past["value"] <= 0:
        return None
    return (latest["value"] / past["value"] - 1) * 100


def _eval_y_usdc_growth() -> tuple[str, str]:
    yoy = _usdc_yoy()
    if yoy is None:
        return "insufficient_data", "USDC 历史数据不足 300 天，无法计算同比"
    if yoy < 15:
        return "triggered", f"USDC 流通量同比 {yoy:.1f}% < 15%"
    return "ok", f"USDC 流通量同比 {yoy:.1f}% ≥ 15%"


def _eval_y_nonreserve_stagnant() -> tuple[str, str]:
    f = _load_fundamentals()
    qs = f.get("quarters", [])
    shares = [q.get("nonreserve_share_pct") for q in qs if q.get("nonreserve_share_pct") is not None]
    if len(shares) < 2:
        return "insufficient_data", "quarters 中不足两季 nonreserve_share_pct 数据（需手工维护）"
    delta = shares[-1] - shares[-2]
    if abs(delta) < 1.0:
        return "triggered", f"非储备占比 {shares[-2]}% → {shares[-1]}%（变化 {delta:+.1f}pp，停滞）"
    return "ok", f"非储备占比 {shares[-2]}% → {shares[-1]}%（{delta:+.1f}pp）"


def _eval_y_distribution_cost() -> tuple[str, str]:
    f = _load_fundamentals()
    ratios = [
        q.get("distribution_cost_ratio_pct")
        for q in f.get("quarters", [])
        if q.get("distribution_cost_ratio_pct") is not None
    ] + [
        a.get("distribution_cost_ratio_pct")
        for a in f.get("annual", [])
        if a.get("distribution_cost_ratio_pct") is not None
    ]
    if not ratios:
        return "insufficient_data", "annual.distribution_cost_ratio_pct 未填写（对照年报后手工维护）"
    if ratios[-1] > 60:
        return "triggered", f"分发成本率 {ratios[-1]}% > 60%"
    return "ok", f"分发成本率 {ratios[-1]}% ≤ 60%"


def _eval_r_thesis_falsified() -> tuple[str, str]:
    f = _load_fundamentals()
    flags = f.get("flags", {})
    qs = f.get("quarters", [])
    shares = [q.get("nonreserve_share_pct") for q in qs if q.get("nonreserve_share_pct") is not None]
    yoy = _usdc_yoy()
    now = _today()
    checkpoint = datetime(2027, 6, 30).date()
    if now < checkpoint:
        return "ok", f"检查点 2027-06-30 未到（当前 {now.isoformat()}）"
    missing = []
    if not shares:
        missing.append("非储备占比")
    if yoy is None:
        missing.append("流通量同比")
    if missing:
        return "insufficient_data", "缺少：" + "、".join(missing)
    conds = shares[-1] < 10 and yoy < 10 and flags.get("fed_cutting", False)
    if conds:
        return "triggered", (
            f"非储备占比 {shares[-1]}% <10%，流通增速 {yoy:.1f}% <10%，降息持续 → 估值锚滑向货币基金侧"
        )
    return "ok", f"未满足证伪组合（非储备 {shares[-1]}%，流通同比 {yoy:.1f}%）"


def _eval_c_thesis_confirmed() -> tuple[str, str]:
    f = _load_fundamentals()
    flags = f.get("flags", {})
    qs = f.get("quarters", [])
    shares = [q.get("nonreserve_share_pct") for q in qs if q.get("nonreserve_share_pct") is not None]
    yoy = _usdc_yoy()
    if not shares or yoy is None:
        return "insufficient_data", "缺少非储备占比或流通量同比数据"
    conds = (
        shares[-1] > 15
        and yoy >= 20
        and flags.get("clarity_act_passed", False)
    )
    detail = f"非储备占比 {shares[-1]}%（需 >15%），流通同比 {yoy:.1f}%（需 ≥20%），Clarity Act {'已' if flags.get('clarity_act_passed') else '未'}通过"
    return ("triggered", detail) if conds else ("ok", detail)


_EVALUATORS = {
    "y_usdc_growth": _eval_y_usdc_growth,
    "y_nonreserve_stagnant": _eval_y_nonreserve_stagnant,
    "y_distribution_cost": _eval_y_distribution_cost,
    "r_thesis_falsified": _eval_r_thesis_falsified,
    "c_thesis_confirmed": _eval_c_thesis_confirmed,
}


def evaluate(run_id: str) -> list[str]:
    """Evaluate all rules; persist only status changes. Returns changed rules."""
    prev = crcl_db.get_rule_status()
    changed: list[str] = []
    for rule, fn in _EVALUATORS.items():
        level, _desc = RULES[rule]
        try:
            status, message = fn()
        except Exception as e:  # noqa: BLE001
            status, message = "insufficient_data", f"评估异常 {type(e).__name__}: {e}"
        last = prev.get(rule, {}).get("status")
        if status != last:
            crcl_db.add_alert(rule, level, status, message)
            crcl_db.add_log(
                run_id, f"alert:{rule}",
                "alert" if status == "triggered" else "info",
                f"[{level}] {status}: {message}", 0,
            )
            changed.append(rule)
    return changed
