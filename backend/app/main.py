"""FastAPI application — thin API over the unchanged analysis core.

Run:  uvicorn backend.app.main:app --reload --port 8000
OpenAPI at:  http://localhost:8000/openapi.json  (consumed by frontend codegen)
"""

import os
import sys
from pathlib import Path

# repo root on sys.path so `import analysis` / `import backend` both resolve
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.api.v1 import router as v1_router
from backend.app.core.db import _load_full

app = FastAPI(
    title="Macro Analysis API",
    version="1.0.0",
    description="中国宏观经济分析 API — 包装不变的 analysis 核心引擎",
)

# GZip compress responses >500 bytes (derived_monthly ~50KB → ~15KB)
app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.on_event("startup")
def prewarm_cache():
    """Pre-load the 4 main tables into lru_cache on startup so the FIRST
    request is as fast as a cached one (~13ms instead of ~65ms)."""
    for table in ("derived_monthly", "derived_quarterly", "leverage", "house_price"):
        try:
            _load_full(table)
        except Exception:
            pass  # table may not exist yet (fresh install) — skip silently


@app.get("/health")
def health():
    return {"status": "ok"}
