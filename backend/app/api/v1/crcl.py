"""CRCL monitor API — metrics, events, alerts, logs, refresh.

Read endpoints serve SQLite (crcl_monitor.db) + two human-maintained JSON
files (events / fundamentals). Refresh endpoints mirror the existing
refresh.py SSE pattern.

Hardening (F11/F12): every query parameter is bounded — ``keys`` is filtered
against the METRIC_LABELS whitelist (so one request can never fan out into N
per-key connections), ``limit`` carries ``ge/le`` bounds (SQLite treats a
NEGATIVE limit as unlimited, so ``?limit=-1`` used to dump the whole table), and
the time series are windowed/downsampled. Error responses carry an opaque
``error_id`` instead of ``str(e)``, which for a missing file is an absolute path.
"""

import asyncio
import datetime
import json
import logging
import math
import threading
import uuid
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.app.core import crcl_alerts, crcl_collect, crcl_db
from backend.app.core.locking import submit_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crcl", tags=["crcl"])

EVENTS_PATH = crcl_db.PROJECT_ROOT / "data" / "crcl_events.json"
FUNDAMENTALS_PATH = crcl_alerts.FUNDAMENTALS_PATH

# Reported when the shared background-job pool has no free slot — same shape and
# wording as crcl_collect's own single-flight busy result.
_POOL_BUSY = {"status": "busy", "msg": "已有采集在进行中，请稍候…",
              "run_id": None, "steps": [], "alerts_changed": []}


def _error_id() -> str:
    """Short opaque handle: logged next to the full detail, returned alone (F12)."""
    return uuid.uuid4().hex[:8]


def _downsample(points: list[dict], max_points: int) -> list[dict]:
    """Uniform-stride thin to ``<= max_points``, always keeping the LAST point.

    A 280px-wide chart cannot show 3187 daily points; the page used to pull
    ~7615 of them (~350KB). Stride sampling preserves the visual shape and the
    latest value (which the KPI deltas read) without any server-side smoothing.
    """
    n = len(points)
    if n <= max_points:
        return points
    stride = math.ceil(n / max_points)
    out = points[::stride]
    if (n - 1) % stride:
        out.append(points[-1])
    return out


# --- Schema for the hand-maintained events JSON (G22) -------------------
# Enum sets mirror the documented values in data/crcl_events.json (_说明).
EventCategory = Literal["财报", "监管", "宏观", "里程碑", "合作", "检查点"]
EventStatus = Literal["已发生", "进行中", "待观察", "待验证", "计划"]


class CrclEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: datetime.date            # rejects 2026/08/05, 2026-13-01, etc.
    category: EventCategory
    title: str
    detail: str = ""
    source: str = ""
    status: EventStatus


class CrclEventsFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    updated_at: datetime.date | None = None
    events: list[CrclEvent] = []


@router.get("/overview")
def overview():
    """KPI 区数据：估值快照 + 流通量快照 + 告警汇总 + 最近采集状态。"""
    snaps = crcl_db.get_snapshots()
    rule_status = crcl_db.get_rule_status()
    triggered = [
        {"rule": r, **s}
        for r, s in rule_status.items()
        if s.get("status") == "triggered"
    ]
    levels = {r: crcl_alerts.RULES[r][0] for r in rule_status}
    logs = crcl_db.get_logs(limit=1)
    return {
        "snapshots": snaps,
        "alert_summary": {
            "triggered": triggered,
            "levels": levels,
            "rule_count": len(rule_status),
        },
        "last_run": logs[0] if logs else None,
        "metric_labels": crcl_collect.METRIC_LABELS,
    }


@router.get("/metrics")
def metrics(
    keys: str | None = None,
    since: datetime.date | None = None,
    max_points: int = Query(1500, ge=1, le=5000),
):
    """时序数据（图表用）。keys 逗号分隔；缺省返回全部。

    F11: ``keys`` 只接受 METRIC_LABELS 白名单内的键（未知键丢弃并记日志），
    去重后扇出上限 = 白名单长度，与用户输入长度无关——旧代码对
    ``?keys=`` 的每个逗号项都新建一个连接并查询一次。
    ``since``（含当日）与 ``max_points`` 把响应体积也框住。
    """
    if keys:
        wanted, dropped = [], []
        for raw in keys.split(","):
            k = raw.strip()
            if k in crcl_collect.METRIC_LABELS:
                if k not in wanted:
                    wanted.append(k)
            elif k:
                dropped.append(k)
        if dropped:
            logger.warning("[crcl] metrics 未知键已丢弃（共 %d 个）: %s",
                           len(dropped), dropped[:5])
    else:
        wanted = crcl_db.all_metrics()
    since_iso = since.isoformat() if since else None
    return {
        "metrics": {
            k: {
                "label": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[0],
                "unit": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[1],
                "source": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[2],
                "freq": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[3],
                "points": _downsample(crcl_db.get_series(k, since=since_iso), max_points),
            }
            for k in wanted
        }
    }


