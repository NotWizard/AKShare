# 中国宏观经济数据分析平台

> **2026-06 架构升级**：前端升级为 **Vue 3 + ECharts**，后端 **FastAPI**；`analysis/` 分析核心与采集管道零改动保值。
> - **新版（默认）**：`./run_app.sh` — FastAPI(:8000) + Vue(:5173)，详见 `docs/architecture-upgrade.md`
> - **旧版（legacy）**：`./run_dashboard.sh` — Dash + Plotly（保留为回退）

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883)](https://vuejs.org/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-aa344d)](https://echarts.apache.org/)
[![AKShare](https://img.shields.io/badge/Data-AKShare-green)](https://www.akshare.xyz/)

一个基于 **Python + FastAPI + Vue 3 + ECharts** 构建的**中国宏观经济数据分析平台**（旧 Dash+Plotly 保留为 legacy），采用 **Terminal Fintech** 暗色主题。项目通过 [`AKShare`](https://www.akshare.xyz/) 自动采集国家统计局、中国人民银行等权威数据源，计算四大经典周期分析框架与综合宏观信号，并以高度交互的可视化方式呈现。

## 架构（新版）

```
Vue 3 + ECharts (:5173) ──HTTP/SSE── FastAPI + Pydantic (:8000) ──同进程── analysis/* (零改动)
```
- `backend/app/` — FastAPI：薄包装 `analysis/`，Pydantic schema + OpenAPI 契约
- `frontend/src/` — Vue 3 SPA：6 页视图、Pinia 全局联动、ECharts 图表
- `analysis/`、`scripts/_pipeline.py`、`data/` — **核心保值，原样复用**

---

## 目录

- [功能特性](#功能特性)
- [四大周期分析框架](#四大周期分析框架)
- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [数据流水线](#数据流水线)
- [设计系统](#设计系统)
- [性能优化](#性能优化)
- [开发规范](#开发规范)
- [许可证](#许可证)

---

## 功能特性

- **六大分析视图**：综合概览、美林时钟、信用周期、库存周期、债务周期、房地产市场
- **综合宏观信号**：聚合四大周期框架生成 `[-4, +4]`  composite score 与英文解读
- **交互式图表**：双轴折线、面积图、柱状+折线组合、四象限散点、阶段时间条、雷达图
- **阶段背景着色**：自动识别经济阶段并以半透明背景连续段高亮
- **日期范围控制**：每个页面支持自定义日期范围 + 5Y / 10Y / 20Y / 全部 快捷按钮
- **城市多选**：房地产页面支持多城市房价对比
- **本地 SQLite 数据库**：采集一次后离线运行，无需重复联网
- **高性能缓存**：数据库表与周期分类器均使用 `lru_cache`，启动与重算秒级响应

---

## 四大周期分析框架

| 框架 | 分析维度 | 阶段 | 信号来源 |
|---|---|---|---|
| **美林时钟** | GDP vs 通胀 | 复苏 / 过热 / 滞胀 / 衰退 | GDP 同比 vs 4 年趋势；CPI 同比 vs 2% |
| **信用周期** | 货币松紧 | 宽松 / 紧缩 / 中性 | M2 同比 vs 12 月均线（credit impulse） |
| **库存周期** | 供需与生产 | 主动补库 / 被动补库 / 主动去库 / 被动去库 | PMI vs 50；工业增加值 vs 6 月均线 |
| **债务周期** | 各部门杠杆率变化 | 加杠杆 / 去杠杆 / 稳定 / 美丽去杠杆 / 丑陋去杠杆等 | 家庭/企业/政府杠杆率 4 季度变化 + GDP 增速 |

**综合信号打分**：每个框架的最新阶段映射为 `-1 / 0 / +1`，四项求和后得到 `[-4, +4]` 的综合得分，并给出解读：

| 得分 | 解读 |
|---|---|
| `+3 ~ +4` | 强烈看多 — 多数周期处于扩张 |
| `+1 ~ +2` | 温和看多 — 增长信号占优 |
| `0` | 中性 — 信号相互冲突 |
| `-1 ~ -2` | 温和看空 — 逆风积聚 |
| `-3 ~ -4` | 强烈看空 — 多数周期处于收缩 |

---

## 技术架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Dashboard 层 (Dash + Plotly)                │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │ 概览    │ │美林时钟 │ │信用周期 │ │库存周期 │ │债务周期  │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘ │
│                     dashboard/components/                       │
│              charts.py | controls.py | layout.py                │
├─────────────────────────────────────────────────────────────────┤
│                     分析引擎层 (analysis/)                      │
│  cycle_merrill | cycle_credit | cycle_inventory | cycle_debt   │
│  real_estate | cross_indicator | signals                       │
├─────────────────────────────────────────────────────────────────┤
│                     数据访问层 (dashboard/db.py)                │
│              SQLite → pandas DataFrame + lru_cache              │
├─────────────────────────────────────────────────────────────────┤
│                     数据层 (data/macro_data.db)                 │
│  原始表 (11张) → derived_monthly / derived_quarterly           │
├─────────────────────────────────────────────────────────────────┤
│                     采集与衍生计算 (scripts/)                   │
│         01_fetch_data.py → 02_compute_derived.py               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 目录结构

```text
AKShare/
├── analysis/                    # 宏观分析引擎（无 UI 依赖）
│   ├── cycle_merrill.py         # 美林时钟
│   ├── cycle_credit.py          # 信用周期
│   ├── cycle_inventory.py       # 库存周期
│   ├── cycle_debt.py            # 债务周期
│   ├── real_estate.py           # 房地产三维评估
│   ├── cross_indicator.py       # 领先/滞后相关性
│   └── signals.py               # 综合信号打分
├── dashboard/                   # Dash Web 仪表盘
│   ├── app.py                   # 主应用、侧边栏、全局 CSS
│   ├── config.py                # 设计系统与常量
│   ├── db.py                    # 数据库缓存加载器
│   ├── callbacks/               # 公共回调
│   ├── components/              # 可复用组件
│   │   ├── charts.py            # Plotly 图表工厂
│   │   ├── controls.py          # 日期/城市/阶段徽章
│   │   └── layout.py            # 卡片/行/指标瓦片
│   └── pages/                   # Dash Pages 自动路由
│       ├── overview.py          # 综合概览
│       ├── merrill_clock.py     # 美林时钟
│       ├── credit_cycle.py      # 信用周期
│       ├── inventory_cycle.py   # 库存周期
│       ├── debt_cycle.py        # 债务周期
│       └── real_estate.py       # 房地产市场
├── scripts/
│   ├── 01_fetch_data.py         # 数据采集脚本
│   └── 02_compute_derived.py    # 衍生指标计算脚本
├── data/
│   └── macro_data.db            # SQLite 数据库（运行时生成）
├── run_dashboard.sh             # 一键启动脚本
├── requirements.txt             # Python 依赖
├── changeLog.md                 # 项目变更日志
├── CLAUDE.md                    # 开发规范与行为指南
└── README.md                    # 本文件
```

---

## 快速开始

### 环境要求

- Python 3.12
- macOS / Linux（macOS 需 Homebrew Python 并处理动态库路径，启动脚本已内置）
- 网络连接（首次采集数据时需要）

### 1. 安装依赖

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
```

### 2. 一键启动

```bash
./run_dashboard.sh
```

`run_dashboard.sh` 会自动完成：

1. 激活虚拟环境 `.venv312`
2. 若数据库不存在，自动运行 `01_fetch_data.py` 与 `02_compute_derived.py`
3. 检查 Dash / Plotly 等关键依赖
4. 释放 8050 端口（如被占用）
5. 启动服务并输出访问地址

浏览器打开：http://localhost:8050

### 3. 手动采集数据（可选）

```bash
python3 scripts/01_fetch_data.py
python3 scripts/02_compute_derived.py
```

### 4. 手动启动 Dashboard

```bash
python3 dashboard/app.py
```

---

## 数据流水线

### 原始数据采集

`scripts/01_fetch_data.py` 从 `AKShare` 采集 11 类宏观经济指标：

| # | 指标 | 说明 |
|---|---|---|
| 1 | 货币供应量 M0/M1/M2 | 月度，含同比增速 |
| 2 | GDP | 季度，绝对值 + 同比增速 |
| 3 | CPI | 月度，同比 + 环比 |
| 4 | PPI | 月度，同比 |
| 5 | PMI | 月度，官方 + 财新 + 非制造业 + 服务业 |
| 6 | 宏观杠杆率 | 季度，CNBS 分部门 |
| 7 | 社会融资规模增量 | 月度，含分项 |
| 8 | LPR 利率 | 月度，1 年/5 年期 |
| 9 | 工业增加值 | 月度，同比 + 累计增长 |
| 10 | 70 城房价指数 | 月度，新建商品住宅/二手住宅 同比/环比/定基 |
| 11 | 新增人民币贷款 | 月度，当月值 |

### 衍生指标计算

`scripts/02_compute_derived.py` 合并原始表，生成两张核心表：

**`derived_monthly`**（月度主表，约 30 列）
- M2-M1 剪刀差
- 实际利率（LPR 1Y - CPI）
- PMI 6 月均线
- 工业增加值趋势
- 社融存量增速、信贷脉冲
- 新增贷款同比、贷款存量增速
- M1 领先 PPI 6 个月标记

**`derived_quarterly`**（季度主表）
- GDP 同比及 4 季度平滑均线
- 各部门杠杆率及季度变化速度

---

## 设计系统

项目采用统一的 **Terminal Fintech** 暗色设计系统，定义于 `dashboard/config.py`。

### 色彩体系

| Token | 值 | 用途 |
|---|---|---|
| `bg` | `#0a0e17` | 页面背景 |
| `surface` | `#111827` | 侧边栏、工具栏 |
| `card` | `#1a2332` | 卡片表面 |
| `accent` | `#6366f1` | 靛蓝强调色、活跃状态 |
| `up` | `#10b981` | 上涨、扩张、宽松 |
| `down` | `#ef4444` | 下跌、紧缩、衰退 |
| `warn` | `#f59e0b` | 中性、过热、 caution |
| `info` | `#3b82f6` | 信息性 |
| `text` / `text_2` / `text_3` | `#f1f5f9` / `#94a3b8` / `#64748b` | 三级文字层级 |

### 图表默认配置

- 透明背景、极淡网格线
- `hovermode='x unified'` + spike crosshair
- 统一色板：`#6366f1`, `#10b981`, `#ef4444`, `#f59e0b`, `#a78bfa`, `#06b6d4`, `#f97316`, `#ec4899`
- 四象限散点、饼图、雷达图使用 `hovermode='closest'` 避免统一悬浮错位

### 字体

```python
FONT = '-apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
MONO = '"SF Mono", "JetBrains Mono", "Fira Code", "Cascadia Code", monospace'
```

---

## 性能优化

- **数据库表缓存**：`db._load_full()` 使用 `lru_cache(maxsize=32)`，首次读盘后全表常驻内存，后续日期切片 < 1ms。
- **分类器缓存**：5 个 `classify_*` 函数使用 `lru_cache(maxsize=4)`，启动期多页重复计算收敛为 1 次。
- **房地产分析缓存**：`analyze_real_estate` 将城市列表转 `tuple` 后缓存。
- **阶段背景合并**：不再逐月添加 `add_vrect`，而是合并连续同阶段段为单一矩形。`fig.layout.shapes` 从约 2600 个降到 78–201 个。
- **启动耗时**：导入耗时从 6–10s 降至约 0.78s。

---

## 开发规范

详见 `CLAUDE.md`，核心要点：

1. **变更日志**：每次提交必须在 `changeLog.md` 中记录变更。
2. **提交信息**：中英双语，中文在前、英文在后，使用 `[类型]` 条目分类（新功能/修复/优化/重构/文档等）。
3. **WorkTree**：新增功能开发前询问是否创建 Git WorkTree 以隔离工作区。
4. **极简原则**：只修改必要的代码，不引入推测性功能。
5. **验证导向**：先定义成功标准，再循环验证。

---

## 依赖

```text
akshare>=1.14.0
pandas>=1.5
numpy>=1.24
scipy>=1.10
statsmodels>=0.14
plotly>=5.18
dash>=2.14
dash-bootstrap-components>=1.5
```

---

## 许可证

本项目为宏观经济数据分析学习与研究用途构建。数据版权归原始发布机构所有。

---

## 维护者

由 Claude Code 辅助开发，遵循 `CLAUDE.md` 项目规范。
