# 架构升级方案：Dash+Plotly → FastAPI + Vue 3 + ECharts

> 目标：在**保留全部 Python 分析投资**（`analysis/`、采集管道、刷新逻辑零改动）的前提下，把前端从 Dash+Plotly 升级为 **Vue 3 + ECharts**，解锁 Dash 摸不到的「极致效果 + 极致功能」天花板。
> 约束：成本不是首要考量；`analysis/` 是核心价值，一行不改；迁移**增量、可回退**（新旧并行到 parity 再切换）。

---

## 0. 设计原则

1. **核心保值**：`analysis/*.py`、`scripts/_pipeline.py`、`scripts/01_fetch_data.py`、刷新逻辑——全部原样成为 FastAPI 的领域层，不重写。
2. **强类型单一真相源**：Pydantic schema 定义契约 → OpenAPI → 自动生成前端 TS 类型（`openapi-typescript`），**消除前后端类型漂移**（CI 守门）。
3. **设计系统迁移而非重做**：`dashboard/config.py` 的 Terminal Fintech 色板（`C` dict）、`CHART_LAYOUT`、`app.py` 的全局暗色 CSS → 迁到 Vue 的 `tokens.css` + ECharts 主题，**视觉延续**。
4. **增量可回退**：FastAPI（:8000）+ Vue（:5173）与旧 Dash（:8050）**并行运行**，逐页迁移；parity 达成后再下线 Dash。
5. **「极致」可验证**：每个里程碑有可验证的退出标准，旗舰页（信用周期）在 P1 先做，**未达极致则止损**。

---

