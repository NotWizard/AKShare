# M4b 设计文档 — AI 生成层：板块 snapshot v2 + 模板 + 结构化生成 + 出处持久化 + 总体卡 v2

> 分支：worktree-ai-commentary-m4 ｜ 日期：2026-08-16
> 范围纪律：M4b 只做生成层——①分板块 snapshot v2 ②默认模板 + 版本 hash ③单次结构化生成
> （校验/重试/降级）④commentary 表扩列 + 出处持久化 + stale 重接线 ⑤Overview CommentaryCard v2。
> **不做**：细分页切片、模板编辑器 UI、生成历史 UI（M4c）。
> 约束：零新依赖；`analysis/` 零 diff；复用 M4a 基线（`ai_client.call_chat` /
> `ai_config.resolve_active` / `keychain.get_key`）与 commentary 既有单飞锁 / stale / ensure_on_startup。

---

## 0. 现状要点（读取结论，约束设计的既有事实）

- `backend/app/core/commentary.py`：单飞锁 `_gen_lock` + `_busy` Event + `_table_ready` 优化；
  `build_snapshot()`（基于 `compute_signals()`，仅四框架 + cross_lags）；`call_model()` 直读
  `COMMENTARY_BASE_URL/API_KEY/MODEL` 三件 env、httpx 手搓 POST；`generate(blocking)` →
  `_generate_impl` → `_persist` 单行写入；`get_current()` / `mark_stale_and_regenerate()` /
  `ensure_on_startup()`。**接管方式**：整个「snapshot + call_model + 单行 persist」段落被 M4b
  替换；锁 / stale / startup / GET-regenerate 路由骨架原样沿用。
  `scripts/signal_history.py` 只在**注释**里提到 `commentary._latest_data_date`，无 import 依赖。
- `backend/app/core/ai_client.py`：`call_chat(profile, key, messages, temperature=None, *,
  timeout=60.0, transport=None)`，错误归一 `AiError(stage∈request/http/parse)`；
  `test_connection` 已用 `timeout=25.0`（M4a 提交 71ee527 已落地——提交说明中「30s/60s 不一致
  记录在案」一句为过时表述，代码实测 25s，见 §7）。
- `backend/app/core/ai_config.py`：`resolve_active()` 注释已声明是「M4b 生成链路的唯一取配置入口」；
  `key_for(name)`（env → COMMENTARY_API_KEY；否则 keychain）；`load()/_save()` 原子写；
  变更点 = `create/update/delete/set_active` 四个函数，全部经 `_save()` 落盘。
- commentary 表现状 8 列：`id, ts, data_as_of, composite_score, phase_snapshot, text, model, stale`
  （`data/macro_data.db` 实测 0 行——尚未生成过，迁移无历史包袱但仍按老库写法设计）。
- analysis 六模块入口与返回列（全部 lru_cache，`/signals`、`/real-estate` 已预热）：
  - `classify_merrill` → date, gdp_yoy, cpi_yoy, gdp_trend, phase, phase_color（**年频**）
  - `classify_credit` → date, m2_yoy, m2_trend, credit_impulse, phase
  - `classify_inventory` → date, pmi_official, pmi_ma6, ip_yoy, ip_trend, phase, phase_color
  - `classify_debt` → date, household, non_fin_corp, gov_total, household_phase, corp_phase,
    gov_phase, overall_phase（**不返回** 4 季差分列 → snapshot 内对返回 df 现算 `diff(4)`，
    analysis/ 零 diff）
  - `analyze_real_estate()["assessment"]` → composite_score + 三分量分 + 数值细节
    （household_leverage / leverage_space_pp / price_mom_12m / lpr_5y / rate_deviation_bp）+ as_of_*
  - fiscal_external 无现成 analysis 函数 → 直读表：
    `fiscal(revenue_cum_yoy, expenditure_cum_yoy)`、`external_demand(exports_yoy, us_ism_pmi)`
    （实测最新：fiscal 2026-04、external_demand 2026-07）
- `backend/app/core/refresh.py`：run_refresh 成功后 `from backend.app.core import commentary;
  commentary.mark_stale_and_regenerate()` —— **函数内延迟 import** 是 core 模块间避免循环依赖的
  既有先例，M4b 的 ai_config → commentary stale 钩子照抄此式。
- `backend/app/main.py` lifespan：预热 4 张热表 + `commentary.ensure_on_startup()`（不改）。
- 前端：`CommentaryCard.vue` 仅被 `Overview.vue` 使用；`client.ts request()` 30s abort +
  2s 轮询模式；types.ts 手写镜像 schema。
- `api/v1/commentary.py` 是纯薄 shell（`Commentary(**commentary.get_current())`）——
  只要 core 返回的 dict 与新 schema 对齐，**路由零 diff**。

---

## 1. snapshot v2 — `build_section_snapshot()`（commentary.py）

