"""AI commentary service — structured generation over a per-section snapshot.

Architecture (M4b generation layer; config via core/ai_config + keychain):
    build_section_snapshot() → per-section scalars + data_as_of + missing
    DEFAULT_TEMPLATES / get_templates() / template_hash() → prompts + version hash
    generate()        → one structured call (validate → retry once → per-section
                        fallback) → persist 7 rows (6 sections + overall, shared ts)

Triggers:
    - lifespan startup: fire-and-forget generate if DB empty
    - refresh success:  mark_stale + async regenerate (refresh-as-rerun)
    - config change:    ai_config._save hook → mark_stale only (no auto-regen)
    - manual POST:      sync generate (caller awaits)

Merged onto the post-1.2.0 baseline: connections come from the one factory in
``core/db.py`` (WAL + busy_timeout, A-M1), and busy-ness is derived from
``_gen_lock.locked()`` — a separate threading.Event flag could be left set
forever when two generations raced (F10), pinning the UI on an endless poll.
While busy, get_current returns the PREVIOUS batch with ``regenerating: True``
instead of blanking the card.
"""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime

from analysis.cycle_credit import classify_credit
from analysis.cycle_debt import classify_debt
from analysis.cycle_inventory import classify_inventory
from analysis.cycle_merrill import classify_merrill
from analysis.real_estate import analyze_real_estate
from backend.app.core import ai_client, ai_config
from backend.app.core.db import DB_PATH, _load_full, connect

COMMENTARY_TABLE = "commentary"

SECTIONS = ("merrill", "credit", "inventory", "debt", "real_estate", "fiscal_external")

# Lock so concurrent generate() calls (startup + manual + refresh) never race.
# Busy-ness is DERIVED from the lock (`_gen_lock.locked()`) — a separate flag
# (the old threading.Event `_busy`) could be left set forever when thread A's
# `finally: clear()` raced thread B's `set()` after a failed acquire (F10).
_gen_lock = threading.Lock()
# Set True after _ensure_table first succeeds; get_current skips the per-poll
# CREATE TABLE IF NOT EXISTS + commit (table provably exists for process lifetime).
_table_ready = False


def _ts() -> str:
    # 毫秒精度：ts 兼作批次键，秒级在同秒两次 persist 会静默并批
    return datetime.now().isoformat(timespec="milliseconds")


def _connect() -> sqlite3.Connection:
    """Macro-DB connection from the ONE factory in ``core/db.py`` (A-M1):
    WAL + busy_timeout（裸 sqlite3.connect 遇到并发写会立刻 database is locked）。
    ``DB_PATH`` 在调用时读取，测试 monkeypatch 依旧生效。"""
    return connect(DB_PATH, row_factory=sqlite3.Row)


# ── Migration: new provenance columns (additive, idempotent) ────────────────
# ts doubles as generated_at and batch key; composite_score stays NULL for new
# rows (kept for legacy rows, SQLite cannot drop columns cheaply).
_NEW_COLS = {
    "section":       "TEXT DEFAULT 'overall'",
    "endpoint":      "TEXT",
    "template_hash": "TEXT",
    "profile":       "TEXT",
}


def _ensure_table(conn: sqlite3.Connection) -> None:
    global _table_ready
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {COMMENTARY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            data_as_of TEXT NOT NULL,
            composite_score INTEGER,
            phase_snapshot TEXT NOT NULL,
            text TEXT NOT NULL,
            model TEXT,
            stale INTEGER DEFAULT 0,
            section TEXT DEFAULT 'overall',
            endpoint TEXT,
            template_hash TEXT,
            profile TEXT
        )"""
    )
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({COMMENTARY_TABLE})")}
    for col, ddl in _NEW_COLS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE {COMMENTARY_TABLE} ADD COLUMN {col} {ddl}")
    conn.commit()
    _table_ready = True


# ── snapshot v2: per-section scalars only, missing explicit ──────────────────

def _r(x):
    """float → round(2); None/NaN → None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, 2)


def _sec_merrill() -> dict:
    df = classify_merrill(str(DB_PATH))   # 年频，「上期」= 上一年
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    return {"phase": str(last["phase"]),
            "gdp_yoy": _r(last["gdp_yoy"]),
            "gdp_yoy_prev": None if prev is None else _r(prev["gdp_yoy"]),
            "cpi_yoy": _r(last["cpi_yoy"]),
            "cpi_yoy_prev": None if prev is None else _r(prev["cpi_yoy"])}


