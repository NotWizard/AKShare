# Change Log

## 2026-06-17 — 仪表盘浅色 SaaS 样式重构（Terminal Fintech 暗色 → Light Analytics SaaS）

### 重构

- **[重构] `dashboard/config.py`**: 设计 token 由暗色翻为浅色——off-white 页面底 `#f8fafc`、白卡片表面 `#ffffff`、近黑文字 `#0f172a`、单一信任蓝强调 `#2563eb`（blue-600）、浅色友好语义色（涨 `#16a34a` / 跌 `#dc2626` / 警 `#d97706`）。图表 `plot_bg` 透明→白、`hoverlabel` 深底→白、colorway 首色改蓝。`PHASE_COLORS` 全部引用 token，自动适配
- **[重构] `dashboard/app.py` + `dashboard/assets/dark-theme.css`**: 全局 CSS 与 Dash 核心组件（DatePickerRange radix 弹窗、Dropdown）整体浅色化；`.chart-tip` tooltip 由深底纯黑阴影→白底 + tinted slate 阴影（`rgba(15,23,42,0.08)`，遵循浅底禁纯黑阴影原则）
- **[重构] `dashboard/components/`**: 阶段徽章去毛玻璃（`backdrop-filter`）→ 实色 chip；散点四象限与美林星标的白描边→深色（浅底白描边会消失）；`empty_dark_fig` 占位改白底
- **[重构] 6 个页面**: 清零绕过 token 的扁平 UI 调色板（`#2ecc71`/`#e74c3c`/`#f39c12`/`#1a73e8` 等统一映射到语义 token）；`real_estate.py` 的 9 色调色板换为浅色克制 `-600` 色系；LPR 分位带、极坐标雷达盘的深色 rgba 填充/背景改浅

### 优化

- **[优化] `dashboard/components/layout.py`**: `make_metric_tile` 数值与 delta 加 `font-variant-numeric: tabular-nums`，KPI 数字等宽对齐

### 说明

- 业务逻辑、数据采集管线（方案 D）、周期分类器、Dash 回调**零改动**，仅视觉层重构
- 旧强调色 `#6366f1`（indigo-500）即典型「AI 紫蓝」默认，本次彻底替换为信任蓝
- Geist 字体自托管作为可选后续迭代，本次保留系统字体栈 + tabular-nums 作为基线

### 验证

- `py_compile` 全部通过；app + 6 页导入无报错；渲染断言（`plot_bg/paper_bg/hoverlabel`=`#ffffff`、colorway 首色 `#2563eb`、散点描边非白、占位白、area 调色板浅色）全部通过
- 服务器 HTTP 200，首页 HTML 含浅色 token、真正暗色（`#0a0e17`/`#111827`/`#1a2332`/`#6366f1`）零残留
- 全局清扫：除有意保留的浅色中性灰 `#64748b`（slate-500）外无遗漏硬编码色

### Refactor (English)

- [refactor] `dashboard/config.py`: design tokens flipped dark → light (off-white canvas, white surfaces, near-black ink, single trust-blue accent `#2563eb`, light-friendly semantic colors). Chart plot bg → white, hoverlabel → white, colorway leads with accent; `PHASE_COLORS` auto-adapts via tokens
- [refactor] `dashboard/app.py` + `dashboard/assets/dark-theme.css`: global CSS and Dash core components (DatePickerRange radix popup, Dropdown) fully light-themed; chart-tip tooltip dark bg + pure-black shadow → white bg + tinted slate shadow
- [refactor] `dashboard/components/`: phase badges drop glassmorphism → solid chips; white marker strokes on scatter/star → dark; empty placeholder → white
- [refactor] 6 pages: mapped flat-UI hex palette (`#2ecc71`/`#e74c3c`/`#f39c12`/`#1a73e8`) to semantic tokens; replaced `real_estate.py` 9-color palette with restrained light `-600` colors; lightened dark rgba fills and polar radar backdrop

### Optimization (English)

- [opt] `dashboard/components/layout.py`: add `tabular-nums` to metric-tile values and deltas for aligned numerics

### Notes (English)

- Zero changes to business logic, data pipeline (Plan D), cycle classifiers, or Dash callbacks — visual layer only
- The old `#6366f1` (indigo-500) was a textbook AI-purple default; replaced with trust-blue
- Self-hosted Geist deferred as an optional follow-up; system font stack + tabular-nums kept as baseline

### Verification (English)