原则：**每板块只给标量数字**（最新值 + 至多一个上期/差分值），严禁长序列入 payload；
缺失显式标记，让模型知道「没有」而不是「不说」。

### 1.1 各板块取数

| 板块 | 来源 | 字段 |
|---|---|---|
| merrill | `classify_merrill` iloc[-1]/[-2] | phase；gdp_yoy / cpi_yoy 最新 + 上期（年频，「上期」=上一年） |
| credit | `classify_credit` iloc[-1]/[-2] | phase；m2_yoy 最新 + 环比差（`m2_yoy_delta` = 最新−上月）；credit_impulse 最新 |
| inventory | `classify_inventory` iloc[-1] | phase；pmi_official；ip_yoy |
| debt | `classify_debt` iloc[-1] + 现算 `diff(4)` | phase(overall_phase)；household / non_fin_corp / gov_total 最新 + 各自 4 季差分（`*_change_4q`） |
| real_estate | `analyze_real_estate()["assessment"]` | composite_score + leverage_space_score / price_momentum_score / rate_env_score + 数值细节（household_leverage, leverage_space_pp, price_mom_12m, lpr_5y, rate_deviation_bp） |
| fiscal_external | `_load_full("fiscal"/"external_demand")` 最新行 | revenue_cum_yoy；expenditure_cum_yoy；exports_yoy；ism（= us_ism_pmi） |

### 1.2 data_as_of 与 missing

- `data_as_of`：7 张来源表各自最新日期（`_load_full(t)["date"].max()`，lru_cache 已热），
  格式 YYYY-MM：`derived_monthly / derived_quarterly / leverage / house_price / lpr / fiscal /
  external_demand`。某表空 → 该键为 null。
- `missing`：**每板块内**自带 `missing: [...]`，列出该板块值为 null 的字段名
  （表空 / 列全 null 时即全部字段）。机械推导，不手工维护：
  `missing = [k for k, v in section.items() if v is None]`。

### 1.3 形状（示例，真实 DB 量级）

```json
{
  "data_as_of": {"derived_monthly": "2026-07", "derived_quarterly": "2026-06",
                 "leverage": "2026-06", "house_price": "2026-06", "lpr": "2026-07",
                 "fiscal": "2026-04", "external_demand": "2026-07"},
  "sections": {
    "merrill":  {"phase": "recession", "gdp_yoy": 5.0, "gdp_yoy_prev": 5.2,
                 "cpi_yoy": 0.4, "cpi_yoy_prev": 0.7, "missing": []},
    "credit":   {"phase": "neutral", "m2_yoy": 7.1, "m2_yoy_delta": 0.2,
                 "credit_impulse": -0.35, "missing": []},
    "inventory":{"phase": "active_restocking", "pmi_official": 50.2, "ip_yoy": 5.7, "missing": []},
    "debt":     {"phase": "beautiful_deleveraging", "household": 63.1, "non_fin_corp": 109.8,
                 "gov_total": 84.6, "household_change_4q": -0.9, "non_fin_corp_change_4q": 1.4,
                 "gov_change_4q": 3.2, "missing": []},
    "real_estate": {"composite_score": 41.9, "leverage_space_score": 46.7,
                 "price_momentum_score": 25.0, "rate_env_score": 54.0,
                 "household_leverage": 63.1, "leverage_space_pp": 6.9,
                 "price_mom_12m": 99.3, "lpr_5y": 3.5, "rate_deviation_bp": -0.12, "missing": []},
    "fiscal_external": {"revenue_cum_yoy": 2.1, "expenditure_cum_yoy": 4.3,
                 "exports_yoy": 6.8, "ism": 49.5, "missing": []}
  }
}
```

### 1.4 实现要点

```python
SECTIONS = ("merrill", "credit", "inventory", "debt", "real_estate", "fiscal_external")

def _r(x):                       # float → round(2)；None/NaN → None
def build_section_snapshot() -> dict: ...
```

- 每板块一个私有 builder，`try/except Exception` 包裹：分类器在空表上会抛
  （`iloc[-1]` 等）→ 该板块全部字段置 None、missing 记全名，**snapshot 永不抛**。
- 行数为 1 时 `_prev` 字段为 None；df 空时全部 None。
- `build_snapshot()` / `_latest_data_date()` 被本函数取代后**删除**（孤儿清理）。

---

## 2. 模板 — DEFAULT_TEMPLATES + 覆盖存储 + template_hash

### 2.1 默认模板（commentary.py 模块常量）

