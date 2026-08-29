# M4c 设计文档 — 呈现层：细分页板块切片 + 模板编辑器 + 生成历史

> 分支：worktree-ai-commentary-m4 ｜ 日期：2026-08-16
> 范围纪律：M4c 只做呈现层——①6 细分页板块切片（共享组件）②AISettings 模板编辑器
> ③AISettings 生成历史 UI。**不做**：生成链路逻辑 / 适配器 / keychain 的改动
> （除呈现所必需的最小接缝：历史只读函数、轮转 prune、模板写入函数）。
> 约束：零新依赖；`GET /commentary` shape 零变化；复用 M4b 基线
> （`_persist_batch` 追加写 / `_save` stale 钩子 / `ai_config.templates{}` 存储结构）。

---

## 0. 现状要点（读取结论，约束设计的既有事实）

- `backend/app/core/commentary.py`：`_persist_batch` **已是追加式** INSERT（一次 7 行同 ts，
  老批次原样留存，`_latest_batch` 取 `MAX(ts)`）——任务预设的「覆盖式写 7 行」**不成立**，
  M4c 不改写入路径，只在 insert 后加轮转 prune。`_ts()` 毫秒精度兼作批次键。
  `mark_stale()` / `get_current()` / `_batch_to_dict()` 可原样复用于历史详情。
- `backend/app/core/ai_config.py`：`load()` 已 `setdefault("templates", {})`（M4b 落存储结构，
  **写入路径仍缺**——M4c 补 `set_templates()`）；`_save()` 已挂 `commentary.mark_stale()`
  钩子 → 模板保存经 `_save` **免费继承** stale 触发，零新钩子。
- `backend/app/api/v1/commentary.py`：纯薄壳（`Commentary(**core_dict)`），router 前缀
  `/commentary`；`api/v1/ai.py` 前缀 `/ai`，profiles CRUD 已就位。
- commentary 表 12 列（M4b 迁移后）；`data/macro_data.db` 实测 0 行，无历史包袱。
- 前端：6 细分页结构一致（header → phase chip → N 个 GraphCard），`watchEffect` 依赖
  `filters/refresh` 重载；`CommentaryCard.vue` 仅 Overview 使用，四态
  （generating/empty/error/ok）+ stale 徽章 + provenance 行样式为基线模板。
  **无 `src/composables/` 目录**（M4c 新建，单文件）；AISettings.vue 为局部 ref 无 store
  （页面内注释明示 YAGNI）。
- `package.json` 脚本仅 `typecheck`（vue-tsc）与 `gen:api`，**无 vitest** → 前端单测跳过，
  请求去重靠结构保证（§2.1 单飞 Promise）。
- 文档惯例：`shared/openapi.json` 重导 + README 端点表 + CHANGELOG `[Unreleased]` 段同步。

---

## 1. 历史留存 — 追加已就位，只补轮转 + history 端点

### 1.1 轮转 `_prune`（commentary.py）

保留最近 **N=10 个 generated_at（=ts）批次**，更旧批次整体删除（7 行一批）。
在 `_persist_batch` 的 insert 之后、同一事务 commit 之前调用（原子，无中间态）：

```python
KEEP_BATCHES = 10

def _prune(conn: sqlite3.Connection) -> None:
    """保留最近 KEEP_BATCHES 个 ts 批次，更旧批次整体删除。"""
    old = conn.execute(
        f"SELECT DISTINCT ts FROM {COMMENTARY_TABLE} "
        f"ORDER BY ts DESC LIMIT -1 OFFSET {KEEP_BATCHES}").fetchall()
    if old:
        conn.executemany(f"DELETE FROM {COMMENTARY_TABLE} WHERE ts = ?",
                         [(r[0],) for r in old])
```

- `_persist_batch` 只加一行 ` _prune(conn)`——生成链路逻辑零改动。
- legacy 单行各占一个 ts → 算一个批次，同样参与轮转（自然淘汰，无需特判）。
- ts 字符串 = ISO8601 毫秒，字典序 == 时间序，`ORDER BY ts` 安全。
- 测试注意：毫秒精度下快速连续 generate 可能同毫秒并批 → 测试 monkeypatch
  `commentary._ts` 注入递增序列（§5）。

