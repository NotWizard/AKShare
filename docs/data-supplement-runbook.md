# 数据补充运行手册（Data Supplement Runbook）

> 目的：列出所有「靠手工 / Agent 补充」的数据，写明**从哪取 / 怎么取 / 取什么**，
> 供 Agent（Claude Code / Codex）按本手册定期补充进数据库。
>
> **为什么不全自动**：NIFD（国家金融与发展实验室）无公开 API，首页/列表页 JS 渲染、
> 无法稳定发现最新报告期，详情页数字解析易碎 → 硬塞进自动刷新易污染数据。
> 故采用「Agent 读取官方报告 → 提取数值 → 走闸门入库」的半自动方式。

---

## 0. 硬编码数据清单（Hardcoded Data Inventory）

全仓排查（scripts/ analysis/ backend/ frontend/）后，**唯一硬编码的时序数据**是 NIFD 宏观杠杆率：

| 指标 | 硬编码位置 | 内容 | 当前到 | 更新方式 |
|---|---|---|---|---|
| NIFD 宏观杠杆率（居民/非金/政府/中央/地方/实体） | `scripts/nifd_leverage.py` `NIFD_DATA`（单一真相源，`01`/`03` 均 import） | 季度杠杆率(%) | 2026-06 (2026Q2) | §1 Agent 补充 |

**非时序数据（配置/分类逻辑，无需定期更新）**：
- 城市清单 `CITIES`（`frontend/src/pages/RealEstate.vue`）/ `_DEFAULT_CITIES`（`backend/app/api/v1/real_estate.py`）/ `01_fetch_data.py` 房价城市列表 —— 配置。
- `analysis/cycle_*.py`、`real_estate.py` 的 `conditions`/`choices`/`scores` —— 周期分类阈值/逻辑配置。

---

## 1. NIFD 宏观杠杆率（季度）—— 主要手工项

| 项 | 内容 |
|---|---|
| 目标表 | `leverage`（列：`date, household, non_fin_corp, gov_total, gov_central, gov_local, real_economy, fin_asset, fin_liability`） |
| 代码位置 | `scripts/nifd_leverage.py` 的 `NIFD_DATA`（单一真相源；`01`/`03` 均 `from nifd_leverage import nifd_supplement_df`） |
| 当前补到 | **2026-06（2026Q2）** |
| 数据源 | NIFD 季报 `http://www.nifd.cn/SeriesReport/Details/<id>`（实测可抓、含"杠杆率"） |
| 已知报告期 URL | 2025Q1=4712、2025Q2=4728、2025Q3=4800、2025Q4=4851、2026Q1=4896、2026Q2=4976；**2026Q3 及以后**需到 NIFD 网站「系列报告→宏观杠杆率」找最新 id（约季后 1 个月发布） |

**取什么**（%）：居民部门、非金融企业部门、政府部门、中央政府、地方政府、实体经济部门（`fin_asset`/`fin_liability` 可缺，填 None）。

**Agent 补充步骤**：
1. 到 NIFD「系列报告→宏观杠杆率」找**最新一期**季报 URL（取最新 id）。
2. 读取报告页正文，提取上述 6 个部门杠杆率数值。
3. 在 `scripts/01_fetch_data.py` 的 `_NIFD_DATA` 末尾追加一行：
   `("YYYY-MM-01", household, non_fin_corp, gov_total, gov_central, gov_local, real_economy, fin_asset, fin_liability)`
   （`MM` = 季末月 03/06/09/12；如 2026Q2 → `2026-06-01`）。
4. 运行 `.venv312/bin/python scripts/01_fetch_data.py`（走暂存→校验→原子切换闸门），再 `.venv312/bin/python scripts/02_compute_derived.py`。
5. 验证：`leverage` 表 `MAX(date)` 已更新；`derived_quarterly.hh_debt_to_income` 末行非空。

**校验规则**（防录错）：
- 各部门值应在合理区间：household 50–70、non_fin_corp 150–190、gov_total 50–75、real_economy 290–320。
- 宏观杠杆率 ≈ 居民 + 非金 + 政府（±1pp）。
- 单季变化应在 ±几 pp 内（异常大跳变需人工复核）。

