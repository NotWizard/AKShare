# 中国宏观经济数据分析平台

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883)](https://vuejs.org/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-aa344d)](https://echarts.apache.org/)
[![AKShare](https://img.shields.io/badge/Data-AKShare-green)](https://www.akshare.xyz/)

一个基于 **Python + FastAPI + Vue 3 + ECharts** 构建的**中国宏观经济数据分析平台**，采用 **Obsidian Blue × Paper** 双主题（一键换肤）。通过 [`AKShare`](https://www.akshare.xyz/) 采集国家统计局、中国人民银行等权威数据源，计算四大经典周期分析框架与综合宏观信号，并以高度交互的可视化方式呈现。

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

- **八大分析视图 + CRCL 监控**：综合概览、美林时钟、信用周期、库存周期、债务周期、房地产市场、人口与城镇化、财政与外需，外加 CRCL（Circle）投资论点监控页
- **综合宏观信号**：聚合四大周期框架生成 `[-4, +4]` composite score 与解读
- **交互式图表**：双轴折线、堆叠面积、柱+折线组合、四象限散点、阶段时间条、雷达图
- **双主题换肤**：Obsidian Blue 暗色 × Paper 亮色，顶栏 ☾/☀ 一键切换（含全部图表联动换肤），跟随系统偏好并记忆选择
- **日期范围控制**：全局工具栏 5Y / 10Y / 20Y / 全部 快捷按钮 + 图表缩放条（拖拽缩放，滚轮已禁用防误触）
- **起点对齐**：`align_start` 让图表从各值列同时有数据的日期起，省去手动拖周期
- **城市对比**：房地产页多城市房价同比 + 三维评估雷达图
- **一键刷新**：看板内按钮触发采集管道，SSE 流式真进度，完成后自动重载
- **KPI 指标瓦**：概览页关键指标 count-up 动画 + 较上期环比涨跌 + ⓘ 说明浮窗（含义 + 取数逻辑）
- **阶段背景着色**：自动识别经济阶段并以半透明背景连续段高亮
- **PMI 荣枯线**：50 线以隐晦灰色细虚线 + 同色小标注呈现（仅维度参考，不与数据序列争焦；与四象限十字线/剪刀差零线同一参考线语汇）
- **图例中文化**：所有图表图例/轴名统一中文（NBS/央行/NIFD 官方术语；CPI/PPI/M2/PMI/LPR/GDP 等特有名词保留英文缩语），见 `options.ts` `COL_ZH`
- **居民真实杠杆空间**：债务周期页「杠杆率 vs 债务收入比」图——杠杆率看似 ~60%，债务收入比已 ~120-140%，更真实反映居民加杠杆空间
- **通胀环比图**：美林页「CPI vs PPI 环比」+「PPI 同比」图，与同比图呼应
- **AI 宏观评论**：OpenAI-compatible 模型对分板块数据快照生成结构化评论（Overview 总评 + 6 细分页板块切片；配套 AI 设置页：profiles 多配置 + 密钥入 macOS 钥匙串 + 提示词模板编辑器 + 生成历史；未配置时优雅降级并给出引导）
- **本地 SQLite**：采集一次后离线运行，无需重复联网

---

## 四大周期分析框架

| 框架 | 分析维度 | 阶段 | 信号来源 |
|---|---|---|---|
| **美林时钟** | GDP vs 通胀 | 复苏 / 过热 / 滞胀 / 衰退 | GDP 同比 vs 潜在增长（5 期中位数趋势 + 死区/迟滞）；CPI 同比 vs 2% |
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
│  Frontend  (Vue 3 + Vite + TS + ECharts + Pinia, build)     │
│  pages/ (10 视图) ─ router ─ stores (filters/refresh/theme)  │
│  components/charts/ (EChart + option builders)  design/      │
│  api/ (typed client ← OpenAPI)                               │
└─────────────────────────────────────────────────────────────┘
                      │  HTTP / SSE  (/api/v1/*)
┌─────────────────────────────────────────────────────────────┐
│  Backend   (FastAPI + Pydantic, :8000)                      │
│  api/v1/ (data·cycles·signals·real-estate·refresh·commentary│
│           ·sources·ai·crcl·session)                          │
│  schemas/ (契约真相源)   core/ (db·auth·refresh·commentary·  │
│           ai_config/ai_client/keychain·crcl_collect·serial)  │
│  tests/ (pytest 375 项)                                      │
└─────────────────────────────────────────────────────────────┘
                      │  同进程直接 import（无序列化边界）
┌─────────────────────────────────────────────────────────────┐
│  Domain Core  (零改动保值)                                   │
│  analysis/ (cycle_merrill/credit/inventory/debt, signals,    │
│             real_estate, cross_indicator)                     │
│  scripts/_pipeline.py + 01_fetch_data.py + 02_compute_derived│
└─────────────────────────────────────────────────────────────┘
                      │
              data/macro_data.db (SQLite, 16 原始 + 2 衍生 + commentary + signal_history)
```

- `backend/` — FastAPI：薄包装 `analysis/`，Pydantic schema + OpenAPI 契约 + golden test
- `frontend/` — Vue 3 SPA：10 页视图、Pinia 全局联动、ECharts 图表组件
- **单进程托管**：`frontend/dist` 由 FastAPI 在 `:8000` 上挂载（`/assets` + 404 回落到 `index.html`），`run_app.sh` 不再起 `vite preview`；`:5173` 只在 `npm run dev` 热重载时存在
- `analysis/`、`scripts/_pipeline.py`、`scripts/01_fetch_data.py`、`02_compute_derived.py` — **核心保值，原样复用**

---

## 目录结构

```text
MACRO/
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
│   │   ├── api/v1/              # 端点：data·cycles·signals·real_estate·refresh·commentary·sources·ai·crcl·session
│   │   ├── schemas/             # Pydantic 契约（CycleFrame/SignalSummary/RefreshResult/Commentary/ProfileList…）
│   │   ├── core/                # db(版本键缓存) · auth(本机令牌) · refresh(任务+SSE) · commentary · ai_* · keychain · crcl_*
│   │   └── deps.py
│   ├── tests/                   # pytest 375 项（golden/契约/闸门/auth/评论/CRCL…）
│   └── pyproject.toml           # 后端最小依赖（fastapi/uvicorn/pydantic/httpx）+ pytest 配置
│                                #   分析依赖不在此重述，以根 requirements.txt/.lock 为准
│
├── frontend/                    # Vue 3 SPA
│   ├── src/
│   │   ├── pages/               # Overview · 美林 · 信用 · 库存 · 债务 · 房地产 · 人口 · 财政外需 · CrclMonitor · AISettings
│   │   ├── components/
│   │   │   ├── charts/          # EChart.vue + options.ts(builder) + utils.ts
│   │   │   ├── layout/          # Sidebar · GraphCard · MetricTile · RefreshBar · CommentaryCard · SectionCommentary · HealthLight · PageState
│   │   │   └── controls/        # ChartTip (Teleport 浮窗)
│   │   ├── stores/              # filters(全局联动) · refresh(SSE) · theme(亮暗换肤)
│   │   ├── api/                 # client.ts + types.ts（← OpenAPI）
│   │   ├── composables/         # useAsyncData · useCommentary · useThemedOption · useCountUp
│   │   ├── design/              # tokens.css · echarts.theme.ts · phases.ts
│   │   └── router/
│   ├── public/manifest.webmanifest  # PWA
│   ├── vite.config.ts           # proxy /api → :8000
│   └── package.json
│
├── scripts/                     # 采集与衍生计算（后端复用）
│   ├── _pipeline.py             # 暂存快照 + 校验闸门（多粒度）+ 原子切换 + 备份 + 审计 + live 直写表并入
│   ├── _pipeline_test.py        # 管道自查脚本（31 项 check；无 test_* 函数，pytest 不收集）
│   ├── 01_fetch_data.py         # 宏观数据采集（16 fetcher：AKShare 为主 + 东方财富/中债/世行直连，走闸门管道）
│   ├── 02_compute_derived.py    # 衍生指标计算
│   ├── nifd_leverage.py         # NIFD 杠杆率补充数据单一真相源（01/03 共用）
│   ├── pbc_shrzgm.py            # PBoC 社融 XLSX 备用源（01/04 共用）
│   ├── 03_supplement_leverage.py / 04_supplement_social_finance.py  # 独立补数脚本
│   ├── dual_sources.py          # 双源交叉比对   · diff_vintage.py  # vintage 快照比对
│   └── gen_openapi.py           # OpenAPI 契约导出（shared/openapi.json）
│
├── data/                        # SQLite 数据库（gitignored）
│   ├── macro_data.db            # 16 张原始表 + derived_monthly/derived_quarterly + commentary + signal_history
│   ├── backups/                 # 采集前自动备份（留 10 份）
│   ├── vintages/                # 提交前审计快照（留 12 份，供 scripts/diff_vintage.py 比对）
│   ├── logs/                    # 运行日志：fetch.log（采集，轮转）· api.log（uvicorn，超 5MB 转存 .1）
│   └── last_run.json            # 上次采集审计 manifest
│
├── shared/openapi.json          # OpenAPI 契约快照（gen_openapi.py 导出，test_openapi_drift 守门）
├── docs/architecture-upgrade.md # 架构升级方案文档
├── docs/design/                 # 设计方案（dual-theme-plan.md 双主题色彩体系）
├── docs/data-sources-guide.md   # 数据源现状与实测记录
├── docs/data-supplement-runbook.md # 数据补充运行手册（发布窗口+手动触发+校验）
├── run_app.sh                   # 一键启动（单进程 FastAPI:8000，同时托管 API 与 Vue 构建产物）
├── 启动面板.command             # macOS 双击入口（委托 run_app.sh）
├── requirements.txt             # 直接依赖（人读，akshare 精确锁定）
├── requirements.lock            # 逐包精确锁（63 包传递闭包，源自 .venv312 实测）
├── .env.example                 # 环境变量模板（复制为 .env；.env 已 gitignored）
├── CHANGELOG.md                 # 变更日志
├── CLAUDE.md / AGENTS.md        # 开发规范
└── README.md                    # 本文件
```

---

## 快速开始

### 环境要求

- Python 3.12+。**权威环境是 `./.venv312`（实测 Python 3.12.14，`pyvenv.cfg` 记 3.12.13）**；仓库里还有一个 `./.venv` 是 Python 3.11.14，违反 `backend/pyproject.toml` 的 `requires-python >= 3.12`，且装的是另一个 akshare 版本，**已陈旧、不受支持，勿使用**（未删除，属本机环境）
- 依赖：`requirements.txt`（人读直接依赖，akshare 锁定 `==1.18.64`）+ `requirements.lock`（逐包精确锁）
- macOS 需 `DYLD_LIBRARY_PATH` 处理 expat，启动脚本已内置
- Node 20+（前端构建）
- 网络连接（首次采集数据时需要；NBS 2026-03 改版曾封禁旧接口，akshare ≥1.18 已适配新接口，详见 [`docs/data-sources-guide.md`](docs/data-sources-guide.md) §十一）

### 一键启动

```bash
./run_app.sh          # 或双击 启动面板.command
```

`run_app.sh` 自动完成：解析解释器（`PYTHON`/`VENV` 覆盖 → `.venv312` → `.venv` → `python3`，都不可用则打印 bootstrap 指引并退出 1）→ 前端指纹比对，有变更才 `npm ci && npm run build` → 后端/采集依赖自检（按 `requirements.txt` 固定版本）→ **单进程** 启动 FastAPI(:8000) 并轮询 `/health`（30s 未就绪即打印日志尾部并退出 1）→ trap 退出清理。

浏览器打开：**http://localhost:8000** —— API 与 UI 同一个端口（API 文档 http://localhost:8000/docs，OpenAPI `http://localhost:8000/openapi.json`）。已不再起 `vite preview`，没有 `:5173`。

后端日志：`data/logs/api.log`（追加写，超 5MB 转存 `api.log.1`）。

指定别的解释器：

```bash
PYTHON=/path/to/python ./run_app.sh     # 或 VENV=/path/to/venv ./run_app.sh
```

### 开发模式（热重载）

```bash
# 终端 1：后端
.venv312/bin/python -m uvicorn backend.app.main:app --port 8000 --reload
# 终端 2：前端（HMR）
cd frontend && npm run dev
```

### 手动采集 / 重算衍生

```bash
.venv312/bin/python scripts/01_fetch_data.py     # 采集（默认按发布日历增量；走闸门管道：暂存→校验→原子切换→备份→manifest）
.venv312/bin/python scripts/01_fetch_data.py --full  # 全量采集（绕过发布日历）
.venv312/bin/python scripts/02_compute_derived.py  # 重算 derived_monthly / derived_quarterly
```

> 首次启动若 `data/macro_data.db` 不存在，`run_app.sh` 会自动跑这两个脚本。

---

## 数据流水线

### 原始数据采集

`scripts/01_fetch_data.py` 采集 16 类宏观指标（AKShare 为主，CPI/PPI 走东方财富数据中心、国债收益率直连中债信息网、人口数据走世界银行、财政/外需走 NBS 月度），清洗后经**闸门管道**落 SQLite：

| # | 表 | 指标 | 频率 |
|---|---|---|---|
| 1 | `money_supply` | M0/M1/M2 | 月 |
| 2 | `gdp` | GDP 绝对值 + 同比 | 季（累计季度解析：第1-2季度→Q2；年频用于美林/债务收入比）|
| 3 | `cpi` | CPI 同比 + 环比 | 月 |
| 4 | `ppi` | PPI 同比 | 月 |
| 5 | `pmi` | 官方/财新/非制造业/服务业 | 月 |
| 6 | `leverage` | 宏观杠杆率（CNBS 分部门）| 季 |
| 7 | `social_finance` | 社融规模增量 + 分项（akshare 主源滞后时自动走 PBoC 调查统计司 XLSX 备用源）| 月 |
| 8 | `lpr` | LPR 1Y/5Y | 月 |
| 9 | `industrial` | 工业增加值同比 + 累计 | 月 |
| 10 | `house_price` | 70 城房价指数（新建/二手 同比/环比/定基）| 月 |
| 11 | `new_credit` | 新增人民币贷款 | 月 |
| 12 | `household_income` | 居民可支配收入（NBS；2026-03 改版曾失效，2026-08-09 已修复为 akshare 1.18 新路径）| 年 |
| 13 | `bond_yield` | 10 年国债收益率（中债信息网直连，日频→月末重采样；增量：仅重抓近 2 年）| 月 |
| 14 | `demographics` | 总人口/城镇化率（NBS 官方优先、WB 长历史回退）+ 出生率/自然增长率（WB + 2025 统计公报补充）| 年 |
| 15 | `fiscal` | 国家财政预算收入/支出累计值 + 累计增长（NBS 月度，2015- 起）| 月 |
| 16 | `external_demand` | 货物进出口美元口径（NBS 月度）+ 美国 ISM 制造业 PMI | 月 |

> 注：`fiscal` / `external_demand` 不进衍生计算，经 `/table/{name}` 直通前端「财政与外需」页。

> 注：`household_income` / `demographics` 两张表在 NBS 失效期间未生成，修复后（2026-08-09）下次采集自动重建。数据源现状与实测记录详见 [`docs/data-sources-guide.md`](docs/data-sources-guide.md)。

### 采集闸门管道（`scripts/_pipeline.py`）

根治"采集覆写好数据"：生产库在最终原子 `os.replace` 前一字节不被触碰。

- **暂存快照**：复制生产库到 `macro_data.db.staging`，fetcher 全部写暂存
- **校验闸门**：每表 `TABLE_SPECS` 契约（min_rows / required cols / distinct-date 反缩水）；空/残缺/萎缩 → 拒绝 replace，暂存保留旧好表
- **原子切换**：`os.replace(staging → live)`，崩溃零损失
- **备份 + 审计**：每次采集前归档 `data/backups/`（留 10 份），写 `data/last_run.json`（每表 updated/kept_previous + 行数 + 原因）

### 衍生指标计算

`scripts/02_compute_derived.py` 合并原始表，生成两张核心表：

**`derived_monthly`**（月度主表，32 列；各源 outer join 成日期并集，发布错位期新月不丢失）
- M2-M1 剪刀差、实际利率（LPR1Y - CPI）、PMI 6 月均线、工业增加值趋势
- 社融存量增速、信贷脉冲、新增贷款同比、贷款存量增速、M1 领先 PPI 标记

**`derived_quarterly`**（季度主表）
- GDP 同比 + 4 季平滑、各部门杠杆率及季度变化速度

> 注：`derived_quarterly` 以 leverage 季频为锚、GDP 年频经 `merge_asof` + ffill 填充到各季，各部门杠杆率及季度变化列已填充（旧实现因 GDP 年频 `YYYY-01-01` 与 leverage 季末 `YYYY-{03,06,09,12}` 等值 merge 日期不重叠而全 NULL，已修复）。债务图表仍直读 `leverage` 原始表（见 DebtCycle.vue），`cycle_debt` 也直读 leverage。

### 定时刷新（可选，launchd）

默认**不安装**。需要每日自动采集时手动安装（macOS launchd，每日 10:07 触发，晚于 NBS 09:30 晨间发布）：

```bash
scripts/schedule/schedule_install.sh    # 安装（幂等，重装自动先卸载旧任务）
scripts/schedule/schedule_uninstall.sh  # 卸载
```

- 按发布日历过滤：窗口外的表自动跳过，窗口外日期近乎空转，成本可忽略
- 运行日志：`data/refresh_schedule.log`

### 数据补充（NIFD / PBoC / 统计公报，手工或 Agent 触发）

杠杆率（NIFD 季报）、社融（PBoC XLSX 备用源）、人口出生率/自然增长率（统计公报）等「自动源滞后/缺失」的数据，按 [`docs/data-supplement-runbook.md`](docs/data-supplement-runbook.md) 由 Agent 手动触发补充（含各指标发布窗口表、手动触发命令与校验规则），**不做定时任务**。数据源现状与实测记录见 [`docs/data-sources-guide.md`](docs/data-sources-guide.md)。

---

## 后端 API

FastAPI（`:8000`，同时托管 Vue 构建产物），OpenAPI 文档 `http://localhost:8000/docs`。

> `shared/openapi.json` 由 `scripts/gen_openapi.py` 从运行中的应用导出，并有 `test_openapi_drift` 守门（漂移即 CI 红）；改契约后必须重新导出。

| 方法 路径 | 作用 |
|---|---|
| `GET /api/v1/derived/monthly` | 月度主表切片（支持 `start/end/cols/align_start`）|
| `GET /api/v1/derived/quarterly` | 季度主表切片 |
| `GET /api/v1/table/{name}` | 任意原始表切片（house_price/leverage…）|
| `GET /api/v1/cycles/{merrill\|credit\|inventory\|debt}` | 周期分类 + 最新阶段 |
| `GET /api/v1/signals` | 综合信号 `[-4,+4]` + 各框架阶段 |
| `GET /api/v1/signals/history` | 信号快照历史（倒序 + 相位翻转标注 flips）|
| `GET /api/v1/real-estate?cities=…&frames=false` | 房地产三维评估（frames=false 仅 assessment，~0.5KB；默认完整三维帧 ~199KB）|
| `GET /api/v1/commentary` | AI 评论当前批（overall + 6 板块 + 出处；ok/generating/empty/error）|
| `POST /api/v1/commentary/regenerate` | 同步重新生成（🔒 令牌守门）|
| `GET /api/v1/commentary/history` | 评论批次历史索引（?ts=… 单批详情）|
| `GET/POST/PUT/DELETE /api/v1/ai/profiles[…]` | AI 配置 profiles（写操作 🔒；密钥只进钥匙串）|
| `POST /api/v1/ai/active` | 设默认 profile（🔒）|
| `GET/PUT /api/v1/ai/templates` | 提示词模板默认全文 + 覆盖（PUT 🔒）|
| `GET /api/v1/session` | 本机能力令牌（F4；同源页面自取，跨站页面读不到响应体）|
| `GET /api/v1/crcl/*` | CRCL 监控（overview / metrics / events / fundamentals / alerts / logs / refresh 🔒）|
| `GET /api/v1/refresh/status` | 上次刷新 manifest |
| `POST /api/v1/refresh` | 触发闸门管道（阻塞）|
| `GET /api/v1/refresh/stream` | SSE 流式真进度 |
| `GET /health` | 健康检查 |

- **Pydantic schema**（`backend/app/schemas/`）= 契约真相源 → OpenAPI → 前端 TS 类型，零漂移
- **缓存**：`db._load_full` + 7 个分类器 lru_cache；刷新成功后 `clear_all_caches()` 失效

---

## 前端架构

- **10 页视图**（`pages/`）：Overview / MerrillClock / CreditCycle / InventoryCycle / DebtCycle / RealEstate / Demographics / FiscalExternal（财政与外需）/ CrclMonitor（CRCL 监控）/ AISettings（AI 设置）
- **Pinia stores**：`filters`（全局日期联动——改一处全图重取）、`refresh`（SSE 进度消费）
- **图表层**（`components/charts/options.ts`）：纯函数 builder——`buildDualAxisLine` / `buildStackedArea` / `buildBarLineCombo` / `buildMultiLine` / `buildScatterQuadrant` / `buildCreditM2Chart` / `buildCreditImpulseChart` / `buildSpreadChart` / `buildRadar`
- **EChart.vue**：vue-echarts 封装，按需注册（Line/Bar/Scatter/Radar + 组件）
- **ChartTip**（`controls/`）：Teleport 到 `<body>` + 视口自适应定位，永不裁切
- **设计系统**（`design/`）：tokens.css（色板）+ echarts.theme.ts（connectNulls/dataZoom/axisPointer）+ phases.ts
- **PWA**：`public/manifest.webmanifest`，可"安装"为桌面应用

---

## 设计系统

双主题色彩体系（**Obsidian Blue** 暗色 × **Paper** 亮色，顶栏 ☾/☀ 一键换肤），定义于 `frontend/src/design/` + `stores/theme.ts`；完整方案见 `docs/design/dual-theme-plan.md`。

### 色彩体系（`tokens.css` + `tailwind.config.ts`）

双套 CSS 变量（`:root` 暗 / `[data-theme='light']` 亮），tailwind 色板全部 var() 引用；完整色值表与决策见 `docs/design/dual-theme-plan.md`。

| Token | 暗（Obsidian Blue） | 亮（Paper） | 用途 |
|---|---|---|---|
| `bg` | `#070b12` | `#f6f7f9` | 页面背景 |
| `surface` | `#0c1322` | `#ffffff` | 侧边栏、工具栏 |
| `card` | `#101a2b` | `#ffffff` | 卡片表面 |
| `accent` | `#5b8cff` 电蓝 | `#2f5bff` 皇家蓝 | 品牌强调、活跃状态、焦点环 |
| `up` / `down` / `warn` | `#34d399` / `#f87171` / `#fbbf24` | `#059669` / `#dc2626` / `#b45309` | 扩张·涨 / 紧缩·跌 / 中性·过热 |
| `text` ~ `text-4` | `#e8eef7` ~ `#7f90a4` | `#0f172a` ~ `#64748b` | 四级文字层级（双主题均过 WCAG AA） |

相位语义色（复苏绿/过热琥珀/滞胀红/衰退蓝…）双套同 hue 异明度，定义于 `design/phases.ts`；图表色板经 `chartTheme()` 按主题即时取值。

### ECharts 图表默认（`echarts.theme.ts`）

- 透明背景、极淡网格、`axisPointer: cross` 十字线
- `connectNulls: true` 原生跨接断线（替代 Plotly 的 connectgaps）
- `dataZoom`（slider + inside，滚轮已禁用防误触）对 category 时间轴自动启用
- `tooltip.confine + appendToBody` 防裁切；日期统一 `YYYY-MM-DD`
- 轴标签跨度感知抽稀：>8 年跨度在每年首个出现的类目标年份（兼容 NBS 1 月不发布），2.5–8 年到月
- 统一色板随主题切换（暗：电蓝/紫/琥珀/玉绿…；亮：皇家蓝/深紫/深琥珀/深绿…），相位微染 + 四象限角落标注

### 字体

```css
font-family: -apple-system, BlinkMacSystemFont, Inter, 'SF Pro Display', 'Segoe UI', 'Noto Sans SC', PingFang SC, sans-serif;
```

---

## 测试与质量

- **后端全量**：`cd backend && ../.venv312/bin/python -m pytest -q`（375 项：golden + 契约 + 闸门 + auth + 评论 + CRCL + 跨指标方向…）
- **管道自查**（`scripts/_pipeline_test.py`，31 项 check）：闸门全分支 + 暂存继承 + 崩溃安全 + 原子切换 + live 直写表并入。
  ⚠️ 它**不是** pytest 用例——文件里没有 `test_*` 函数，`pytest --collect-only scripts/` 收集为 0，必须手动跑：
  `.venv312/bin/python scripts/_pipeline_test.py`（全通过时打印 `✅ ALL CHECKS PASSED`，失败非零退出）
- **前端**：`vue-tsc --noEmit` 0 error（`npm run build` 已内置）+ vitest 42 例（`src/__tests__/`）
- **契约守门**：`scripts/gen_openapi.py` 导出 `shared/openapi.json`，`test_openapi_drift` 与 CI 漂移即红；前端手写 `src/api/types.ts` 与其对应
- **前端类型**：`vue-tsc --noEmit` 0 error（`npm run build` 已内置）
---

## 性能优化

- **数据库表缓存**：`db._load_full()` 按（表名, DB 版本）键控缓存，首次读盘后常驻内存，切片 < 1ms
- **分类器缓存**：分类器经 `db_versioned_cache` 按 DB 版本键控；原子切换后版本号变化即自动失效，下次读到新库（无需手动清缓存）
- **SSE 真进度**：子进程流式 stdout 数 `✅` 行驱动进度，非假 spinner
- **暂存隔离**：采集只动 staging，生产库原子切换前零接触

---

## 开发规范

详见 `CLAUDE.md` / `AGENTS.md`，核心要点：

1. **变更日志**：每次提交必须在 `CHANGELOG.md` 记录（中英双语，`[类型]` 分类）
2. **提交信息**：中英双语，中文在前、英文在后
3. **WorkTree**：新增功能/代码修改前询问是否创建 Git WorkTree 隔离
4. **极简原则**：只改必要的代码，不引入推测性功能
5. **验证导向**：先定义成功标准，再循环验证
6. **分支**：默认分支为 `main`（原 `master` 已改名）

---

## 依赖

### 后端

依赖只有一处权威来源：根目录 `requirements.txt`（人读的直接依赖）+ `requirements.lock`（逐包精确锁）。`backend/pyproject.toml` 只声明后端自身最小依赖与 pytest 配置，**不再平行重述**一份分析依赖（旧版两处各自漂移，是审计项 O-H2 的成因）。

```text
# requirements.txt —— 下界全部 == 实测在用版本（旧版 pandas>=1.5 / numpy>=1.24 跨了
# 两个 pandas 大版本，按下界解出来的组合根本跑不通本仓代码）
akshare==1.18.64                  # 精确锁：爬虫库，minor 升级会静默改列名
requests>=2.34.2,<3
yfinance>=1.4.1,<2                # crcl_collect 备用行情源（惰性 import）
pandas>=3.0.3,<4
numpy>=2.4.6,<3
scipy>=1.17.1,<2                  # 注：当前代码未直接 import
statsmodels>=0.14.6,<0.15         # 同上
fastapi>=0.137.1,<0.140
uvicorn[standard]>=0.49.0,<0.50
pydantic>=2.13.4,<3
httpx>=0.28.1,<0.29
pytest>=9.1.0,<10
```

```bash
.venv312/bin/python -m pip install -r requirements.lock   # 精确复现（63 包传递闭包）
.venv312/bin/python -m pip install -r requirements.txt    # 只按直接依赖装
```

- `requirements.lock` 由 `.venv312/bin/python -m pip list --format=freeze` 离线导出后取直接依赖的传递闭包，每个 `==` 都对应真实安装的版本
- **无 `--hash`**：生成哈希需联网向 PyPI 取每个 wheel/sdist 摘要，本仓离线环境无法生成，故不写、也不伪造；有网环境用 `uv pip compile --generate-hashes` 补齐
- **升级 akshare 必须做回归**：它决定采集出来的列名，`data/last_run.json` 记录的就是 `1.18.64`。改版本前后要跑 `scripts/diff_vintage.py`（与 `data/vintages/` 快照比对）与 `scripts/dual_sources.py`（双源交叉校验），通过后再同步改 `requirements.txt` / `requirements.lock` / `changeLog.md`

### 环境变量

`.env.example` 是模板（`.env` 已 gitignored）：`COMMENTARY_BASE_URL` / `COMMENTARY_API_KEY` / `COMMENTARY_MODEL`（AI 点评，三者同时非空才启用）、`REFRESH_TIMEOUT_S`（默认 300）、`HEALTH_STALE_DAYS`（默认 40）、`CORS_ORIGINS`、`CRCL_STARTUP_COLLECT`、`EXPAT_LIB_PATH`。仓库没有接 dotenv 自动加载，需 `set -a; source .env; set +a` 后再启动。

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

由 Claude Code / Pi 辅助开发，遵循 `CLAUDE.md` / `AGENTS.md` 项目规范。