### 1.2 GET /commentary/history — 索引 + 单批详情共用一端点

| 调用 | 返回 |
|---|---|
| `GET /commentary/history` | `{"items": [BatchItem…]}` 按 ts **倒序** |
| `GET /commentary/history?ts=<ts>` | 该批完整 `Commentary` shape（6 sections + overall + provenance）；不存在 → **404** |

核心层两个**只读**新函数（commentary.py）：

```python
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
```

- `status` 恒 `"ok"`：生成全败不写库，落库批次必然完整——字段保留只为与
  `Commentary` 契约对齐，不做差分逻辑。
- 路由（api/v1/commentary.py，+1 函数；响应两形，不套 response_model）：

```python
@router.get("/history")
def history(ts: str | None = None):
    if ts is None:
        return {"items": commentary.history_index()}
    batch = commentary.get_batch(ts)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"批次不存在：{ts}")
    return Commentary(**batch)
```

- `GET /commentary` 与 `POST /commentary/regenerate` **零 diff**（当前批次语义不变）。

### 1.3 schemas

`backend/app/schemas/commentary.py`（+索引模型；Commentary 不动）：

```python
class BatchItem(BaseModel):
    generated_at: str
    model: str | None = None
    profile: str | None = None
    template_hash: str | None = None
    status: str = "ok"
    stale: bool = False
    overall_preview: str = ""

class HistoryIndex(BaseModel):
    items: list[BatchItem] = []
```

---

## 2. 细分页板块切片 — SectionCommentary.vue + useCommentary composable

### 2.1 composable — `frontend/src/composables/useCommentary.ts`（新目录，单文件）

目标：**一次 GET /commentary，多卡共享同响应**——单飞 Promise 去重并发、
refresh tick 去重跨页导航、generating 时轮询、失败保 last-good。
模块级共享态（不进 pinia：单一消费者族、无跨组件写入，YAGNI 同 AISettings 注释先例）：

```ts
const data = ref<Commentary>(EMPTY)      // 模块级：任意细分页共享同一响应
let inflight: Promise<void> | null = null
let loadedTick = -1                      // 绑定 refresh.lastRefreshedAt
let subs = 0                             // 挂载中的消费者数 → 轮询启停
let pollTimer: ReturnType<typeof setInterval> | null = null

export function useCommentary() {
  const refresh = useRefreshStore()

  async function load() {
    if (inflight) return inflight                       // 并发去重：共享同一请求
    const tick = refresh.lastRefreshedAt
    if (loadedTick === tick && data.value.status !== 'generating') return  // 跨页复用
    inflight = (async () => {
      try { data.value = await api.getCommentary() }
      catch (e) {
        // error last-good：有文本 → 保留内容只记 msg；无文本 → 转 error 态
        const hasText = !!data.value.overall || Object.keys(data.value.sections).length > 0
        data.value = hasText
          ? { ...data.value, msg: (e as Error).message }
          : { ...data.value, status: 'error', msg: (e as Error).message }
      }
      loadedTick = tick
      inflight = null
      armPoll()
    })()
    return inflight
  }

  function armPoll() {                                  // generating → 2s 轮询（同 CommentaryCard 节奏）
    if (data.value.status === 'generating' && subs > 0 && !pollTimer) {
      pollTimer = setInterval(() => void load(), 2000)
    }
    if (data.value.status !== 'generating' && pollTimer) {
      clearInterval(pollTimer); pollTimer = null
    }
  }
  function enter() { subs++; void load() }              // onMounted
  function leave() { subs--; if (subs <= 0) armPoll() } // onUnmounted：归零停轮询
  return { data, enter, leave }
}
```

要点：
- `loadedTick` 只挡「同 tick 且非 generating」的重取；数据刷新（tick 变化）或
  generating 中均放行。
- 轮询由 `subs` 引用计数启停——最后一个消费者卸载即停，无后台残留。
- 与 `stores/refresh.ts` 的交互仅读 `lastRefreshedAt`，不改 store。

