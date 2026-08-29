"""AI client adapter — both dialects via httpx.MockTransport (no network).

Run:  .venv312/bin/python -m pytest backend/tests -q
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx  # noqa: E402
import pytest  # noqa: E402

from backend.app.core.ai_client import AiError, call_chat  # noqa: E402
from backend.app.core.ai_client import test_connection as conn_test  # noqa: E402  # 别名避免 pytest 误收集

KEY = "sk-test-secret-key-123"
CHAT = {"name": "t", "endpoint": "chat_completions", "base_url": "https://x.com/v1",
        "model": "m", "temperature": 0.3}
RESP = dict(CHAT, endpoint="responses")


def _mock(handler):
    return httpx.MockTransport(handler)


def test_chat_completions_happy():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.read())
        assert body["model"] == "m" and body["temperature"] == 0.3
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        return httpx.Response(200, json={"choices": [{"message": {"content": " hi "}}]})

    assert call_chat(CHAT, KEY, [{"role": "user", "content": "hi"}],
                     transport=_mock(handler)) == "hi"   # strip 生效


def test_responses_happy_output_text():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/responses")
        body = json.loads(request.read())
        assert set(body) == {"model", "input", "temperature"}
        return httpx.Response(200, json={"output_text": "ok"})

    assert call_chat(RESP, KEY, [{"role": "user", "content": "hi"}],
                     transport=_mock(handler)) == "ok"


def test_responses_fallback_output_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": [
            {"content": [{"type": "output_text", "text": "a"}, {"text": "b"}]}]})

    assert call_chat(RESP, KEY, [], transport=_mock(handler)) == "ab"


def test_http_401_no_key_in_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid key")

    with pytest.raises(AiError) as ei:
        call_chat(CHAT, KEY, [], transport=_mock(handler))
    assert ei.value.stage == "http" and ei.value.status == 401
    assert KEY not in str(ei.value)


def test_timeout_is_request_stage():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("t")

    with pytest.raises(AiError) as ei:
        call_chat(CHAT, KEY, [], transport=_mock(handler))
    assert ei.value.stage == "request"


def test_bad_json_and_missing_fields_are_parse():
    with pytest.raises(AiError) as ei:
        call_chat(CHAT, KEY, [], transport=_mock(
            lambda r: httpx.Response(200, text="not json")))
    assert ei.value.stage == "parse"

    with pytest.raises(AiError) as ei:
        call_chat(CHAT, KEY, [], transport=_mock(
            lambda r: httpx.Response(200, json={})))
    assert ei.value.stage == "parse"


def test_test_connection_shapes_and_no_key_leak():
    ok = conn_test(CHAT, KEY, transport=_mock(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})))
    assert ok["ok"] is True and ok["latency_ms"] >= 0 and ok["error"] is None
    assert KEY not in json.dumps(ok)

    bad = conn_test(CHAT, KEY, transport=_mock(
        lambda r: httpx.Response(401, text="denied")))
    assert bad["ok"] is False and "http" in bad["error"]
    assert KEY not in json.dumps(bad)


def test_test_connection_timeout_pinned(monkeypatch):
    """回归钉住：ping 用 25s，严格小于前端 request() 的 30s abort（防将来回退）。"""
    seen = {}

    def spy(profile, key, messages, temperature=None, *, timeout=60.0, transport=None):
        seen["timeout"] = timeout
        return "OK"

    monkeypatch.setattr("backend.app.core.ai_client.call_chat", spy)
    conn_test(CHAT, KEY)
    assert seen["timeout"] == 25.0
