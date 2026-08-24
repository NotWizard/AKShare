"""OpenAPI drift gate (G16 · O-H7).

``shared/openapi.json`` is a COMMITTED artefact (frontend codegen + external
consumers read it). It must not drift from the live app. This test fails when
they diverge and tells you to regenerate:

    .venv312/bin/python scripts/gen_openapi.py

Version tolerance: ``info.version`` is bumped at release (1.0.0 → 1.1.0) in a
separate step, and the regen happens alongside it. Comparing the version field
here would make every release spuriously fail this test before the regen lands,
so the version is normalised out on BOTH sides — the gate guards the SHAPE
(paths, operations, schemas), not the version string.

Run:  .venv312/bin/python -m pytest backend/tests/test_openapi_drift.py -q
"""

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED = _ROOT / "shared" / "openapi.json"


def _clean_live_schema() -> dict:
    """The app's OpenAPI as produced by a PRISTINE process.

    Cannot use ``app.openapi()`` in-process: sibling tests (test_json_safety,
    test_static_serving) intentionally ``app.add_api_route`` probe routes onto the
    shared singleton app, so the in-process schema carries extra paths that a
    clean ``gen_openapi.py`` run (and the frontend's codegen) never see. A
    subprocess imports the app fresh — the exact schema the committed file must
    match. stdlib only (no new dependency)."""
    code = "import json;from backend.app.main import app;print(json.dumps(app.openapi()))"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=_ROOT,
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def _normalise(schema: dict) -> dict:
    """JSON round-trip (so tuples→lists etc. match the on-disk form) with the
    release-managed ``info.version`` blanked out."""
    normalised = json.loads(json.dumps(schema, ensure_ascii=False))
    normalised.get("info", {}).pop("version", None)
    return normalised


def test_committed_openapi_matches_live_app():
    committed = json.loads(_COMMITTED.read_text(encoding="utf-8"))
    live = _clean_live_schema()
    assert _normalise(committed) == _normalise(live), (
        "shared/openapi.json is out of sync with the live FastAPI schema — "
        "regenerate it with `.venv312/bin/python scripts/gen_openapi.py`"
    )


def test_committed_openapi_covers_crcl_and_session_routes():
    """Guards against re-committing the pre-G08/pre-CRCL stale schema: the exact
    routes that were missing before must be present."""
    committed = json.loads(_COMMITTED.read_text(encoding="utf-8"))
    paths = committed["paths"]
    assert "/api/v1/session" in paths                       # G08 token handoff
    assert "/api/v1/crcl/overview" in paths                 # CRCL family
    assert "post" in paths["/api/v1/refresh"]               # mutation is a POST (F4)
    assert "get" in paths["/api/v1/refresh/stream"]         # SSE subscribe is a GET


def test_drift_gate_ignores_version_bump():
    """The gate compares SHAPE, not the release-managed version string, so the
    1.0.0 → 1.1.0 bump (a separate release step) does not spuriously fail it."""
    base = {"info": {"title": "x", "version": "1.0.0"}, "paths": {"/a": {"get": {}}}}
    bumped = {"info": {"title": "x", "version": "1.1.0"}, "paths": {"/a": {"get": {}}}}
    assert _normalise(base) == _normalise(bumped)
    # a genuine SHAPE change is still caught
    changed = {"info": {"title": "x", "version": "1.1.0"}, "paths": {"/b": {"get": {}}}}
    assert _normalise(base) != _normalise(changed)


def test_version_is_consistent_across_all_three_manifests():
    """版本号有三处独立来源，必须一字不差。

    v1.1.0 发布时实测踩到：`backend/pyproject.toml` 与 `frontend/package.json`
    都 bump 到 1.1.0 后，`backend/app/main.py` 的 FastAPI 字面量仍是 1.0.0，
    于是重生出来的 `shared/openapi.json` 对外宣告了错误版本（漂移门禁按设计把
    version 归一化，正好照不到这处）。这条断言把三者钉在一起，杜绝再犯。
    """
    import re
    import tomllib

    pyproject = tomllib.loads(
        (_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    backend_version = pyproject["project"]["version"]

    pkg = json.loads((_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    frontend_version = pkg["version"]

    main_src = (_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*version="([^"]+)"', main_src, re.MULTILINE)
    assert m, "backend/app/main.py 里找不到 FastAPI(version=...) 字面量"
    app_version = m.group(1)

    assert backend_version == frontend_version == app_version, (
        f"版本号三处不一致：pyproject={backend_version} / "
        f"package.json={frontend_version} / main.py={app_version}")

    # 已提交的 openapi.json 必须由当前 app 版本重生（发布步骤漏跑 regen 即报）
    committed_version = json.loads(_COMMITTED.read_text(encoding="utf-8"))["info"]["version"]
    assert committed_version == app_version, (
        f"shared/openapi.json 的 version={committed_version} 落后于 app 的 {app_version}"
        "——请重跑 scripts/gen_openapi.py")