### 2.2 组件 — `frontend/src/components/layout/SectionCommentary.vue`

`props = { section: string }`（6 板块键之一）。样式令牌 / 卡片外观 / 徽章配色
照抄 `CommentaryCard.vue`（bg-card border-border rounded-xl p-4；amber stale chip）。

**四态**（对齐 CommentaryCard）：

| 状态 | 渲染 |
|---|---|
| `empty` 无 hint | **不渲染**（`v-if` 整体隐藏，页面零占位） |
| `empty` 有 hint | 极小提示一行 + RouterLink「前往 AI 设置」（=hint） |
| `generating` | `animate-pulse` 一行 msg（「评论生成中…」） |
| `ok` 且 `sections[section]` 有值 | 板块文本（whitespace-pre-line leading-relaxed）+ provenance 简行（model · 生成于 · tpl hash 前 8 位）；`stale` → 头部「数据已更新」amber 徽章 |
| `ok` 但该板块无文本（legacy 批次 sections={}） | 不渲染 |
| `error`（fetch 失败且无 last-good） | 一行 red-400 msg；有 last-good → 保留文本 + msg 附注 |

**a11y**：外层 `<section role="region" :aria-label="'AI 评论 — ' + LABELS[section]">`；
状态容器 `role="status" aria-live="polite"`（同 CommentaryCard，通告
generating→ok 切换）。

组件内常量：

```ts
const LABELS: Record<string, string> = {
  merrill: '美林时钟', credit: '信用周期', inventory: '库存周期',
  debt: '债务周期', real_estate: '房地产', fiscal_external: '财政与外需',
}
```

### 2.3 六个细分页接线 — 统一位置：各页**首屏卡片（第一个 GraphCard）之后**

| 页面 | section 键 | 插入位置（既有卡片之后） |
|---|---|---|
| MerrillClock.vue | `merrill` | 「美林投资时钟」散点卡后 |
| CreditCycle.vue | `credit` | 「M2 同比与趋势」卡后 |
| InventoryCycle.vue | `inventory` | 「PMI vs 工业增加值同比」卡后 |
| DebtCycle.vue | `debt` | 「分部门宏观杠杆率（堆叠）」卡后 |
| RealEstate.vue | `real_estate` | 「新建商品住宅价格指数同比（多城市）」卡后 |
| FiscalExternal.vue | `fiscal_external` | 「财政收支累计同比」卡后 |

每页 diff = 1 行 import + 1 行标签 `<SectionCommentary section="…" />`；
脚本数据流（watchEffect/load）零触碰。

---

## 3. 模板编辑器 — AISettings 新 section

### 3.1 后端接缝（呈现所需最小面）

**core：`ai_config.set_templates()`（唯一新函数）**——整 map 替换写入，
经既有 `_save()` 落盘 → stale 钩子自动触发，零新钩子：

```python
def set_templates(overrides: dict) -> tuple[dict, str]:
    """整 map 替换 templates{}：空串/纯空白 = 移除该覆盖；未知键/非字符串 → ValueError。
    返回 (规范化后的 overrides, 新 template_hash)。"""
    from backend.app.core import commentary   # 延迟 import：循环防护（_save 同式）
    known = set(commentary.DEFAULT_TEMPLATES)
    clean = {}
    for k, v in overrides.items():
        if k not in known:
            raise ValueError(f"未知模板键：{k}")
        if not isinstance(v, str):
            raise ValueError(f"模板值须为字符串：{k}")
        if v.strip():
            clean[k] = v
    with _lock:
        cfg = load()
        cfg["templates"] = clean
        _save(cfg)                             # 钩子自动 mark_stale
    return clean, commentary.template_hash()
```

**路由：`api/v1/ai.py` +2**（模板属 AI 配置域，归 `/ai` 前缀）：