## 1. 目标架构

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + TS + Vite, :5173)                          │
│  pages/ (6 个视图) ←→ router ←→ Pinia stores                  │
│  components/charts/ (EChart 包装)  design/ (tokens + theme)    │
│  api/ (OpenAPI 生成的 TS client)                              │
└──────────────────────────────────────────────────────────────┘
                       │ HTTPS / SSE  (/api/v1/*)
┌──────────────────────────────────────────────────────────────┐
│  Backend (FastAPI + Pydantic, :8000)                          │
│  api/v1/ (cycles, real_estate, signals, data, refresh)        │
│  schemas/ (Pydantic = 契约真相源)   core/ (cache, pipeline)   │
└──────────────────────────────────────────────────────────────┘
                       │ 同进程直接 import（无序列化边界）
┌──────────────────────────────────────────────────────────────┐
│  Domain Core（零改动保值）                                     │
│  analysis/ (cycle_merrill/credit/inventory/debt, signals,     │
│             real_estate, cross_indicator)                      │
│  scripts/_pipeline.py + 01_fetch_data.py (闸门管道)           │
│  dashboard/db.py → 抽到 backend/app/core/db.py                │
└──────────────────────────────────────────────────────────────┘
                       │
                data/macro_data.db (SQLite, 共享)
```

**关键**：FastAPI 与 `analysis/` 仍同进程，**计算→渲染边界从「进程内」变成「HTTP」，但分析逻辑零改动**——只加一层薄 API + schema。

---

## 2. 目录结构（新增 + 保留并存）

```
AKShare/
├── analysis/                  # 【不变】核心分析引擎
├── scripts/                   # 【不变】_pipeline.py / 01_fetch / 02_compute（后端复用）
├── data/                      # 【不变】macro_data.db（前后端共享）
│
├── backend/                   # 【新】FastAPI
│   ├── app/
│   │   ├── main.py            # FastAPI 实例 + CORS + 路由挂载 + 静态（OpenAPI 导出）
│   │   ├── api/v1/
│   │   │   ├── cycles.py      # /merrill /credit /inventory /debt
│   │   │   ├── real_estate.py
│   │   │   ├── signals.py      # 综合信号
│   │   │   ├── data.py         # /derived/monthly /derived/quarterly（切片）
│   │   │   └── refresh.py      # POST /refresh + GET /refresh/stream（SSE 进度）
│   │   ├── schemas/            # 【契约真相源】Pydantic v2 模型
│   │   │   ├── cycles.py signals.py refresh.py common.py
│   │   ├── core/
│   │   │   ├── db.py           # ← 从 dashboard/db.py 迁来（_load_full + lru_cache）
│   │   │   ├── cache.py        # ← 从 dashboard/refresh.py 迁来（clear_all_caches）
│   │   │   └── pipeline.py     # ← 从 scripts/_pipeline.py 迁来（或直接 import）
│   │   └── deps.py             # DB session / 缓存失效 / 配置注入
│   ├── tests/                  # pytest：API 契约 + golden data 一致性
│   └── pyproject.toml
│
├── frontend/                  # 【新】Vue 3 SPA
│   ├── src/
│   │   ├── main.ts  App.vue
│   │   ├── router/             # vue-router（对应旧 6 页路由）
│   │   ├── stores/             # Pinia：filters / signal / refresh（跨图联动）
│   │   ├── api/                # openapi-typescript 生成 client + 手写封装
│   │   ├── composables/        # useChartOption / useDateRange / useRefresh
│   │   ├── components/
│   │   │   ├── charts/         # EChart 包装组件（见 §3.3）
│   │   │   ├── layout/         # Sidebar / GraphCard / MetricTile
│   │   │   └── controls/       # DateRangeToolbar / CityPicker / PhaseBadge / ChartTip
│   │   ├── pages/              # 6 个视图（1:1 旧 dash 页）
│   │   │   ├── Overview.vue MerrillClock.vue CreditCycle.vue
│   │   │   ├── InventoryCycle.vue DebtCycle.vue RealEstate.vue
│   │   ├── design/
│   │   │   ├── tokens.css      # ← config.py 的 C 色板 → CSS 变量
│   │   │   ├── echarts.theme.ts # ← CHART_LAYOUT/CHART_DEFAULTS → ECharts theme
│   │   │   └── tailwind.config.ts
│   │   └── types/api.ts        # 由 OpenAPI 生成
│   ├── vite.config.ts          # proxy /api → :8000
│   ├── package.json  tsconfig.json
│   └── tests/                  # vitest + @vue/test-utils
│
├── shared/                    # 【新】OpenAPI 契约 + codegen 配置
│   └── openapi.json            # CI 生成、提交、前端消费
├── dashboard/                 # 【保留→后删】旧 Dash，并行到 cutover
├── docs/architecture-upgrade.md
└── docker-compose.yml         # （可选）dev 一键起 backend+frontend
```

---

## 3. 各层设计

### 3.1 Backend — FastAPI（薄 API + 强契约）

**路由（全部 `analysis/` 的薄包装，零重写）：**

| 方法 路径 | 作用 | 对应旧逻辑 |
|---|---|---|
| `GET /api/v1/derived/monthly?start&end&cols` | 月度主表切片 | `db.load('derived_monthly', ...)` |
| `GET /api/v1/derived/quarterly` | 季度主表 | `db.load('derived_quarterly')` |
| `GET /api/v1/cycles/{merrill\|credit\|inventory\|debt}` | 周期分类 | `classify_*` |
| `GET /api/v1/signals` | 综合信号 | `compute_signals` |
| `GET /api/v1/real-estate?cities` | 房地产三维 | `analyze_real_estate` |
| `GET /api/v1/manifest` | 上次刷新摘要 | `read_manifest_summary` |
| `POST /api/v1/refresh` | 触发闸门管道（子进程） | `run_refresh` |
| `GET /api/v1/refresh/stream` | **SSE 真进度**（流 `✅` 行） | 取代 Dash 后台回调 |

**缓存**：保留 lru_cache 模式（`_load_full` + 6 分类器）。`POST /api/v1/cache/invalidate` 在刷新成功后调用 `clear_all_caches()`（从 `dashboard/refresh.py` 迁来）。可选升级为 `cachetools.TTLCache` 按 DB mtime 失效。

**环境**：macOS expat/DYLD 问题仍在（FastAPI 用同一个 venv、刷新子进程仍需 `DYLD_LIBRARY_PATH`），`run_refresh` 逻辑原样复用。

**OpenAPI → TS**：FastAPI 自动产出 `shared/openapi.json`；CI 跑 `openapi-typescript` 生成 `frontend/src/types/api.ts`。**前后端类型零漂移**。

### 3.2 Pydantic Schema（契约真相源，节选）

```python
# backend/app/schemas/cycles.py
class CreditPoint(BaseModel):
    date: str
    m2_yoy: float | None
    phase: str | None
    m2_trend: float | None
    credit_impulse: float | None

class CreditCycle(BaseModel):
    series: list[CreditPoint]
    latest_phase: str | None
    latest_m2_yoy: float | None

# schemas/signals.py
class SignalSummary(BaseModel):
    composite_score: int            # [-4, +4]
    interpretation: str
    merrill: PhaseScore
    credit: PhaseScore
    inventory: PhaseScore
    debt: PhaseScore

# schemas/refresh.py
class RefreshResult(BaseModel):
    status: Literal["ok","busy","error"]
    msg: str
    updated: list[str]
    kept_previous: list[str]
    ts: str | None
```

### 3.3 Frontend — Vue 3 + ECharts

**图表组件（1:1 映射旧工厂，ECharts 原生等价）：**

| Vue 组件 | 旧工厂 | ECharts 实现 |
|---|---|---|
| `DualAxisLine.vue` | `make_dual_axis_line` | 双 yAxis + series |
| `AreaChart.vue` | `make_area_chart` | stack 堆叠面积 |
| `BarLineCombo.vue` | `make_bar_line_combo` | bar + line 双轴 |
| `ScatterQuadrant.vue` | `make_scatter_quadrant` | scatter + markLine 十字 |
| `PhaseTimeline.vue` | `make_phase_timeline` | 自定义 series |
| `PhaseBackground` composable | `add_phase_background` | **markArea**（合并连续段）|
| `GapMarker` composable | `add_gap_marker` | markArea + graphic 文字 |
| `connectNulls` | `connectgaps=True` | ECharts **原生 `connectNulls:true`**（比 Plotly 干净）|

> 断线修复在 ECharts 里是**原生一行**，无需咽喉点技巧。M2 空洞用 `GapMarker`（markArea + graphic 文字）实现，效果一致。

**Pinia stores（跨图联动——Dash 做不好的核心）：**
- `useFiltersStore`：全局日期范围 + preset（5Y/10Y/20Y/全部）+ 城市选择。**一处改，全图表联动重取**。
- `useSignalStore`：综合信号 + 各周期最新阶段（多页共享徽章状态）。
- `useRefreshStore`：刷新状态 + SSE 进度 + manifest 结果。

**Composables**：
- `useChartOption(builder)`：统一装配 ECharts option（hover、axisPointer 十字线、暗色主题）—— 等价于 `_apply_layout` 但为 ECharts。
- `useDateRange`、`useRefresh`（SSE 订阅）、`useChartTip`。

**设计系统迁移（视觉延续）**：
- `frontend/src/design/tokens.css` ← `dashboard/config.py` 的 `C` dict（`--bg:#0a0e17`、`--accent:#6366f1`…）。
- `echarts.theme.ts` ← `CHART_LAYOUT` + `CHART_DEFAULTS`（透明背景、极淡网格、`hovermode`→`axisPointer`、统一色板）。
- `PHASE_COLORS`/`PHASE_LABELS` ← `design/phases.ts`（TS 常量）。
- `app.py` 的 `index_string` CSS（暗色 DatePicker/Dropdown/滚动条/chart-tip tooltip）→ `style.css` + Tailwind。

### 3.4 「极致」功能（本次迁移的核心收益）

| 能力 | Dash 现状 | Vue 升级后 |
|---|---|---|
| 跨图联动（改范围→全图更新） | 回调图痛苦 | Pinia 一处改全局联动 |
| 微交互/动效 | CSS transition | Motion-V / GSAP（页面切换、KPI count-up、入场动画）|
| 刷新进度 | Dash 后台回调 | **SSE 流式真进度**（更顺滑）|
| 可拖拽定制看板 | 不可行 | `vue-grid-layout`（用户自摆卡片）|
| 实时推送 | 后台回调勉强 | WebSocket ready |
| 注释/对比模式/情景模拟 | 难 | 原生交互 |
| 移动端 / PWA / 分享链接 | 一般 | 原生强 |

---

## 4. 迁移阶段（增量、可回退、每步可验证）

> 每阶段有**退出标准**；未达标不进下一阶段。旗舰页 P1 先验证「极致」是否兑现。

### Phase 0 — 地基（无 UI 变化）
- 建 `backend/` FastAPI 骨架包装 `analysis/` + `db.py` + 刷新逻辑。
- Pydantic schema + OpenAPI + TS codegen 流水线。
- **退出标准**：`GET /api/v1/derived/monthly` 与 `db.load` 返回**逐字节一致**（golden test）；`/api/v1/cycles/credit` 返回 `classify_credit` 结果。
- Dash 照常运行，用户无感知。

### Phase 1 — 前端骨架 + 设计系统 + 旗舰页（**决策门**）
- Vue 脚手架 + router + Pinia + tokens + ECharts theme。
- 建全部图表组件（`DualAxisLine` 等）—— 共享图表词汇。
- **重建信用周期页 `CreditCycle.vue`**（M2 图 + 阶段背景 + 信贷脉冲 + GapMarker + connectNulls）。
- **退出标准（决策门）**：与旧 Dash 信用周期页**像素近似 + 数据一致 + M2 空洞标注在位 + connectNulls 原生**。**达到你心里的「极致」→ 继续；达不到 → 止损，保留 Dash+ECharts 方案。**

### Phase 2 — 迁移其余 5 页
- overview / merrill / inventory / debt / real_estate，每页一迭代。
- **退出标准**：6 页全部 parity（数据、外观、交互）。

### Phase 3 — 横切「极致」功能
- Pinia 全局日期联动（改范围→全图表更新）。
- 刷新改 SSE + 进度条。
- Motion-V 微交互（KPI count-up、页面/图表入场）。
- **退出标准**：demo「改一个日期范围，全页 6+ 图表联动刷新」+「刷新有 SSE 进度」——这是 Dash 做不到、肉眼可见的超越。

### Phase 4 — 切换 + 清理
- Vue 为默认入口（`启动面板.command` 起 `vite preview` / nginx）。
- 加 PWA manifest。
- **下线 `dashboard/`（Dash）**，更新 README / changeLog / requirements。

### Phase 5（可选，未来）— 高级
- 可拖拽看板布局、保存视图、实时推送、移动端。

---

## 5. 技术选型与版本（pin）

**Backend**
- Python 3.12、FastAPI `^0.115`、uvicorn[standard]、pydantic `^2`
- 复用：akshare / pandas / numpy / scipy / statsmodels（不变）

**Frontend**
- Node 20 LTS、Vue `3.5`、Vite `5`、TypeScript `5.5`
- ECharts `5.5` + `vue-echarts ^7`（官方封装，按需 tree-shake）
- Pinia `^2`、vue-router `^4`、Tailwind CSS `^3.4`、`@vueuse/core`
- Motion-V（或 GSAP）做微交互
- Naive UI（或 Element Plus）做基础组件——**不手搓每个交互**，用成熟库降单人风险

**契约/质量**
- `openapi-typescript ^7`（schema→TS）
- 后端：pytest + ruff；前端：vitest + @vue/test-utils + eslint + vue-tsc
- E2E：Playwright（6 页渲染 + 刷新 + 无 console error）

---

## 6. CI / 质量门

- **契约守门**：CI 生成 `shared/openapi.json` → 跑 codegen → `git diff` 若 `frontend/src/types/api.ts` 变了未提交 → **fail**。强制类型不漂移。
- **golden test**：后端 API 输出 vs `db.load` 快照，防回归。
- **前端类型检查**：`vue-tsc --noEmit` 必须 0 error。
- **E2E**：Playwright 跑全 6 页 + 刷新 SSE。
- pre-commit：ruff / eslint / type-check / openapi-codegen。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| **API 契约漂移**（改 analysis 忘改前端类型）| OpenAPI codegen + CI 守门——本方案最大持续风险，已用强类型堵死 |
| ECharts 对高度自定义项（阶段背景、双轴 hover）不如 Plotly | **P1 旗舰页先验证**；ECharts markArea/axisPointer 覆盖；不可行则 P1 即暴露，非 P4 才发现 |
| 单人达到「极致」执行力 | 重度依赖 Claude/AI + 成熟组件库（Naive UI/shadcn-vue），不手搓每个交互 |
| macOS expat/DYLD | 后端复用同 venv，刷新子进程保留 env 处理（已验证可行）|
| 迁移期双栈维护负担 | 并行期 FastAPI 与 Dash 共享 `analysis/`+DB，无数据重复；逐页迁移降低并行面 |
| scope 膨胀（Phase 5 提前）| 严格阶段门，P1 决策门未过即止损 |

---

## 8. 里程碑与验收

| 里程碑 | 退出标准（可验证）|
|---|---|
| **P0 地基** | API golden test：`/derived/monthly` 与 `db.load` 逐字节一致；OpenAPI→TS codegen 跑通 |
| **P1 旗舰页** ⭐决策门 | `CreditCycle.vue` 像素近似旧页 + 数据一致 + M2 GapMarker + connectNulls 原生；刷新 SSE 可用。**未达极致则止损** |
| **P2 全页 parity** | 6 页全部数据/外观/交互 parity |
| **P3 横切极致** | 改日期范围→全图联动；刷新 SSE 进度；微交互入场 |
| **P4 切换** | Dash 下线，Vue 为唯一入口，changeLog/README 更新 |

---

## 9. 开干起点

P0 第一步（最小可验证）：
1. 建 `backend/app/main.py` + `api/v1/data.py`，暴露 `GET /api/v1/derived/monthly`。
2. Pydantic schema + `core/db.py`（迁自 `dashboard/db.py`）。
3. 写 golden test 断言 API == `db.load`。
4. 跑通 OpenAPI 导出 + 前端 codegen。

> `analysis/`、`scripts/_pipeline.py`、刷新逻辑——全程零改动，是这份方案的核心保值承诺。

---

## 附：与现状的资产对照（哪些保留 / 哪些迁 / 哪些新写）

| 现状资产 | 去向 |
|---|---|
| `analysis/*.py`（周期/信号/房地产/交叉）| ✅ **零改动**，FastAPI import |
| `scripts/_pipeline.py` + `01_fetch_data.py`（闸门管道）| ✅ **零改动**，refresh 端点子进程调用 |
| `dashboard/db.py`（lru_cache）| 迁到 `backend/app/core/db.py` |
| `dashboard/refresh.py`（clear_all_caches / run_refresh / manifest）| 迁到 `backend/app/core/cache.py` + `api/v1/refresh.py` |
| `dashboard/config.py`（C 色板/PHASE_*/CHART_*）| 迁到 `frontend/src/design/`（tokens.css + echarts.theme.ts + phases.ts）|
| `dashboard/components/charts.py`（工厂）| 重写为 `frontend/src/components/charts/*.vue`（ECharts）|
| `dashboard/pages/*.py`（6 页）| 重写为 `frontend/src/pages/*.vue` |
| `dashboard/app.py`（侧边栏/CSS/回调）| 重写为 Vue router + layout + Pinia |
| `requirements.txt` | 拆 `backend/pyproject.toml` + `frontend/package.json` |