def _sec_credit() -> dict:
    df = classify_credit(str(DB_PATH))
    last = df.iloc[-1]
    return {"phase": str(last["phase"]),
            "m2_yoy": _r(last["m2_yoy"]),
            "m2_yoy_delta": _r(df["m2_yoy"].diff(1).iloc[-1]),
            "credit_impulse": _r(last["credit_impulse"])}


def _sec_inventory() -> dict:
    last = classify_inventory(str(DB_PATH)).iloc[-1]
    return {"phase": str(last["phase"]),
            "pmi_official": _r(last["pmi_official"]),
            "ip_yoy": _r(last["ip_yoy"])}


def _sec_debt() -> dict:
    df = classify_debt(str(DB_PATH))
    last = df.iloc[-1]
    return {"phase": str(last["overall_phase"]),
            "household": _r(last["household"]),
            "non_fin_corp": _r(last["non_fin_corp"]),
            "gov_total": _r(last["gov_total"]),
            # classify_debt 不返回 4 季差分列 → 对返回 df 现算，analysis/ 零 diff
            "household_change_4q": _r(df["household"].diff(4).iloc[-1]),
            "non_fin_corp_change_4q": _r(df["non_fin_corp"].diff(4).iloc[-1]),
            "gov_change_4q": _r(df["gov_total"].diff(4).iloc[-1])}


def _sec_real_estate() -> dict:
    a = analyze_real_estate(str(DB_PATH))["assessment"]
    return {k: _r(a[k]) for k in ("composite_score", "leverage_space_score",
                                  "price_momentum_score", "rate_env_score",
                                  "household_leverage", "leverage_space_pp",
                                  "price_mom_12m", "lpr_5y", "rate_deviation_bp")}


def _sec_fiscal_external() -> dict:
    fis = _load_full("fiscal").iloc[-1]
    ext = _load_full("external_demand").iloc[-1]
    return {"revenue_cum_yoy": _r(fis["revenue_cum_yoy"]),
            "expenditure_cum_yoy": _r(fis["expenditure_cum_yoy"]),
            "exports_yoy": _r(ext["exports_yoy"]),
            "ism": _r(ext["us_ism_pmi"])}


_BUILDERS = {"merrill": _sec_merrill, "credit": _sec_credit,
             "inventory": _sec_inventory, "debt": _sec_debt,
             "real_estate": _sec_real_estate, "fiscal_external": _sec_fiscal_external}

_FIELDS = {
    "merrill": ("phase", "gdp_yoy", "gdp_yoy_prev", "cpi_yoy", "cpi_yoy_prev"),
    "credit": ("phase", "m2_yoy", "m2_yoy_delta", "credit_impulse"),
    "inventory": ("phase", "pmi_official", "ip_yoy"),
    "debt": ("phase", "household", "non_fin_corp", "gov_total",
             "household_change_4q", "non_fin_corp_change_4q", "gov_change_4q"),
    "real_estate": ("composite_score", "leverage_space_score", "price_momentum_score",
                    "rate_env_score", "household_leverage", "leverage_space_pp",
                    "price_mom_12m", "lpr_5y", "rate_deviation_bp"),
    "fiscal_external": ("revenue_cum_yoy", "expenditure_cum_yoy", "exports_yoy", "ism"),
}

_AS_OF_TABLES = ("derived_monthly", "derived_quarterly", "leverage",
                 "house_price", "lpr", "fiscal", "external_demand")


def _data_as_of() -> dict:
    """7 张来源表各自最新日期（YYYY-MM）；表空/缺 date → 该键 null。"""
    import pandas as pd
    out = {}
    for t in _AS_OF_TABLES:
        try:
            df = _load_full(t)
            d = df["date"].max() if not df.empty and "date" in df.columns else None
            out[t] = str(d)[:7] if pd.notna(d) else None
        except Exception:
            out[t] = None
    return out


def build_section_snapshot() -> dict:
    """Assemble the per-section scalar snapshot fed to the model. Never raises.

    Builder 抛异常（空表等）→ 该板块全部字段 None + missing 记全名；
    长序列禁入 payload，缺失显式标记（模型知道「没有」而不是「不说」）。
    """
    sections = {}
    for name in SECTIONS:
        try:
            raw = _BUILDERS[name]()
        except Exception:
            raw = {}
        sec = {k: raw.get(k) for k in _FIELDS[name]}
        sec["missing"] = [k for k, v in sec.items() if v is None]
        sections[name] = sec
    return {"data_as_of": _data_as_of(), "sections": sections}


