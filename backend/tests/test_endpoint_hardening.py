"""Endpoint hardening — G10 (async SSE + bounded pool) and G24-rest (F11/F12).

Three families of bugs, all reachable by one unauthenticated request:

* F7  — both SSE endpoints returned SYNC generators, which Starlette drives via
  ``iterate_in_threadpool``: every ``next()`` (including the one blocked in
  ``q.get(timeout=1.0)``) holds one of AnyIO's 40 tokens, so each open SSE
  connection effectively occupied a token and a few dozen tabs starved EVERY
  endpoint, ``/health`` included. Each request also started an uncapped
  ``threading.Thread``, and the CRCL worker had no ``stop_event``.
* F11 — ``/crcl/metrics?keys=`` split raw user input and queried per key with no
  whitelist (50k comma items = 50k connections), responses were unbounded, and
  ``/crcl/logs?limit=`` was a bare ``int`` — SQLite treats a NEGATIVE limit as
  unlimited, so ``?limit=-1`` dumped the whole table.
* F12 — error bodies carried ``str(e)`` / the child process's output tail, i.e.
  absolute paths like ``/Users/<name>/…`` and tracebacks.

Hermetic: no network, no data/*.db access (every DB accessor is stubbed), and the
SSE tests stub the collector/refresh drivers.

Run: .venv312/bin/python -m pytest backend/tests/test_endpoint_hardening.py -q
"""

import asyncio
import inspect
import json
import os
import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.api.v1 import crcl as crcl_api  # noqa: E402
from backend.app.api.v1 import refresh as refresh_api  # noqa: E402
from backend.app.core import crcl_collect, crcl_db, locking, refresh  # noqa: E402
from backend.app.core import auth  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.schemas.refresh import RefreshResult  # noqa: E402

client = TestClient(app)

CRCL_STREAM = "/api/v1/crcl/refresh/stream"
REFRESH_STREAM = "/api/v1/refresh/stream"


def _walk(routes):
    """Yield every route, recursing into included/mounted sub-routers.

    This FastAPI version keeps ``include_router`` results behind an
    ``_IncludedRouter`` wrapper instead of flattening them into ``app.routes``.
    """
    for r in routes:
        yield r
        sub = getattr(r, "routes", None)
        if sub is None:
            sub = getattr(getattr(r, "original_router", None), "routes", None)
        if sub:
            yield from _walk(sub)


def _route_for(endpoint):
    """The registered route serving ``endpoint`` (asserts it IS registered)."""
    matches = [r for r in _walk(app.routes) if getattr(r, "endpoint", None) is endpoint]
    assert len(matches) == 1, f"{endpoint.__name__} is not wired exactly once"
    return matches[0]


def _events(body: str) -> list[str]:
    return [e for e in body.split("\n\n") if e]


def _start_job(runner):
    """Register a background job and return its id (F4: the stream no longer
    submits work — it only subscribes to an id a POST/create_job minted)."""
    job = locking.create_job(runner)
    assert job is not None, "the shared pool had no free slot for the test job"
    return job.id


# ═══════════════════════════ F7: async SSE, zero threadpool tokens ══════════
@pytest.mark.parametrize("endpoint", [crcl_api.refresh_stream, refresh_api.stream])
def test_sse_endpoints_are_async(endpoint):
    """A sync endpoint/generator is what burns a threadpool token per connection.
    (Pre-fix both were plain ``def`` → iscoroutinefunction is False.)"""
    route = _route_for(endpoint)
    assert inspect.iscoroutinefunction(route.endpoint), \
        f"{route.path} must be async def"


def test_sse_body_iterator_is_an_async_generator():
    """The streamed body must be an ASYNC generator: Starlette only pushes
    non-async iterators through ``iterate_in_threadpool``."""
    # F4: the stream now subscribes to a job_id instead of submitting work, so we
    # register a trivial job for each and hand its id to the endpoint.
    crcl_id = _start_job(lambda pcb, se: {"status": "ok", "run_id": "x",
                                          "steps": [], "alerts_changed": []})
    refresh_id = _start_job(lambda pcb, se: {"status": "ok", "msg": "", "ts": None,
                                             "updated": [], "kept_previous": []})
    for coro in (crcl_api.refresh_stream(crcl_id), refresh_api.stream(refresh_id)):
        response = asyncio.run(_await(coro))
        it = response.body_iterator
        assert inspect.isasyncgen(it), f"{it!r} is not an async generator"
        assert not inspect.isgenerator(it)


async def _await(coro):
    return await coro


