"""Pydantic schemas — the single source of truth for the API contract.

OpenAPI generated from these (FastAPI) → consumed by the Vue frontend via
openapi-typescript, so frontend TS types never drift.
"""

from backend.app.schemas.refresh import RefreshResult
from backend.app.schemas.signals import SignalSummary, SignalHistory
from backend.app.schemas.cycles import CycleFrame, DerivedFrame
from backend.app.schemas.commentary import Commentary
from backend.app.schemas.ai import ProfileList, TestResult

__all__ = ["RefreshResult", "SignalSummary", "SignalHistory",
           "CycleFrame", "DerivedFrame", "Commentary",
           "ProfileList", "TestResult"]