# ── Templates: defaults + ai_config overrides + version hash ─────────────────

# 默认提示词（v2，2026-08-30 重写）：每板块 = 框架语义 + 字段口径 + 必答任务 + 写作结构。
# 长度约束与后端校验一致（每板块 ≤600 字）；数值引用必须带单位与口径，禁止编造。
DEFAULT_TEMPLATES = {
    "system": (
        "你是资深宏观经济分析师，为一套中国宏观周期监测系统撰写研究备忘录。"
        "写作规则：① 只引用数据快照中出现的数值，且引用时必须带单位与口径（如「M2 同比 7.7%」"
        "「居民杠杆率 59.0%」）；快照没有的一概不写，不得编造任何指标、日期、趋势或历史对比；"
        "② 术语以国家统计局/中国人民银行官方口径为准；CPI、PPI、M2、PMI、LPR、GDP、ISM 等"
        "保留英文缩写；③ 不给任何投资建议或买卖指引，只做形势研判；④ 行文正式、精炼、书面化，"
        "用「本期/上期/边际」等研究语汇，禁止口语化表达与emoji；⑤ 最终输出必须是合法 JSON，"
        "除 JSON 外不含任何文字、注释或 markdown 围栏。"
    ),
    # 每板块规定必答：现状定位 / 边际变化 / 矛盾张力 / 含义；精准备忘录 3-5 句
    "merrill": (
        "为「美林投资时钟」板块写 3-5 句研究备忘录。框架语义：以 GDP 同比相对潜在增长（5 期中位数趋势）"
        "定义增长方向，以 CPI 同比相对 2% 定义通胀方向，四象限为复苏/过热/滞胀/衰退。"
        "快照字段：phase（当前阶段）、gdp_yoy/gdp_yoy_prev（本期与上年同期 GDP 同比 %）、"
        "cpi_yoy/cpi_yoy_prev（本期与上年同期 CPI 同比 %）。"
        "写作结构：先点明当前阶段判定及两轴取值；再说明相对上期的边际迁移方向；"
        "若取值与阶段含义存在张力（如增长仍在趋势之上但通胀逼近阈值），指出并解释；"
        "末句给出该阶段在框架内的标准含义（如复苏=增长升+通胀降）。"
    ),
    "credit": (
        "为「信用周期」板块写 3-5 句研究备忘录。框架语义：以 M2 同比相对其 12 月均线的偏离"
        "（信贷脉冲）刻画货币条件松紧，脉冲>0 且上行=宽松，<0 且下行=紧缩，其余=中性。"
        "快照字段：phase（当前阶段）、m2_yoy（M2 同比 %）、m2_yoy_delta（环比变化 pp）、"
        "credit_impulse（信贷脉冲，M2 同比−12 月均线，pp）。"
        "写作结构：点明阶段与 M2 同比取值；用脉冲的符号与方向解释判定依据；"
        "若脉冲与阶段存在张力（如脉冲为正但趋势走弱），指出矛盾；末句说明该货币条件对实体融资的含义。"
    ),
    "inventory": (
        "为「库存周期」板块写 3-5 句研究备忘录。框架语义：以官方制造业 PMI 相对荣枯线 50 刻画需求，"
        "以工业增加值同比相对其 6 月均线刻画生产，四象限为主动补库/被动补库/主动去库/被动去库。"
        "快照字段：phase（当前阶段）、pmi_official（官方制造业 PMI，点）、ip_yoy（工业增加值同比 %）。"
        "写作结构：点明阶段及两项取值；说明需求（PMI）与生产（工业增加值）各自相对基准的位置；"
        "若二者方向背离（如需求收缩但生产仍强），指出矛盾及其对库存方向的含义。"
    ),
    "debt": (
        "为「债务周期」板块写 3-5 句研究备忘录。框架语义（达利欧口径）：以各部门杠杆率 4 季度变化"
        "判定加/去杠杆（>+1pp 加杠杆，<-0.5pp 去杠杆），结合增长分方向合成总体阶段"
        "（美丽去杠杆/丑陋去杠杆/加杠杆繁荣/加杠杆衰退/稳定增长/稳定收缩）。"
        "快照字段：phase（总体阶段）、household/non_fin_corp/gov_total（居民/非金融企业/政府杠杆率，"
        "占 GDP %）、household_change_4q/non_fin_corp_change_4q/gov_change_4q（各自 4 季度变化，pp）。"
        "写作结构：点明总体阶段；分部门引用杠杆率取值与 4 季变化，指出哪个部门在驱动总体方向；"
        "若部门间方向不一致（如政府加杠杆对冲居民去杠杆），点明对冲结构。"
    ),
    "real_estate": (
        "为「房地产」板块写 3-5 句研究备忘录。框架语义：三维评分（0-100，越高越支撑需求）——"
        "杠杆空间（居民杠杆率相对 70% 上限的余量）、价格动能（70 城新房环比 12 个月均值相对 100 的偏离）、"
        "利率环境（5 年期 LPR 相对其历史中位数的偏离）。"
        "快照字段：composite_score（综合分）、leverage_space_score/price_momentum_score/rate_env_score"
        "（三分量）、household_leverage（居民杠杆率 %）、leverage_space_pp（余量 pp）、"
        "price_mom_12m（环比 12 月均值，100=持平）、lpr_5y（5 年期 LPR %）、rate_deviation_bp（偏离中位数，pp）。"
        "写作结构：点明综合分与最强/最弱维度及各自取值；用底层取值解释得分来源；"
        "若维度间存在张力（如利率宽松但价格动能仍弱），指出矛盾。"
    ),
    "fiscal_external": (
        "为「财政与外需」板块写 3-5 句研究备忘录。框架语义：财政收入/支出累计同比刻画财政姿态，"
        "出口同比（美元口径）与美国 ISM 制造业 PMI 刻画外需强弱。"
        "快照字段：revenue_cum_yoy/expenditure_cum_yoy（财政收入/支出累计同比 %）、"
        "exports_yoy（出口同比 %）、ism（美国 ISM 制造业 PMI，点；荣枯线 50）。"
        "写作结构：点明财政收支两端的方向与取值（收>支或支>收的含义）；"
        "再评估外需（出口同比 + ISM 相对 50 的位置）；若内需与外需方向背离，指出并解释其政策含义。"
    ),
    # overall：6-8 句跨板块综合
    "overall": (
        "写 6-8 句跨板块综合研判（不是逐板块复述）。要求：① 先给出当前宏观组合的一句话总判定"
        "（增长×通胀×货币×杠杆的组合姿态）；② 指出六大框架之间最主要的一致点与背离点"
        "（如货币宽松与库存去化的张力、财政发力与外需走弱的背离），并引用关键取值佐证；"
        "③ 评估当前组合的可持续性与下一阶段最可能的演化方向；④ 点明最值得关注的一两个风险或"
        "确认信号（如下次 PMI 是否重回荣枯线上方）；⑤ 全程不给投资建议，只做形势研判。"
    ),
}