def test_crcl_sse_payload_format_is_unchanged(monkeypatch):
    """The wire format the frontend parses is byte-for-byte what it was:
    ``data: {"progress": <rounded>}`` events then one ``done`` event."""
    def fake_collect_all(progress_cb=None, stop_event=None):
        for frac in (0.25, 0.5, 1.0):
            progress_cb(frac)
        return {"status": "ok", "run_id": "abc12345", "steps": [], "alerts_changed": []}

    monkeypatch.setattr(crcl_collect, "collect_all", fake_collect_all)
    # F4: the POST/create_job mints the job; the GET only subscribes to its id.
    job_id = _start_job(lambda pcb, se: crcl_collect.collect_all(
        progress_cb=pcb, stop_event=se))
    with client.stream("GET", CRCL_STREAM, params={"job_id": job_id}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _events(r.read().decode())

    progress = [e for e in events if '"progress"' in e]
    assert progress == ['data: {"progress": 0.25}',
                        'data: {"progress": 0.5}',
                        'data: {"progress": 1.0}']
    assert all(e.startswith("data: ") or e.startswith(": keepalive") for e in events)
    done = json.loads(events[-1][len("data: "):])
    assert done["done"] is True
    assert done["result"]["run_id"] == "abc12345"


def test_refresh_sse_payload_format_is_unchanged(monkeypatch):
    def fake_run_refresh(progress_cb=None, stop_event=None, full=False):
        progress_cb(0.0)
        progress_cb(0.5)
        return {"status": "ok", "msg": "done", "ts": None,
                "updated": ["cpi"], "kept_previous": []}

    monkeypatch.setattr(refresh, "run_refresh", fake_run_refresh)
    job_id = _start_job(lambda pcb, se: refresh.run_refresh(
        progress_cb=pcb, stop_event=se))
    with client.stream("GET", REFRESH_STREAM, params={"job_id": job_id}) as r:
        events = _events(r.read().decode())

    progress = [e for e in events if '"progress"' in e]
    assert progress == ['data: {"progress": 0.0}', 'data: {"progress": 0.5}']
    done = json.loads(events[-1][len("data: "):])
    assert done == {"done": True, "result": {"status": "ok", "msg": "done", "ts": None,
                                             "updated": ["cpi"], "kept_previous": []}}


def test_crcl_sse_passes_a_stop_event_for_cancellation(monkeypatch):
    """The CRCL worker gets the same cancellation handle the macro refresh has
    (pre-fix a disconnecting client left a full network collection running)."""
    seen: dict = {}

    def fake_collect_all(progress_cb=None, stop_event=None):
        seen["stop_event"] = stop_event
        return {"status": "ok", "run_id": "x", "steps": [], "alerts_changed": []}

    monkeypatch.setattr(crcl_collect, "collect_all", fake_collect_all)
    job_id = _start_job(lambda pcb, se: crcl_collect.collect_all(
        progress_cb=pcb, stop_event=se))
    with client.stream("GET", CRCL_STREAM, params={"job_id": job_id}) as r:
        r.read()
    assert isinstance(seen["stop_event"], threading.Event)


# ═══════════════════════════ F7: bounded executor ═══════════════════════════
def test_submit_job_refuses_instead_of_queueing():
    """The shared pool admits at most MAX_BACKGROUND_JOBS and then says no —
    it must never queue unboundedly (pre-fix: a new thread per request)."""
    hold = threading.Event()
    acquired = []
    try:
        while (fut := locking.submit_job(hold.wait, 10)) is not None:
            acquired.append(fut)
            if len(acquired) > locking.MAX_BACKGROUND_JOBS:
                pytest.fail("pool admitted more jobs than its cap")
        assert acquired, "pool refused every job (no free slot to test with)"
        assert locking.submit_job(lambda: None) is None   # refused, not queued
    finally:
        hold.set()
    for fut in acquired:
        fut.result(timeout=10)
    assert locking.submit_job(lambda: None) is not None    # slots released


@pytest.mark.parametrize("path,module", [("/api/v1/crcl/refresh", crcl_api),
                                         ("/api/v1/refresh", refresh_api)])
def test_saturated_pool_reports_busy_on_the_post(monkeypatch, tmp_path, path, module):
    """A saturated pool reports busy — but on the POST now, not the stream.

    F4 moved admission control with the mutation: the GET no longer submits
    work, so the "pool full" answer belongs to the POST that tries to create the
    job. It returns a busy envelope and mints NO job_id (so there is nothing to
    subscribe to), instead of the pre-fix stream emitting a lone terminal event.
    """
    monkeypatch.setattr(module, "create_job", lambda *a, **k: None)
    monkeypatch.setattr(auth, "TOKEN_PATH", tmp_path / ".api_token")
    monkeypatch.setattr(auth, "_TOKEN", None)
    token = auth.rotate_token()
    r = client.post(path, headers={auth.HEADER_NAME: token})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "busy"
    assert body.get("job_id") is None


# ═══════════════════════════ F11: bounded query params ═════════════════════
@pytest.fixture
def series_spy(monkeypatch):
    """Record every get_series call; never touch the real DB."""
    calls: list[dict] = []

    def _fake(metric, since=None):
        calls.append({"metric": metric, "since": since})
        return [{"date": "2026-01-01", "value": 1.0}]

    monkeypatch.setattr(crcl_db, "get_series", _fake)
    monkeypatch.setattr(crcl_db, "all_metrics", lambda: ["usdc_circ"])
    return calls


def test_unknown_keys_do_not_fan_out(series_spy):
    """5000 bogus keys must produce ZERO queries (pre-fix: 5000 connections)."""
    bogus = ",".join(f"bogus{i}" for i in range(5000))
    r = client.get("/api/v1/crcl/metrics", params={"keys": bogus})
    assert r.status_code == 200
    assert r.json()["metrics"] == {}
    assert series_spy == [], f"unknown keys were queried: {series_spy[:3]}"


def test_known_keys_are_kept_deduped_and_unknown_dropped(series_spy):
    r = client.get("/api/v1/crcl/metrics",
                   params={"keys": "usdc_circ, usdc_circ ,crcl_close,../../etc/passwd"})
    assert r.status_code == 200
    assert list(r.json()["metrics"]) == ["usdc_circ", "crcl_close"]
    assert [c["metric"] for c in series_spy] == ["usdc_circ", "crcl_close"]


def test_metrics_response_shape_is_unchanged(series_spy):
    body = client.get("/api/v1/crcl/metrics", params={"keys": "usdc_circ"}).json()
    entry = body["metrics"]["usdc_circ"]
    assert set(entry) == {"label", "unit", "source", "freq", "points"}
    assert entry["label"] == crcl_collect.METRIC_LABELS["usdc_circ"][0]
    assert entry["points"] == [{"date": "2026-01-01", "value": 1.0}]


def test_since_is_pushed_into_the_query_and_validated(series_spy):
    r = client.get("/api/v1/crcl/metrics",
                   params={"keys": "usdc_circ", "since": "2025-01-01"})
    assert r.status_code == 200
    assert series_spy[-1]["since"] == "2025-01-01"
    assert client.get("/api/v1/crcl/metrics",
                      params={"since": "not-a-date"}).status_code == 422


def test_max_points_bounds_the_payload(monkeypatch):
    big = [{"date": f"2026-{m:02d}-{d:02d}", "value": float(m * 100 + d)}
           for m in range(1, 13) for d in range(1, 29)]      # 336 points
    monkeypatch.setattr(crcl_db, "get_series", lambda m, since=None: list(big))

    pts = client.get("/api/v1/crcl/metrics",
                     params={"keys": "usdc_circ", "max_points": 50}
                     ).json()["metrics"]["usdc_circ"]["points"]
    assert len(pts) <= 50, f"payload not bounded: {len(pts)} points"
    assert pts[0] == big[0]
    assert pts[-1] == big[-1], "the latest point must survive downsampling"
    # dates stay ascending and unique
    dates = [p["date"] for p in pts]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)

    for bad in (0, -1, 10**6):
        assert client.get("/api/v1/crcl/metrics",
                          params={"max_points": bad}).status_code == 422


