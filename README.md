# 中国宏观经济数据分析平台

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883)](https://vuejs.org/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-aa344d)](https://echarts.apache.org/)
[![AKShare](https://img.shields.io/badge/Data-AKShare-green)](https://www.akshare.xyz/)

一个基于 **Python + FastAPI + Vue 3 + ECharts** 构建的**中国宏观经济数据分析平台**，采用 **Terminal Fintech** 暗色主题。通过 [`AKShare`](https://www.akshare.xyz/) 采集国家统计局、中国人民银行等权威数据源，计算四大经典周期分析框架与综合宏观信号，并以高度交互的可视化方式呈现。

> 架构升级历史详见 [`docs/architecture-upgrade.md`](docs/architecture-upgrade.md)（Dash+Plotly → FastAPI+Vue 迁移全过程）。

---

## 目录

- [功能特性](#功能特性)
- [四大周期分析框架](#四大周期分析框架)
- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [数据流水线](#数据流水线)
- [后端 API](#后端-api)
- [前端架构](#前端架构)
- [设计系统](#设计系统)
- [测试与质量](#测试与质量)
- [性能优化](#性能优化)
- [开发规范](#开发规范)
- [依赖](#依赖)
- [许可证](#许可证)

---

## 功能特性

- **六大分析视图**：综合概览、美林时钟、信用周期、库存周期、债务周期、房地产市场
- **综合宏观信号**：聚合四大周期框架生成 `[-4, +4]` composite score 与解读
- **交互式图表**：双轴折线、堆叠面积、柱+折线组合、四象限散点、阶段时间条、雷达图
- **阶段背景着色**：自动识别经济阶段并以半透明背景连续段高亮
- **日期范围控制**：全局工具栏 5Y / 10Y / 20Y / 全部 快捷按钮 + 图表缩放条（拖拽缩放，滚轮已禁用防误触）
- **起点对齐**：`align_start` 让图表从各值列同时有数据的日期起，省去手动拖周期
- **城市对比**：房地产页多城市房价同比 + 三维评估雷达图
- **一键刷新**：看板内按钮触发采集管道，SSE 流式真进度，完成后自动重载
- **KPI 指标瓦 + tooltip**：概览页关键指标 count-up 动画 + ⓘ 说明浮窗（含义 + 取数逻辑）
- **PMI 荣枯线**：50 线以琥珀实线 + 标注重点突出（PMI 语义零轴）
- **本地 SQLite**：采集一次后离线运行，无需重复联网

---

## 四大周期分析框架

| 框架 | 分析维度 | 阶段 | 信号来源 |
|---|---|---|---|
| **美林时钟** | GDP vs 通胀 | 复苏 / 过热 / 滞胀 / 衰退 | GDP 同比 vs 4 年趋势；CPI 同比 vs 2% |
| **信用周期** | 货币松紧 | 宽松 / 紧缩 / 中性 | M2 同比 vs 12 月均线（credit impulse） |
| **库存周期** | 供需与生产 | 主动补库 / 被动补库 / 主动去库 / 被动去库 | PMI vs 50；工业增加值 vs 6 月均线 |
| **债务周期** | 各部门杠杆率变化 | 加杠杆 / 去杠杆 / 稳定 / 美丽去杠杆 / 丑陋去杠杆等 | 家庭/企业/政府杠杆率 4 季度变化 + GDP 增速 |

**综合信号打分**：每个框架的最新阶段映射为 `-1 / 0 / +1`，四项求和后得到 `[-4, +4]` 的综合得分：

| 得分 | 解读 |
|---|---|
| `+3 ~ +4` | 强烈看多 — 多数周期处于扩张 |
| `+1 ~ +2` | 温和看多 — 增长信号占优 |
| `0` | 中性 — 信号相互冲突 |
| `-1 ~ -2` | 温和看空 — 逆风积聚 |
| `-3 ~ -4` | 强烈看空 — 多数周期处于收缩 |

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  (Vue 3 + Vite + TS + ECharts + Pinia, :5173)     │
│  pages/ (6 视图) ─ router ─ stores (filters/refresh)         │
│  components/charts/ (EChart + option builders)  design/      │
│  api/ (typed client ← OpenAPI)                               │
└─────────────────────────────────────────────────────────────┘
                      │  HTTP / SSE  (/api/v1/*)
┌─────────────────────────────────────────────────────────────┐
│  Backend   (FastAPI + Pydantic, :8000)                      │
│  api/v1/ (data · cycles · signals · real-estate · refresh)   │
│  schemas/ (契约真相源)   core/ (db · cache · refresh · serial)│
│  tests/ (golden test)                                       │
└─────────────────────────────────────────────────────────────┘
                      │  同进程直接 import（无序列化边界）
┌─────────────────────────────────────────────────────────────┐
│  Domain Core  (零改动保值)                                   │
│  analysis/ (cycle_merrill/credit/inventory/debt, signals,    │
│             real_estate, cross_indicator)                     │
│  scripts/_pipeline.py + 01_fetch_data.py + 02_compute_derived│
└─────────────────────────────────────────────────────────────┘
                      │
              data/macro_data.db (SQLite, 13 表)
```

- `backend/` — FastAPI：薄包装 `analysis/`，Pydantic schema + OpenAPI 契约 + golden test
- `frontend/` — Vue 3 SPA：6 页视图、Pinia 全局联动、ECharts 图表组件
- `analysis/`、`scripts/_pipeline.py`、`scripts/01_fetch_data.py`、`02_compute_derived.py` — **核心保值，原样复用**

---

## 目录结构

```text
AKShare/
├── analysis/                    # 宏观分析引擎（无 UI / API 依赖，纯计算）
│   ├── cycle_merrill.py         # 美林时钟
│   ├── cycle_credit.py          # 信用周期
│   ├── cycle_inventory.py       # 库存周期
│   ├── cycle_debt.py            # 债务周期
│   ├── real_estate.py           # 房地产三维评估
│   ├── cross_indicator.py       # 领先/滞后相关性
│   └── signals.py               # 综合信号打分
│
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # FastAPI 实例 + CORS + 路由挂载
│   │   ├── api/v1/              # 端点：data · cycles · signals · real_estate · refresh
│   │   ├── schemas/             # Pydantic 契约（CycleFrame/SignalSummary/RefreshResult…）
│   │   ├── core/                # db(lru_cache) · cache(clear_all) · refresh(子进程+SSE) · serial
│   │   └── deps.py
│   ├── tests/test_golden.py     # golden test：API 输出 == db.load
│   └── pyproject.toml           # 后端依赖（fastapi/uvicorn/pydantic/httpx + analysis 依赖）
│
├── frontend/                    # Vue 3 SPA
│   ├── src/
│   │   ├── pages/               # Overview · MerrillClock · CreditCycle · InventoryCycle · DebtCycle · RealEstate
│   │   ├── components/
│   │   │   ├── charts/          # EChart.vue + options.ts(builder) + utils.ts
│   │   │   ├── layout/          # Sidebar · GraphCard · MetricTile · RefreshBar
│   │   │   └── controls/        # ChartTip (Teleport 浮窗)
│   │   ├── stores/              # Pinia: filters(全局联动) · refresh(SSE)
│   │   ├── api/                 # client.ts + types.ts（← OpenAPI）
│   │   ├── composables/         # useCountUp
│   │   ├── design/              # tokens.css · echarts.theme.ts · phases.ts
│   │   └── router/
│   ├── public/manifest.webmanifest  # PWA
│   ├── vite.config.ts           # proxy /api → :8000
│   └── package.json
│
├── scripts/                     # 采集与衍生计算（后端复用）
│   ├── _pipeline.py             # 暂存快照 + 校验闸门 + 原子切换 + 备份 + 审计
│   ├── _pipeline_test.py        # 管道离线测试（15/15）
│   ├── 01_fetch_data.py         # AKShare 采集（12 fetcher，走闸门管道）
│   └── 02_compute_derived.py    # 衍生指标计算
│
├── data/                        # SQLite 数据库（gitignored）
│   ├── macro_data.db            # 13 张表：11 原始 + derived_monthly/quarterly
│   ├── backups/                 # 采集前自动备份（留 10 份）
│   └── last_run.json            # 上次采集审计 manifest
│
├── shared/openapi.json          # OpenAPI 契约（供前端 codegen）
├── docs/architecture-upgrade.md # 架构升级方案文档
├── run_app.sh                   # 一键启动（FastAPI:8000 + Vue:5173）
├── 启动面板.command             # macOS 双击入口（委托 run_app.sh）
├── requirements.txt             # analysis/scripts 依赖（akshare/pandas/numpy/scipy/statsmodels）
├── changeLog.md                 # 变更日志
├── CLAUDE.md / AGENTS.md        # 开发规范
└── README.md                    # 本文件
```

---

## 快速开始

### 环境要求

- Python 3.12（macOS 需 Homebrew Python + `DYLD_LIBRARY_PATH` 处理 expat，启动脚本已内置）
- Node 20+（前端构建）
- 网络连接（首次采集数据时需要；NBS 接口在某些出口 IP 可能被 WAF 拦截，见下）

### 一键启动

```bash
./run_app.sh          # 或双击 启动面板.command
```

`run_app.sh` 自动完成：激活 `.venv312` → 首次构建前端（`npm install && npm run build`）→ 后端依赖自检 → 启动 FastAPI(:8000) + Vue preview(:5173) → trap 退出清理。

浏览器打开：**http://localhost:5173**（API 文档：http://localhost:8000/docs）

### 开发模式（热重载）

```bash
# 终端 1：后端
.venv312/bin/python -m uvicorn backend.app.main:app --port 8000 --reload
# 终端 2：前端（HMR）
cd frontend && npm run dev
```

### 手动采集 / 重算衍生

```bash
python3 scripts/01_fetch_data.py     # 采集（走闸门管道：暂存→校验→原子切换→备份→manifest）
python3 scripts/02_compute_derived.py  # 重算 derived_monthly / derived_quarterly
```

> 首次启动若 `data/macro_data.db` 不存在，`run_app.sh` 会自动跑这两个脚本。

---

## 数据流水线

### 原始数据采集

`scripts/01_fetch_data.py` 从 AKShare 采集 12 类宏观指标，清洗后经**闸门管道**落 SQLite：

| # | 表 | 指标 | 频率 |
|---|---|---|---|
| 1 | `money_supply` | M0/M1/M2 | 月 |
| 2 | `gdp` | GDP 绝对值 + 同比 | 季（实际为年度口径）|
| 3 | `cpi` | CPI 同比 + 环比 | 月 |
| 4 | `ppi` | PPI 同比 | 月 |
| 5 | `pmi` | 官方/财新/非制造业/服务业 | 月 |
| 6 | `leverage` | 宏观杠杆率（CNBS 分部门）| 季 |
| 7 | `social_finance` | 社融规模增量 + 分项 | 月 |
| 8 | `lpr` | LPR 1Y/5Y | 月 |
| 9 | `industrial` | 工业增加值同比 + 累计 | 月 |
| 10 | `house_price` | 70 城房价指数（新建/二手 同比/环比/定基）| 月 |
| 11 | `new_credit` | 新增人民币贷款 | 月 |
| 12 | `household_income` | 居民可支配收入（NBS，部分环境被拦）| 年 |

### 采集闸门管道（`scripts/_pipeline.py`）

根治"采集覆写好数据"：生产库在最终原子 `os.replace` 前一字节不被触碰。

- **暂存快照**：复制生产库到 `macro_data.db.staging`，fetcher 全部写暂存
- **校验闸门**：每表 `TABLE_SPECS` 契约（min_rows / required cols / distinct-date 反缩水）；空/残缺/萎缩 → 拒绝 replace，暂存保留旧好表
- **原子切换**：`os.replace(staging → live)`，崩溃零损失
- **备份 + 审计**：每次采集前归档 `data/backups/`（留 10 份），写 `data/last_run.json`（每表 updated/kept_previous + 行数 + 原因）

### 衍生指标计算

`scripts/02_compute_derived.py` 合并原始表，生成两张核心表：

**`derived_monthly`**（月度主表，30 列）
- M2-M1 剪刀差、实际利率（LPR1Y - CPI）、PMI 6 月均线、工业增加值趋势
- 社融存量增速、信贷脉冲、新增贷款同比、贷款存量增速、M1 领先 PPI 标记

**`derived_quarterly`**（季度主表）
- GDP 同比 + 4 季平滑、各部门杠杆率及季度变化速度

> 注：`derived_quarterly` 的 leverage 列因 gdp 年频与 leverage 季频日期不重叠而为空；债务图表直读 `leverage` 原始表（见 DebtCycle.vue），`cycle_debt` 也直读 leverage，不受影响。

---

## 后端 API

FastAPI（`:8000`），OpenAPI 文档 `http://localhost:8000/docs`，契约导出至 `shared/openapi.json`。

| 方法 路径 | 作用 |
|---|---|
| `GET /api/v1/derived/monthly` | 月度主表切片（支持 `start/end/cols/align_start`）|
| `GET /api/v1/derived/quarterly` | 季度主表切片 |
| `GET /api/v1/table/{name}` | 任意原始表切片（house_price/leverage…）|
| `GET /api/v1/cycles/{merrill\|credit\|inventory\|debt}` | 周期分类 + 最新阶段 |
| `GET /api/v1/signals` | 综合信号 `[-4,+4]` + 各框架阶段 |
| `GET /api/v1/real-estate?cities=…` | 房地产三维评估（雷达数据）|
| `GET /api/v1/refresh/status` | 上次刷新 manifest |
| `POST /api/v1/refresh` | 触发闸门管道（阻塞）|
| `GET /api/v1/refresh/stream` | SSE 流式真进度 |
| `GET /health` | 健康检查 |

- **Pydantic schema**（`backend/app/schemas/`）= 契约真相源 → OpenAPI → 前端 TS 类型，零漂移
- **缓存**：`db._load_full` + 7 个分类器 lru_cache；刷新成功后 `clear_all_caches()` 失效

---

## 前端架构

- **6 页视图**（`pages/`）：Overview / MerrillClock / CreditCycle / InventoryCycle / DebtCycle / RealEstate
- **Pinia stores**：`filters`（全局日期联动——改一处全图重取）、`refresh`（SSE 进度消费）
- **图表层**（`components/charts/options.ts`）：纯函数 builder——`buildDualAxisLine` / `buildStackedArea` / `buildBarLineCombo` / `buildMultiLine` / `buildScatterQuadrant` / `buildCreditM2Chart` / `buildCreditImpulseChart` / `buildSpreadChart` / `buildRadar`
- **EChart.vue**：vue-echarts 封装，按需注册（Line/Bar/Scatter/Radar + 组件）
- **ChartTip**（`controls/`）：Teleport 到 `<body>` + 视口自适应定位，永不裁切
- **设计系统**（`design/`）：tokens.css（色板）+ echarts.theme.ts（connectNulls/dataZoom/axisPointer）+ phases.ts
- **PWA**：`public/manifest.webmanifest`，可"安装"为桌面应用

---

## 设计系统

统一的 **Terminal Fintech** 暗色主题，定义于 `frontend/src/design/`。

### 色彩体系（`tokens.css` + `tailwind.config.ts`）

| Token | 值 | 用途 |
|---|---|---|
| `bg` | `#0a0e17` | 页面背景 |
| `surface` | `#111827` | 侧边栏、工具栏 |
| `card` | `#1a2332` | 卡片表面 |
| `accent` | `#6366f1` | 靛蓝强调色、活跃状态 |
| `up` | `#10b981` | 上涨、扩张、宽松 |
| `down` | `#ef4444` | 下跌、紧缩、衰退 |
| `warn` | `#f59e0b` | 中性、过热、荣枯线 |
| `text` / `text-2` / `text-3` | `#f1f5f9` / `#94a3b8` / `#64748b` | 三级文字层级 |

### ECharts 图表默认（`echarts.theme.ts`）

- 透明背景、极淡网格、`axisPointer: cross` 十字线
- `connectNulls: true` 原生跨接断线（替代 Plotly 的 connectgaps）
- `dataZoom`（slider + inside，滚轮已禁用防误触）对 category 时间轴自动启用
- `tooltip.confine + appendToBody` 防裁切；日期统一 `YYYY-MM-DD`
- 统一色板：`#6366f1, #10b981, #ef4444, #f59e0b, #a78bfa, #06b6d4, #f97316, #ec4899`

### 字体

```css
font-family: -apple-system, BlinkMacSystemFont, Inter, 'SF Pro Display', 'Segoe UI', 'Noto Sans SC', PingFang SC, sans-serif;
```

---

## 测试与质量

- **后端 golden test**（`backend/tests/test_golden.py`，6/6）：`/derived/monthly` 与 `db.load` 逐字节一致 + 各周期/signals/refresh 端点
- **管道测试**（`scripts/_pipeline_test.py`，15/15）：闸门全分支 + 暂存继承 + 崩溃安全 + 原子切换
- **前端类型**：`vue-tsc --noEmit` 0 error
- **契约守门**：OpenAPI → 前端 TS codegen（`npm run gen:api`），防类型漂移

---

## 性能优化

- **数据库表缓存**：`db._load_full()` `lru_cache(maxsize=32)`，首次读盘后全表常驻内存，切片 < 1ms
- **分类器缓存**：7 个 `classify_*`/`compute_signals`/`analyze_real_estate` `lru_cache`，启动期多页重复计算收敛为 1 次
- **刷新缓存失效**：`clear_all_caches()` 在原子切换后清空全部 7 处，保证下次读新库
- **SSE 真进度**：子进程流式 stdout 数 `✅` 行驱动进度，非假 spinner
- **暂存隔离**：采集只动 staging，生产库原子切换前零接触

---

## 开发规范

详见 `CLAUDE.md` / `AGENTS.md`，核心要点：

1. **变更日志**：每次提交必须在 `changeLog.md` 记录（中英双语，`[类型]` 分类）
2. **提交信息**：中英双语，中文在前、英文在后
3. **WorkTree**：新增功能/代码修改前询问是否创建 Git WorkTree 隔离
4. **极简原则**：只改必要的代码，不引入推测性功能
5. **验证导向**：先定义成功标准，再循环验证
6. **分支**：默认分支为 `main`（原 `master` 已改名）

---

## 依赖

### 后端（`requirements.txt` + `backend/pyproject.toml`）

```text
akshare>=1.14.0
pandas>=1.5
numpy>=1.24
scipy>=1.10
statsmodels>=0.14
# backend 额外（pyproject.toml）：
fastapi>=0.115  uvicorn[standard]  pydantic>=2  httpx  pytest
```

### 前端（`frontend/package.json`）

```text
vue ^3.5  vue-router ^4  pinia ^2  vue-echarts ^7  echarts ^5.5  @vueuse/core
vite ^5  typescript ^5.5  vue-tsc  tailwindcss ^3.4  openapi-typescript ^7
```

---

## 许可证

本项目为宏观经济数据分析学习与研究用途构建。数据版权归原始发布机构所有。

---

## 维护者

由 Claude Code 辅助开发，遵循 `CLAUDE.md` 项目规范。
