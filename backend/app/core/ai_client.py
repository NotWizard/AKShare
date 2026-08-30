"""Provider adapter for AI profiles — two endpoint dialects.

- chat_completions: POST {base}/chat/completions → choices[0].message.content
  (OpenAI-compatible: dashscope / deepseek / openrouter / …)
- responses:        POST {base}/responses → output_text, falling back to
  output[].content[].text (both OpenAI Responses return shapes).

Errors are normalized to AiError(stage ∈ request/http/parse). Keys never
reach logs or exception text. `transport=` is for httpx.MockTransport tests.
"""

import time

import httpx

PRESETS = {
    "dashscope":  "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek":   "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "custom":     "",
}


class AiError(Exception):
    """归一化错误：stage ∈ {request(网络/超时), http(非 2xx), parse(响应解析)}。
    msg 永不含 key。"""

    def __init__(self, stage: str, status: int | None, msg: str):
        self.stage, self.status, self.msg = stage, status, msg
        super().__init__(f"{stage}: {msg}")   # 只带 stage+msg，key 无进入路径


def call_chat(profile: dict, key: str, messages: list[dict],
              temperature: float | None = None, *, timeout: float = 60.0,
              transport=None) -> str:
    """POST 一次对话，返回纯文本。profile 为 ai_config 产出的 dict。"""
    base = profile["base_url"].rstrip("/")
    # temperature=None → 不带该字段（部分推理模型如 kimi-k3 拒收 temperature 参数，传了直接 400）
    temp = profile.get("temperature", 0.3) if temperature is None else temperature
    endpoint = profile.get("endpoint", "chat_completions")
    headers = {"Authorization": f"Bearer {key}"}

    if endpoint == "responses":
        url = base + "/responses"
        payload = {"model": profile["model"], "input": messages}
    else:
        url = base + "/chat/completions"
        payload = {"model": profile["model"], "messages": messages}
    if temp is not None:
        payload["temperature"] = temp

    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            r = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:  # TimeoutException ⊂ HTTPError
        raise AiError("request", None, f"网络错误/超时（{type(e).__name__}）") from None

    if r.status_code // 100 != 2:
        # provider 错误正文截断 200 字符——其中只有 provider 自己的报文，无我方 key
        raise AiError("http", r.status_code, r.text[:200])

    try:
        text = _parse(r.json(), endpoint)
    except AiError:
        raise
    except Exception:
        raise AiError("parse", None, "响应解析失败") from None
    if not text:
        raise AiError("parse", None, "空回复")   # 连接测试需要明确的成败信号
    return text


def _parse(data: dict, endpoint: str) -> str:
    if endpoint == "responses":
        text = data.get("output_text")
        if not text:  # 回退：output[].content[].text
            parts = [p.get("text", "") for item in data.get("output", [])
                     for p in (item.get("content") or []) if isinstance(p, dict)]
            text = "".join(parts)
    else:
        text = data["choices"][0]["message"]["content"]
    return (text or "").strip()


PING = [{"role": "user", "content": "Reply with the single word OK"}]


def test_connection(profile: dict, key: str, *, transport=None) -> dict:
    """返回 {ok, latency_ms, error?}；失败 error 形如 "http: 401 …"（不含 key）。"""
    t0 = time.perf_counter()
    try:
        # ping 用 25s：严格小于前端 request() 的 30s abort，慢 provider 由后端给出
        # 可读超时错误，而不是前端先断、后端请求白跑
        call_chat(profile, key, PING, 0.0, timeout=25.0, transport=transport)
        return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000), "error": None}
    except AiError as e:
        return {"ok": False, "latency_ms": round((time.perf_counter() - t0) * 1000),
                "error": f"{e.stage}: {e.msg}" + (f" (HTTP {e.status})" if e.status else "")}