def test_default_max_points_is_bounded(monkeypatch):
    """The DEFAULT (no max_points given) must also be finite — the page used to
    pull ~7615 points (~350KB) to draw a handful of 280px charts."""
    huge = [{"date": f"{2000 + i // 365}-01-01", "value": float(i)} for i in range(9000)]
    monkeypatch.setattr(crcl_db, "get_series", lambda m, since=None: list(huge))
    pts = client.get("/api/v1/crcl/metrics", params={"keys": "usdc_circ"}
                     ).json()["metrics"]["usdc_circ"]["points"]
    assert len(pts) < len(huge)
    assert len(pts) <= 1501


@pytest.mark.parametrize("limit", [-1, 0, 100000])
def test_logs_limit_is_bounded(monkeypatch, limit):
    """SQLite treats LIMIT -1 as unlimited, so an out-of-range limit must be
    rejected BEFORE it reaches the query (pre-fix ?limit=-1 dumped the table)."""
    monkeypatch.setattr(crcl_db, "get_logs",
                        lambda limit=100: pytest.fail(f"query ran with limit={limit}"))
    r = client.get("/api/v1/crcl/logs", params={"limit": limit})
    assert r.status_code == 422, f"limit={limit} was accepted"


def test_logs_valid_limit_still_works(monkeypatch):
    monkeypatch.setattr(crcl_db, "get_logs", lambda limit=100: [{"limit": limit}])
    body = client.get("/api/v1/crcl/logs", params={"limit": 60}).json()
    assert body == {"logs": [{"limit": 60}]}