- `py_compile` passes; app + 6 pages import cleanly; render assertions (white plot/paper/hoverlabel, accent-led colorway, non-white marker stroke, white placeholder, light area palette) all pass
- Server returns HTTP 200; served HTML contains light tokens with zero true-dark residue (`#0a0e17`/`#111827`/`#1a2332`/`#6366f1`)
- Global sweep clean: only intentional light neutral `#64748b` remains

---

## 2026-06-16 — 新增居民真实杠杆率指标（债务 / 可支配收入）

### 新功能

- **[新功能] `scripts/01_fetch_data.py`**: 新增 `fetch_household_income()`，通过国家统计局的 `居民人均可支配收入` 与 `总人口` 计算居民可支配收入 aggregate（亿元），存入 `household_income` 表
- **[新功能] `scripts/02_compute_derived.py`**: 合并 `household_income` 到 `derived_quarterly`，计算 `hh_debt_to_income`（居民债务 / 可支配收入 ×100）
- **[新功能] `dashboard/pages/real_estate.py`**: 新增「居民真实杠杆率 (债务 / 可支配收入)」图表卡片，含 90% 分位与历史中位参考线

### 说明

- 居民真实杠杆率 = 居民部门债务余额 ÷ 居民可支配收入 = `居民杠杆率(债务/GDP)` ÷ `居民可支配收入/GDP`
- 该指标比单纯的「债务/GDP」更能反映居民的实际偿债压力
- 国家统计局接口 (`data.stats.gov.cn`) 在当前环境可能被拦截；脚本使用 try/except 降级，目标网络环境通常可正常采集

### New Feature

- [feat] `scripts/01_fetch_data.py`: add `fetch_household_income()` to pull per-capita disposable income and population from NBS, derive aggregate household income
- [feat] `scripts/02_compute_derived.py`: merge household income into `derived_quarterly`, compute `hh_debt_to_income`
- [feat] `dashboard/pages/real_estate.py`: add "Household debt / disposable income" chart with 90% percentile and median reference lines

### Note

- Household real leverage = household debt ÷ household disposable income = household_leverage(Debt/GDP) ÷ (disposable_income/GDP)
- More realistic than debt/GDP for gauging household debt burden
- NBS endpoint may be blocked in some network environments; script gracefully falls back

---

## 2026-06-16 — 仪表盘全面性能与交互升级

### 性能优化

- **[优化] `dashboard/app.py`**: 默认关闭 Dash debug 模式与 dev tools UI，通过 `DASH_DEBUG=1` 环境变量开启；移除 `update_title` 切换标题闪烁
- **[优化] `run_dashboard.sh`**: 增加 `DASH_DEBUG=1` 提示，默认以生产模式启动
- **[优化] `dashboard/config.py`**: `CHART_LAYOUT` 顶部边距从 48px 降到 32px，释放图表可用空间
- **[优化] `dashboard/components/layout.py`**: 新增 `make_graph_card` 统一卡片（含 `dcc.Loading` + 固定 `minHeight: 380px` + 图表 `height: 320px`），减少回调期间的布局抖动

### 交互与可读性

- **[改进] `dashboard/components/charts.py`**: 所有图表工厂函数 (`make_dual_axis_line` / `make_area_chart` / `make_scatter_quadrant` / `make_bar_line_combo` / `make_phase_timeline`) 的 `title` 改为可选参数
- **[改进] 全部 6 个页面**: 移除图表内部与卡片标题重复的 Plotly 标题，避免视觉重复，提升图表可读性
- **[改进] 全部 6 个页面**: 统一使用 `make_graph_card`，所有图表进入加载状态时显示 Dot spinner，不再白闪或塌陷
- **[修复] `dashboard/components/layout.py`**: 移除 `overflow: hidden` 修复 chart-tip tooltip 被卡片裁切的问题

### Optimization

- [opt] `dashboard/app.py`: default Dash debug off, dev tools UI off; enable via `DASH_DEBUG=1`; remove `update_title` tab flicker
- [opt] `run_dashboard.sh`: add `DASH_DEBUG=1` hint, default production-like start
- [opt] `dashboard/config.py`: reduce `CHART_LAYOUT` top margin 48px → 32px
- [opt] `dashboard/components/layout.py`: add `make_graph_card` with `dcc.Loading` and fixed `minHeight` to prevent layout shift

### UI / Readability

- [ui] `dashboard/components/charts.py`: make `title` optional in all chart factories
- [ui] All 6 pages: remove duplicate internal Plotly titles where card title already exists
- [ui] All 6 pages: wrap every chart in `dcc.Loading` via `make_graph_card` for consistent loading skeletons
- [fix] `dashboard/components/layout.py`: remove `overflow: hidden` so chart-tip tooltip is no longer clipped

---

## 2026-06-16 — 为所有图表标题添加说明 Tips

