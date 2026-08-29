"""Mutating endpoints must be unreachable from a browsed page — G08/F4.

Every state-changing endpoint used to be unauthenticated, and two of them were
GETs. uvicorn binds 127.0.0.1, so the attacker is not on the LAN — this is
**localhost CSRF**: any page the user browses can aim a request at
``http://localhost:8000``. CORS does not stop the request from being SENT (only a
cross-origin READ of the response), and the attacker never needs the body:

    <img src="http://localhost:8000/api/v1/crcl/refresh/stream">
        → pre-fix: a full network collection + DB writes, no preflight, and a
          browser prefetch/prerender or link scanner could fire it by accident;
    fetch('…/api/v1/commentary/regenerate', {method:'POST', mode:'no-cors'})
        → pre-fix: a paid LLM call per invocation, i.e. a billing attack;
    GET /api/v1/refresh/stream
        → pre-fix: spawned the collector subprocess and rewrote the production DB.

The fix has two halves and this file pins both:
  1. the mutation is back on POST — the SSE GET only SUBSCRIBES to a ``job_id``
     that only a POST can mint, so a GET with no/unknown id does nothing;
  2. the 3 POSTs require the local capability token from ``data/.api_token``
     (0600), which the same-origin SPA reads via ``GET /api/v1/session`` and a
     CSRF page can never obtain.

Hermetic: the token lives under tmp_path, and every refresh/collect/LLM driver is
stubbed, so no test spawns the fetch subprocess, touches data/*.db, or hits the
network.

Run: .venv312/bin/python -m pytest backend/tests/test_mutation_auth.py -q
"""

import json
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.api.v1 import crcl as crcl_api  # noqa: E402
from backend.app.api.v1 import refresh as refresh_api  # noqa: E402
from backend.app.core import auth, commentary, crcl_collect, locking, refresh  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)

REFRESH = "/api/v1/refresh"
REFRESH_STREAM = "/api/v1/refresh/stream"
CRCL_REFRESH = "/api/v1/crcl/refresh"
CRCL_STREAM = "/api/v1/crcl/refresh/stream"
REGENERATE = "/api/v1/commentary/regenerate"
# M4 移植新增的 AI 变更端点（F4 同规则：令牌拒绝必须发生在端点体之前，零副作用）
AI_MUTATIONS = [
    ("POST", "/api/v1/ai/profiles"),
    ("PUT", "/api/v1/ai/profiles/p1"),
    ("DELETE", "/api/v1/ai/profiles/p1"),
    ("POST", "/api/v1/ai/profiles/p1/test"),
    ("POST", "/api/v1/ai/active"),
    ("PUT", "/api/v1/ai/templates"),
]


@pytest.fixture
def token(tmp_path, monkeypatch):
    """A real token in a throwaway file — never the repo's data/.api_token."""
    monkeypatch.setattr(auth, "TOKEN_PATH", tmp_path / ".api_token")
    monkeypatch.setattr(auth, "_TOKEN", None)
    return auth.rotate_token()


def auth_header(token: str) -> dict:
    return {auth.HEADER_NAME: token}


@pytest.fixture
def drivers(monkeypatch):
    """Stub every side effect and COUNT it. Nothing here touches the real world.

    ``refresh.run_refresh`` spawns the fetch subprocess and rewrites the DB,
    ``crcl_collect.collect_all`` does the full network collection, and
    ``commentary.generate`` calls the paid LLM — so a non-empty counter is
    literally the side effect the CSRF bug delivered.
    """
    calls: list[str] = []
    started = threading.Event()

    def fake_run_refresh(progress_cb=None, stop_event=None, full=False):
        calls.append("run_refresh")
        if progress_cb:
            progress_cb(0.0)
            progress_cb(0.5)
        started.set()
        return {"status": "ok", "msg": "done", "ts": None,
                "updated": ["cpi"], "kept_previous": []}

    def fake_collect_all(progress_cb=None, stop_event=None):
        calls.append("collect_all")
        if progress_cb:
            for frac in (0.25, 0.5, 1.0):
                progress_cb(frac)
        started.set()
        return {"status": "ok", "run_id": "abc12345", "steps": [], "alerts_changed": []}

    def fake_generate(blocking=False):
        calls.append("llm_generate")
        started.set()
        return {"status": "ok", "overall": "生成的评论", "msg": None}

    monkeypatch.setattr(refresh, "run_refresh", fake_run_refresh)
    monkeypatch.setattr(crcl_collect, "collect_all", fake_collect_all)
    monkeypatch.setattr(commentary, "generate", fake_generate)
    return calls, started


