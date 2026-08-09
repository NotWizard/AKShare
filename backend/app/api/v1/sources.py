"""Sources health endpoint — derived from data/last_run.json on request."""

from fastapi import APIRouter

from backend.app.core import refresh
from backend.app.schemas.sources import SourcesHealth

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/health", response_model=SourcesHealth)
def health():
    """数据源健康（红/黄/绿）— 读 manifest 纯函数推导，无新存储、无缓存。"""
    return SourcesHealth(**refresh.read_sources_health())
