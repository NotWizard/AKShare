"""FastAPI application — thin API over the unchanged analysis core.

Run:  uvicorn backend.app.main:app --reload --port 8000
OpenAPI at:  http://localhost:8000/openapi.json  (consumed by frontend codegen)
"""

import json
import logging
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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1 import router as v1_router
from backend.app.core.db import _load_full
from backend.app.core import auth, commentary, crcl_collect
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
    # F4: mint a fresh local capability token for this process BEFORE any request
    # can arrive. Every mutating endpoint (the 3 POSTs) requires it, which is what
    # stops localhost CSRF — a page the user merely browses can SEND a request to
    # 127.0.0.1:8000 but can neither read data/.api_token nor read a cross-origin
    # response, so it can never present the token. Rotating per start means a
    # restart invalidates a stale tab's copy (the SPA re-reads /api/v1/session).
    # The token itself is never logged or printed.
    auth.rotate_token()
    for table in ("derived_monthly", "derived_quarterly", "leverage", "house_price"):
        try:
            _load_full(table)
        except Exception:
            pass  # table may not exist yet (fresh install) — skip silently
    commentary.ensure_on_startup()
    # CRCL 监控：启动自动采集（后台线程，不阻塞）。与手动刷新共用同一把
    # flock 单飞锁，谁后到谁直接 busy 返回，绝不会并发跑第二遍采集。
    crcl_collect.schedule_startup_collection()
    yield


app = FastAPI(
    title="Macro Analysis API",
    version="1.2.0",   # 与 backend/pyproject.toml、frontend/package.json 三处一致（有测试守）
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


@app.get("/api/v1/session")
def session():
    """Hand this process's capability token to the SAME-ORIGIN SPA (F4).

    The SPA is served by this very app, so for it this is a plain same-origin
    read; ``frontend/src/api/client.ts`` caches the value and sends it as
    ``X-API-Token`` on every POST.

    A localhost-CSRF page can still SEND this GET, but:
      * it cannot READ the response body (cross-origin, and the response is not
        a script/image the browser would hand it), and
      * it cannot read ``data/.api_token`` (mode 0600, no filesystem access),
    so it can never present the token on a mutating POST. ``no-store`` keeps the
    token out of the browser's disk cache.
    """
    return SafeJSONResponse({"token": auth.current_token()},
                            headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Serve the built Vue SPA from FastAPI — single-process deployment.
#
# A catch-all mount/route at "/" registered here would shadow EVERY route added
# after import (Starlette matches in insertion order) — including routes tests
# attach post-import. So instead we serve the SPA without any catch-all in the
# route table:
#   1. Hashed, immutable bundles are served by a plain StaticFiles mount at the
#      "/assets" sub-path (correct content-types + caching, cannot shadow /api).
#   2. index.html + SPA deep-link fallback are served by a 404 exception handler
#      that runs ONLY after normal routing fails, so it never shadows a real or
#      dynamically-added route. It returns index.html for unknown GET/HEAD
#      NON-API paths (client-side routing) while /api/* and missing assets keep
#      their genuine JSON 404 — never a misleading HTML shell.
#
# NOTE: resolve dist from parents[2] (backend/app/main.py → repo root), NOT the
# module-level _PROJECT_ROOT, which is one level too shallow for this file.
# ---------------------------------------------------------------------------
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_INDEX_HTML = _FRONTEND_DIST / "index.html"


def _mount_spa() -> None:
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    dist_root = _FRONTEND_DIST.resolve()

    @app.exception_handler(404)
    async def _spa_fallback(request, exc):
        path = request.url.path
        if request.method in ("GET", "HEAD") and not path.startswith(("/api/", "/assets/")):
            rel = path.lstrip("/")
            if rel:
                # Serve a real root-level file (e.g. /manifest.webmanifest) when
                # present; the resolve()+parents guard blocks path traversal.
                candidate = (_FRONTEND_DIST / rel).resolve()
                if candidate.is_file() and dist_root in candidate.parents:
                    return FileResponse(candidate)
            return FileResponse(_INDEX_HTML)  # SPA shell for client-side routes
        return JSONResponse({"detail": getattr(exc, "detail", "Not Found")}, status_code=404)


if _INDEX_HTML.is_file():
    _mount_spa()
else:
    logging.getLogger(__name__).warning(
        "frontend/dist/index.html not found at %s — serving API only (SPA "
        "disabled). Build it with `npm run build` in frontend/ to serve the UI.",
        _INDEX_HTML,
    )