def _events(body: str) -> list[str]:
    return [e for e in body.split("\n\n") if e]


def _walk(routes):
    """Yield every route, recursing into included/mounted sub-routers."""
    for r in routes:
        yield r
        sub = getattr(r, "routes", None)
        if sub is None:
            sub = getattr(getattr(r, "original_router", None), "routes", None)
        if sub:
            yield from _walk(sub)


# ═══════════════ 1. no token → no side effect on any mutating POST ═══════════
@pytest.mark.parametrize("path", [REFRESH, CRCL_REFRESH, REGENERATE])
def test_post_without_a_token_is_refused_and_changes_nothing(drivers, token, path):
    """Pre-fix all three answered 200 and did the work for ANY caller."""
    calls, _ = drivers
    r = client.post(path)
    assert r.status_code in (401, 403), f"{path} accepted an unauthenticated POST"
    assert "detail" in r.json(), "a refusal must carry a readable message"
    assert calls == [], f"{path} still ran {calls} without a token"


@pytest.mark.parametrize("path", [REFRESH, CRCL_REFRESH, REGENERATE])
def test_post_with_a_wrong_token_is_403_and_changes_nothing(drivers, token, path):
    calls, _ = drivers
    r = client.post(path, headers=auth_header("not-the-token"))
    assert r.status_code == 403
    assert calls == [], f"{path} ran with a forged token: {calls}"


def test_refusals_are_401_403_never_500(drivers, token):
    """A missing capability is a client error with a message, not a crash."""
    assert client.post(REFRESH).status_code == 401                       # absent
    assert client.post(REFRESH, headers=auth_header("x")).status_code == 403  # wrong
    body = client.post(REFRESH).json()
    assert auth.HEADER_NAME in body["detail"], "the message must name the header"


@pytest.mark.parametrize("method,path", AI_MUTATIONS)
def test_ai_mutations_refused_without_token(method, path, token):
    """M4 新增的 AI 变更端点：无令牌/错令牌一律 401/403，鉴权依赖先于端点体执行。"""
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers=auth_header("wrong")).status_code == 403


def test_every_mutating_route_is_token_guarded():
    """全路由清扫：任何 POST/PUT/DELETE/PATCH 端点都必须挂 require_token——
    防未来新增变更端点忘了守门（本仓已因此类遗漏被 CSRF 过一次）。

    检测两处：route.dependencies 的原始 Depends 列表（.dependency）与
    dependant 的子依赖（新版 FastAPI 里属性名是 .call，不再是 .dependency）。
    """
    def _guarded(r) -> bool:
        raw = getattr(r, "dependencies", None) or []
        if any(getattr(d, "dependency", None) is auth.require_token for d in raw):
            return True
        dependant = getattr(r, "dependant", None)
        deps = getattr(dependant, "dependencies", []) if dependant else []
        return any(
            (getattr(d, "dependency", None) or getattr(d, "call", None)) is auth.require_token
            for d in deps
        )

    unguarded = []
    for r in _walk(app.routes):
        methods = getattr(r, "methods", None) or set()
        if not methods & {"POST", "PUT", "DELETE", "PATCH"}:
            continue
        if not _guarded(r):
            unguarded.append(f"{sorted(methods)} {getattr(r, 'path', '?')}")
    assert unguarded == [], f"未守门的变更端点: {unguarded}"


