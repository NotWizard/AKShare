"""G23 的透明度字段必须穿过 `response_model`（遗留 7）。

`compute_signals()` 现在返回 `as_of` / `included` / `excluded` / `stale` /
`composite_raw`——「缺失的子信号被剔除并重新归一，而不是当成中性 0 计入」这一
修复的可观测面就在这几个字段上。但 `schemas/signals.SignalSummary` 没声明它们，
FastAPI 的响应模型会直接过滤掉，于是 HTTP 客户端完全看不到 coverage/as-of。

这里既比对真实库的 `compute_signals()` 返回（只读），也走 TestClient 打
`/api/v1/signals`，确保两侧一致；另外断言新字段是可选的（老 payload 仍可校验）。

Run:  .venv312/bin/python -m pytest backend/tests/test_signals_schema_fields.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from analysis.signals import compute_signals  # noqa: E402
from backend.app.core import db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.schemas.signals import SignalSummary  # noqa: E402

client = TestClient(app)

NEW_FIELDS = ("as_of", "included", "excluded", "stale", "composite_raw")
EXISTING_FIELDS = ("merrill", "credit", "inventory", "debt", "cross_lags",
                   "composite_score", "interpretation")


def test_endpoint_exposes_as_of_and_coverage():
    expected = compute_signals(str(db.DB_PATH))      # 只读真实库
    body = client.get("/api/v1/signals").json()

    for key in NEW_FIELDS:
        assert key in body, f"response_model 过滤掉了 {key}"
        assert body[key] == expected[key], f"{key} 与 compute_signals 不一致"
    assert body["as_of"], "真实库应有一个非空的公共 as-of"


def test_existing_fields_unchanged():
    """纯加字段：原有 7 个字段仍逐一等于 compute_signals 的返回。"""
    expected = compute_signals(str(db.DB_PATH))
    body = client.get("/api/v1/signals").json()
    for key in EXISTING_FIELDS:
        assert body[key] == expected[key], f"{key} 被改动了"


def test_new_fields_are_optional():
    """缺这几个字段的 payload 仍可校验 → 加字段不会把端点变成 500。"""
    m = SignalSummary(merrill={}, credit={}, inventory={}, debt={},
                      cross_lags={}, composite_score=0, interpretation="x")
    assert m.as_of is None
    assert m.included == [] and m.excluded == [] and m.stale == []
    assert m.composite_raw is None
