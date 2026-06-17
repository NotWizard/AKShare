"""Composite macro signals — analysis.signals.compute_signals."""

from fastapi import APIRouter

from analysis.signals import compute_signals
from backend.app.core import db
from backend.app.schemas.signals import SignalSummary

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=SignalSummary)
def signals():
    """Composite [-4,+4] signal + per-framework latest phase."""
    return compute_signals(str(db.DB_PATH))