def get_templates() -> dict:
    """默认模板 + ai_config.json templates{} 覆盖（仅接受非空字符串、仅已知键）。"""
    overrides = ai_config.load().get("templates") or {}
    return {**DEFAULT_TEMPLATES,
            **{k: v for k, v in overrides.items()
               if k in DEFAULT_TEMPLATES and isinstance(v, str) and v.strip()}}


def template_hash(tpls: dict | None = None) -> str:
    """sha256(全模板确定性序列化)，64 hex；出处行展示前 8 位。"""
    t = tpls if tpls is not None else get_templates()
    return hashlib.sha256(
        json.dumps(t, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# ── Generation: one structured call → validate → retry once → fallback ───────

def _build_messages(snapshot: dict, tpls: dict) -> list[dict]:
    req = "\n".join(f"- sections.{k}：{tpls[k]}" for k in SECTIONS)
    user = ("数据快照（JSON）：\n" + json.dumps(snapshot, ensure_ascii=False)
            + "\n\n写作要求（每条对应输出 JSON 的一个字段）：\n" + req
            + f"\n- overall：{tpls['overall']}"
            + '\n\n只输出一个 JSON 对象，形如 {"sections": {"merrill": "…", "credit": "…", '
              '"inventory": "…", "debt": "…", "real_estate": "…", "fiscal_external": "…"}, '
              '"overall": "…"}，不要输出任何其他文字。')
    return [{"role": "system", "content": tpls["system"]},
            {"role": "user", "content": user}]


def _section_messages(name: str, snapshot: dict, tpls: dict) -> list[dict]:
    user = ("数据快照（JSON）：\n" + json.dumps(snapshot, ensure_ascii=False)
            + f"\n\n写作要求：{tpls[name]}"
            + "\n请直接输出该板块的中文文本，不要 JSON、不要标题"
            + "（本次调用例外：忽略系统提示中关于 JSON 输出的要求，只输出纯文本）。")
    return [{"role": "system", "content": tpls["system"]},
            {"role": "user", "content": user}]


def _extract_json(text: str) -> dict | None:
    """提取第一个可解析的平衡 {...}：容忍前后散文、markdown 围栏、嵌套大括号。

    从每个 '{' 起做深度计数（识别字符串内大括号/转义），平衡时 json.loads；
    失败则取下一个 '{' 重来。
    """
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except Exception:
                        break                       # 该平衡块非 JSON → 下一个 '{'
                    return obj if isinstance(obj, dict) else None
    return None


def _valid_text(v) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= 600


def _unwrap_section(text: str, name: str) -> str:
    """补调防御：强对齐模型若服从 system 的 JSON 规则而返回包裹 → 取本板块值。

    依次试 obj[name]、obj.sections[name]、单键包装的唯一字符串；
    取不出 → 空串（校验失败，走 last-good），绝不让带大括号的原始 JSON 过校验。
    """
    obj = _extract_json(text)
    if not isinstance(obj, dict):
        return text                                 # 纯文本：正常路径原样返回
    for cand in (obj, obj.get("sections")):
        if isinstance(cand, dict) and _valid_text(cand.get(name)):
            return cand[name]
    strs = [v for v in obj.values() if isinstance(v, str)]
    return strs[0] if len(strs) == 1 and len(obj) == 1 else ""


def _validate_structured(raw: str) -> tuple[dict, list[str]]:
    """返回 (通过校验的 parts, problems)。

    校验：sections 是 dict 且 6 板块键全；每值为非空字符串且 ≤600 字；overall 同。
    """
    parts: dict = {}
    problems: list[str] = []
    obj = _extract_json(raw)
    if obj is None:
        return parts, ["输出不是合法 JSON 对象"]
    secs = obj.get("sections")
    if not isinstance(secs, dict):
        problems.append("sections 不是对象")
    else:
        for k in SECTIONS:
            if k not in secs:
                problems.append(f"sections.{k} 缺失")
            elif not _valid_text(secs[k]):
                problems.append(f"sections.{k} 为空或超 600 字")
            else:
                parts[k] = secs[k].strip()
    if not _valid_text(obj.get("overall")):
        problems.append("overall 为空或超 600 字")
    else:
        parts["overall"] = obj["overall"].strip()
    return parts, problems


def _call_structured_with_fallback(profile: dict, key: str,
                                   snapshot: dict, tpls: dict) -> dict | None:
    """结构化一次 → 校验 → 带错误反馈重试一次 → 逐板块补调。全败返回 None。"""
    messages = _build_messages(snapshot, tpls)
    best: dict = {}
    transport_failed = False
    for _ in range(2):                              # 首次 + 带错误反馈重试一次
        try:
            raw = ai_client.call_chat(profile, key, messages, timeout=300.0)   # 推理模型（kimi-k3）单次要 2-4 分钟
        except ai_client.AiError:
            transport_failed = True                 # 网络/http 错误：换格式重试与补调均无意义
            break
        parts, problems = _validate_structured(raw)
        if not problems:
            return parts
        best.update(parts)                          # 保留已合格的部分
        messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"上次输出不合格：{'；'.join(problems)}。请只输出符合要求的 JSON。"}]
    # 降级：逐板块补调——只补缺失/不合格的键（最多 7 次补调），纯文本输出更易通过。
    # transport_failed 时跳过：死网络上补调只是每次白吃 60s timeout
    if not transport_failed:
        for name in (*SECTIONS, "overall"):
            if _valid_text(best.get(name)):
                continue
            try:
                text = ai_client.call_chat(profile, key, _section_messages(name, snapshot, tpls), timeout=150.0)
            except ai_client.AiError:
                break                               # 同结构化循环：网络错误换板块重试无意义
            text = _unwrap_section(text, name)
            if _valid_text(text):
                best[name] = text.strip()
    return best if all(_valid_text(best.get(k)) for k in (*SECTIONS, "overall")) else None