### 新功能

- **[新功能] `dashboard/components/controls.py`**: 新增 `make_chart_tip(tip)` 可复用问号图标组件，支持 `data-tip` 悬停提示
- **[新功能] `dashboard/components/layout.py`**: `make_card` 增加 `tip` 可选参数，标题行自动在右侧渲染说明图标
- **[新功能] `dashboard/app.py`**: 追加 `.chart-tip` CSS 样式，Terminal Fintech 暗色主题 tooltip（max-width 320px、阴影、底部箭头）
- **[新功能] 全部 6 个页面**: 为 24 张图表/评估卡片补充中文说明文案，解释图表计算逻辑与经济含义

### New Feature

- [feat] `dashboard/components/controls.py`: add `make_chart_tip(tip)` reusable question-mark icon with `data-tip` hover tooltip
- [feat] `dashboard/components/layout.py`: `make_card` accepts optional `tip` parameter and renders the icon to the right of the card title
- [feat] `dashboard/app.py`: add `.chart-tip` CSS for Terminal Fintech dark tooltip (max-width 320px, shadow, bottom-aligned)
- [feat] All 6 dashboard pages: add Chinese explanation tooltips for 24 charts/assessment cards covering logic and macro meaning

---

## 2026-06-15 — 仪表盘性能与图表交互优化

### 性能优化

- **[优化] `dashboard/db.py`**: 引入 `lru_cache` 全表缓存，`_load_full(table)` 首次读盘后常驻内存；`load(start,end)` 复用缓存切片，重复调用 <1ms
- **[优化] `analysis/*.py`**: 5 个分类器 (`compute_signals`/`classify_credit`/`classify_inventory`/`classify_merrill`/`classify_debt`) 加 `lru_cache(maxsize=4)`，启动期多页重复计算收敛到 1 次
- **[优化] `analysis/real_estate.py`**: 拆出 `_analyze_real_estate_impl` + `_analyze_real_estate_cached`，cities 列表转 tuple 后可哈希缓存
- **[优化] `credit_cycle.py` / `inventory_cycle.py`**: 逐月 `add_vrect` 合并为 phase 连续段，`fig.layout.shapes` 从 ~2600 降到 78-201 (≤1/13)
- 启动 import 耗时从 6-10s 降到 0.78s，切日期/城市后重算全量命中缓存

### 图表交互

- **[改进] `config.py`**: `CHART_DEFAULTS` 轴配置增加 spike (across+cursor+dot)，顶层 `hovermode='x unified'` + `spikedistance=-1` + `hoverdistance=100`
- **[改进] `charts.py`**: 新增 `HOVER_PCT` / `HOVER_PP` / `HOVER_IDX` 常量；工厂函数 `make_dual_axis_line` / `make_area_chart` / `make_bar_line_combo` 支持 hovertemplate 参数；新增 `add_phase_background(fig,dates,phases,color_map)` 段合并函数
- **[改进] 6 个页面手写 trace 统一接入 hovertemplate**: 指数取 1 位小数，百分比 / 百分点取 2 位，点位差带符号
- **[改进] 散点四象限 / 饼图 / 雷达图**: 单独 override 为 `hovermode='closest'`，避免 unified 在二维场景错位

---

## 2026-06-15 — 修复 CHART_LAYOUT update_layout 关键字冲突

### 架构修复

- **[严重] `update_layout()` 重复关键字**: `CHART_LAYOUT` 中 `legend`/`xaxis`/`yaxis`/`hoverlabel` 与页面自定义冲突，导致 11 处 TypeError
- `config.py`: 拆分为 `CHART_LAYOUT` (安全基础: bg/font/margin/colorway) + `CHART_DEFAULTS` (轴/图例/悬停)
- `charts.py`: `_apply_layout()` 智能合并 — 页面显式覆盖的 key 自动跳过默认值
- 全部 6 个页面: 移除 `**CHART_LAYOUT` 直接展开，统一通过 `_apply_layout(fig)` 应用样式
- 33 项自动化测试全部通过 (6 页图表函数 + 边界用例 + 组件 + 引擎)

---

## 2026-06-15 — 修复 Plotly 8位 hex 颜色格式错误

### Bug 修复

- **[严重] Plotly 不支持 `#RRGGBBAA` 格式**: `f'{C["accent"]}10'` 生成 `#6366f110` 导致 scatter fillcolor `ValueError`
- 新增 `_alpha(hex_color, opacity)` 辅助函数: hex + 透明度 → `rgba(r,g,b,a)` 格式
- 修复 `charts.py` 2 处 + `overview.py` 3 处 + `controls.py` 3 处颜色拼接

