"""Composite macro signals — analysis.signals.compute_signals."""

from fastapi import APIRouter, Query

from analysis.signals import compute_signals
from backend.app.core import db
from backend.app.core.signal_history import read_history
from backend.app.schemas.signals import SignalHistory, SignalSummary

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=SignalSummary)
def signals():
    """Composite [-4,+4] signal + per-framework latest phase."""
    return compute_signals(str(db.DB_PATH))


@router.get("/history", response_model=SignalHistory)
def history(limit: int = Query(60, ge=1, le=500)):
    """信号快照历史（倒序；每次成功刷新一行，附相位翻转标注 flips）。"""
    return {"items": read_history(limit)}