def generate(blocking: bool = True) -> dict:
    """Snapshot → structured model call → persist 7-row batch.

    blocking=True  → caller waits for the model call (manual POST).
    blocking=False → fire-and-forget on a worker thread (startup/refresh).
    """
    if not blocking:
        t = threading.Thread(target=_generate_impl, daemon=True)
        t.start()
        return {"status": "generating", "msg": "评论生成中…"}
    return _generate_impl()


def _configured() -> tuple[dict | None, str | None]:
    """resolve_active() 唯一配置入口 + key_for() 取密钥。"""
    profile = ai_config.resolve_active()
    key = ai_config.key_for(profile["name"]) if profile else None
    return profile, key or None


def _generate_impl() -> dict:
    if not _gen_lock.acquire(blocking=False):
        # Another generation is in flight — don't stack a second one. The lock
        # being held IS the busy signal, so there is nothing to flag here.
        return {"status": "generating", "msg": "已有生成在进行中…"}
    try:
        profile, key = _configured()
        if profile is None:
            return {"status": "empty", "msg": "未配置 AI 模型", "hint": "/ai-settings"}
        if not key:
            return {"status": "empty", "msg": f"profile「{profile['name']}」未配置密钥",
                    "hint": "/ai-settings"}
        snapshot = build_section_snapshot()
        tpls = get_templates()
        parts = _call_structured_with_fallback(profile, key, snapshot, tpls)
        if parts is None:                      # 全败 → 不写库，保留 last-good
            return {"status": "error",
                    "msg": "生成失败：重试与逐板块补调均未通过校验（已保留上一版评论）"}
        return _persist_batch(snapshot, parts, profile, tpls)
    except Exception as e:
        return {"status": "error", "msg": f"生成失败：{type(e).__name__}: {e}"}
    finally:
        _gen_lock.release()


