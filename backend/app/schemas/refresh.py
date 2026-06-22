"""Refresh result schema (mirrors core.refresh.run_refresh output)."""

from typing import Literal

from pydantic import BaseModel


class RefreshResult(BaseModel):
    status: Literal["ok", "busy", "error", "unknown", "cancelled"]
    msg: str
    ts: str | None = None
    updated: list[str] = []
    kept_previous: list[str] = []
    detail: str | None = None