```python
@router.get("/templates", response_model=TemplatesOut)
def get_templates():
    from backend.app.core import commentary   # 延迟 import
    overrides = {k: v for k, v in (ai_config.load().get("templates") or {}).items()
                 if k in commentary.DEFAULT_TEMPLATES and isinstance(v, str) and v.strip()}
    return TemplatesOut(defaults=dict(commentary.DEFAULT_TEMPLATES),
                        overrides=overrides,
                        template_hash=commentary.template_hash())

@router.put("/templates", response_model=TemplatesSaved)
def save_templates(body: TemplatesUpdate):
    try:
        overrides, thash = ai_config.set_templates(body.templates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TemplatesSaved(overrides=overrides, template_hash=thash)
```

**schemas：`schemas/ai.py` +3 模型**：

```python
class TemplatesOut(BaseModel):
    defaults: dict[str, str]          # 8 键全文 → 编辑器 placeholder
    overrides: dict[str, str]         # 当前覆盖（已规范化）
    template_hash: str

class TemplatesUpdate(BaseModel):
    templates: dict[str, str]         # 8 键全量提交；值 = 覆盖文本或空串（=重置）

class TemplatesSaved(BaseModel):
    overrides: dict[str, str]
    template_hash: str
```

链路闭环：保存 → `cfg["templates"]` 变 → `template_hash()` 变（下次生成批次带新 hash）
→ `_save` 钩子已 `mark_stale()` → 前端现有 stale 徽章生效。无任何新触发逻辑。

### 3.2 前端 — AISettings.vue 新增「模板」卡（profiles 卡之后、dialog 之前）

- 加载：`onMounted` 与 profiles 并行 `api.getAiTemplates()` → `tplDefaults / tplDraft / tplHash`。
  `tplDraft[k] = overrides[k] ?? ''`——**空串态 placeholder 即默认模板全文**，
  输入框留空 = 使用默认，所见即所得。
- 8 项固定顺序 + 标签：`system` 系统提示 → 6 板块（§2.2 LABELS）→ `overall` 总体研判。
- 每项：标签行（名称 + 覆盖中标记 `已覆盖`，当 draft 非空）+「重置默认」按钮
  （`tplDraft[k] = ''`，本地操作，保存后生效）+ `<textarea v-model="tplDraft[k]"
  :placeholder="tplDefaults[k]" rows="3" :class="inputCls">`。
- 底栏：`当前 tpl {{ tplHash.slice(0, 8) }}` + 「保存全部」按钮
  （`:disabled="!tplDirty || saving"`；`tplDirty = computed(() =>
  JSON.stringify(tplDraft) !== JSON.stringify(tplInitial))` —— 无改动不保存，
  避免误触 `_save` 造成假 stale）+ 保存结果行（成功：「已保存——评论已标记过期，
  重新生成后生效」+ 刷新 hash；失败：pageError 同款 red 文案）。
- 提交：`api.saveAiTemplates(tplDraft)` → 用响应 `overrides/template_hash`
  重置 `tplInitial/tplHash`（服务端规范化为准，如纯空白被移除）。

---

## 4. 生成历史 UI — AISettings 新增「生成历史」卡（模板卡之后）

- 加载：`onMounted` 与上两者并行 `api.getCommentaryHistory()` → `batches`。
- 行 = **原生 `<details>/<summary>`**（键盘 / aria 免费，零组件依赖）：
  summary 行：`{{ generated_at }} · {{ model }} · {{ profile }} · tpl {{ hash 前 8 位 }} · ok`
  （+ stale 时 amber「已过期」chip）。
- **懒加载**：`@toggle` 首次展开且未缓存 → `api.getCommentaryHistory(item.generated_at)`
  → 存 `details[ts] = Commentary`（按 ts 缓存，重复展开不再请求）；展开内容 =
  overall + 6 板块（§2.2 LABELS 小标题 + whitespace-pre-line），加载中「加载中…」，
  失败一行 red 文案。
- 空列表 → 「暂无生成记录」。无分页（N=10 上限，§1.1）、无手动刷新按钮（进页面即拉）。

---

## 5. 测试计划

### 5.1 backend/tests/test_commentary.py（+3，沿用既有 `_isolate` fixture）

