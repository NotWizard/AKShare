"""Static SPA serving — FastAPI mounts the built Vue bundle without shadowing
the API surface.

The app is deployed as a SINGLE process: FastAPI serves both the JSON API and
the built SPA (``frontend/dist``) via a ``StaticFiles`` mount at ``/``. The mount
is registered LAST, so every explicit route (all ``/api/v1/*``, ``/health``,
``/openapi.json``, ``/docs``, ``/redoc``) must still win; only unmatched paths
fall through to static serving. For an unmatched NON-API path we serve
``index.html`` (SPA client-side routing), but an unmatched ``/api/*`` path must
keep its genuine 404 JSON — never a misleading HTML shell.

These tests are robust to ``frontend/dist`` presence/absence: the API invariants
run unconditionally (proving the app boots + API works even in API-only/dev
mode), while the HTML-specific assertions skip with a clear reason when the
bundle has not been built.

Run:  cd backend && ../.venv312/bin/python -m pytest tests/test_static_serving.py -q
Deterministic, no network.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app, _FRONTEND_DIST  # noqa: E402

client = TestClient(app)

DIST_PRESENT = _FRONTEND_DIST.is_dir()
_INDEX_FILE = _FRONTEND_DIST / "index.html"
INDEX_HTML = _INDEX_FILE.read_text(encoding="utf-8") if _INDEX_FILE.is_file() else None

_needs_dist = pytest.mark.skipif(
    not (DIST_PRESENT and INDEX_HTML is not None),
    reason="frontend/dist not built in this env — SPA mount inactive (API-only mode)",
)


def _is_html(resp) -> bool:
    return "text/html" in resp.headers.get("content-type", "")


def _is_json(resp) -> bool:
    return "application/json" in resp.headers.get("content-type", "")


# --- API invariants: run unconditionally (also proves API-only boot) ----------

def test_health_still_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert _is_json(resp)
    assert resp.json() == {"status": "ok"}


def test_api_route_still_works():
    """A real API route must be served by the API, not shadowed by the SPA mount."""
    resp = client.get("/api/v1/derived/monthly")
    assert resp.status_code == 200, resp.text
    assert _is_json(resp)          # NOT text/html — the mount did not shadow it
    assert not _is_html(resp)
    assert isinstance(resp.json(), (list, dict))


def test_openapi_still_ok():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert _is_json(resp)
    assert "paths" in resp.json()


def test_unknown_api_path_returns_json_404_not_index():
    """CRITICAL: an unknown /api/* path must 404 as JSON, never the HTML shell."""
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404, resp.text
    assert _is_json(resp)
    assert not _is_html(resp)
    assert "<!doctype html" not in resp.text.lower()
    assert resp.json().get("detail")  # FastAPI's default 404 JSON body


# --- SPA serving: only when the bundle has been built -------------------------

@_needs_dist
def test_root_serves_index_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert _is_html(resp)
    assert resp.text == INDEX_HTML


@_needs_dist
def test_spa_deeplink_falls_back_to_index():
    """An unknown NON-API path (SPA client-side route) returns index.html."""
    resp = client.get("/some/deep/spa/route")
    assert resp.status_code == 200
    assert _is_html(resp)
    assert resp.text == INDEX_HTML  # byte-identical to the app shell at "/"


def test_post_import_route_is_not_shadowed():
    """Regression: SPA serving must NOT shadow a route added AFTER import.

    A catch-all mount/route at "/" registered at import time would shadow any
    route attached later (Starlette matches in insertion order) — the exact
    trap that returns the HTML shell for a JSON endpoint. The 404-handler design
    only runs after routing fails, so a post-import route still wins.
    """
    app.add_api_route("/__spa_shadow_probe__", lambda: {"shadowed": False}, methods=["GET"])
    probe = TestClient(app)
    resp = probe.get("/__spa_shadow_probe__")
    assert resp.status_code == 200, resp.text
    assert _is_json(resp)
    assert not _is_html(resp)
    assert resp.json() == {"shadowed": False}


@_needs_dist
def test_real_asset_served_with_js_content_type():
    asset = next(iter((_FRONTEND_DIST / "assets").glob("*.js")), None)
    assert asset is not None, "no hashed .js asset found in dist/assets"
    resp = client.get(f"/assets/{asset.name}")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
    assert not _is_html(resp)


@_needs_dist
def test_missing_asset_returns_json_404_not_index():
    resp = client.get("/assets/__does_not_exist__.js")
    assert resp.status_code == 404
    assert not _is_html(resp)
    assert "<!doctype html" not in resp.text.lower()


@_needs_dist
def test_root_manifest_served_as_itself_not_shell():
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    assert not _is_html(resp)
    assert resp.text != INDEX_HTML