# ═══════════════════════════ F12: no internals in error bodies ═════════════
def _assert_no_path_leak(payload: dict):
    blob = json.dumps(payload, ensure_ascii=False)
    for marker in ("/Users/", str(PROJECT_ROOT), "Errno", "Traceback"):
        assert marker not in blob, f"error body leaks {marker!r}: {blob}"


def test_events_read_failure_returns_error_id_only(tmp_path, monkeypatch):
    monkeypatch.setattr(crcl_api, "EVENTS_PATH", tmp_path / "missing.json")
    body = client.get("/api/v1/crcl/events").json()
    assert body["events"] == []
    assert len(body["error_id"]) == 8
    assert body["error_id"] in body["error"]
    _assert_no_path_leak(body)


def test_fundamentals_read_failure_returns_error_id_only(tmp_path, monkeypatch):
    monkeypatch.setattr(crcl_api, "FUNDAMENTALS_PATH", tmp_path / "missing.json")
    body = client.get("/api/v1/crcl/fundamentals").json()
    assert len(body["error_id"]) == 8
    _assert_no_path_leak(body)


def test_refresh_failure_hides_the_child_output(tmp_path, monkeypatch):
    """A nonzero-exit child's output tail (stderr merged in → tracebacks with
    absolute paths) must stay in the LOG; the response gets only an error_id."""
    lock = tmp_path / ".refresh.lock"
    monkeypatch.setattr(refresh, "refresh_lock", lambda: locking.refresh_lock(lock))
    leak = "/Users/secret-operator/Projects/private/fetch.py"
    monkeypatch.setattr(refresh, "_build_cmd", lambda full: [
        sys.executable, "-c",
        f"import sys; print('Traceback: {leak}'); sys.exit(3)"])

    result = refresh.run_refresh()
    assert result["status"] == "error"
    assert result.get("error_id") and len(result["error_id"]) == 8
    assert "detail" not in result
    _assert_no_path_leak(result)
    # and the response MODEL cannot carry a detail field any more either
    model = RefreshResult(**result)
    assert model.error_id == result["error_id"]
    assert not hasattr(model, "detail")


def test_refresh_timeout_hides_the_child_output(tmp_path, monkeypatch):
    lock = tmp_path / ".refresh.lock"
    monkeypatch.setattr(refresh, "REFRESH_TIMEOUT_S", 1)
    monkeypatch.setattr(refresh, "refresh_lock", lambda: locking.refresh_lock(lock))
    monkeypatch.setattr(refresh, "_build_cmd", lambda full: [
        sys.executable, "-c",
        "import time; print('/Users/secret/leak.py', flush=True); time.sleep(30)"])

    result = refresh.run_refresh()
    assert result["status"] == "error"
    assert "超时" in result["msg"]
    assert result.get("error_id")
    _assert_no_path_leak(result)


def test_subprocess_env_is_an_allowlist(monkeypatch):
    """The fetch child never talks to an LLM, so it must not inherit the
    commentary secret (pre-fix ``dict(os.environ)`` gave it everything)."""
    monkeypatch.setenv("COMMENTARY_API_KEY", "sk-must-not-leak")
    monkeypatch.setenv("COMMENTARY_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-must-not-leak")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:3128")

    env = refresh._subprocess_env()

    assert "COMMENTARY_API_KEY" not in env
    assert "COMMENTARY_BASE_URL" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "must-not-leak" not in " ".join(env.values())
    # …while everything the child actually needs survives
    assert env["HTTPS_PROXY"] == "http://proxy.local:3128"
    assert env.get("PATH") == os.environ.get("PATH")
    assert "/opt/homebrew/opt/expat/lib" in env["DYLD_LIBRARY_PATH"]
    assert env["PYTHONIOENCODING"] == "utf-8"