1. **轮转**：monkeypatch `commentary._ts` 为递增序列（`f"2026-01-01T00:00:{i:03f}"`
   式确定性 ts，避开毫秒并批）；桩 chat 恒返回合法 JSON；循环 `generate(blocking=True)`
   **12 次** → 表中 DISTINCT ts **恰 10**（70 行），最早 2 批的所有行被删；
   `get_current()` 返回第 12 批。
2. **history 索引 shape 与倒序**：生成 3 批（其间改 profile model 制造字段差异可选）→
   `GET /api/v1/commentary/history` → `items` 长 3、`generated_at` 严格递减；
   每项字段集恰为 `{generated_at, model, profile, template_hash, status, stale,
   overall_preview}`；overall > 80 字时 preview 以「…」结尾。
3. **单批详情**：取索引中间项 ts → `GET /history?ts=…` 返回 status=ok、
   sections 6 键、`provenance.generated_at == ts`；`?ts=不存在` → 404。

### 5.2 backend/tests/test_ai_profiles_api.py（+4，沿用既有 `_isolate` fixture）

4. **GET /ai/templates**：无覆盖时 `overrides == {}` 且 `defaults` 恰 8 键、
   `template_hash == commentary.template_hash()`（64 hex）。
5. **保存 → hash 变 → stale**：先生成一批（stale=False，桩 chat）→
   `PUT /ai/templates {"templates": {"merrill": "改写版"}}` → 200；
   新 hash ≠ 旧 hash；`GET /commentary` 的 `stale == true`；
   落盘 `ai_config.json` 的 `templates.merrill == "改写版"`。
6. **重置默认移除覆盖**：接 5，`PUT {"templates": {"merrill": ""}}` →
   `overrides == {}` 且 hash 回到默认 hash。
7. **未知键 400**：`PUT {"templates": {"bogus": "x"}}` → 400。

### 5.3 前端

- `cd frontend && npm run typecheck`（vue-tsc --noEmit）0 error。
- 组件请求去重断言：**跳过**——仓库无 vitest（package.json 仅 typecheck/gen:api）；
  去重由 useCommentary 单飞 Promise + tick 结构保证，网络面板人工可验。
  （引入 vitest 的决定留待前端逻辑进一步增长时统一做。）

---

## 6. 验收标准 + 文件清单 + changeLog 草稿

### 验收标准

1. **轮转**：连续 12 次生成 → commentary 表恰留最近 10 个批次（70 行），
   最旧 2 批整批删除；`GET /commentary` shape 与「当前批次」语义零变化。
2. **history 端点**：`GET /commentary/history` 倒序索引，每项含
   `{generated_at, model, profile, template_hash, status, stale, overall_preview}`；
   `?ts=` 返回该批完整 sections + overall + provenance；未知 ts → 404。
3. **共享组件**：6 细分页经 useCommentary 共享一次 GET /commentary
   （单飞 + refresh tick 去重；generating 2s 轮询、订阅归零即停）。
4. **四态**：empty 无 hint 不渲染 / 有 hint 极小 CTA；generating 脉冲提示；
   stale「数据已更新」徽章；fetch 失败保 last-good 文本。
   a11y：`role="region" + aria-label`、状态容器 `aria-live="polite"`。
   六页统一插在各页第一个 GraphCard 之后。
5. **模板编辑器**：列出 system + 6 板块 + overall 共 8 项；textarea
   placeholder = 默认全文、值 = 当前覆盖或空；单项「重置默认」；「保存全部」
   整 map PUT 且 dirty 才可点；空串 = 移除覆盖 → template_hash 变化 →
   既有批次 stale=1（走既有 `_save` 钩子）；页面显示当前 hash 前 8 位。
6. **生成历史 UI**：批次列表（时间/model/profile/hash 前 8/status/stale chip）；
   原生 `<details>` 展开懒加载单批 overall + 6 板块文本（按 ts 缓存）。
7. **测试**：backend pytest 全绿（轮转 / 索引 shape 倒序 / 详情 404 /
   保存→hash 变→stale / 重置移除覆盖 / 未知键 400）；vue-tsc 0 error。
