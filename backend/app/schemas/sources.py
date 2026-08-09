"""Sources health schemas (mirrors core.refresh.sources_health output)."""

from typing import Literal

from pydantic import BaseModel


class SourceHealth(BaseModel):
    table: str
    channel: str
    ok: bool
    elapsed_s: float | None = None
    error: str | None = None
    consecutive_failures: int = 0
    last_success: str | None = None
    warning: str | None = None


class SourcesHealth(BaseModel):
    status: Literal["green", "yellow", "red"]
    updated_at: str | None = None
    sources: list[SourceHealth] = []