---

## 2026-06-15 — UI 全面重设计: Terminal Fintech 主题

### 设计系统重构 (`config.py`)

- 全新 **Terminal Fintech** 色彩体系: 深海军黑底 (`#0a0e17`) + 靛蓝强调色 (`#6366f1`) + 语义色 (翡翠绿涨/红跌/琥珀中性)
- 字体层级: `-apple-system / Inter` 全栈，3 级文字色彩层级
- Plotly 图表默认布局: 透明背景 + 极淡网格 + 悬停标签暗色 + 统一色板

### 组件层重写

- `layout.py`: 新增 `make_metric_tile()` KPI 指标卡片组件; 卡片改为细边框 + 标题分隔线
- `controls.py`: 日期选择器改为嵌入式工具栏; 按钮改为透明底 + 悬停边框; 阶段徽章改为毛玻璃发光效果
- `charts.py`: 双轴图添加主系列渐变填充; 散点图标记加白色描边; 范围滑块自定义暗色主题

### 页面层更新

- `app.py`: 侧边栏重设计 — 品牌标识 (MACRO) + 图标导航 + 活跃状态左边框 + 底部数据来源
- `overview.py`: 新增顶部 KPI 指标条 (M2增速/CPI/PMI/剪刀差/综合信号); 图表加渐变填充和零线
- 全部 6 个页面: 旧色值批量替换为新设计系统 (`C['card']`, `C['text']` 等)

### 全局 CSS

- 自定义滚动条 (深色 + 圆角)
- DatePickerRange 全暗色主题
- Dropdown 全暗色 + 悬停效果
- Plotly modebar 低透明度 + 悬停显现

---

## 2026-06-15 — 修复 Dashboard 6个审计 Bug

### Bug 修复

- **[严重] 房地产雷达图数据错误** (`real_estate.py`): 四维评估使用了不存在的 key，导致雷达图始终显示静态菱形。修复为正确的 key 映射并归一化到 0-1 范围
- **[中等] 债务周期阶段标签缺失** (`config.py`): 缺少 `leveraging`/`deleveraging`/`beautiful_deleveraging` 等 9 个阶段的颜色和中文标签，导致徽章显示英文原文
- **[轻微] 信用周期"中性"阶段无颜色** (`config.py`): 新增 `neutral` 颜色和中文标签
- **[轻微] 美林时钟时间线条宽度错误** (`merrill_clock.py`): 宽度从 ~1 年修正为 ~1 季度
- **[轻微] 债务周期页面死代码** (`debt_cycle.py`): 移除未使用的 `CITIES` 常量
- **[轻微] 未使用的 import** (`credit_cycle.py`, `real_estate.py`): 清理

---

## 2026-06-15 — 补全社会融资规模数据

### 数据补充

- **社会融资规模增量** (`social_finance` 表): 136 行月度数据（2015-01 至今），来源商务部 data.mofcom.gov.cn
  - 包含: 社融总量、人民币贷款、委托贷款、信托贷款、未贴现银行承兑汇票、企业债券、股票融资

### 数据变化

- `derived_monthly`: 26 列 → **30 列**，新增 `total`（社融总量）、`rmb_loan`（社融-人民币贷款）、`sf_stock_yoy`（社融存量同比增速）、`sf_impulse`（信贷脉冲）
- 信用周期分析现在拥有完整的社融数据 + 新增信贷数据双重指标

---

## 2026-06-15 — 补充新增信贷数据，扩展信用周期指标

### 数据补充

- **新增人民币贷款** (`new_credit` 表): 221 行月度数据，来源东方财富，覆盖 2008-2026
- **M2 年率** (`m2_yoy_jin10` 表): 337 行，来源金十数据，覆盖 1998-2026

### 脚本更新

- `scripts/01_fetch_data.py`: 新增 `fetch_new_credit()` 采集函数，加入标准采集流程
- `scripts/02_compute_derived.py`: 新增信贷数据合并到月度衍生表，计算 `loan_yoy`（新增贷款同比）和 `loan_stock_yoy`（贷款存量同比增速）

### 数据变化

- `derived_monthly`: 23 列 → **26 列**，新增 `new_rmb_loan`、`loan_yoy`、`loan_stock_yoy`
- 信用周期分析现在可使用新增贷款数据作为社融的补充指标

### 环境说明

- 社融数据源 `data.mofcom.gov.cn`（商务部）在当前环境无法连接
- 使用 Python 3.12 (`/opt/homebrew/bin/python3.12`) + `DYLD_LIBRARY_PATH` 可解决本机 LibreSSL 兼容问题
- 新增信贷数据源（东方财富）在 Python 3.9 和 3.12 下均可正常采集