---

## 2. 居民可支配收入 `household_income`（NBS，年度）—— 现已自动，监控

| 项 | 内容 |
|---|---|
| 目标表 | `household_income`（`income_per_capita, population_10k, income_abs`） |
| 源 | akshare `macro_china_nbs_nation`（NBS）。现到 2025（年度，正常）。 |
| 若 NBS 再封 | 参考 `01_fetch_data.py` 中 NBS 目录路径修正（「人民生活→全国居民人均收入情况」）；备选 World Bank。 |
| 取什么 | 人均可支配收入、总人口 → 计算 `income_abs`。 |

> 年度数据，NBS 每年初发布上年值；无需每季度补充。

---

## 3. GDP 季度（可选，非必须）

| 项 | 内容 |
|---|---|
| 现状 | `gdp` 表为年度（每年 01-01 一行，Q1 累计）。 |
| 源 | akshare `macro_china_gdp` / 东财 `RPT_ECONOMY_GDP`（实测到 2026-06）。 |
| 是否补 | 可选。债务收入比已用 Q1×4 年化近似，不补季度亦可。 |

---

## 4. PPI 环比 —— 推导值，无需手工

- 由 PPI 同比经 `_derive_ppi_mom`（同比→定基→环比）推导，无需补充。图注已标明"推导值"。

---

## 5. 社融 `social_finance`（case 2：主源滞后，有备用源）

| 项 | 内容 |
|---|---|
| 现状 | DB 到 2026-04；主源 akshare `macro_china_shrzgm`（MOFCOM 镜像）滞后 2 个月；**PBoC 官方已有 2026-06**。 |
| 备用源 | PBoC 调查统计社 XLSX：列表页 `http://www.pbc.gov.cn/diaochatongjisi/116219/116319/.../shrzgm/index.html` → 最新 `attachDir/*.xlsx`（社会融资规模增量统计表，亿元）。 |
| 怎么取 | GET 列表页→正则取最新 xlsx→`pandas.read_excel(header=None)`→数据行约第 11 行起；月份为 float（2026.05→5 月；注意 2026.1==10 月）；列对齐 DB（社会融资规模增量/人民币贷款/委托贷款/信托贷款/未贴现承兑/企业债券/股票）。 |
| 校验 | 2026.05 total=20293 亿、2026.06=33645 亿（已实测）；仅追加 date>主源max 的行。 |
| 处理 | 由 Agent 按上述补充（同 NIFD 模式）；解析脆弱，失败则保留主源。东财社融接口已下线（shrzgm.js 404），勿用。 |

---

## 6. GDP 季度（case 1：源有更新，解析器未跟上）

| 项 | 内容 |
|---|---|
| 现状 | DB gdp 到 2026-01（仅每年 Q1 行）；源 akshare `macro_china_gdp` 已有 **2026 第1-2季度**（2026-07-15 发布）。 |
| 原因 | `fetch_gdp` 的 `parse_quarter` 正则 `^(\d{4})年第(\d)季度` 丢弃累计行（"第1-2季度"），裸重抓仍停 2026-01。 |
| 处理 | 扩展正则为 `(\d{4})年第(\d)(?:-(\d))?季度`（累计取末季：第1-2季度→2026-04-01）后重抓。**注意**：gdp 变累计行后，`hh_debt_to_income` 的年化基数（现用 Q1×4）需改为用该年 Q4(10月)累计行，二者需联动改、联动验证。 |

---

## 7. 定期更新窗口与手动触发（供 Agent 手动触发，非定时任务）

> 不做定时任务。到发布窗口后由 Agent 手动触发刷新即可。

| 频率 | 指标 | 发布窗口（次月） | 触发动作 |
|---|---|---|---|
| 月 | M2/新增信贷 (PBoC) | ~10-15 日 | 跑 `01_fetch_data.py` |
| 月 | 工业 / 70城房价 (NBS) | ~15 日 | 跑 `01_fetch_data.py` |
| 月 | CPI / PPI / PMI | ~9-10 日 / PMI 月末 | 跑 `01_fetch_data.py` |
| 月 | 社融 | ~15 日（主源滞后时自动走 PBoC XLSX 备用源） | 跑 `01_fetch_data.py` |
| 月 | LPR | ~20 日 | 跑 `01_fetch_data.py` |
| 月 | 美国 ISM 制造业 PMI | ~次月 1 日（ISM 官方 / PR Newswire） | akshare Jin10 源冻结于 2025-08；按 `_ISM_SUPPLEMENT`（01_fetch_data.py）逐月补官方值后跑 `01_fetch_data.py`；2025-09~2026-05 缺口可逐月回补 |

