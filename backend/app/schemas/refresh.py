"""Refresh result schema (mirrors core.refresh.run_refresh output)."""

from typing import Literal

from pydantic import BaseModel


class RefreshResult(BaseModel):
    status: Literal["ok", "busy", "error", "unknown", "cancelled", "running"]
    msg: str
    ts: str | None = None
    updated: list[str] = []
    kept_previous: list[str] = []
    # F4: POST /refresh no longer blocks until the pipeline finishes — it STARTS
    # the job (status="running") and returns this handle, which is the only thing
    # that lets GET /refresh/stream subscribe. The GET therefore cannot start a
    # refresh any more, so a prefetch/<img> of the stream URL is inert.
    job_id: str | None = None
    # F12: replaces the old free-text `detail`, which carried the fetch child's
    # merged stdout/stderr tail — i.e. absolute paths and tracebacks — straight
    # into the browser. The full detail is now logged server-side ONLY and this
    # opaque id is the greppable handle an operator uses to find it.
    error_id: str | None = None
