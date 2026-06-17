"""Cycle + derived-table frames.

Series records are kept as list[dict] (the analysis DataFrames have nullable,
heterogeneous columns), which round-trips cleanly to the frontend chart layer.
"""

from pydantic import BaseModel


class CycleFrame(BaseModel):
    """A classified cycle series + its latest-phase summary."""
    series: list[dict]
    latest_phase: str | None = None
    latest_value: float | None = None
    value_col: str | None = None


class DerivedFrame(BaseModel):
    """A derived table slice (monthly/quarterly)."""
    table: str
    columns: list[str]
    records: list[dict]
