"""Refresh result schema (mirrors core.refresh.run_refresh output)."""

from typing import Literal

from pydantic import BaseModel


class RefreshResult(BaseModel):
    status: Literal["ok", "busy", "error", "unknown", "cancelled"]
    msg: str
    ts: str | None = None
    updated: list[str] = []
    kept_previous: list[str] = []
    # F12: replaces the old free-text `detail`, which carried the fetch child's
    # merged stdout/stderr tail — i.e. absolute paths and tracebacks — straight
    # into the browser. The full detail is now logged server-side ONLY and this
    # opaque id is the greppable handle an operator uses to find it.
    error_id: str | None = None
