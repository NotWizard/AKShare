"""AI profiles CRUD API — KEYCHAIN=off fallback, zero key material in responses.

Run:  .venv312/bin/python -m pytest backend/tests -q
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import backend.app.api.v1.ai as ai_router  # noqa: E402
from backend.app.core import ai_config, commentary, keychain  # noqa: E402
from backend.app.core import auth  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)

API = "/api/v1/ai"
KEY = "sk-test-secret-key-123"
P1 = {"name": "p1", "base_url": "https://x.com/v1", "model": "m1"}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("MACRO_AI_KEYCHAIN", "off")
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    for v in ("COMMENTARY_BASE_URL", "COMMENTARY_API_KEY", "COMMENTARY_MODEL"):
        monkeypatch.delenv(v, raising=False)
    keychain._FALLBACK.clear()
    # _save 钩子会 commentary.mark_stale() → 隔离评论库，绝不写真实库
    monkeypatch.setattr(commentary, "DB_PATH", tmp_path / "c.db")
    commentary._table_ready = False
    # 变更端点令牌（F4）：令牌落临时目录，绝不动仓库的 data/.api_token
    monkeypatch.setattr(auth, "TOKEN_PATH", tmp_path / ".api_token")
    client.headers.update({auth.HEADER_NAME: auth.rotate_token()})
    yield
    client.headers.pop(auth.HEADER_NAME, None)
    keychain._FALLBACK.clear()


def _names():
    return [p["name"] for p in client.get(f"{API}/profiles").json()["profiles"]]


def test_crud_shape_and_no_key_leak():
    assert client.post(f"{API}/profiles", json={**P1, "api_key": KEY}).status_code == 200
    assert client.post(f"{API}/profiles", json={
        "name": "p2", "preset": "deepseek", "endpoint": "responses",
        "base_url": "https://api.deepseek.com", "model": "m2"}).status_code == 200

    r = client.get(f"{API}/profiles")
    by = {p["name"]: p for p in r.json()["profiles"]}
    assert set(by) == {"p1", "p2"}
    assert by["p1"]["has_key"] is True and by["p2"]["has_key"] is False
    assert by["p2"]["endpoint"] == "responses" and by["p1"]["source"] == "user"
    assert KEY not in r.text                                # GET 零 key 物料

    assert client.post(f"{API}/profiles", json=P1).status_code == 409          # 重名
    assert client.post(f"{API}/profiles", json={**P1, "name": "bad name"}).status_code == 422
    assert client.post(f"{API}/profiles", json={**P1, "name": "x" * 50}).status_code == 422

    r = client.put(f"{API}/profiles/p2", json={"model": "m3", "temperature": 0.5})
    assert r.status_code == 200 and r.json()["model"] == "m3" and r.json()["temperature"] == 0.5
    assert KEY not in r.text

    by = {p["name"]: p for p in client.get(f"{API}/profiles").json()["profiles"]}
    assert by["p1"]["has_key"] is True                      # PUT 不带 key → 原 key 仍在
    assert by["p2"]["has_key"] is False
    client.put(f"{API}/profiles/p2", json={"api_key": KEY + "n"})               # 覆盖
    by = {p["name"]: p for p in client.get(f"{API}/profiles").json()["profiles"]}
    assert by["p2"]["has_key"] is True
    assert keychain._FALLBACK["p2"] == KEY + "n"


def test_update_explicit_null_is_noop():
    """显式 null 字段 == 未设：不写坏配置，列表端点不 500。"""
    client.post(f"{API}/profiles", json=P1)
    r = client.put(f"{API}/profiles/p1",
                   json={"model": None, "base_url": None, "temperature": None})
    assert r.status_code == 200
    got = r.json()
    assert (got["model"], got["base_url"], got["temperature"]) == ("m1", "https://x.com/v1", 0.3)
    assert client.get(f"{API}/profiles").status_code == 200   # 落盘后列表仍可读


def test_delete():
    client.post(f"{API}/profiles", json={**P1, "api_key": KEY})
    assert client.delete(f"{API}/profiles/p1").status_code == 200
    assert "p1" not in _names()
    assert "p1" not in keychain._FALLBACK                   # keychain 项连带删
    assert client.delete(f"{API}/profiles/nope").status_code == 400

    # 删 active：无 env → null
    client.post(f"{API}/profiles", json=P1)
    client.post(f"{API}/active", json={"name": "p1"})
    client.delete(f"{API}/profiles/p1")
    assert client.get(f"{API}/profiles").json()["active_profile"] is None


def test_active():
    client.post(f"{API}/profiles", json=P1)
    client.post(f"{API}/profiles", json={"name": "p2", "base_url": "https://y.com", "model": "m"})
    r = client.post(f"{API}/active", json={"name": "p2"})
    assert r.status_code == 200 and r.json()["active_profile"] == "p2"
    assert client.post(f"{API}/active", json={"name": "nope"}).status_code == 404


def test_test_endpoint_shape(monkeypatch):
    monkeypatch.setattr(ai_router, "test_connection",
                        lambda p, k: {"ok": True, "latency_ms": 5, "error": None})
    client.post(f"{API}/profiles", json={**P1, "api_key": KEY})
    client.post(f"{API}/profiles", json={"name": "nk", "base_url": "https://y.com", "model": "m"})
    r = client.post(f"{API}/profiles/p1/test")
    assert r.status_code == 200 and r.json() == {"ok": True, "latency_ms": 5, "error": None}
    assert client.post(f"{API}/profiles/nk/test").status_code == 400            # 无 key
    assert client.post(f"{API}/profiles/nope/test").status_code == 404


def test_env_fallback_readonly(monkeypatch):
    for k, v in {"COMMENTARY_BASE_URL": "https://e.com/v1",
                 "COMMENTARY_API_KEY": KEY, "COMMENTARY_MODEL": "em"}.items():
        monkeypatch.setenv(k, v)
    r = client.get(f"{API}/profiles").json()
    assert r["profiles"][-1] == {"name": "env", "source": "env", "preset": "custom",
                                 "endpoint": "chat_completions", "base_url": "https://e.com/v1",
                                 "model": "em", "temperature": 0.3, "has_key": True}
    assert r["active_profile"] == "env"                     # 无 user profile → env
    assert client.put(f"{API}/profiles/env", json={"model": "x"}).status_code == 400
    assert client.delete(f"{API}/profiles/env").status_code == 400

    monkeypatch.delenv("COMMENTARY_API_KEY")
    assert all(p["name"] != "env" for p in client.get(f"{API}/profiles").json()["profiles"])


def test_keychain_failure_500(monkeypatch):
    monkeypatch.setattr(keychain, "set_key", lambda name, key: False)
    r = client.post(f"{API}/profiles", json={**P1, "api_key": KEY})
    assert r.status_code == 500
    by = {p["name"]: p for p in client.get(f"{API}/profiles").json()["profiles"]}
    assert by["p1"]["has_key"] is False                     # profile 已存、key 未存


# ── M4c: 模板读写 ────────────────────────────────────────────────────────────

def _gen_one(monkeypatch):
    """配置 profile + 桩 chat 生成一批（stale=False），供模板保存/stale 断言。"""
    client.post(f"{API}/profiles", json={**P1, "api_key": KEY})
    client.post(f"{API}/active", json={"name": "p1"})
    monkeypatch.setattr(commentary.ai_client, "call_chat", lambda *a, **kw: json.dumps(
        {"sections": {s: f"{s} 评论文本" for s in commentary.SECTIONS},
         "overall": "总体研判文本"}, ensure_ascii=False))
    r = commentary.generate(blocking=True)
    assert r["status"] == "ok" and r["stale"] is False


def test_templates_get_defaults():
    r = client.get(f"{API}/templates")
    assert r.status_code == 200
    body = r.json()
    assert body["overrides"] == {}
    assert set(body["defaults"]) == set(commentary.DEFAULT_TEMPLATES)   # 恰 8 键
    assert body["template_hash"] == commentary.template_hash()
    assert len(body["template_hash"]) == 64


def test_templates_save_marks_stale(monkeypatch):
    _gen_one(monkeypatch)
    old = client.get(f"{API}/templates").json()["template_hash"]
    r = client.put(f"{API}/templates", json={"templates": {"merrill": "改写版"}})
    assert r.status_code == 200
    body = r.json()
    assert body["overrides"] == {"merrill": "改写版"}
    assert body["template_hash"] != old                                  # hash 变
    assert client.get("/api/v1/commentary").json()["stale"] is True      # _save 钩子 mark_stale
    assert json.loads(ai_config.CONFIG_PATH.read_text())["templates"]["merrill"] == "改写版"


def test_templates_reset_removes_override(monkeypatch):
    _gen_one(monkeypatch)
    default_hash = client.get(f"{API}/templates").json()["template_hash"]
    client.put(f"{API}/templates", json={"templates": {"merrill": "改写版"}})
    r = client.put(f"{API}/templates", json={"templates": {"merrill": ""}})
    assert r.status_code == 200 and r.json()["overrides"] == {}
    assert r.json()["template_hash"] == default_hash                     # hash 回到默认
    assert json.loads(ai_config.CONFIG_PATH.read_text())["templates"] == {}


def test_templates_unknown_key_400():
    assert client.put(f"{API}/templates", json={"templates": {"bogus": "x"}}).status_code == 400


def test_templates_noop_save_not_stale(monkeypatch):
    """规范化后与既有覆盖等同（如纯空白输入无覆盖键）→ 跳过写入，不假标 stale。"""
    _gen_one(monkeypatch)
    r = client.put(f"{API}/templates", json={"templates": {"merrill": "   "}})
    assert r.status_code == 200 and r.json()["overrides"] == {}
    assert client.get("/api/v1/commentary").json()["stale"] is False