---

## 2026-06-15 — 初始化中国宏观经济数据分析平台

### 新增功能

- **数据采集层** (`scripts/`)
  - `01_fetch_data.py`: AKShare 宏观数据采集脚本，支持 10 类指标（M0/M1/M2、GDP、CPI、PPI、PMI、杠杆率、社融、LPR、工业增加值、房价指数），清洗后存入 SQLite
  - `02_compute_derived.py`: 衍生指标计算（M2-M1 剪刀差、PMI 均线、工业增加值趋势、实际利率、社融存量增速等）

- **分析引擎** (`analysis/`)
  - `cycle_merrill.py`: 美林投资时钟 — GDP增速 + CPI → 复苏/过热/滞胀/衰退 四象限分类
  - `cycle_credit.py`: 信用周期 — M2增速 vs 趋势 → 宽信用/紧信用/中性 判定
  - `cycle_inventory.py`: 库存周期（基钦）— PMI + 工业增加值 → 主动补库存/被动补库存/主动去库存/被动去库存
  - `cycle_debt.py`: 债务周期（达利欧框架）— 各部门杠杆率变化 → 加杠杆/去杠杆 + 美丽/丑陋判定
  - `real_estate.py`: 房地产综合分析 — 居民杠杆空间/利率环境/价格动能 三维评分
  - `cross_indicator.py`: 交叉指标分析 — M1→PPI 领先滞后关系、M2-M1→CPI 相关性
  - `signals.py`: 综合信号系统 — 四大周期 + 交叉指标 → 综合评分 (-4 到 +4)

- **可视化看板** (`dashboard/`, Plotly Dash)
  - `app.py`: 主应用入口，深色主题侧边栏导航，6 页面多页应用
  - `pages/overview.py`: P1 总览仪表盘 — GDP/CPI/PPI/M1/M2/PMI/杠杆率 6 组图表 + 信号徽章
  - `pages/merrill_clock.py`: P2 美林时钟 — 四象限散点图 + 阶段分布饼图 + 时间线
  - `pages/credit_cycle.py`: P3 信用周期 — M2 趋势着色 + 信贷脉冲柱状图
  - `pages/inventory_cycle.py`: P4 库存周期 — PMI+工增四象限 + 阶段着色时间线
  - `pages/debt_cycle.py`: P5 债务周期 — 各部门杠杆率堆叠面积图 + 达利欧评估
  - `pages/real_estate.py`: P6 房地产 — 多城市房价对比 + 杠杆vs房价双轴 + 雷达图评估
  - `components/`: 可复用图表工厂、控件（日期选择器/城市选择器/阶段徽章）、布局组件
  - `callbacks/`: 全局回调（日期范围联动）

- **基础设施**
  - `requirements.txt`: 依赖声明 (akshare, pandas, numpy, scipy, plotly, dash, dash-bootstrap-components)
  - `run_dashboard.sh`: 一键启动脚本
  - `data/macro_data.db`: SQLite 数据库（11 张表，8,034 行数据）

### 数据覆盖

| 指标 | 数据起始 | 频率 | 行数 |
|---|---|---|---|
| 货币供应 M0/M1/M2 | 1978 | 月 | 581 |
| GDP | 2000 | 季 | 21 |
| CPI 年率/月率 | 1986/1996 | 月 | 475 |
| PPI 年率 | 1995 | 月 | 361 |
| PMI (官方+财新+非制造业+服务业) | 2005 | 月 | 321 |
| 宏观杠杆率 (各部门) | 1992 | 季 | 80 |
| LPR 利率 | 2019 | 月 | 1,534 |
| 工业增加值 | 2008 | 月 | 201 |
| 房价指数 (10城市) | 2011 | 月 | 1,840 |

---

## 2026-06-15 — Initialize China Macro Data Analysis Platform

### Features

- **Data Layer** (`scripts/`): AKShare macro data fetchers (10 indicator categories), derived metrics computation (M2-M1 spread, PMI moving averages, real interest rate, etc.)
- **Analysis Engines** (`analysis/`): 7 modules — Merrill Lynch clock, credit cycle, inventory cycle (Kitchin), debt cycle (Dalio), real estate analysis, cross-indicator leading/lag analysis, composite signal system
- **Dashboard** (`dashboard/`, Plotly Dash): 6-page interactive dashboard with dark theme, date range selectors, multi-city house price comparison, 4-quadrant scatter plots, stacked area charts, radar charts
- **Infrastructure**: requirements.txt, one-click launch script, SQLite database (11 tables, 8,034 rows)
