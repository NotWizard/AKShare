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
