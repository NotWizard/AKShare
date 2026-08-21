"""FastAPI application — thin API over the unchanged analysis core.

Run:  uvicorn backend.app.main:app --reload --port 8000
OpenAPI at:  http://localhost:8000/openapi.json  (consumed by frontend codegen)
"""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# repo root on sys.path so `import analysis` / `import backend` both resolve
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1 import router as v1_router
from backend.app.core.db import _load_full
from backend.app.core import commentary, crcl_collect
from backend.app.core.serial import _json_safe


class SafeJSONResponse(JSONResponse):
    """JSONResponse that nulls non-finite floats (nan / ±inf) before encoding.

    Starlette's default ``render()`` uses ``json.dumps(..., allow_nan=False)``,
    so a single stray ``nan``/``inf`` anywhere in a response body raises
    ``ValueError`` → a hard HTTP 500 (not merely invalid JSON). Endpoints
    without a Pydantic ``response_model`` (all of ``crcl.py`` and
    ``real_estate.py``) had no protection. Registering this as the app-wide
    ``default_response_class`` makes JSON-safety a transport-layer invariant
    for EVERY endpoint at once, instead of relying on per-endpoint discipline.
    """

    def render(self, content: Any) -> bytes:
        return json.dumps(
            _json_safe(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load the 4 main tables into lru_cache on startup so the FIRST
    request is as fast as a cached one (~13ms instead of ~65ms)."""
    for table in ("derived_monthly", "derived_quarterly", "leverage", "house_price"):
        try:
            _load_full(table)
        except Exception:
            pass  # table may not exist yet (fresh install) — skip silently
    commentary.ensure_on_startup()
    crcl_collect.schedule_startup_collection()  # CRCL 监控：启动自动采集（后台线程，不阻塞）
    yield


app = FastAPI(
    title="Macro Analysis API",
    version="1.0.0",
    description="中国宏观经济分析 API — 包装不变的 analysis 核心引擎",
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,  # nan/±inf → null for EVERY endpoint
)

# GZip compress responses >500 bytes (derived_monthly ~50KB → ~15KB)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS origins configurable via CORS_ORIGINS env var (comma-separated).
# Defaults to Vite dev server origins for local development.
_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/health")
def health():
    return {"status": "ok"}