# ── Persistence: 7 rows per batch (shared ts = batch key) ────────────────────

KEEP_BATCHES = 10   # 轮转：保留最近 N 个 generated_at 批次（M4c）


def _prune(conn: sqlite3.Connection) -> None:
    """保留最近 KEEP_BATCHES 个 ts 批次，更旧批次整体删除（与 insert 同事务）。"""
    old = conn.execute(
        f"SELECT DISTINCT ts FROM {COMMENTARY_TABLE} "
        f"ORDER BY ts DESC LIMIT -1 OFFSET {KEEP_BATCHES}").fetchall()
    if old:
        conn.executemany(f"DELETE FROM {COMMENTARY_TABLE} WHERE ts = ?",
                         [(r[0],) for r in old])


def _persist_batch(snapshot: dict, parts: dict, profile: dict, tpls: dict) -> dict:
    ts = _ts()
    rows = [(ts, json.dumps(snapshot["data_as_of"], ensure_ascii=False),
             json.dumps(snapshot, ensure_ascii=False),   # phase_snapshot 复用：模型看到的原始输入
             parts[name], profile["model"], name,
             profile.get("endpoint", "chat_completions"),
             template_hash(tpls), profile["name"])
            for name in (*SECTIONS, "overall")]
    conn = _connect()
    try:
        _ensure_table(conn)
        conn.executemany(
            f"INSERT INTO {COMMENTARY_TABLE} "
            "(ts, data_as_of, phase_snapshot, text, model, section, "
            "endpoint, template_hash, profile, stale) VALUES (?,?,?,?,?,?,?,?,?,0)",
            rows)
        _prune(conn)
        conn.commit()
        batch = _latest_batch(conn)
    finally:
        conn.close()
    return batch


def _latest_batch(conn: sqlite3.Connection) -> dict:
    ts = conn.execute(f"SELECT MAX(ts) FROM {COMMENTARY_TABLE}").fetchone()[0]
    if ts is None:
        return _empty()
    rows = conn.execute(
        f"SELECT * FROM {COMMENTARY_TABLE} WHERE ts = ?", (ts,)).fetchall()
    return _batch_to_dict(rows)


