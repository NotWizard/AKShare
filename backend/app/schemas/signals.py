"""Composite macro-signal schema (mirrors analysis.signals.compute_signals)."""

from pydantic import BaseModel


class PhaseScore(BaseModel):
    date: str | None = None
    phase: str
    score: int


class SignalSummary(BaseModel):
    merrill: dict
    credit: dict
    inventory: dict
    debt: dict
    cross_lags: dict
    composite_score: int            # [-4, +4]
    interpretation: str


class PhaseFlip(BaseModel):
    framework: str            # merrill | credit | inventory | debt
    prev: str | None = None
    curr: str | None = None


class SignalHistoryRow(BaseModel):
    ts: str
    data_as_of: str | None = None
    composite: int
    merrill: str | None = None
    credit: str | None = None
    inventory: str | None = None
    debt: str | None = None
    flips: list[PhaseFlip] = []


class SignalHistory(BaseModel):
    items: list[SignalHistoryRow]