8. **卫生**：生成链路（`_generate_impl` / 校验 / 重试 / 降级）、`ai_client.py`、
   `keychain.py`、`refresh.py`、`main.py`、`analysis/`、`Overview.vue`、
   `CommentaryCard.vue`、requirements.txt、package.json、tokens.css 零 diff；
   `shared/openapi.json` 重导、README 端点表 +3 行、CHANGELOG 同步。

### 改动文件清单

**新增（3）**
- `docs/plans/M4c-design.md`（本文档）
- `frontend/src/composables/useCommentary.ts`
- `frontend/src/components/layout/SectionCommentary.vue`

**修改（15）**
- `backend/app/core/commentary.py`（`KEEP_BATCHES` + `_prune` + `_persist_batch`
  一行调用；只读 `history_index()` / `get_batch()`）
- `backend/app/api/v1/commentary.py`（+`GET /history` 路由，双形响应）
- `backend/app/schemas/commentary.py`（+`BatchItem` / `HistoryIndex`）
- `backend/app/core/ai_config.py`（+`set_templates()`）
- `backend/app/api/v1/ai.py`（+`GET/PUT /ai/templates`）
- `backend/app/schemas/ai.py`（+`TemplatesOut` / `TemplatesUpdate` / `TemplatesSaved`）
- `backend/tests/test_commentary.py`（+轮转 / history 索引 / 单批详情 3 组）
- `backend/tests/test_ai_profiles_api.py`（+模板 GET / 保存→stale / 重置 / 400 4 组）
- `frontend/src/api/types.ts`（+`TemplatesOut` / `TemplatesSaved` /
  `HistoryItem` / `HistoryIndex`）
- `frontend/src/api/client.ts`（+`getAiTemplates` / `saveAiTemplates` /
  `getCommentaryHistory(ts?)`）
- `frontend/src/pages/AISettings.vue`（+模板卡 + 生成历史卡）
- 6 细分页：`MerrillClock.vue` / `CreditCycle.vue` / `InventoryCycle.vue` /
  `DebtCycle.vue` / `RealEstate.vue` / `FiscalExternal.vue`
  （各 +1 import +1 `<SectionCommentary>` 标签）
- `shared/openapi.json`（重导）
- `README.md`（端点表 +3 行：GET /commentary/history、GET/PUT /ai/templates）
- `CHANGELOG.md`（[Unreleased] M4c 段）

**明确不动**：`_generate_impl` / `_call_structured_with_fallback` /
`_validate_structured` / `_extract_json` 等生成链路全部函数、`ai_client.py`、
`keychain.py`、`refresh.py`、`main.py`、`analysis/`、`Overview.vue`、
`CommentaryCard.vue`、`stores/`、requirements.txt、package.json、tokens.css。

### changeLog 条目草稿（[Unreleased] 下新增 M4c 段）

