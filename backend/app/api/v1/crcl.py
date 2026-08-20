"""CRCL monitor API — metrics, events, alerts, logs, refresh.

Read endpoints serve SQLite (crcl_monitor.db) + two human-maintained JSON
files (events / fundamentals). Refresh endpoints mirror the existing
refresh.py SSE pattern.
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.core import crcl_alerts, crcl_collect, crcl_db

router = APIRouter(prefix="/crcl", tags=["crcl"])

EVENTS_PATH = crcl_db.PROJECT_ROOT / "data" / "crcl_events.json"
FUNDAMENTALS_PATH = crcl_alerts.FUNDAMENTALS_PATH


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
def metrics(keys: str | None = None):
    """时序数据（图表用）。keys 逗号分隔；缺省返回全部。"""
    wanted = [k.strip() for k in keys.split(",")] if keys else crcl_db.all_metrics()
    return {
        "metrics": {
            k: {
                "label": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[0],
                "unit": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[1],
                "source": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[2],
                "freq": crcl_collect.METRIC_LABELS.get(k, (k, "", "", ""))[3],
                "points": crcl_db.get_series(k),
            }
            for k in wanted
        }
    }


@router.get("/events")
def events():
    """宏观事件与里程碑时间线（手工维护的 JSON 文件）。"""
    try:
        data = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"updated_at": None, "events": [], "error": str(e)}
    evts = sorted(data.get("events", []), key=lambda x: x.get("date", ""))
    return {"updated_at": data.get("updated_at"), "events": evts}


@router.get("/fundamentals")
def fundamentals():
    """季报拆解与标志位（手工维护的 JSON 文件）。"""
    try:
        return json.loads(FUNDAMENTALS_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


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
def logs(limit: int = 100):
    """采集/告警日志（倒序）。"""
    return {"logs": crcl_db.get_logs(limit=limit)}


@router.post("/refresh")
def refresh():
    """阻塞式全量采集 + 告警评估。"""
    return crcl_collect.collect_all()


@router.get("/refresh/stream")
def refresh_stream():
    """SSE 实时进度（与现有 /refresh/stream 同模式）。"""
    import threading
    from queue import Empty, Queue

    q: Queue = Queue()
    result_box: dict = {}

    def cb(frac: float):
        q.put(frac)

    def worker():
        result_box["r"] = crcl_collect.collect_all(progress_cb=cb)
        q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_source():
        while True:
            try:
                item = q.get(timeout=1.0)
            except Empty:
                yield ": keepalive\n\n"
                continue
            if item is None:
                break
            yield f"data: {json.dumps({'progress': round(item, 3)})}\n\n"
        yield f"data: {json.dumps({'done': True, 'result': result_box.get('r')}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
