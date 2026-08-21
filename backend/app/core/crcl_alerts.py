"""CRCL alert engine — evaluates spec rules against collected data.

Rules come from docs/CRCL监控体系.md 决策规则. Each evaluate() returns
(status, message) with status ∈ {ok, triggered, insufficient_data}.
Only status *changes* are written to the alerts table (no log spam).

Data-driven rules use metric_points (auto-collected); judgment rules use
data/crcl_fundamentals.json (human-maintained quarters + flags).
"""

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, ValidationError

from backend.app.core import crcl_db

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FUNDAMENTALS_PATH = PROJECT_ROOT / "data" / "crcl_fundamentals.json"


class CrclDataError(ValueError):
    """data/crcl_fundamentals.json failed schema validation (field-located)."""


def format_validation_error(exc: ValidationError) -> str:
    """Collapse a pydantic ValidationError into one field-located line."""
    parts = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(x) for x in err["loc"]) or "(root)"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def validation_error_details(exc: ValidationError) -> list[dict]:
    """Structured per-field errors for API error responses."""
    return [
        {"loc": ".".join(str(x) for x in e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]


# StrictFloat accepts int *and* float but rejects strings (e.g. "4.7"), which
# is exactly the semantic-typo guard we want for hand-maintained numbers.
class _Flags(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fed_cutting: bool = False
    clarity_act_passed: bool = False


class _Quarter(BaseModel):
    model_config = ConfigDict(extra="ignore")
    period: str
    total_revenue_m: StrictFloat | None = None
    total_revenue_yoy_pct: StrictFloat | None = None
    reserve_revenue_m: StrictFloat | None = None
    reserve_revenue_yoy_pct: StrictFloat | None = None
    other_revenue_m: StrictFloat | None = None
    nonreserve_share_pct: StrictFloat | None = None
    eps_actual: StrictFloat | None = None
    eps_consensus: StrictFloat | None = None
    usdc_circ_end_b: StrictFloat | None = None
    usdc_circ_avg_b: StrictFloat | None = None
    usdc_circ_yoy_pct: StrictFloat | None = None
    usdc_onchain_volume_t: StrictFloat | None = None
    distribution_cost_m: StrictFloat | None = None
    distribution_cost_ratio_pct: StrictFloat | None = None
    eurc_circ_m: StrictFloat | None = None
    cpn_tpv_annualized_b: StrictFloat | None = None
    cpn_usdc_volume_yoy_pct: StrictFloat | None = None
    cpn_institutions: StrictFloat | None = None
    source: str | None = None


class _Annual(BaseModel):
    model_config = ConfigDict(extra="ignore")
    period: str
    distribution_cost_m: StrictFloat | None = None
    coinbase_distribution_m: StrictFloat | None = None
    distribution_cost_ratio_pct: StrictFloat | None = None
    ratio_note: str | None = None
    source: str | None = None


class _Presale(BaseModel):
    model_config = ConfigDict(extra="ignore")
    arc_presale_m: StrictFloat | None = None
    arc_fdv_b: StrictFloat | None = None
    presale_revenue_guidance_m: StrictFloat | None = None
    milestone_linked_pct: StrictFloat | None = None
    source: str | None = None


class FundamentalsFile(BaseModel):
    """Schema for data/crcl_fundamentals.json (unknown keys like _说明 ignored)."""

    model_config = ConfigDict(extra="ignore")
    updated_at: date | None = None
    flags: _Flags = Field(default_factory=_Flags)
    quarters: list[_Quarter] = Field(default_factory=list)
    annual: list[_Annual] = Field(default_factory=list)
    presale: _Presale | None = None


RULES = {
    "y_usdc_growth": ("yellow", "USDC 流通量同比增速 <15%（跑不赢降息）"),
    "y_nonreserve_stagnant": ("yellow", "非储备收入占比连续两季停滞（变化 <1pp）"),
    "y_distribution_cost": ("yellow", "分发成本率 >60% 且无下降趋势"),
    "r_thesis_falsified": ("red", "论点证伪：2027 年中 非储备占比 <10% + 流通增速 <10% + 降息持续"),
    "c_thesis_confirmed": ("confirm", "论点确认：非储备占比 >15% + 流通增速 ≥20% + Clarity Act 通过"),
}


def _today():
    return datetime.now(timezone.utc).date()


def _load_fundamentals() -> FundamentalsFile:
    """Load + schema-validate the fundamentals JSON.

    Missing file → empty model (rules degrade to insufficient_data, as before).
    Unreadable / invalid JSON / schema violation → CrclDataError with a
    field-located message, so a stringified number surfaces loudly instead of
    being swallowed into a vague TypeError → "评估异常".
    """
    try:
        raw = json.loads(FUNDAMENTALS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return FundamentalsFile()
    except (OSError, json.JSONDecodeError) as e:
        raise CrclDataError(f"读取/解析 crcl_fundamentals.json 失败: {e}") from e
    try:
        return FundamentalsFile.model_validate(raw)
    except ValidationError as e:
        raise CrclDataError(format_validation_error(e)) from e


_QUARTER_RE = re.compile(r"^\s*(\d{4})Q([1-4])\s*$")


def _quarter_ordinal(period: str | None) -> int | None:
    """'2026Q2' → absolute quarter index (year*4 + q-1); None if unparseable."""
    if not period:
        return None
    m = _QUARTER_RE.match(period)
    if not m:
        return None
    return int(m.group(1)) * 4 + (int(m.group(2)) - 1)


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
    # Keep only quarters that have a numeric share *and* a parseable period,
    # then compare the two most-recent ones ONLY if they are adjacent — a
    # missing middle quarter must not be treated as "two consecutive".
    pts = []
    for q in f.quarters:
        if q.nonreserve_share_pct is None:
            continue
        ordinal = _quarter_ordinal(q.period)
        if ordinal is None:
            continue
        pts.append((ordinal, q.nonreserve_share_pct, q.period))
    if len(pts) < 2:
        return "insufficient_data", "quarters 中不足两季 nonreserve_share_pct 数据（需手工维护）"
    pts.sort(key=lambda t: t[0])
    (prev_o, prev_s, prev_p), (last_o, last_s, last_p) = pts[-2], pts[-1]
    if last_o - prev_o != 1:
        return "insufficient_data", (
            f"最近两条非空季度（{prev_p} → {last_p}）不相邻，缺中间季度，无法判定连续停滞"
        )
    delta = last_s - prev_s
    if abs(delta) < 1.0:
        return "triggered", f"非储备占比 {prev_s}% → {last_s}%（变化 {delta:+.1f}pp，停滞）"
    return "ok", f"非储备占比 {prev_s}% → {last_s}%（{delta:+.1f}pp）"


def _eval_y_distribution_cost() -> tuple[str, str]:
    f = _load_fundamentals()
    ratios = [
        q.distribution_cost_ratio_pct
        for q in f.quarters
        if q.distribution_cost_ratio_pct is not None
    ] + [
        a.distribution_cost_ratio_pct
        for a in f.annual
        if a.distribution_cost_ratio_pct is not None
    ]
    if not ratios:
        return "insufficient_data", "annual.distribution_cost_ratio_pct 未填写（对照年报后手工维护）"
    if ratios[-1] > 60:
        return "triggered", f"分发成本率 {ratios[-1]}% > 60%"
    return "ok", f"分发成本率 {ratios[-1]}% ≤ 60%"


def _eval_r_thesis_falsified() -> tuple[str, str]:
    f = _load_fundamentals()
    shares = [q.nonreserve_share_pct for q in f.quarters if q.nonreserve_share_pct is not None]
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
    conds = shares[-1] < 10 and yoy < 10 and f.flags.fed_cutting
    if conds:
        return "triggered", (
            f"非储备占比 {shares[-1]}% <10%，流通增速 {yoy:.1f}% <10%，降息持续 → 估值锚滑向货币基金侧"
        )
    return "ok", f"未满足证伪组合（非储备 {shares[-1]}%，流通同比 {yoy:.1f}%）"


def _eval_c_thesis_confirmed() -> tuple[str, str]:
    f = _load_fundamentals()
    shares = [q.nonreserve_share_pct for q in f.quarters if q.nonreserve_share_pct is not None]
    yoy = _usdc_yoy()
    if not shares or yoy is None:
        return "insufficient_data", "缺少非储备占比或流通量同比数据"
    conds = (
        shares[-1] > 15
        and yoy >= 20
        and f.flags.clarity_act_passed
    )
    detail = f"非储备占比 {shares[-1]}%（需 >15%），流通同比 {yoy:.1f}%（需 ≥20%），Clarity Act {'已' if f.flags.clarity_act_passed else '未'}通过"
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
        except CrclDataError as e:
            status, message = "insufficient_data", f"数据校验失败: {e}"
            logger.error("[crcl_alerts] rule %s 数据校验失败: %s", rule, e)
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
