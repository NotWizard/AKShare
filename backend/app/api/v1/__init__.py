"""API v1 router aggregation."""
from fastapi import APIRouter

from backend.app.api.v1 import data, cycles, signals, refresh, real_estate

router = APIRouter(prefix="/api/v1")
router.include_router(data.router)
router.include_router(cycles.router)
router.include_router(signals.router)
router.include_router(refresh.router)
router.include_router(real_estate.router)