def _batch_to_dict(rows: list[sqlite3.Row]) -> dict:
    first = rows[0]
    sections: dict = {}
    overall = ""
    stale = False
    for row in rows:
        if (row["section"] or "overall") == "overall":
            overall = row["text"]
        else:
            sections[row["section"]] = row["text"]
        stale = stale or bool(row["stale"])
    # data_as_of：新批次存 JSON dict；legacy 单行是裸 "YYYY-MM" → 兜底 dict
    try:
        as_of = json.loads(first["data_as_of"])
        if not isinstance(as_of, dict):
            raise ValueError
    except Exception:
        as_of = {"derived_monthly": first["data_as_of"]}
    return {"status": "ok", "stale": stale, "overall": overall, "sections": sections,
            "provenance": {"model": first["model"], "endpoint": first["endpoint"],
                           "template_hash": first["template_hash"], "data_as_of": as_of,
                           "profile": first["profile"], "generated_at": first["ts"]}}


def _empty() -> dict:
    d = {"status": "empty", "msg": "暂无评论"}
    profile, key = _configured()
    if profile is None or not key:
        d["hint"] = "/ai-settings"
    return d


def get_current() -> dict:
    """Return the latest commentary batch, or a generating/empty status.

    生成在途（锁被持有）时返回上一批 + ``regenerating: True``——而不是把卡片
    清空成「生成中」（旧行为会在每次模型调用期间扔掉一整版完好的评论）。
    读取只豁免「no such table」（fresh install）；其余错误冒泡，不把读取失败
    静默伪装成「暂无评论」（与 F13/signal_history 同一口径）。
    """
    conn = _connect()
    try:
        if not _table_ready:
            _ensure_table(conn)
        batch = _latest_batch(conn)
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e).lower():
            raise
        return _empty()
    finally:
        conn.close()
    if _gen_lock.locked():
        if batch.get("status") != "ok":
            return {"status": "generating", "msg": "评论生成中…", "regenerating": False}
        return {
            **batch,
            "status": "generating",
            "msg": "评论重新生成中…（以下为上一版）",
            "regenerating": True,
        }
    return batch


# ── History: read-only batch index + single-batch detail (M4c 呈现层) ────────

def history_index() -> list[dict]:
    """批次索引：ts 倒序；每批一行（GROUP BY ts），overall 行取前 80 字作预览。"""
    conn = _connect()
    try:
        if not _table_ready:
            _ensure_table(conn)
        rows = conn.execute(
            f"SELECT ts, model, profile, template_hash, MAX(stale) AS stale, "
            f"MAX(CASE WHEN COALESCE(section,'overall')='overall' THEN text END) AS ov "
            f"FROM {COMMENTARY_TABLE} GROUP BY ts ORDER BY ts DESC").fetchall()
    finally:
        conn.close()
    return [{"generated_at": r["ts"], "model": r["model"], "profile": r["profile"],
             "template_hash": r["template_hash"], "status": "ok",
             "stale": bool(r["stale"]),
             "overall_preview": (r["ov"][:80] + "…") if r["ov"] and len(r["ov"]) > 80
                                else (r["ov"] or "")}
            for r in rows]


def get_batch(ts: str) -> dict | None:
    """单批详情：复用 _batch_to_dict（含 legacy 兜底），无此批次 → None。"""
    conn = _connect()
    try:
        if not _table_ready:
            _ensure_table(conn)
        rows = conn.execute(
            f"SELECT * FROM {COMMENTARY_TABLE} WHERE ts = ?", (ts,)).fetchall()
    finally:
        conn.close()
    return _batch_to_dict(rows) if rows else None


# ── stale wiring ──────────────────────────────────────────────────────────────

def mark_stale() -> None:
    """所有未 stale 行置 stale=1（数据/配置已变）。失败静默——评论非关键路径。"""
    try:
        conn = _connect()
        try:
            _ensure_table(conn)
            conn.execute(f"UPDATE {COMMENTARY_TABLE} SET stale = 1 WHERE stale = 0")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def mark_stale_and_regenerate() -> dict:
    """Called after a successful data refresh: mark old rows stale + trigger
    a fresh generation (refresh-as-rerun policy)."""
    mark_stale()
    return generate(blocking=False)


def ensure_on_startup() -> None:
    """lifespan hook: generate if no commentary exists yet (fire-and-forget)."""
    try:
        conn = _connect()
        _ensure_table(conn)
        n = conn.execute(f"SELECT COUNT(*) FROM {COMMENTARY_TABLE}").fetchone()[0]
        conn.close()
        if n == 0:
            generate(blocking=False)
    except Exception:
        pass  # startup must never crash on commentary


if __name__ == "__main__":
    # manual smoke test: python -m backend.app.core.commentary
    print(json.dumps(build_section_snapshot(), ensure_ascii=False, indent=2))