---

## 8. 数据获取方式区分（API 直连 vs Agent 网页获取）

> 原则：能用结构化 API 的全部走 API；只有「无可用 API、仅网页/PDF/公报发布」的数据才由 Agent 读网页/搜索补全，且**只录官方发布值**，录入 `_NIFD_DATA` / `_ISM_SUPPLEMENT` 等显式补充表，与 API 数据分开记录、按月维护。

| 数据 | 获取方式 | 来源 |
|---|---|---|
| M2/M1/M0、新增信贷 | **API** | akshare（新浪/东财） |
| CPI / PPI / PMI | **API** | 东财数据中心 `RPT_ECONOMY_*` |
| GDP（累计季度） | **API** | akshare `macro_china_gdp` |
| 财政收支 | **API** | akshare `macro_china_nbs_nation`（NBS 月度） |
| 外需 货物进出口 | **API** | akshare `macro_china_nbs_nation`（NBS 月度） |
| 社融 | **API** 主源 + **文件下载** 备用 | akshare `shrzgm` + PBoC 调查统计司 XLSX（程序化解析 Excel，非读网页） |
| 债券收益率 | **API** | 中债信息网直连 |
| 人口 总人口/城镇化率 | **API** | akshare `macro_china_nbs_nation`（NBS） |
| 人口 出生率/自然增长率（2025） | **Agent 网页获取** | 《2025年国民经济和社会发展统计公报》stats.gov.cn（Web 搜索读取官方值 5.63‰ / -2.41‰） |
| 宏观杠杆率 NIFD | **Agent 网页获取** | NIFD 季报 nifd.cn / PDF（人工/Agent 读取录入 `_NIFD_DATA`） |
| 美国 ISM 制造业 PMI | **Agent 网页获取** | ISM 官方 / PR Newswire 月度发布（Workflow 逐月读取录入 `_ISM_SUPPLEMENT`） |
| CRCL 稳定币流通量/总盘/美债收益率/行情估值 | **API** | DefiLlama / Treasury.gov / AKShare / yfinance（启动+手动自动采集，见 §9.1） |
| CRCL 季报拆解/事件日历/标志位 | **手工 JSON** | Circle 新闻稿/财报会、Fed 日历、立法进展（`data/crcl_fundamentals.json`、`data/crcl_events.json`，见 §9.2） |

**Agent 网页获取的维护**：上述三项均为官方发布值，录入显式补充表；每发布周期由 Agent 按 §7 窗口读取官方网页/公报补一行，跑 `01_fetch_data.py` 入库。API 数据无需此步骤。
| 季 | GDP（累计季度） | 季后 ~1 个月（Q3≈10 月） | 跑 `01_fetch_data.py`（解析器已支持累计季度） |
| 季 | 杠杆率 NIFD | 季后 ~1 个月（Q3≈10 月） | 按 §1 由 Agent 补一期 `_NIFD_DATA` 后跑 `01_fetch_data.py` |
| 季 | Circle 季报拆解（CRCL 监控） | 2/5/8/11 月初财报 | 按 §9.2 补 `data/crcl_fundamentals.json` 一期 |
| 年 | 居民收入 / 人口 | 次年 1 月 | 跑 `01_fetch_data.py` |

**手动触发命令**（项目根目录）：
```bash
.venv312/bin/python scripts/01_fetch_data.py     # 采集（走闸门，自动追加 NIFD/PBoC 补充）
.venv312/bin/python scripts/02_compute_derived.py  # 重算衍生表
# 或一键（含后端缓存失效）: POST http://localhost:8000/api/v1/refresh
```

**触发后校验**：查各表 `MAX(date)` 是否前进到预期月份（见上表）；`derived_quarterly.hh_debt_to_income` 末行非空且量级 ~120-140。

