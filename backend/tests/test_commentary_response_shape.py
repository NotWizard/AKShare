"""`/api/v1/commentary/regenerate` 的非成功路径必须回可读状态，而不是 500。

`schemas/commentary.Commentary` 要求 `text: str`，但 `core/commentary` 的三个
早退分支（生成中 / 已有生成在进行 / 生成失败）原先都没带 `text`，于是 FastAPI
的响应校验抛错 → 端点返回 500「服务端内部错误」，把"模型未配置"这类可解释的
失败伪装成服务器崩溃。改前这些用例失败，改后通过。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import commentary  # noqa: E402


def test_generate_failure_carries_schema_required_text(monkeypatch):
    """生成失败 → status=error 且带 text（否则响应校验失败 → 500）。"""
    def boom():
        raise RuntimeError("commentary model not configured: set COMMENTARY_BASE_URL / …")

    monkeypatch.setattr(commentary, "build_snapshot", boom)
    out = commentary._generate_impl()

    assert out["status"] == "error"
    assert "text" in out, "缺 text 会让 FastAPI 响应校验失败，端点回 500"
    assert out["text"] == ""
    assert "not configured" in out["msg"], "失败原因应可读，而非被 500 吞掉"


def test_already_generating_carries_schema_required_text():
    """已有生成在进行中 → status=generating 且带 text。"""
    assert commentary._gen_lock.acquire(blocking=False)
    try:
        out = commentary._generate_impl()
    finally:
        commentary._gen_lock.release()

    assert out["status"] == "generating"
    assert out.get("text") == ""


def test_fire_and_forget_carries_schema_required_text(monkeypatch):
    """非阻塞触发的即时返回同样要满足 schema。"""
    monkeypatch.setattr(commentary.threading, "Thread", lambda *a, **k: type(
        "_T", (), {"start": lambda self: None}
    )())
    out = commentary.generate(blocking=False)

    assert out["status"] == "generating"
    assert out.get("text") == ""
