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
    # ── G23 coverage / as-of transparency ───────────────────────────────────
    # compute_signals() excludes a sub-signal with no data (instead of counting
    # it as a neutral 0) and half-weights a stale one, then renormalises. These
    # fields are how a client SEES that happen; without them the response model
    # filtered them out and the composite looked unconditional. All optional so
    # a payload predating them still validates.
    as_of: str | None = None        # newest observation across frameworks
    included: list[str] = []        # frameworks in the composite
    excluded: list[str] = []        # frameworks with no usable phase
    stale: list[str] = []           # frameworks kept at half weight
    composite_raw: float | None = None   # composite before rounding


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