---

## 9. CRCL 监控体系（Circle）—— API 自动 + 手工 JSON 混合

> 页面：`/crcl-monitor`；规范：`docs/CRCL监控体系.md`；进度：`docs/crcl_monitor_progress.md`。
> 存储：`data/crcl_monitor.db`（独立于 macro_data.db，互不影响）。

### 9.1 自动采集（API，无需手工）

| 数据 | 源 | 端点 / 接口 | 频率 |
|---|---|---|---|
| USDC 流通量历史 | DefiLlama | `stablecoins.llama.fi/stablecoincharts/all?stablecoin=2`（已去跨链桥重复） | 日 |
| EURC 流通量历史 | DefiLlama | `stablecoins.llama.fi/stablecoincharts/all?stablecoin=50`（欧元计价） | 日 |
| 稳定币总盘历史 | DefiLlama | `stablecoins.llama.fi/stablecoincharts/all` | 日 |
| 短端美债收益率 3M/6M/1Y | Treasury.gov | `home.treasury.gov/.../daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv`（回填 2 年；fiscaldata JSON API 实测不可用，弃用） | 日 |
| CRCL 日线 | AKShare 主 / yfinance 备 | `ak.stock_us_daily(symbol='CRCL')`；新浪端点不可达时自动切 `yf.Ticker('CRCL').history(period='max')` | 日 |
| CRCL 估值快照 | yfinance | `Ticker('CRCL').info`（marketCap/trailingPE/forwardPE/P-S/52 周） | 每次采集 |

触发：应用启动自动一次（lifespan 后台线程；`CRCL_STARTUP_COLLECT=0` 可关）+ 页内「手动刷新」（SSE 进度）。
代码：`backend/app/core/crcl_collect.py`；告警引擎 `crcl_alerts.py`（5 规则，状态变化写历史）。

### 9.2 手工补充（Agent / 人工，季度维护）

| 项 | 目标文件 | 当前补到 | 数据源 | 更新时机 |
|---|---|---|---|---|
| 季报拆解 | `data/crcl_fundamentals.json` → `quarters[]` | 2026Q1+Q2 | Circle 财报新闻稿 + 财报会转录 | 每季财报后（2/5/8/11 月初） |
| 标志位 | 同上 → `flags` | 已填 | Fed 决议 / 立法进展 | 事件发生时 |
| 宏观事件与里程碑 | `data/crcl_events.json` | 11 条 | Fed 日历 / SEC / Circle IR / 媒体 | 滚动维护 |

**Agent 补充步骤（每季财报）**：
1. 读 Circle 官方新闻稿（circle.com/pressroom）+ 财报会转录（Motley Fool 等）。
2. 提取：总收入 / 储备收入 / 其他收入 / EPS 实际与预期 / 分发成本 / USDC 期末流通 / CPN 统计。
3. 在 `quarters` 按 period 升序追加一条；派生字段：`nonreserve_share_pct` = 其他收入 ÷ 总收入 ×100；`distribution_cost_ratio_pct` = 分发成本 ÷ 总收入 ×100。
4. 刷新 `/crcl-monitor` 验证 KPI delta 与告警面板；跑 `backend/tests/test_crcl_alerts.py` 确认规则无回归。

**校验规则**（防录错）：
- `reserve_revenue_m + other_revenue_m ≈ total_revenue_m`（±1%）。
- `total_revenue_m` 当前量级 600–900；单季环比变化 >±20% 需复核。
- `nonreserve_share_pct` 应在 0–20；`distribution_cost_ratio_pct` 应在 40–75。
- EURC 无需手工（已自动采集）；若手工值与自动序列冲突，以自动序列为准。

---

## 自动化边界说明

- **AKShare `macro_cnbs`** 会在 CNBS 更新后自动带上（无需动作），但滞后大（现到 2024-12），不可依赖。
- **不建议**把 NIFD 抓取硬塞进自动刷新：发现最新期 + 解析数字不可靠，静默失败会污染数据库。
- 推荐节奏：每季度 NIFD 报告发布后（约季后 1 个月），由 Agent 按本手册 §1 补充一期。