```python
DEFAULT_TEMPLATES = {
    "system": (
        "你是资深宏观经济分析师。根据用户提供的数据快照与写作要求撰写中文分析。"
        "规则：① 只引用快照中出现的数值，不得编造任何未提供的指标、日期或趋势；"
        "② 不给投资建议；③ 最终输出必须是合法 JSON，除 JSON 外不含任何文字。"
    ),
    # 每板块规定必答：现状 / 边际 / 与框架的矛盾；精准备忘录 3-5 句
    "merrill":  "为「美林投资时钟」板块写 3-5 句精准备忘录：点明当前阶段与 GDP/CPI 同比最新值；说明相对上期的边际变化；若数据与阶段含义有张力，指出矛盾。",
    "credit":   "为「信用周期」板块写 3-5 句精准备忘录：点明当前阶段、M2 同比最新值与环比变化、信贷脉冲；说明边际方向；若脉冲符号与阶段含义有张力，指出矛盾。",
    "inventory":"为「库存周期」板块写 3-5 句精准备忘录：点明当前阶段、官方 PMI 与工业增加值同比；说明相对荣枯线/趋势的位置；若需求与生产信号有张力，指出矛盾。",
    "debt":     "为「债务周期」板块写 3-5 句精准备忘录：点明总体阶段与居民/非金融企业/政府杠杆率最新值及各自 4 季变化；说明哪个部门在驱动；若部门方向不一致，指出矛盾。",
    "real_estate":"为「房地产」板块写 3-5 句精准备忘录：点明综合分与杠杆空间/价格动能/利率环境三分量；说明最强与最弱维度及其数值；若分量间有张力，指出矛盾。",
    "fiscal_external":"为「财政与外需」板块写 3-5 句精准备忘录：点明财政收入/支出累计同比、出口同比与美国 ISM；说明财政姿态与外需强弱；若内外需方向背离，指出矛盾。",
    # overall：6-8 句跨板块综合
    "overall":  "写 6-8 句跨板块综合研判：整合六个板块的现状与边际变化，点明板块间的主要矛盾与背离，给出总体判断。不要逐板块复述。",
}
```

### 2.2 覆盖存储与 hash

- `ai_config.json` 增加可选顶层键 `"templates": {}`（键 = 模板名，值 = 覆盖字符串）。
  **M4b 只落存储结构与读取路径**：`load()` 里 `cfg.setdefault("templates", {})`；
  编辑器 UI 与写入路径是 M4c。
- 读取（commentary.py）：

```python
def get_templates() -> dict:
    """默认模板 + ai_config.json templates{} 覆盖（仅接受非空字符串、仅已知键）。"""
    overrides = ai_config.load().get("templates") or {}
    return {**DEFAULT_TEMPLATES,
            **{k: v for k, v in overrides.items()
               if k in DEFAULT_TEMPLATES and isinstance(v, str) and v.strip()}}

def template_hash(tpls: dict | None = None) -> str:
    t = tpls if tpls is not None else get_templates()
    return hashlib.sha256(
        json.dumps(t, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
```

