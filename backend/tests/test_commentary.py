"""AI commentary generation layer — snapshot v2 / 模板 / 结构化生成 / 持久化 / stale.

Run:  .venv312/bin/python -m pytest backend/tests -q
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core import ai_config, commentary, keychain  # noqa: E402
from backend.app.core import auth  # noqa: E402
from backend.app.main import app  # noqa: E402

client = TestClient(app)

SECTIONS = commentary.SECTIONS
ALL_KEYS = (*SECTIONS, "overall")
REAL_DB = Path(__file__).resolve().parents[2] / "data" / "macro_data.db"

_LEGACY_DDL = """CREATE TABLE commentary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    data_as_of TEXT NOT NULL,
    composite_score INTEGER,
    phase_snapshot TEXT NOT NULL,
    text TEXT NOT NULL,
    model TEXT,
    stale INTEGER DEFAULT 0)"""


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("MACRO_AI_KEYCHAIN", "off")
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    for v in ("COMMENTARY_BASE_URL", "COMMENTARY_API_KEY", "COMMENTARY_MODEL"):
        monkeypatch.delenv(v, raising=False)
    keychain._FALLBACK.clear()
    monkeypatch.setattr(commentary, "DB_PATH", tmp_path / "c.db")   # 绝不写真实库
    commentary._table_ready = False
    # 变更端点令牌（F4）：令牌落临时目录，绝不动仓库的 data/.api_token
    monkeypatch.setattr(auth, "TOKEN_PATH", tmp_path / ".api_token")
    client.headers.update({auth.HEADER_NAME: auth.rotate_token()})
    yield
    client.headers.pop(auth.HEADER_NAME, None)
    keychain._FALLBACK.clear()


def _profile(name="p1"):
    ai_config.create({"name": name, "base_url": "https://x.com/v1", "model": "m1"})
    keychain.set_key(name, "sk-test-secret-key-123")
    ai_config.set_active(name)


def _ok_json() -> str:
    return json.dumps({"sections": {k: f"{k} 评论文本" for k in SECTIONS},
                       "overall": "总体研判文本"}, ensure_ascii=False)


def _stub_chat(monkeypatch, fn):
    monkeypatch.setattr(commentary.ai_client, "call_chat", fn)


def _rows():
    conn = sqlite3.connect(commentary.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM commentary").fetchall()
    conn.close()
    return rows


# ── 1. 宽容解析 ───────────────────────────────────────────────────────────────

def test_extract_json():
    ej = commentary._extract_json
    assert ej('{"a": 1}') == {"a": 1}                                   # 纯 JSON
    assert ej('前置散文 {"sections": {}} 后置散文') == {"sections": {}}  # 散文包裹
    assert ej('```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}       # markdown 围栏
    assert ej('{"outer": {"inner": 1}}') == {"outer": {"inner": 1}}     # 嵌套取首个平衡块
    assert ej('先 {bad} 然后 {"ok": 1}') == {"ok": 1}                   # 首块非法 → 下一块
    assert ej('没有 JSON') is None
    assert ej('[1, 2, 3]') is None                                      # 只有数组
    assert ej('{"unclosed": 1') is None                                 # 未闭合


# ── 2. 校验 ──────────────────────────────────────────────────────────────────

def test_validate_structured():
    good = {"sections": {k: f"{k} 文本" for k in SECTIONS}, "overall": "总体"}
    parts, problems = commentary._validate_structured(json.dumps(good, ensure_ascii=False))
    assert not problems and set(parts) == set(ALL_KEYS)

    parts, problems = commentary._validate_structured("纯散文输出")
    assert problems and not parts

    bad = {"sections": {k: "" for k in SECTIONS}, "overall": "字" * 601}
    parts, problems = commentary._validate_structured(json.dumps(bad, ensure_ascii=False))
    assert len(problems) == 7 and not parts                            # 6 空串 + 超长 overall

    miss = {"sections": {k: "ok" for k in SECTIONS[:-1]}, "overall": "ov"}
    parts, problems = commentary._validate_structured(json.dumps(miss, ensure_ascii=False))
    assert any("fiscal_external" in p for p in problems)
    assert "fiscal_external" not in parts and parts["merrill"] == "ok"

    parts, problems = commentary._validate_structured(
        json.dumps({"sections": "不是对象", "overall": "ov"}, ensure_ascii=False))
    assert problems and "overall" in parts


# ── 3. happy path ────────────────────────────────────────────────────────────

def test_generate_happy_path(monkeypatch):
    _profile()
    calls = []
    _stub_chat(monkeypatch, lambda p, k, m, *a, **kw: calls.append(m) or _ok_json())

    r = commentary.generate(blocking=True)
    assert r["status"] == "ok" and len(calls) == 1
    assert set(r["sections"]) == set(SECTIONS) and r["overall"] == "总体研判文本"
    assert r["stale"] is False
    prov = r["provenance"]
    assert set(prov) == {"model", "endpoint", "template_hash", "data_as_of",
                         "profile", "generated_at"}
    assert len(prov["template_hash"]) == 64
    assert prov["template_hash"] == commentary.template_hash()
    assert isinstance(prov["data_as_of"], dict)
    assert prov["model"] == "m1" and prov["profile"] == "p1"
    assert prov["endpoint"] == "chat_completions"

    rows = _rows()
    assert len(rows) == 7                                              # 6 板块 + overall
    assert len({row["ts"] for row in rows}) == 1                       # 同 ts = 批次键
    assert prov["generated_at"] == rows[0]["ts"]
    assert {row["section"] for row in rows} == set(ALL_KEYS)
    assert all(row["stale"] == 0 for row in rows)
    snap = json.loads(rows[0]["phase_snapshot"])                       # 模型原始输入
    assert set(snap) == {"data_as_of", "sections"}


# ── 4. 重试一次 ──────────────────────────────────────────────────────────────

def test_retry_once_with_error_feedback(monkeypatch):
    _profile()
    seen = []
    outs = iter(["这是散文不是 JSON", _ok_json()])

    def stub(p, k, m, *a, **kw):
        seen.append(m)
        return next(outs)

    _stub_chat(monkeypatch, stub)
    r = commentary.generate(blocking=True)
    assert r["status"] == "ok" and len(seen) == 2
    assert seen[1][-2] == {"role": "assistant", "content": "这是散文不是 JSON"}
    assert seen[1][-1]["role"] == "user" and "不合格" in seen[1][-1]["content"]


# ── 5. 降级逐板块 ────────────────────────────────────────────────────────────

def test_fallback_per_section(monkeypatch):
    _profile()
    n = []

    def stub(p, k, m, *a, **kw):
        n.append(1)
        return "乱码" if len(n) <= 2 else "补调文本"   # 结构化两次全乱 → 7 次补调

    _stub_chat(monkeypatch, stub)
    r = commentary.generate(blocking=True)
    assert r["status"] == "ok"
    assert len(n) == 2 + 7                                             # 最坏 9 次调用
    assert set(r["sections"]) == set(SECTIONS) and r["overall"] == "补调文本"
    assert all(v == "补调文本" for v in r["sections"].values())


# ── 5b. 补调 JSON 包裹解包 + 网络失败短路 ────────────────────────────────────

def test_unwrap_section():
    u = commentary._unwrap_section
    assert u("纯文本不是 JSON", "merrill") == "纯文本不是 JSON"        # 正常路径原样
    assert u('{"merrill": "包装文本"}', "merrill") == "包装文本"       # 顶层键
    assert u('{"sections": {"merrill": "嵌套文本"}, "overall": "o"}',
             "merrill") == "嵌套文本"                                  # 结构化形状
    assert u('{"content": "唯一值"}', "merrill") == "唯一值"           # 单键包装
    assert u('{"a": "x", "b": "y"}', "merrill") == ""                  # 歧义 → 判不合格


def test_fallback_unwraps_json_wrapped_text(monkeypatch):
    """强对齐模型在补调中服从 system 的 JSON 规则 → 解包取值，原始 JSON 不得落库。"""
    _profile()
    wrapped = json.dumps({"sections": {k: f"{k} 纯文本" for k in SECTIONS},
                          "overall": "总体纯文本"}, ensure_ascii=False)
    n = []

    def stub(p, k, m, *a, **kw):
        n.append(1)
        return "乱码" if len(n) <= 2 else wrapped

    _stub_chat(monkeypatch, stub)
    r = commentary.generate(blocking=True)
    assert r["status"] == "ok" and len(n) == 2 + 7
    assert r["sections"]["merrill"] == "merrill 纯文本"                # 解包后的值
    assert r["overall"] == "总体纯文本"
    assert not any(row["text"].lstrip().startswith("{") for row in _rows())


def test_transport_failure_skips_fallback(monkeypatch):
    """结构化调用即 AiError（死网络）→ 不再补调 7 次，直接 error 保留 last-good。"""
    _profile()
    n = []

    def stub(p, k, m, *a, **kw):
        n.append(1)
        raise commentary.ai_client.AiError("request", None, "net down")

    _stub_chat(monkeypatch, stub)
    r = commentary.generate(blocking=True)
    assert r["status"] == "error" and len(n) == 1                      # 仅结构化那一次调用


# ── 6. 全败保留 last-good ────────────────────────────────────────────────────

def test_total_failure_keeps_last_good(monkeypatch):
    _profile()
    _stub_chat(monkeypatch, lambda *a, **kw: _ok_json())
    r1 = commentary.generate(blocking=True)
    assert r1["status"] == "ok"

    _stub_chat(monkeypatch, lambda *a, **kw: "乱" * 601)               # 超 600 字 → 补调也不合格
    r2 = commentary.generate(blocking=True)
    assert r2["status"] == "error" and "上一版" in r2["msg"]

    cur = commentary.get_current()                                     # GET 仍回旧批次
    assert cur["status"] == "ok" and cur["overall"] == r1["overall"]
    assert len(_rows()) == 7                                           # 行数不增


# ── 7. 无 profile / 无 key ───────────────────────────────────────────────────

def test_empty_without_profile_or_key():
    r = commentary.generate(blocking=True)                             # 无 profile
    assert r["status"] == "empty" and r["hint"] == "/ai-settings"
    cur = commentary.get_current()
    assert cur["status"] == "empty" and cur["hint"] == "/ai-settings"

    ai_config.create({"name": "p1", "base_url": "https://x.com/v1", "model": "m1"})
    ai_config.set_active("p1")                                         # 有 profile 无 key
    r = commentary.generate(blocking=True)
    assert r["status"] == "empty" and r["hint"] == "/ai-settings"
    assert commentary.get_current()["hint"] == "/ai-settings"


# ── 8. 迁移幂等 + legacy 读回 ────────────────────────────────────────────────

def test_migration_idempotent_and_legacy_read():
    conn = sqlite3.connect(commentary.DB_PATH)
    conn.execute(_LEGACY_DDL)                                          # 老 8 列
    conn.execute("INSERT INTO commentary (ts, data_as_of, phase_snapshot, text, model) "
                 "VALUES ('2026-01-01T00:00:00', '2025-12', '{}', '旧评论', 'old-model')")
    conn.commit()
    conn.close()

    commentary._table_ready = False
    conn = commentary._connect()
    commentary._ensure_table(conn)
    commentary._ensure_table(conn)                                     # 第二遍幂等
    cols = {r[1] for r in conn.execute("PRAGMA table_info(commentary)")}
    assert set(commentary._NEW_COLS) <= cols
    assert conn.execute("SELECT COUNT(*) FROM commentary").fetchone()[0] == 1

    batch = commentary._latest_batch(conn)
    conn.close()
    assert batch["status"] == "ok"
    assert batch["sections"] == {} and batch["overall"] == "旧评论"    # 老行读作 overall
    assert batch["provenance"]["data_as_of"] == {"derived_monthly": "2025-12"}
    assert batch["provenance"]["model"] == "old-model"


# ── 9/10. stale 重接线 ───────────────────────────────────────────────────────

def test_mark_stale_on_refresh(monkeypatch):
    _profile()
    _stub_chat(monkeypatch, lambda *a, **kw: _ok_json())
    commentary.generate(blocking=True)
    assert commentary.get_current()["stale"] is False

    monkeypatch.setattr(commentary, "generate",
                        lambda blocking=True: {"status": "generating"})
    commentary.mark_stale_and_regenerate()
    assert commentary.get_current()["stale"] is True


@pytest.mark.parametrize("op", ["create", "update", "delete", "set_active"])
def test_config_mutation_marks_stale(op, monkeypatch):
    _profile()
    if op == "set_active":
        ai_config.create({"name": "p2", "base_url": "https://y.com", "model": "m2"})
    _stub_chat(monkeypatch, lambda *a, **kw: _ok_json())
    commentary.generate(blocking=True)
    assert commentary.get_current()["stale"] is False

    {"create": lambda: ai_config.create(
        {"name": "p3", "base_url": "https://z.com", "model": "m3"}),
     "update": lambda: ai_config.update("p1", {"model": "m9"}),
     "delete": lambda: ai_config.delete("p1"),
     "set_active": lambda: ai_config.set_active("p2")}[op]()
    assert commentary.get_current()["stale"] is True


# ── 11. 端点 shape ───────────────────────────────────────────────────────────

def test_endpoint_shapes(monkeypatch):
    r = client.get("/api/v1/commentary")                               # empty
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "msg", "hint", "stale", "regenerating",
                         "overall", "sections", "provenance"}
    assert body["status"] == "empty" and body["hint"] == "/ai-settings"

    # generating 由 _gen_lock 派生（F10：不再存在可卡死的独立 _busy 旗标）
    assert commentary._gen_lock.acquire(blocking=False)
    try:
        assert client.get("/api/v1/commentary").json()["status"] == "generating"
    finally:
        commentary._gen_lock.release()

    _profile()                                                         # ok
    _stub_chat(monkeypatch, lambda *a, **kw: _ok_json())
    r = client.post("/api/v1/commentary/regenerate")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert set(r.json()["sections"]) == set(SECTIONS)

    body = client.get("/api/v1/commentary").json()
    assert body["status"] == "ok" and body["provenance"]["model"] == "m1"


def test_single_flight():
    _profile()
    with commentary._gen_lock:                                         # 模拟在飞生成
        assert commentary.generate(blocking=True)["status"] == "generating"


# ── M4c: 轮转 ────────────────────────────────────────────────────────────────

def test_prune_keeps_latest_batches(monkeypatch):
    """12 批 → 恰留最近 10 批（70 行），最旧 2 批整批删除；当前批次语义不变。"""
    _profile()
    _stub_chat(monkeypatch, lambda *a, **kw: _ok_json())
    seq = iter(f"2026-01-01T00:{i:02d}:00.000" for i in range(12))   # 确定性递增 ts，避开毫秒并批
    monkeypatch.setattr(commentary, "_ts", lambda: next(seq))

    for _ in range(12):
        assert commentary.generate(blocking=True)["status"] == "ok"

    conn = sqlite3.connect(commentary.DB_PATH)
    ts_all = [r[0] for r in conn.execute("SELECT DISTINCT ts FROM commentary ORDER BY ts")]
    n = conn.execute("SELECT COUNT(*) FROM commentary").fetchone()[0]
    conn.close()
    assert len(ts_all) == commentary.KEEP_BATCHES == 10
    assert n == 10 * 7
    assert ts_all[0] == "2026-01-01T00:02:00.000"                # 最早 2 批的所有行被删
    assert ts_all[-1] == "2026-01-01T00:11:00.000"
    assert commentary.get_current()["provenance"]["generated_at"] == ts_all[-1]


# ── M4c: history 索引 / 单批详情 ─────────────────────────────────────────────

def _three_batches(monkeypatch):
    """3 批确定性 ts；第 2 批 overall 超 80 字以验预览省略号。"""
    _profile()
    n = []

    def stub(p, k, m, *a, **kw):
        n.append(1)
        ov = "综" * 100 if len(n) == 2 else "总体研判文本"
        return json.dumps({"sections": {s: f"{s} 评论文本" for s in SECTIONS},
                           "overall": ov}, ensure_ascii=False)

    _stub_chat(monkeypatch, stub)
    seq = iter(f"2026-02-01T00:0{i}:00.000" for i in range(3))
    monkeypatch.setattr(commentary, "_ts", lambda: next(seq))
    for _ in range(3):
        assert commentary.generate(blocking=True)["status"] == "ok"


def test_history_index_descending_and_shape(monkeypatch):
    _three_batches(monkeypatch)
    r = client.get("/api/v1/commentary/history")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3
    ts_list = [it["generated_at"] for it in items]
    assert ts_list == sorted(ts_list, reverse=True)              # ts 严格倒序
    for it in items:
        assert set(it) == {"generated_at", "model", "profile", "template_hash",
                           "status", "stale", "overall_preview"}
        assert it["status"] == "ok" and it["stale"] is False
        assert it["model"] == "m1" and it["profile"] == "p1"
        assert len(it["template_hash"]) == 64
    assert items[0]["overall_preview"] == "总体研判文本"          # ≤80 字原样
    assert len(items[1]["overall_preview"]) == 81 and items[1]["overall_preview"].endswith("…")


def test_same_second_batches_do_not_merge(monkeypatch):
    """同秒两批（仅毫秒不同）→ 独立批次键，不并批、读回不互蚀（_ts 毫秒精度）。"""
    _profile()
    tags = []

    def stub(p, k, m, *a, **kw):
        tags.append(f"批{len(tags) + 1}")
        return json.dumps({"sections": {s: f"{tags[-1]} {s}" for s in SECTIONS},
                           "overall": f"{tags[-1]} 总体"}, ensure_ascii=False)

    _stub_chat(monkeypatch, stub)
    seq = iter(["2026-03-01T12:00:00.001", "2026-03-01T12:00:00.002"])
    monkeypatch.setattr(commentary, "_ts", lambda: next(seq))

    assert commentary.generate(blocking=True)["status"] == "ok"
    assert commentary.generate(blocking=True)["status"] == "ok"

    conn = sqlite3.connect(commentary.DB_PATH)
    n = conn.execute("SELECT COUNT(*) FROM commentary").fetchone()[0]
    n_ts = conn.execute("SELECT COUNT(DISTINCT ts) FROM commentary").fetchone()[0]
    conn.close()
    assert n == 14 and n_ts == 2                                # 并批 → 1 ts，后写覆盖前写

    items = commentary.history_index()
    assert [it["generated_at"] for it in items] == ["2026-03-01T12:00:00.002",
                                                    "2026-03-01T12:00:00.001"]
    assert commentary.get_batch("2026-03-01T12:00:00.001")["overall"] == "批1 总体"
    assert commentary.get_batch("2026-03-01T12:00:00.002")["overall"] == "批2 总体"
    assert commentary.get_current()["provenance"]["generated_at"] == "2026-03-01T12:00:00.002"


def test_history_batch_detail_and_404(monkeypatch):
    _three_batches(monkeypatch)
    items = client.get("/api/v1/commentary/history").json()["items"]
    ts = items[1]["generated_at"]                                # 中间项
    r = client.get("/api/v1/commentary/history", params={"ts": ts})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and set(body["sections"]) == set(SECTIONS)
    assert body["provenance"]["generated_at"] == ts
    assert client.get("/api/v1/commentary/history", params={"ts": "不存在"}).status_code == 404


# ── 12. snapshot 形状（真库）─────────────────────────────────────────────────

@pytest.mark.skipif(not REAL_DB.exists(), reason="无真实 data/macro_data.db")
def test_snapshot_shape_real_db(monkeypatch):
    monkeypatch.setattr(commentary, "DB_PATH", REAL_DB)
    snap = commentary.build_section_snapshot()
    assert set(snap) == {"data_as_of", "sections"}
    assert set(snap["sections"]) == set(SECTIONS)
    assert set(snap["data_as_of"]) == set(commentary._AS_OF_TABLES)

    def _scalar_only(v):
        assert v is None or isinstance(v, (str, int, float, bool)), f"非标量入 payload: {v!r}"

    for sec in snap["sections"].values():
        assert isinstance(sec["missing"], list)
        assert sec["missing"] == [k for k, v in sec.items() if v is None and k != "missing"]
        for k, v in sec.items():
            if k == "missing":
                continue
            _scalar_only(v)                                            # 长序列禁入

    assert set(snap["sections"]["merrill"]) == {
        "phase", "gdp_yoy", "gdp_yoy_prev", "cpi_yoy", "cpi_yoy_prev", "missing"}
    assert set(snap["sections"]["credit"]) == {
        "phase", "m2_yoy", "m2_yoy_delta", "credit_impulse", "missing"}
    assert set(snap["sections"]["inventory"]) == {
        "phase", "pmi_official", "ip_yoy", "missing"}
    assert set(snap["sections"]["debt"]) == {
        "phase", "household", "non_fin_corp", "gov_total", "household_change_4q",
        "non_fin_corp_change_4q", "gov_change_4q", "missing"}
    assert set(snap["sections"]["real_estate"]) == {
        "composite_score", "leverage_space_score", "price_momentum_score",
        "rate_env_score", "household_leverage", "leverage_space_pp",
        "price_mom_12m", "lpr_5y", "rate_deviation_bp", "missing"}
    assert set(snap["sections"]["fiscal_external"]) == {
        "revenue_cum_yoy", "expenditure_cum_yoy", "exports_yoy", "ism", "missing"}
