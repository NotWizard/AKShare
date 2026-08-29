"""`/api/v1/commentary/regenerate` 的非成功路径必须回可读状态，而不是 500。

`schemas/commentary.Commentary` 的全部字段都有默认值（M4 批次形状：
overall/sections/provenance），但前提仍是 `_generate_impl` 的每个早退分支
（生成中 / 未配置 / 生成失败）都返回可校验的 dict——否则 FastAPI 响应校验抛错
→ 端点 500「服务端内部错误」，把"模型未配置"这类可解释的失败伪装成服务器崩溃。

Run:  .venv312/bin/python -m pytest backend/tests/test_commentary_response_shape.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import commentary  # noqa: E402
from backend.app.schemas.commentary import Commentary  # noqa: E402


def _validate(out: dict) -> None:
    """必须能被响应模型校验（否则端点 500）。"""
    Commentary(**out)


def test_generate_failure_carries_valid_shape(monkeypatch):
    """生成失败 → status=error，且形状满足响应模型。"""
    def boom():
        raise RuntimeError("commentary model not configured")

    monkeypatch.setattr(commentary, "build_section_snapshot", boom)
    monkeypatch.setattr(commentary, "_configured", lambda: ({"name": "p", "model": "m"}, "k"))
    out = commentary._generate_impl()

    assert out["status"] == "error"
    _validate(out)
    assert "not configured" in out["msg"], "失败原因应可读，而非被 500 吞掉"


def test_already_generating_carries_valid_shape():
    """已有生成在进行中 → status=generating，且形状满足响应模型。"""
    assert commentary._gen_lock.acquire(blocking=False)
    try:
        out = commentary._generate_impl()
    finally:
        commentary._gen_lock.release()

    assert out["status"] == "generating"
    _validate(out)


def test_fire_and_forget_carries_valid_shape(monkeypatch):
    """非阻塞触发的即时返回同样要满足 schema。"""
    monkeypatch.setattr(commentary.threading, "Thread", lambda *a, **k: type(
        "_T", (), {"start": lambda self: None}
    )())
    out = commentary.generate(blocking=False)

    assert out["status"] == "generating"
    _validate(out)


def test_unconfigured_returns_empty_with_hint(monkeypatch):
    """未配置 profile → status=empty + hint 指向 /ai-settings，形状合法。"""
    monkeypatch.setattr(commentary, "_configured", lambda: (None, None))
    out = commentary._generate_impl()
    assert out["status"] == "empty"
    assert out["hint"] == "/ai-settings"
    _validate(out)