- hash = sha256(system + 各模板的确定性序列化（sort_keys），64 位 hex；出处行展示前 8 位。

---

## 3. 生成 — `generate()` 单飞 → 结构化一次 → 校验 → 重试一次 → 逐板块降级

`generate(blocking)` 签名与线程分发**不变**（blocking=False 仍是 fire-and-forget，
manual POST 仍是同步）。`_generate_impl` 重写：

```python
def _generate_impl(_mark_done: bool = False) -> dict:
    # _gen_lock / _busy 单飞逻辑原样
    profile = ai_config.resolve_active()
    if profile is None:
        return {"status": "empty", "msg": "未配置 AI 模型", "hint": "/ai-settings"}
    key = ai_config.key_for(profile["name"])
    if not key:
        return {"status": "empty", "msg": f"profile「{profile['name']}」未配置密钥",
                "hint": "/ai-settings"}
    snapshot = build_section_snapshot()
    tpls = get_templates()
    parts = _call_structured_with_fallback(profile, key, snapshot, tpls)
    if parts is None:                      # 全败 → 不写库，保留 last-good
        return {"status": "error", "msg": "生成失败：重试与逐板块补调均未通过校验（已保留上一版评论）"}
    return _persist_batch(snapshot, parts, profile, tpls)
```

### 3.1 消息装配

```python
def _build_messages(snapshot, tpls) -> list[dict]:
    req = "\n".join(f"- sections.{k}：{tpls[k]}" for k in SECTIONS)
    user = ("数据快照（JSON）：\n" + json.dumps(snapshot, ensure_ascii=False)
            + "\n\n写作要求（每条对应输出 JSON 的一个字段）：\n" + req
            + f"\n- overall：{tpls['overall']}"
            + '\n\n只输出一个 JSON 对象，形如 {"sections": {"merrill": "…", "credit": "…", '
              '"inventory": "…", "debt": "…", "real_estate": "…", "fiscal_external": "…"}, '
              '"overall": "…"}，不要输出任何其他文字。')
    return [{"role": "system", "content": tpls["system"]},
            {"role": "user", "content": user}]
```

调用走 M4a 适配器：`ai_client.call_chat(profile, key, messages)`（temperature 缺省 →
profile.temperature；timeout 缺省 60s，与现状一致）。

### 3.2 宽容解析 + 校验

```python
def _extract_json(text: str) -> dict | None:
    """提取第一个平衡的 {...}：容忍前后散文、markdown 围栏、嵌套大括号。
    从每个 '{' 起做深度计数，平衡时 json.loads；失败则找下一个 '{'。"""

def _valid_text(v) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= 600

def _validate_structured(raw: str) -> tuple[dict, list[str]]:
    """返回 (通过校验的 parts, problems)。
    校验：sections 是 dict 且 6 板块键全；每值为非空字符串且 ≤600 字；overall 同。"""
```

### 3.3 重试 + 降级流程

```python
def _call_structured_with_fallback(profile, key, snapshot, tpls) -> dict | None:
    messages = _build_messages(snapshot, tpls)
    best: dict = {}
    for _ in range(2):                              # 首次 + 带错误反馈重试一次
        try:
            raw = ai_client.call_chat(profile, key, messages)
        except ai_client.AiError:
            break                                   # 网络/http 错误：换格式重试无意义，直接进降级
        parts, problems = _validate_structured(raw)
        if not problems:
            return parts
        best.update(parts)                          # 保留已合格的部分
        messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"上次输出不合格：{'；'.join(problems)}。请只输出符合要求的 JSON。"}]
    # 降级：逐板块补调——只补缺失/不合格的键（最多 7 次补调），纯文本输出更易通过
    for name in (*SECTIONS, "overall"):
        if _valid_text(best.get(name)):
            continue
        try:
            text = ai_client.call_chat(profile, key, _section_messages(name, snapshot, tpls))
        except ai_client.AiError:
            continue
        if _valid_text(text):
            best[name] = text.strip()
    return best if all(_valid_text(best.get(k)) for k in (*SECTIONS, "overall")) else None
```

- `_section_messages(name, snapshot, tpls)`：system 同模板，user = 快照 JSON +
  `tpls[name]` + 「请直接输出该板块的中文文本，不要 JSON、不要标题」。
- 最坏情况调用次数 = 2（结构化）+ 7（补调）= 9 次；全败 → 返回 None → status=error，
  **不写库**，GET 继续返回 last-good 批次。

---

## 4. 持久化 — 加法迁移 + 一次生成 7 行 + GET v2 shape

### 4.1 扩列（SQLite 加法迁移，幂等）

新行需要的出处列：section / model / endpoint / template_hash / data_as_of / profile / 生成时间。
**model、data_as_of、ts 已存在**（ts 即生成时间 = 规格中的 generated_at，不新增重复列）。
实际新增 4 列：

```python
# _ensure_table：CREATE TABLE IF NOT EXISTS 直接含全列（新库），
# 老库走 PRAGMA 检测 + ALTER（幂等，可重复执行）
_NEW_COLS = {
    "section":       "TEXT DEFAULT 'overall'",
    "endpoint":      "TEXT",
    "template_hash": "TEXT",
    "profile":       "TEXT",
}

def _ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS commentary (
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
        profile TEXT)""")
    have = {r[1] for r in conn.execute("PRAGMA table_info(commentary)")}
    for col, ddl in _NEW_COLS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE commentary ADD COLUMN {col} {ddl}")
    conn.commit()
```

- `section DEFAULT 'overall'` → 老行（若有）ALTER 后自动读作 overall 行，legacy 兼容免费。
- composite_score 不再写入（snapshot v2 不含 composite），列保留为 NULL，不做删列。
- `data_as_of` 列改存 **JSON dict**（§1.2 的每表最新日期）。

### 4.2 一次生成写 7 行（同一 ts = 批次键）

```python
def _persist_batch(snapshot, parts, profile, tpls) -> dict:
    ts = _ts()
    rows = [(ts, json.dumps(snapshot["data_as_of"], ensure_ascii=False),
             json.dumps(snapshot, ensure_ascii=False),          # phase_snapshot 复用：模型看到的原始输入
             parts[name], profile["model"], name,
             profile.get("endpoint", "chat_completions"),
             template_hash(tpls), profile["name"])
            for name in (*SECTIONS, "overall")]
    # executemany INSERT（stale=0）→ commit → 读回批次组装响应
```

- 批次键 = ts（同一秒内不可能完成两次生成，模型调用远超 1s）；不引入 generated_at 新列。
- 老批次不删——历史留存给 M4c 生成历史 UI。

### 4.3 GET /commentary 响应 v2

```python
def _latest_batch(conn) -> dict:
    ts = conn.execute("SELECT MAX(ts) FROM commentary").fetchone()[0]
    if ts is None:
        return {"status": "empty", ...}
    rows = conn.execute("SELECT * FROM commentary WHERE ts = ?", (ts,)).fetchall()
    return _batch_to_dict(rows)
```

```json
{
  "status": "ok",
  "msg": null,
  "hint": null,
  "stale": false,
  "overall": "……6-8 句……",
  "sections": {"merrill": "…", "credit": "…", "inventory": "…",
               "debt": "…", "real_estate": "…", "fiscal_external": "…"},
  "provenance": {
    "model": "qwen-max", "endpoint": "chat_completions",
    "template_hash": "9f2c…（64 hex）", 
    "data_as_of": {"derived_monthly": "2026-07", "…": "…"},
    "profile": "qwen-max", "generated_at": "2026-08-16T21:00:00"
  }
}
```

- legacy 单行（ts 唯一、section='overall'）→ `sections: {}`、overall 为旧文本；
  其 data_as_of 是裸 "YYYY-MM" → 解析失败时兜底 `{"derived_monthly": 原值}`。
- `get_current()`：`_busy` → generating；空库时按 `resolve_active()` 是否为 None 决定
  是否带 `"hint": "/ai-settings"`。
- schema（`schemas/commentary.py` 重写，嵌套 Provenance；`schemas/__init__.py` 不变）：

```python
class Provenance(BaseModel):
    model: str | None = None
    endpoint: str | None = None
    template_hash: str | None = None
    data_as_of: dict[str, str] | None = None
    profile: str | None = None
    generated_at: str | None = None

class Commentary(BaseModel):
    status: str = "ok"                 # ok | generating | empty | error
    msg: str | None = None
    hint: str | None = None            # 无 profile/key 时给前端 CTA 路由（/ai-settings）
    stale: bool = False
    overall: str = ""
    sections: dict[str, str] = {}
    provenance: Provenance | None = None
```

- `api/v1/commentary.py` **零 diff**（仍是 `Commentary(**core_dict)` 薄壳）。
- 旧顶层字段（ts/data_as_of/composite_score/text/model）从契约移除——唯一消费者
  CommentaryCard 本里程碑同步重写，无兼容包袱。

---

## 5. stale 重接线

| 触发 | 动作 | 实现 |
|---|---|---|
| refresh 成功 | mark_stale + 异步重生成（沿用） | `mark_stale_and_regenerate()` = `mark_stale()` + `generate(blocking=False)`（refresh.py 调用点零 diff） |
| profile/template 变更（create/update/delete/set_active） | **仅 mark_stale**（不自动重生成） | 钩子放 `ai_config._save()`——四个变更点的唯一落盘口，一处挂钩全覆盖；M4c 模板保存走同一 `_save` 自动继承 |
| 手动 POST /commentary/regenerate | 同步生成（沿用） | 零 diff |

```python
# commentary.py
def mark_stale() -> None:
    """所有未 stale 行置 stale=1（数据/配置已变）。失败静默——评论非关键路径。"""

# ai_config.py
def _save(cfg: dict) -> None:
    ...原子写...
    try:
        from backend.app.core import commentary   # 延迟 import：ai_config ↔ commentary 循环防护
        commentary.mark_stale()                   # ponytail: 配置变更只标 stale，重生成由用户/refresh 触发
    except Exception:
        pass
```

- update 不做「patch 是否真的改了」的差分判断——无条件 mark_stale，误报无害（徽章提示，
  点重生成即刷新），省一套比较逻辑。
- 无评论行时 mark_stale = UPDATE 0 行，无害。

---

## 6. 前端 — CommentaryCard v2（Overview 总体卡）

`frontend/src/api/types.ts`（镜像 §4.3）：

```ts
export interface CommentaryProvenance {
  model: string | null; endpoint: string | null; template_hash: string | null
  data_as_of: Record<string, string> | null; profile: string | null; generated_at: string | null
}
export interface Commentary {
  status: 'ok' | 'generating' | 'empty' | 'error'
  msg: string | null
  hint: string | null
  stale: boolean
  overall: string
  sections: Record<string, string>     // M4b 卡片不渲染，M4c 细分页切片消费
  provenance: CommentaryProvenance | null
}
```

`CommentaryCard.vue` 改造（脚本逻辑基本沿用，模板重写）：

1. **总体文本**：ok 态渲染 `data.overall`（whitespace-pre-line，替换旧 `text`）。
2. **出处行**（ok 态 footer，各段 v-if 缺省不显示）：
   `{{ model }} · 生成于 {{ provenance.generated_at }} · 数据截至 {{ provenance.data_as_of?.derived_monthly }} · tpl {{ provenance.template_hash?.slice(0, 8) }} · {{ provenance.profile }}`
3. **stale 徽章**：头部 `text-amber-400` 「数据已更新」chip（沿用现配色与文案风格）。
4. **regenerate 按钮**：沿用现样式/禁用逻辑。
5. **生成中轮询沿用**：2s `startPolling`；**小修**：`regenerate()` catch 到超时错误
   （前端 30s abort 但后端仍在生成）→ 转入 `startPolling()` 而不是显示 error
   （现行为会误报失败）。
6. **无 profile CTA**：`data.status === 'empty' && data.hint` →
   `<RouterLink :to="data.hint">` 按钮样式「前往 AI 设置」。
7. 状态机四态（generating/empty/error/ok）结构沿用；`watch(refresh.lastRefreshedAt)` 沿用。

---

## 7. M4a minor 核实 — test_connection timeout

**读取结论：已修，无需代码改动。** `ai_client.test_connection` 在 M4a 提交 71ee527 中即为
`call_chat(..., timeout=25.0)`（严格小于前端 `request()` 30s abort），注释在案；
M4a 提交说明里「30s/60s 不一致记录在案」是过时表述。
M4b 只补一条回归测试钉住该值（§8 test_ai_client.py 新增），防止将来回退。

---

## 8. 测试计划

### 8.1 backend/tests/test_commentary.py（新）

fixture 基座（autouse）：`MACRO_AI_KEYCHAIN=off`、`monkeypatch.setattr(ai_config, "CONFIG_PATH",
tmp_path/…)`、清空三件 `COMMENTARY_*` env、`keychain._FALLBACK.clear()`、
`monkeypatch.setattr(commentary, "DB_PATH", tmp_path/"c.db")`（**绝不写真实库**）、
`commentary._table_ready = False` 复位。`call_chat` 一律 monkeypatch 桩（不起网络）。

1. **解析** `_extract_json`：纯 JSON / 前后散文包裹 / ```json 围栏 / 嵌套大括号取首个平衡块；
   非 JSON、只有 `[...]`、未闭合 → None。
2. **校验** `_validate_structured`：6 键 + overall 全过；空串 / 601 字 / 缺键 /
   sections 非 dict → problems 非空、对应键不入 parts。
3. **happy path**：桩返回合法结构化 JSON → generate → GET shape 完整：6 sections + overall、
   provenance 六字段齐（template_hash 64 hex、data_as_of 为 dict、generated_at == 行 ts）、
   DB 恰 7 行同 ts、stale=0。
4. **重试一次**：桩第一次返回散文、第二次合法 → 成功且 call_chat 恰 2 次；
   第 2 次 messages 含 assistant 原文 + 不合格反馈。
5. **降级逐板块**：桩结构化两次全乱 → 逐板块补调；call_chat 总次数 = 2 + 7；最终 ok。
6. **全败保留 last-good**：先成功生成一批；改桩恒返回乱码 → generate 返回 status=error；
   GET 仍回旧批次文本，行数不增。
7. **无 profile / 无 key**：generate 与 GET 均 status=empty 且 `hint == "/ai-settings"`。
8. **迁移幂等**：用老 8 列 DDL 建表 + 插 1 行 → `_ensure_table` 跑两遍 → PRAGMA 含全部新列、
   老行仍在；读回批次 sections={} 且 overall=旧文本、data_as_of 兜底 dict。
9. **stale on refresh**：`mark_stale()` 后批次 stale=1（`mark_stale_and_regenerate` 的
   generate 部分 monkeypatch 掉）。
10. **stale on config change**：有 stale=0 批次时，`ai_config.create / update / delete /
    set_active` 任一 → 批次 stale=1。
11. **端点 shape**：TestClient GET /commentary 的 empty / generating（`_busy.set()`）/ ok
    三态字段恰为 §4.3 契约；POST /commentary/regenerate 同步返回新批次。
12. **snapshot 形状**（真库，`pytest.mark.skipif(not 真实 macro_data.db 存在)`）：
    顶层键 = data_as_of + sections；每板块字段恰为 §1.3 所列；**无 list 值**（长序列禁入断言）；
    missing 为 list。

### 8.2 backend/tests/test_ai_client.py（改，+1）

- `test_connection` 的 timeout 钉住：monkeypatch spy 替换 `call_chat`，断言收到
  `timeout=25.0`（§7 回归防护）。

### 8.3 前端

- `cd frontend && npm run typecheck`（vue-tsc --noEmit）0 error。

---

## 9. 验收标准 + 文件清单 + changeLog 草稿

### 验收标准

1. **snapshot v2**：`build_section_snapshot()` 输出 §1.3 形状；6 板块全标量（无 list）；
   data_as_of 为 7 表日期 dict；缺失字段自动进各板块 missing；任一来源表空不抛、
   该板块降级为全 missing；浮点统一 round(2)。
2. **模板**：DEFAULT_TEMPLATES 含 system + 6 板块 + overall；get_templates 覆盖只接受
   已知键的非空字符串；template_hash = sha256(sort_keys JSON)，64 hex；
   ai_config.json `templates{}` 存储结构就位（load setdefault），M4b 无写入路径。
3. **生成**：resolve_active 为唯一配置入口；无 profile/key → status=empty + hint=/ai-settings；
   结构化输出经宽容解析（首个平衡 {...}）+ 校验（6 键全、非空、≤600 字）；
   不合格带错误反馈重试一次；仍不合格逐板块补调（保留已合格部分，最多 +7 次调用）；
   全败不写库、status=error、GET 仍回 last-good；单飞锁语义不变（并发第二次 → generating）。
4. **持久化**：老 8 列表经 PRAGMA+ALTER 补齐 4 新列，重复执行幂等、数据无损；
   一次生成恰写 7 行（同 ts、stale=0、section 恰 6 板块+overall）；
   phase_snapshot 存 snapshot v2 原文；GET 契约恰为 §4.3（含 legacy 单行兼容）。
5. **重接线**：refresh 成功 → mark_stale + 异步重生成（调用点零 diff）；
   ai_config create/update/delete/set_active 任一 → 现存批次 stale=1（不自动重生成）；
   手动 regenerate 同步语义不变。
6. **前端**：CommentaryCard v2 渲染 overall + 出处行（model · generated_at · data_as_of ·
   tpl hash 前 8 位 · profile）+ stale 徽章 + regenerate；生成中轮询沿用、
   regenerate 超时转轮询不误报；empty+hint 显示 /ai-settings CTA；vue-tsc 0 error。
7. **卫生**：`analysis/`、`api/v1/commentary.py`、`main.py`、`refresh.py`、`keychain.py`、
   `AISettings.vue`、`Overview.vue`、requirements.txt、package.json、tokens.css 零 diff；
   commentary.py 内旧 build_snapshot/call_model/SYSTEM_PROMPT/_latest_data_date/env 三件常量
   删除（孤儿清理）；backend pytest 全绿（72 + 新增）。

### 改动文件清单

**新增（2）**
- `docs/plans/M4b-design.md`（本文档）
- `backend/tests/test_commentary.py`

**修改（9）**
- `backend/app/core/commentary.py`（生成层主体：snapshot v2 + DEFAULT_TEMPLATES/get_templates/
  template_hash + 结构化生成/重试/降级 + 7 行批次持久化 + PRAGMA 迁移 + mark_stale 拆分；
  删旧 build_snapshot/call_model/SYSTEM_PROMPT/_latest_data_date/env 常量）
- `backend/app/core/ai_config.py`（load() setdefault templates{}；_save() 延迟 import
  commentary.mark_stale 钩子）
- `backend/app/schemas/commentary.py`（Commentary v2 + Provenance）
- `backend/tests/test_ai_client.py`（+test_connection timeout=25 回归）
- `frontend/src/api/types.ts`（Commentary v2 + CommentaryProvenance）
- `frontend/src/components/layout/CommentaryCard.vue`（v2 卡片）
- `shared/openapi.json`（重导）
- `changeLog.md`（[Unreleased] M4b 段）
- `README.md`（端点表 +2 行 GET /commentary、POST /commentary/regenerate）
- （一行）`scripts/signal_history.py` 注释更新（其引用的 `_latest_data_date` 被本次删除）

**明确不动**：`analysis/`、`api/v1/commentary.py`、`schemas/__init__.py`、`main.py`、
`refresh.py`、`keychain.py`、`ai_client.py`（仅测试加回归）、`AISettings.vue`、`Overview.vue`、
requirements.txt、package.json、tokens.css。

### changeLog 条目草稿（[Unreleased] 下新增 M4b 段）

```markdown
### M4b：AI 生成层 — 板块 snapshot v2 + 模板 + 结构化生成 + 出处持久化 + 总体卡 v2

### 新功能

1. **[新功能] snapshot v2（`backend/app/core/commentary.py`）**：build_section_snapshot()
   按板块只给标量——merrill（phase+GDP/CPI 同比最新与上期）、credit（phase+M2 同比与环比差+
   信贷脉冲）、inventory（phase+PMI+工业增加值同比）、debt（phase+三部门杠杆率与 4 季差分）、
   real_estate（综合分+三分量+数值细节）、fiscal_external（财政收支累计同比+出口同比+ISM）；
   data_as_of 为 7 张来源表最新日期 dict；缺失字段自动记入各板块 missing；长序列禁入 payload
2. **[新功能] 模板体系**：DEFAULT_TEMPLATES（system 宏观分析师角色/只引用提供数字/不给投资
   建议/中文；每板块必答现状/边际/矛盾 3-5 句；overall 6-8 句跨板块综合）；
   ai_config.json templates{} 覆盖存储结构（编辑器 M4c）；template_hash=sha256(全模板)
3. **[新功能] 结构化生成**：generate() 单飞沿用 → resolve_active + key_for 取配置
   （无 profile/key → status=empty + hint=/ai-settings）→ 单次 call_chat 要求输出
   {sections:{…6 板块}, overall} JSON → 宽容解析（首个平衡 {...}）→ 校验（6 键全、
   非空、≤600 字）→ 不合格带错误反馈重试一次 → 仍败逐板块补调（保留已合格部分）→
   全败保留 last-good 并 status=error
4. **[新功能] 出处持久化**：commentary 表 PRAGMA 检测 + ALTER 加 4 列
   （section/endpoint/template_hash/profile；generated_at 复用既有 ts 列），迁移幂等；
   一次生成写 7 行（6 板块+overall，同 ts 为批次键）；GET /commentary 返回
   {overall, sections, provenance(model/endpoint/template_hash/data_as_of/profile/
   generated_at), status, stale, hint}；stale 重接线：refresh 沿用，ai_config 变更
   （create/update/delete/set_active）经 _save 钩子 mark_stale（不自动重生成）
5. **[新功能] CommentaryCard v2**：总体文本 + 出处行（model · generated_at · 数据截至 ·
   tpl hash 前 8 位 · profile）+ stale 徽章 + regenerate；生成中轮询沿用、
   regenerate 前端超时转轮询不误报；empty+hint 时 CTA 链接 /ai-settings

### 修复 / 其他

1. **[核实] test_connection 后端 timeout**：确认 M4a 已落地 25s（< 前端 30s abort），
   补回归测试钉住，无代码改动

### 验证

- ✅ backend pytest 全绿：test_commentary（解析/校验/重试/降级/全败保 last-good/出处字段/
  迁移幂等/stale on refresh & on config change/端点 shape/snapshot 形状）+
  test_ai_client timeout 回归
- ✅ commentary.py 旧路径（build_snapshot/call_model/env 三件）删除，孤儿清零；
  analysis/、api/v1/commentary.py、main.py、refresh.py 零 diff
- ✅ vue-tsc --noEmit 0 error；requirements.txt/package.json/tokens.css 零变化

### M4b: AI Generation Layer — Section Snapshot v2 + Templates + Structured Generation + Provenance + Overview Card v2 (English)

### New Features

1. **[feat] snapshot v2 (`backend/app/core/commentary.py`)**: build_section_snapshot()
   feeds the model per-section scalars only — merrill (phase + GDP/CPI yoy latest &
   previous), credit (phase + M2 yoy & MoM delta + credit impulse), inventory (phase +
   PMI + IP yoy), debt (phase + three-sector leverage & 4-quarter diffs), real_estate
   (composite + three components + underlying figures), fiscal_external (fiscal
   revenue/expenditure cumulative yoy + exports yoy + ISM); data_as_of is a dict of the
   latest date per source table; missing fields recorded per section; long series never
   enter the payload
2. **[feat] template system**: DEFAULT_TEMPLATES (system: macro-analyst role, cite only
   provided numbers, no investment advice, Chinese; each section must answer
   current/marginal/contradiction in 3-5 sentences; overall 6-8 sentences cross-section);
   ai_config.json templates{} override storage (editor lands in M4c);
   template_hash = sha256(all templates)
3. **[feat] structured generation**: generate() keeps the single-flight lock →
   resolve_active + key_for for config (no profile/key → status=empty + hint=/ai-settings)
   → one call_chat demanding {sections:{…6}, overall} JSON → lenient parse (first balanced
   {...}) → validation (all 6 keys, non-empty, ≤600 chars) → one retry with error feedback
   → per-section fallback calls (keeping already-valid parts) → total failure keeps the
   last-good batch with status=error
4. **[feat] provenance persistence**: commentary table gains 4 columns via PRAGMA +
   ALTER (section/endpoint/template_hash/profile; generated_at reuses the existing ts
   column), migration idempotent; one generation writes 7 rows (6 sections + overall,
   shared ts as batch key); GET /commentary returns {overall, sections, provenance,
   status, stale, hint}; stale re-wiring: refresh path unchanged, ai_config mutations
   (create/update/delete/set_active) mark stale through the _save hook (no auto-regen)
5. **[feat] CommentaryCard v2**: overall text + provenance line (model · generated_at ·
   data as-of · tpl hash first 8 · profile) + stale badge + regenerate; polling kept,
   regenerate front-end timeout now falls back to polling instead of a false error;
   empty+hint shows a CTA link to /ai-settings

### Verification

- ✅ backend pytest green: test_commentary (parse/validate/retry/fallback/total-failure
  keeps last-good/provenance fields/migration idempotence/stale on refresh & config
  change/endpoint shapes/snapshot shape) + test_ai_client timeout regression
- ✅ legacy commentary path removed (build_snapshot/call_model/env trio), zero orphans;
  analysis/, api/v1/commentary.py, main.py, refresh.py zero diff
- ✅ vue-tsc --noEmit 0 errors; requirements.txt/package.json/tokens.css unchanged
```