@router.get("/events")
def events():
    """宏观事件与里程碑时间线（手工维护的 JSON 文件）。"""
    try:
        raw = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        # str(e) is "[Errno 2] … '/Users/<name>/…/data/crcl_events.json'" — an
        # absolute path leak. Full detail to the log, only the id to the client.
        eid = _error_id()
        logger.error("[crcl] events 文件读取/解析失败 (error_id=%s): %r", eid, e)
        return {"updated_at": None, "events": [],
                "error": f"文件读取/解析失败（error_id={eid}）", "error_id": eid}
    try:
        CrclEventsFile.model_validate(raw)
    except ValidationError as e:
        detail = crcl_alerts.format_validation_error(e)
        logger.error("[crcl] events schema 校验失败: %s", detail)
        return {
            "updated_at": None,
            "events": [],
            "error": f"数据校验失败: {detail}",
            "errors": crcl_alerts.validation_error_details(e),
        }
    evts = sorted(raw.get("events", []), key=lambda x: x.get("date", ""))
    return {"updated_at": raw.get("updated_at"), "events": evts}


@router.get("/fundamentals")
def fundamentals():
    """季报拆解与标志位（手工维护的 JSON 文件）。"""
    try:
        raw = json.loads(FUNDAMENTALS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        eid = _error_id()
        logger.error("[crcl] fundamentals 文件读取/解析失败 (error_id=%s): %r", eid, e)
        return {"error": f"文件读取/解析失败（error_id={eid}）", "error_id": eid}
    try:
        crcl_alerts.FundamentalsFile.model_validate(raw)
    except ValidationError as e:
        detail = crcl_alerts.format_validation_error(e)
        logger.error("[crcl] fundamentals schema 校验失败: %s", detail)
        return {
            "error": f"数据校验失败: {detail}",
            "errors": crcl_alerts.validation_error_details(e),
        }
    return raw


@router.get("/alerts")
def alerts():
    """告警规则当前状态 + 触发历史。"""
    rule_status = crcl_db.get_rule_status()
    rules = [
        {
            "rule": r,
            "level": crcl_alerts.RULES[r][0],
            "description": crcl_alerts.RULES[r][1],
            "status": rule_status.get(r, {}).get("status", "not_evaluated"),
            "message": rule_status.get(r, {}).get("message", ""),
            "ts": rule_status.get(r, {}).get("ts"),
        }
        for r in crcl_alerts.RULES
    ]
    return {"rules": rules, "history": crcl_db.get_logs(limit=50)}


@router.get("/logs")
def logs(limit: int = Query(100, ge=1, le=500)):
    """采集/告警日志（倒序）。

    F11: ``limit`` 必须有界——SQLite 把负数 LIMIT 当作"无限制"，旧签名
    ``limit: int`` 让 ``?limit=-1`` 一次导出整张表。
    """
    return {"logs": crcl_db.get_logs(limit=limit)}


@router.post("/refresh")
def refresh():
    """阻塞式全量采集 + 告警评估。

    单飞（F6）：已有采集在进行时立即返回 ``status="busy"``，不再并发跑第二遍。
    """
    return crcl_collect.collect_all()


@router.get("/refresh/stream")
async def refresh_stream():
    """SSE 实时进度（与现有 /refresh/stream 同模式）。

    ``async def`` on purpose (F7): a SYNC generator is driven through
    ``iterate_in_threadpool``, so each open SSE connection permanently occupied
    one of AnyIO's 40 threadpool tokens while blocked in ``q.get(timeout=1.0)``.
    An async generator awaiting an ``asyncio.Queue`` holds ZERO tokens. The
    collection itself runs on the ONE shared bounded pool (``submit_job``) rather
    than an uncapped per-request thread, and a disconnecting client now sets
    ``stop_event`` so the remaining network collection is abandoned instead of
    running to completion for nobody.
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    result_box: dict = {}
    stop_event = threading.Event()

    def emit(item):
        try:
            loop.call_soon_threadsafe(q.put_nowait, item)
        except RuntimeError:
            pass  # event loop already closed (client gone / server shutdown)

    def cb(frac: float):
        if stop_event.is_set():
            return
        emit(frac)

    def worker():
        try:
            result_box["r"] = crcl_collect.collect_all(
                progress_cb=cb, stop_event=stop_event)
        finally:
            emit(None)  # sentinel: collection finished (even if it raised)

    if submit_job(worker) is None:
        result_box["r"] = _POOL_BUSY  # pool saturated → terminal event only
        q.put_nowait(None)

    # NOTE: the wire format below is frozen — the frontend parses `data: ` lines
    # and reads payload.progress (CrclMonitor.vue) / payload.done.
    async def event_source():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                yield f"data: {json.dumps({'progress': round(item, 3)})}\n\n"
            yield f"data: {json.dumps({'done': True, 'result': result_box.get('r')}, ensure_ascii=False)}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            stop_event.set()  # client disconnected → abandon the collection
            raise

    return StreamingResponse(event_source(), media_type="text/event-stream")
