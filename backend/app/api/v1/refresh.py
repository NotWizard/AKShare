"""Refresh + manifest endpoints.

POST /refresh triggers the gated pipeline (subprocess); GET /refresh/stream is an
SSE feed of progress (P3 wires the frontend to it).
"""

import asyncio
import json
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.core import refresh
from backend.app.core.locking import submit_job
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


@router.post("", response_model=RefreshResult)
def trigger(full: bool = False):
    """Run the fetch pipeline (blocks ~30s; cleared caches on success).

    ``full=true`` bypasses the release calendar (fetch all tables).
    """
    result = refresh.run_refresh(full=full)
    return RefreshResult(**result)


@router.get("/stream")
async def stream(full: bool = False):
    """SSE: real-time progress (0.0 → 1.0) then the final result.

    ``async def`` on purpose (F7): a SYNC generator is driven by Starlette via
    ``iterate_in_threadpool``, so every ``next()`` — including the one blocked in
    ``q.get(timeout=1.0)`` — burns one of AnyIO's 40 threadpool tokens for the
    whole life of the connection. A few dozen open tabs therefore starved EVERY
    endpoint, ``/health`` included, on this single-worker uvicorn. An async
    generator awaiting an ``asyncio.Queue`` holds ZERO tokens.

    The blocking refresh runs on the ONE shared bounded pool
    (``locking.submit_job``) instead of a fresh unbounded thread per request;
    a saturated pool reports "busy" rather than queueing. The worker hands
    progress back with ``loop.call_soon_threadsafe``.
    Cancellation is preserved: if the client disconnects, the generator is closed
    and the worker is signalled to stop early (kills subprocess + releases lock).
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
            return  # worker will check stop_event and abort
        emit(frac)

    def worker():
        try:
            result_box["r"] = refresh.run_refresh(
                progress_cb=cb, stop_event=stop_event, full=full)
        finally:
            emit(None)  # sentinel: refresh finished (even if it raised)

    if submit_job(worker) is None:
        result_box["r"] = _POOL_BUSY  # pool saturated → terminal event only
        q.put_nowait(None)

    # NOTE: the wire format below is frozen — the frontend parses `data: `
    # lines and reads payload.progress / payload.done / payload.result.
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
            yield f"data: {json.dumps({'done': True, 'result': result_box.get('r')})}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected — signal worker to stop early
            stop_event.set()
            raise

    return StreamingResponse(event_source(), media_type="text/event-stream")
