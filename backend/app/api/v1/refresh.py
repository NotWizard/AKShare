"""Refresh + manifest endpoints.

POST /refresh triggers the gated pipeline (subprocess); GET /refresh/stream is an
SSE feed of progress (P3 wires the frontend to it).
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.core import refresh
from backend.app.schemas.refresh import RefreshResult

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.get("/status", response_model=RefreshResult)
def status():
    """Last-refresh manifest summary + whether a refresh is already running."""
    summary = refresh.read_manifest_summary()
    summary["busy"] = refresh.is_running()
    return RefreshResult(**summary)


@router.post("", response_model=RefreshResult)
def trigger():
    """Run the fetch pipeline (blocks ~30s; cleared caches on success)."""
    result = refresh.run_refresh()
    return RefreshResult(**result)


@router.get("/stream")
def stream():
    """SSE: real-time progress (0.0 → 1.0) then the final result.

    Runs the blocking refresh on a worker thread and polls a queue from the
    generator so progress lines stream as the fetcher emits them (not buffered
    until completion). Supports cancellation: if the client disconnects, the
    worker is signaled to stop early (kills subprocess + releases lockfile).
    """
    import threading
    from queue import Queue, Empty

    q: Queue = Queue()
    result_box: dict = {}
    stop_event = threading.Event()

    def cb(frac: float):
        if stop_event.is_set():
            return  # worker will check stop_event and abort
        q.put(frac)

    def worker():
        result_box["r"] = refresh.run_refresh(progress_cb=cb, stop_event=stop_event)
        q.put(None)  # sentinel: refresh finished

    threading.Thread(target=worker, daemon=True).start()

    def event_source():
        try:
            while True:
                try:
                    item = q.get(timeout=1.0)
                except Empty:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                yield f"data: {json.dumps({'progress': round(item, 3)})}\n\n"
            yield f"data: {json.dumps({'done': True, 'result': result_box.get('r')})}\n\n"
        except GeneratorExit:
            # Client disconnected — signal worker to stop early
            stop_event.set()
            raise

    return StreamingResponse(event_source(), media_type="text/event-stream")
