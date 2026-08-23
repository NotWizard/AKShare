"""Refresh + manifest endpoints.

POST /refresh STARTS the gated pipeline (subprocess) and returns a job id;
GET /refresh/stream?job_id=… only SUBSCRIBES to that job's SSE progress.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.core import refresh
from backend.app.core.auth import require_token
from backend.app.core.locking import create_job, get_job
from backend.app.schemas.refresh import RefreshResult

router = APIRouter(prefix="/refresh", tags=["refresh"])

# Reported when the shared background-job pool has no free slot. Same shape and
# wording as core.refresh's own busy result, so the client cannot tell (or care)
# whether it lost the flock race or the admission-control race.
_POOL_BUSY = {"status": "busy", "msg": "已有刷新在进行中，请稍候…",
              "ts": None, "updated": [], "kept_previous": []}


@router.get("/status", response_model=RefreshResult)
def status():
    """Last-refresh manifest summary + whether a refresh is already running."""
    summary = refresh.read_manifest_summary()
    summary["busy"] = refresh.is_running()
    return RefreshResult(**summary)


@router.post("", response_model=RefreshResult, dependencies=[Depends(require_token)])
def trigger(full: bool = False):
    """Start the fetch pipeline in the background; returns its ``job_id`` at once.

    F4: this POST is now the ONLY way to start a refresh — ``GET /refresh/stream``
    just subscribes — and it requires the local capability token, so a
    cross-origin page can no longer rewrite the production DB by pointing an
    ``<img>``/prefetch at an API URL.

    ``full=true`` bypasses the release calendar (fetch all tables). The final
    manifest arrives on the stream's terminal ``done`` event (or via
    ``GET /refresh/status``); a saturated pool reports busy instead of queueing.
    """
    job = create_job(lambda progress_cb, stop_event: refresh.run_refresh(
        progress_cb=progress_cb, stop_event=stop_event, full=full))
    if job is None:
        return RefreshResult(**_POOL_BUSY)
    return RefreshResult(status="running", msg="刷新已启动", job_id=job.id)


# NOTE: the wire format below is frozen — the frontend parses `data: ` lines and
# reads payload.progress / payload.done / payload.result.
async def _event_source(job):
    """SSE body for one subscriber of ``job``.

    ``async`` on purpose (F7): a SYNC generator is driven by Starlette via
    ``iterate_in_threadpool``, so every ``next()`` — including the one blocked in
    ``q.get(timeout=1.0)`` — burns one of AnyIO's 40 threadpool tokens for the
    whole life of the connection. A few dozen open tabs therefore starved EVERY
    endpoint, ``/health`` included, on this single-worker uvicorn. An async
    generator awaiting an ``asyncio.Queue`` holds ZERO tokens.

    ``job.subscribe`` replays whatever the worker already emitted before this
    request arrived, so splitting POST/GET does not lose the first ticks.
    Cancellation is preserved: if the client disconnects, the generator is closed
    and the worker is signalled to stop early (kills subprocess + releases lock).
    """
    q = job.subscribe(asyncio.get_running_loop())
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
        yield f"data: {json.dumps({'done': True, 'result': job.result})}\n\n"
    except (asyncio.CancelledError, GeneratorExit):
        # Client disconnected — signal worker to stop early
        job.stop_event.set()
        raise
    finally:
        job.unsubscribe(q)


@router.get("/stream")
async def stream(job_id: str):
    """SSE: real-time progress (0.0 → 1.0) then the final result. READ-ONLY.

    F4: ``job_id`` is required and is only ever minted by ``POST /refresh``, so
    this GET can no longer start a refresh — which is what made
    ``<img src="…/refresh/stream">``, a browser prefetch/prerender or a link
    scanner able to rewrite the production DB. A missing ``job_id`` is a 422 from
    validation (the handler never runs) and an unknown/expired one is a 404.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404,
                            detail="job_id 不存在或已过期：请重新触发 POST /api/v1/refresh")
    return StreamingResponse(_event_source(job), media_type="text/event-stream")