# ═══════════════ 2. with the token the flow proceeds as before ══════════════
def test_post_refresh_with_token_starts_the_job(drivers, token):
    calls, started = drivers
    r = client.post(REFRESH, headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["job_id"], "POST must mint the job_id the stream subscribes to"
    assert started.wait(5), "the authorised refresh never ran"
    assert calls == ["run_refresh"]


def test_post_crcl_refresh_with_token_starts_the_job(drivers, token):
    calls, started = drivers
    body = client.post(CRCL_REFRESH, headers=auth_header(token)).json()
    assert body["status"] == "running" and body["job_id"]
    assert started.wait(5), "the authorised collection never ran"
    assert calls == ["collect_all"]


def test_post_regenerate_with_token_still_returns_the_commentary(drivers, token):
    calls, _ = drivers
    body = client.post(REGENERATE, headers=auth_header(token)).json()
    assert body["overall"] == "生成的评论"
    assert calls == ["llm_generate"]


# ═══════════════ 3. the <img src=…> case: a GET starts NOTHING ══════════════
@pytest.mark.parametrize("path", [REFRESH_STREAM, CRCL_STREAM])
def test_stream_get_without_job_id_starts_no_work(drivers, path):
    """THE CSRF-via-<img> case. Pre-fix this GET ran the whole pipeline."""
    calls, _ = drivers
    r = client.get(path)
    assert r.status_code == 422, f"{path} must reject a job_id-less GET"
    assert calls == [], f"a bare GET {path} still started {calls}"


@pytest.mark.parametrize("path", [REFRESH_STREAM, CRCL_STREAM])
def test_stream_get_with_unknown_job_id_starts_no_work(drivers, path):
    """A guessed/expired id is a 404 — never an implicit "start one for me"."""
    calls, _ = drivers
    r = client.get(path, params={"job_id": "deadbeef" * 4})
    assert r.status_code == 404
    assert "job_id" in r.json()["detail"]
    assert calls == [], f"an unknown job_id started {calls}"


def test_stream_get_is_not_a_mutating_route(drivers):
    """Belt and braces: hammer the bare stream GETs the way a prefetching
    browser would and prove the collector count stays at zero."""
    calls, _ = drivers
    for _ in range(5):
        client.get(REFRESH_STREAM)
        client.get(CRCL_STREAM)
        client.get(CRCL_STREAM, params={"job_id": "nope"})
    assert calls == []


# ═══════════════ 4. the SSE wire format is unchanged ════════════════════════
def test_refresh_sse_payload_format_is_unchanged_via_the_job(drivers, token):
    """Same bytes as the pre-split stream: `data: {"progress": …}` events then
    one terminal `done` event carrying the driver's result."""
    _, started = drivers
    job_id = client.post(REFRESH, headers=auth_header(token)).json()["job_id"]
    assert started.wait(5)
    with client.stream("GET", REFRESH_STREAM, params={"job_id": job_id}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _events(r.read().decode())

    progress = [e for e in events if '"progress"' in e]
    assert progress == ['data: {"progress": 0.0}', 'data: {"progress": 0.5}']
    assert all(e.startswith("data: ") or e.startswith(": keepalive") for e in events)
    done = json.loads(events[-1][len("data: "):])
    assert done == {"done": True, "result": {"status": "ok", "msg": "done", "ts": None,
                                             "updated": ["cpi"], "kept_previous": []}}


def test_crcl_sse_payload_format_is_unchanged_via_the_job(drivers, token):
    _, started = drivers
    job_id = client.post(CRCL_REFRESH, headers=auth_header(token)).json()["job_id"]
    assert started.wait(5)
    with client.stream("GET", CRCL_STREAM, params={"job_id": job_id}) as r:
        events = _events(r.read().decode())

    progress = [e for e in events if '"progress"' in e]
    assert progress == ['data: {"progress": 0.25}',
                        'data: {"progress": 0.5}',
                        'data: {"progress": 1.0}']
    done = json.loads(events[-1][len("data: "):])
    assert done["done"] is True
    assert done["result"]["run_id"] == "abc12345"


def test_a_late_subscriber_still_sees_every_progress_tick(drivers, token):
    """The POST starts the work, so the GET usually attaches AFTER the first
    ticks. The job replays its buffer, which is what keeps the format identical
    (a fire-and-forget queue would have silently dropped them)."""
    _, started = drivers
    job_id = client.post(CRCL_REFRESH, headers=auth_header(token)).json()["job_id"]
    assert started.wait(5), "collection did not run"
    # subscribe only once the job has finished — the extreme "late" case
    job = locking.get_job(job_id)
    for _ in range(200):
        if job.done:
            break
        time.sleep(0.025)
    assert job.done, "job never finished"
    with client.stream("GET", CRCL_STREAM, params={"job_id": job_id}) as r:
        events = _events(r.read().decode())
    assert [e for e in events if '"progress"' in e] == [
        'data: {"progress": 0.25}', 'data: {"progress": 0.5}', 'data: {"progress": 1.0}']


# ═══════════════ 5. saturated pool: busy on the POST, no queueing ═══════════
@pytest.mark.parametrize("path,module", [(REFRESH, refresh_api),
                                         (CRCL_REFRESH, crcl_api)])
def test_saturated_pool_reports_busy_on_the_post(drivers, token, monkeypatch,
                                                 path, module):
    """Admission control moved with the mutation: the POST says busy (and mints
    no job_id) instead of the stream emitting a lone terminal event."""
    calls, _ = drivers
    monkeypatch.setattr(module, "create_job", lambda *a, **k: None)
    body = client.post(path, headers=auth_header(token)).json()
    assert body["status"] == "busy"
    assert body.get("job_id") is None
    assert calls == []


# ═══════════════ 6. the token itself ═══════════════════════════════════════
def test_token_file_is_0600_and_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_PATH", tmp_path / ".api_token")
    monkeypatch.setattr(auth, "_TOKEN", None)

    first = auth.rotate_token()
    mode = stat.S_IMODE(os.stat(auth.TOKEN_PATH).st_mode)
    assert mode == 0o600, f"token file is {oct(mode)}, must be 0600"
    assert auth.TOKEN_PATH.read_text(encoding="utf-8").strip() == first
    assert len(first) >= 32

    monkeypatch.setattr(auth, "_TOKEN", None)
    second = auth.rotate_token()
    assert second != first, "a restart must invalidate the previous token"
    assert auth.current_token() == second


def test_token_file_is_gitignored():
    """The generated secret must never be committable."""
    import subprocess
    r = subprocess.run(["git", "check-ignore", "-q", "data/.api_token"],
                       cwd=PROJECT_ROOT)
    assert r.returncode == 0, "data/.api_token is not covered by .gitignore"


def test_session_endpoint_hands_the_token_to_a_same_origin_reader(drivers, token):
    """How the SPA gets the capability. A cross-origin page may SEND this GET but
    cannot read the body — and cannot read the 0600 file — so it stays locked out.
    """
    r = client.get("/api/v1/session")
    assert r.status_code == 200
    assert r.json() == {"token": token}
    assert r.headers.get("cache-control") == "no-store"
    # and that token is exactly what the guarded POST accepts
    assert client.post(REGENERATE,
                       headers=auth_header(r.json()["token"])).status_code == 200


def test_every_mutating_route_requires_the_token():
    """Structural guard: a future POST/PUT/PATCH/DELETE added without the
    dependency fails HERE instead of shipping another unauthenticated mutation.
    """
    unguarded = []
    for route in _walk(app.routes):
        methods = getattr(route, "methods", None) or set()
        if not methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        dependant = getattr(route, "dependant", None)
        deps = getattr(dependant, "dependencies", []) if dependant else []
        if not any(d.call is auth.require_token for d in deps):
            unguarded.append(f"{sorted(methods)} {route.path}")
    assert unguarded == [], f"mutating routes without require_token: {unguarded}"