```markdown
### M4c：AI 呈现层 — 细分页板块切片 + 模板编辑器 + 生成历史

### 新功能

1. **[新功能] 历史留存与轮转（`backend/app/core/commentary.py`）**：批次追加写沿用
   （M4b 即 INSERT 非覆盖），_persist_batch 同事务内 _prune 轮转——保留最近 10 个
   generated_at 批次（KEEP_BATCHES=10），更旧批次整批删除；GET /commentary 的
   当前批次 shape 与语义零变化
2. **[新功能] 历史端点（`backend/app/api/v1/commentary.py`）**：
   GET /commentary/history 返回批次索引（ts 倒序，每项 generated_at/model/profile/
   template_hash/status/stale/overall_preview=overall 前 80 字）；
   GET /commentary/history?ts=… 返回该批完整 sections+overall+provenance
   （复用 _batch_to_dict），未知 ts → 404
3. **[新功能] 细分页板块切片（`frontend/src/components/layout/SectionCommentary.vue`
   + `frontend/src/composables/useCommentary.ts`）**：6 细分页统一在首屏卡片后渲染
   本板块 AI 评论；composable 模块级共享一次 GET /commentary——单飞 Promise 并发去重、
   refresh tick 跨页去重、generating 2s 轮询（订阅计数启停）；四态对齐 CommentaryCard
   （empty 无 hint 不渲染/有 hint 极小 CTA、generating 脉冲、stale「数据已更新」徽章、
   fetch 失败保 last-good）；role=region + aria-label、状态容器 aria-live
4. **[新功能] 模板编辑器（AISettings 新 section）**：列出 system+6 板块+overall 共 8 个
   模板；textarea placeholder=默认全文、值=当前覆盖或空（空=用默认）；单项「重置默认」；
   「保存全部」整 map PUT /ai/templates（空串=移除覆盖、未知键 400），经既有 _save 钩子
   mark_stale → template_hash 变化即时显示（前 8 位）；dirty 校验防误触假 stale
5. **[新功能] 生成历史 UI（AISettings 新 section）**：批次列表（时间/model/profile/
   tpl hash 前 8/status + stale chip）；原生 <details> 展开按 ts 懒加载单批
   overall+6 板块文本（缓存不重拉）

### 验证

- ✅ backend pytest 全绿：轮转（12 批留 10）/ history 索引 shape 与倒序 / 单批详情与 404 /
  模板保存→hash 变→stale / 重置默认移除覆盖 / 未知键 400
- ✅ 生成链路（_generate_impl/校验/重试/降级）、ai_client、keychain、refresh、main、
  analysis/ 零 diff；GET /commentary 契约零变化
- ✅ vue-tsc --noEmit 0 error；shared/openapi.json 重导、README 端点表同步

### M4c: AI Presentation Layer — Section Slices on Detail Pages + Template Editor + Generation History (English)

### New Features

1. **[feat] history retention & rotation (`backend/app/core/commentary.py`)**: batch
   writes stay append-only (M4b already INSERT, never overwrite); _persist_batch now
   prunes in the same transaction — keeps the latest 10 generated_at batches
   (KEEP_BATCHES=10), deletes older batches wholesale; GET /commentary shape and
   current-batch semantics unchanged
2. **[feat] history endpoints (`backend/app/api/v1/commentary.py`)**:
   GET /commentary/history returns the batch index (ts descending; each item
   generated_at/model/profile/template_hash/status/stale/overall_preview = first 80
   chars of overall); GET /commentary/history?ts=… returns that batch's full
   sections+overall+provenance (reuses _batch_to_dict); unknown ts → 404
3. **[feat] section slices on detail pages
   (`frontend/src/components/layout/SectionCommentary.vue` +
   `frontend/src/composables/useCommentary.ts`)**: the six detail pages render their
   section's AI commentary after the first-screen chart card; the composable shares ONE
   GET /commentary across cards — single-flight promise dedupe, refresh-tick reuse across
   navigation, 2s polling while generating (subscriber-counted start/stop); four states
   match CommentaryCard (empty renders nothing / minimal CTA with hint, generating
   pulse, stale "数据已更新" badge, fetch failure keeps last-good); role=region +
   aria-label, aria-live status container
4. **[feat] template editor (new AISettings section)**: lists all 8 templates
   (system + 6 sections + overall); textarea placeholder = full default text, value =
   current override or empty (empty = use default); per-item "reset to default";
   "save all" PUTs the whole map to /ai/templates (empty string removes the override,
   unknown key → 400), stale marking inherited from the existing _save hook →
   template_hash change shown immediately (first 8 chars); dirty check prevents
   no-op saves that would false-flag stale
5. **[feat] generation history UI (new AISettings section)**: batch list
   (time/model/profile/tpl hash first 8/status + stale chip); native <details> rows
   lazy-load a batch's overall + six section texts on first expand (cached per ts)

### Verification

- ✅ backend pytest green: rotation (12 batches → keep 10) / history index shape &
  descending order / single-batch detail & 404 / template save → hash change → stale /
  reset-to-default removes override / unknown key 400
- ✅ generation pipeline (_generate_impl/validation/retry/fallback), ai_client,
  keychain, refresh, main, analysis/ zero diff; GET /commentary contract unchanged
- ✅ vue-tsc --noEmit 0 errors; shared/openapi.json regenerated, README endpoint
  table updated
```
