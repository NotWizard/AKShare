# Change Log

## [Unreleased] — 数据源参考手册交叉验证与修正

### 首页重构与 AI 评论功能

### 重构

1. **[重构] `frontend/src/pages/Overview.vue`**：移除 6 张 GraphCard 及其图表 imports/refs/fetch（m2st/cpiPpi/m1m2/spread/cpiMom/rate/pmi），首页仅保留 KPI 指标卡 + 综合信号 + 信号解读 + CommentaryCard——消除架构冗余，首页聚焦指标与研判
2. **[重构] `frontend/src/pages/MerrillClock.vue`**：新增「CPI vs PPI」与「CPI 同比 vs 环比」两张图——通胀维度归美林时钟
3. **[重构] `frontend/src/pages/CreditCycle.vue`**：扩展 M2 图上下文，新增「M1 vs M2 双线」与「M2−M1 剪刀差」两张图——货币松紧核心归信贷周期
4. **[重构] `frontend/src/pages/InventoryCycle.vue`**：将原「PMI 官方 vs 财新」替换为四线版（官方/财新/非制造业/服务业）——多维 PMI 归库存周期
5. **[重构] `frontend/src/pages/DebtCycle.vue`**：新增「利率环境」图（LPR/实际利率/10Y 国债）——社融↔债券利率↔期限利差归债务周期

### 新功能

1. **[新功能] `backend/app/schemas/commentary.py`**：Commentary Pydantic 模型（ts/data_as_of/composite_score/text/model/stale/status/msg）
2. **[新功能] `backend/app/core/commentary.py`**：AI 评论核心——`build_snapshot()` 取 `compute_signals()` 快照；`call_model()` 经 httpx POST 调 OpenAI-compatible `/chat/completions`；`generate()` 带 threading 锁 + `_busy` 事件防并发；`_persist()` 写 SQLite `commentary` 表；`get_current()`；`mark_stale_and_regenerate()`；`ensure_on_startup()`——服务启动默认生成一次
3. **[新功能] `backend/app/api/v1/commentary.py`**：`GET /commentary` 取当前评论 + `POST /commentary/regenerate` 触发重跑
4. **[新功能] `backend/app/core/refresh.py`**：数据刷新后调 `commentary.mark_stale_and_regenerate()`——刷新即重跑（非标记过期）
5. **[新功能] `backend/app/main.py`**：lifespan 启动钩子调 `commentary.ensure_on_startup()`
6. **[新功能] `frontend/src/components/layout/CommentaryCard.vue`**：挂载时拉取评论，「重新分析」按钮触发重跑，generating 状态 2s 轮询，stale 提示，四态（generating/empty/error/ok）
7. **[新功能] `frontend/src/api/client.ts` + `types.ts`**：`getCommentary()` + `regenerateCommentary()` 方法 + Commentary 接口

### 说明

- **模型接入**：OpenAI-compatible 模式，经环境变量配置 `COMMENTARY_BASE_URL`/`COMMENTARY_API_KEY`/`COMMENTARY_MODEL`，用户自选服务商，通用性强
- **刷新策略**：刷新即重跑（非标记过期）；服务启动默认生成一次；生成异步（同步无必要）
- **Prompt 约束**：三段式（综合研判/四大周期逐一点评/一句话结论），temperature 0.3，只能引用快照数值不得编造，250-400 字，不给投资建议

### 验证

- 后端 golden test 6/6 无回归；`build_snapshot()` 返回 composite_score=-2、data_as_of=2026-06、frameworks 四周期齐全；未配模型时 `get_current()` 返回 `{status:empty, msg:暂无评论}`
- 前端 `vue-tsc --noEmit` 0 error；vite proxy + SPA fallback + API proxy 经 curl 验证
- Chrome 截图确认：overview 渲染 KPI 卡（M2 8.0%/CPI 1.0%/PMI 49.4 等）、信号 -2.0、CommentaryCard 显示「暂无评论 — 点击「重新分析」生成（需配置模型）」、跨指标解读段保留

### Refactor (English)

1. **[refactor] `frontend/src/pages/Overview.vue`**: removed 6 GraphCards + chart imports/refs/fetches (m2st/cpiPpi/m1m2/spread/cpiMom/rate/pmi); homepage now only KPI tiles + composite signal + interpretation + CommentaryCard — eliminate architecture redundancy, homepage focuses on metrics & judgment
2. **[refactor] `MerrillClock.vue`**: added "CPI vs PPI" and "CPI YoY vs MoM" charts — inflation dimension to Merrill Clock
3. **[refactor] `CreditCycle.vue`**: extended M2 chart context, added "M1 vs M2 dual-line" and "M2−M1 spread" charts — monetary tightening core to Credit Cycle
4. **[refactor] `InventoryCycle.vue`**: replaced "PMI official vs Caixin" with 4-line version (official/Caixin/non-manufacturing/services) — multi-dim PMI to Inventory Cycle
5. **[refactor] `DebtCycle.vue`**: added "利率环境" chart (LPR/real-rate/10Y bond) — social-financing↔bond-rate↔term-spread to Debt Cycle

### New Feature (English)

1. **[feat] `backend/app/schemas/commentary.py`**: Commentary Pydantic model (ts/data_as_of/composite_score/text/model/stale/status/msg)
2. **[feat] `backend/app/core/commentary.py`**: AI commentary core — `build_snapshot()` from `compute_signals()`; `call_model()` via httpx POST to OpenAI-compatible `/chat/completions`; `generate()` with threading lock + `_busy` event; `_persist()` to SQLite `commentary` table; `get_current()`; `mark_stale_and_regenerate()`; `ensure_on_startup()` — auto-generate on service start
3. **[feat] `backend/app/api/v1/commentary.py`**: `GET /commentary` + `POST /commentary/regenerate`
4. **[feat] `backend/app/core/refresh.py`**: after data refresh calls `commentary.mark_stale_and_regenerate()` — refresh-as-rerun (not mark-stale)
5. **[feat] `backend/app/main.py`**: lifespan startup hook calls `commentary.ensure_on_startup()`
6. **[feat] `frontend/src/components/layout/CommentaryCard.vue`**: fetch on mount, "重新分析" button triggers rerun, 2s polling when generating, stale hint, 4 states (generating/empty/error/ok)
7. **[feat] `frontend/src/api/client.ts` + `types.ts`**: `getCommentary()` + `regenerateCommentary()` + Commentary interface

### Notes (English)

- **Model integration**: OpenAI-compatible mode, configured via env vars `COMMENTARY_BASE_URL`/`COMMENTARY_API_KEY`/`COMMENTARY_MODEL`, user picks provider, high generality
- **Refresh policy**: refresh-as-rerun (not mark-stale); auto-generate on service startup; async generation (sync unnecessary)
- **Prompt constraints**: 3-paragraph (综合研判/four-cycles-point-by-point/one-line conclusion), temperature 0.3, only cite snapshot values no fabrication, 250-400 chars, no investment advice

### Verification (English)

- Backend golden test 6/6 no regression; `build_snapshot()` returns composite_score=-2, data_as_of=2026-06, all 4 cycle frameworks present; unconfigured model returns `{status:empty, msg:暂无评论}` from `get_current()`
- Frontend `vue-tsc --noEmit` 0 errors; vite proxy + SPA fallback + API proxy verified via curl
- Chrome screenshot confirms: overview renders KPI tiles (M2 8.0%/CPI 1.0%/PMI 49.4 etc.), signal -2.0, CommentaryCard shows "暂无评论 — 点击「重新分析」生成（需配置模型）", cross-indicator interpretation section retained

---

### 债务周期杠杆率数据刷新保护

### 修复

1. **[修复] `scripts/01_fetch_data.py` `fetch_leverage`**：刷新数据时 `ak.macro_cnbs()` 仅返回 80 行（至 2024-Q4），`save_to_db` 以 `if_exists="replace"` 覆盖整张 leverage 表——手动补充的 NIFD 数据（5 个季度）会被清除。新增保留逻辑：在 `save_to_db` 前从 staging 表中读取日期晚于 CNBS 最新日期的行，合并入 DataFrame，使刷新后仍保留补充数据。当 AKShare 更新 `macro_cnbs()` 至 2025+ 后，补充数据自然被更新数据取代。

### 验证

- 模拟刷新测试：staging DB 85 行 → `ak.macro_cnbs()` 80 行 → 保留 5 行 NIFD 数据 → 最终 85 行，max date 2026-03-01
- 未修复时确认数据丢失：85 → 80 行，max date 2024-12-01

### Fix (English)

1. **[fix] `scripts/01_fetch_data.py` `fetch_leverage`**: on data refresh, `ak.macro_cnbs()` returns 80 rows (through 2024-Q4); `save_to_db` with `if_exists="replace"` overwrites the entire leverage table — manually-supplemented NIFD data (5 quarters) would be wiped. Added preservation logic: before `save_to_db`, read rows from the staging table with dates newer than CNBS max and merge into the DataFrame. When AKShare updates `macro_cnbs()` to 2025+, supplemented data is naturally superseded by fresher CNBS data.

### Verification (English)

- Simulated refresh test: staging DB 85 rows -> `ak.macro_cnbs()` 80 rows -> preserved 5 NIFD rows -> final 85 rows, max date 2026-03-01
- Confirmed data loss without fix: 85 -> 80 rows, max date 2024-12-01

---

### 数据源文档更新

### 文档

1. **[文档] `docs/data-sources-guide.md` §五 宏观杠杆率**：从 5 行扩展为完整章节——新增 CNBS 数据滞后说明、NIFD 季度报告备选数据源（含 5 份报告 URL）、补充脚本与刷新保护机制说明

### Documentation (English)

1. **[docs] `docs/data-sources-guide.md` §五 macro leverage**: expanded from 5 lines to a full section — added CNBS data lag note, NIFD quarterly report alternative source (with 5 report URLs), supplement script and refresh-protection mechanism documentation

---

### 债务周期杠杆率数据补全（NIFD 季度报告）

### 数据补全

1. **[数据] `scripts/03_supplement_leverage.py`**：新增杠杆率数据补充脚本——`ak.macro_cnbs()` (AKShare/CNBS) 仅更新至 2024-Q4，从 NIFD（国家金融与发展实验室）季度报告 PDF 中提取 2025Q1–2026Q1 共 5 个季度的居民/非金融企业/政府（中央+地方）分项杠杆率数据，写入 `leverage` 表
2. **[数据] NIFD 报告交叉验证**：5 份季度报告 PDF（2025Q1/Q2/Q3/Q4 + 2026Q1）下载并解析，各季度数值通过报告间交叉验证（季度变化之和 = 全年涨幅），微小差异（≤0.1pp）来自 NIFD 四舍五入

### 验证

- DB: `leverage` 表从 80 行 → 85 行，最后日期从 2024-12-01 → 2026-03-01
- API: `GET /api/v1/table/leverage` 返回 85 条记录，含 2025Q1–2026Q1 全部分项数据
- 前端 Vite proxy 验证：`curl localhost:5173/api/v1/table/leverage` 返回 14.7KB JSON，含 2026-03-01 记录

### Data Supplement (English)

1. **[data] `scripts/03_supplement_leverage.py`**: new leverage data supplement script — `ak.macro_cnbs()` (AKShare/CNBS) only updated through 2024-Q4; extracted 2025Q1–2026Q1 (5 quarters) of household/non-financial-corp/government (central+local) leverage ratios from NIFD quarterly report PDFs, inserted into `leverage` table
2. **[data] NIFD report cross-verification**: 5 quarterly report PDFs (2025Q1/Q2/Q3/Q4 + 2026Q1) downloaded and parsed; all values cross-verified across reports (quarterly changes sum to annual totals), minor differences (≤0.1pp) from NIFD rounding

### Verification (English)

- DB: `leverage` table 80 → 85 rows, latest date 2024-12-01 → 2026-03-01
- API: `GET /api/v1/table/leverage` returns 85 records with all sector breakdowns through 2026-Q1
- Frontend proxy verified: `curl localhost:5173/api/v1/table/leverage` returns 14.7KB JSON including 2026-03-01 record

---

### 变更

1. **[修复] `docs/data-sources-guide.md` §五 货币供应量**：`macro_china_supply_of_money()` 在 AKShare 中不存在，替换为正确的 `macro_china_m2_yearly()`，补充 `macro_china_money_supply()` 备选方案
2. **[修复] §三 新浪财经新闻 API**：原 URL `CN_MarketData.getKLineData` 实际返回 K 线数据而非新闻，替换为正确的 `feed.mix.sina.com.cn/api/roll/get` 新闻接口，附完整参数和代码示例
3. **[修复] §六 Tushare 代码示例**：`ts_code='H30269.CSI'` 格式错误（index_dailybasic 仅支持 SH/SZ 后缀），改为 `ts_code='000300.SH'`
4. **[修复] §三 东方财富新闻 API**：重写为正确的 JSONP 嵌套参数结构和解析代码
5. **[文档] §六 Tushare 输出字段**：补齐全部 12 个字段（新增 total_mv/float_mv/total_share/float_share/free_share/turnover_rate）
6. **[文档] 官方文档链接**：新增 5 个链接——AKShare 数据字典 + GitHub、Tushare index_dailybasic 接口文档 + 积分权限、yfinance API 参考
7. **[文档] FAQ**：新增 2 条——新浪新闻 API 403 解决方案、`macro_china_supply_of_money` 不存在说明
8. **[文档] .gitignore**：补全 `data/` 下遗漏的运行时文件（*.csv、.dashcache/、.refresh.lock）
9. **[修复] `backend/app/api/v1/data.py` align_start**：排除全 null 列后再做 `.all()` 对齐——`bond_10y` 全 null 曾导致利率图 align 完全失效（从 1978 空白起），修复后恢复 2019-09 起点，其余图表零影响
10. **[修复] `scripts/01_fetch_data.py` fetch_demographics**：NBS `data.stats.gov.cn` 自 2026-03 起被 WAF 封禁（403 UrlACL），改用 World Bank API 作为数据源（66 年数据 1960-2025），指标映射：population / urbanization_rate / birth_rate / natural_growth_rate
11. **[修复] `backend/app/api/v1/data.py` _ALLOWED_TABLES**：白名单补充 `demographics`，此前缺失导致 `/table/demographics` 返回 404
12. **[文档] `docs/data-sources-guide.md` §十一**：新增"已知数据源问题"章节，记录 NBS 平台迁移状态（旧 API 废弃 + 新 API 数据层未部署）、受影响函数、替代方案、新 API 参数备忘

### 验证

- 8 个数据源逐一联网验证（Tavily Search + WebFetch 直接调用 API）
- 腾讯 qt.gtimg.cn、web.ifzq.gtimg.cn 接口实测返回正常
- 东方财富 search-api-web.eastmoney.com 新闻搜索 API 实测返回 JSONP 新闻数据
- AKShare 官方文档确认 `macro_china_m2_yearly` 为唯一 M2 函数
- Tushare 官方文档确认 index_dailybasic 参数与积分要求（4000+）

---

### 新功能

- **[新功能] `scripts/01_fetch_data.py`**: 新增 `fetch_bond_yield`——`ak.bond_china_yield` 采「中债国债收益率曲线」的 10 年列，日频存 `bond_yield` 表（date, y_10y）；`_pipeline.TABLE_SPECS` 加闸门（min_rows 1000）；加入 fetchers 列表
- **[新功能] `scripts/02_compute_derived.py`**: 合并 `bond_10y` 到 `derived_monthly`——日频→月频重采样（取每月末值、月初归一对齐 monthly 锚点）；`bond` 表空时预创建全空列，保证列结构稳定（前端始终能请求到该列，采集失败时优雅降级为无线而非缺列报错）
- **[新功能] `frontend/src/pages/Overview.vue`**: 「利率环境」图加 10Y 国债线（`bond_10y`），与 LPR1Y/5Y/实际利率同图，无风险利率锚
- **[新功能] `frontend/src/pages/RealEstate.vue`**: 新增「利率环境（房贷锚）」图——5Y LPR（房贷定价基准）+ 实际利率（LPR1Y−CPI），与房价同页看利率对房市支撑。零采集（`lpr_5y`/`real_rate` 已在 derived_monthly）

### 说明

- **10Y 国债采集网络限制**：中债网（yield.chinabond.com.cn）全历史大批量采集在当前沙箱被限流/拒连（小范围可用，59 行验证通过）；换可达网络跑 `python scripts/01_fetch_data.py` 即填充 `bond_yield` → `derived_monthly.bond_10y`
- **LPR 进房地产页**：零后端改动，纯前端加图

### 验证

- `vue-tsc --noEmit` 0 error；后端 golden test 6/6 无回归；`bond_10y` 列存在（采集失败环境 581 行全 NaN，优雅降级；联网后填充）

### New Feature (English)

- [feat] `scripts/01_fetch_data.py`: add `fetch_bond_yield` — `ak.bond_china_yield` (the "中债国债收益率曲线" curve), 10Y column, daily, stored as `bond_yield` (date, y_10y); added to `_pipeline.TABLE_SPECS` (min_rows 1000) and the fetcher list
- [feat] `scripts/02_compute_derived.py`: merge `bond_10y` into `derived_monthly` — resample daily→monthly (last value of each month, aligned to month-start); pre-create an all-null column when `bond` is empty so the schema stays stable (frontend always gets the column; graceful degradation on fetch failure)
- [feat] `Overview.vue`: add a 10Y-bond line to the "利率环境" chart (`bond_10y`) alongside LPR1Y/5Y/real-rate — the risk-free rate anchor
- [feat] `RealEstate.vue`: add a "利率环境（房贷锚）" chart — 5Y LPR (mortgage pricing base) + real rate (LPR1Y − CPI), on the same page as house prices. Zero backend change (`lpr_5y`/`real_rate` already in derived_monthly)

### Notes (English)

- **10Y bond fetch network limit**: the chinabond host rate-limits/refuses full-history bulk fetches in this sandbox (small-range fetch works, 59 rows verified); run `python scripts/01_fetch_data.py` on a network where the host is reachable to populate `bond_yield` → `derived_monthly.bond_10y`
- **LPR on the real-estate page**: zero backend change, frontend-only chart

### Verification (English)

- `vue-tsc --noEmit` 0 errors; backend golden test 6/6 no regression; `bond_10y` column present (581 rows all-NaN in the fetch-failed sandbox, graceful degradation; populated once the network is reachable)

---

### 刷新按钮端到端失效修复（刷新后图表/KPI/评论自动重取）

### 修复

1. **[修复] `frontend/src/stores/refresh.ts`**：SSE `payload.done` 仅更新 `lastResult`，无任何信号通知页面数据已变——刷新进度条跑完、显示「刷新完成」，但 7 页图表/KPI/综合信号全停留旧数据，须换 preset 或切路由才重取。新增 `lastRefreshedAt` ref，`payload.done` 时 `= Date.now()` 并暴露。
2. **[修复] `frontend/src/pages/*.vue`（7 页：Overview/MerrillClock/CreditCycle/DebtCycle/InventoryCycle/RealEstate/Demographics）**：各 import `useRefreshStore` + watchEffect 追加 `void refresh.lastRefreshedAt`，复用既有 `reqId` race-guard 丢弃刷新途中陈旧的 preset-load 结果。
3. **[修复] `frontend/src/components/layout/CommentaryCard.vue`**：抽 `pull()`（fetch + 若 status==='generating' 则 startPolling），`onMounted(pull)` + `watch(refresh.lastRefreshedAt, pull)`——刷新后 backend 已 `mark_stale_and_regenerate`，前端自动重取评论并按需轮询。

### 验证

1. `vue-tsc --noEmit` 0 error；`vite build` 成功（624 模块）。
2. 独立审查 Agent 确认：响应式正确（`void refresh.lastRefreshedAt` 在 watchEffect 内建立 dep）、reqId 并发安全（stale 结果丢弃）、CommentaryCard 无双轮询（`startPolling` 先 `stopPolling`）、无首屏双 fetch（非 immediate watch 不在 mount 触发）、backend 顺序安全（SSE `done` 在 `run_refresh` 返回后发出=子进程原子 `os.replace` 交换 + `clear_all_caches` 之后，重取读到已提交新数据）。

### Fix (English)

1. **[fix] `frontend/src/stores/refresh.ts`**: SSE `payload.done` only updated `lastResult` with no signal that data changed — the progress bar filled and "刷新完成" showed, but all 7 pages' charts/KPIs/composite-signal stayed stale until preset change or route switch. Added `lastRefreshedAt` ref, set `= Date.now()` on `payload.done`, exposed.
2. **[fix] `frontend/src/pages/*.vue` (7 pages: Overview/MerrillClock/CreditCycle/DebtCycle/InventoryCycle/RealEstate/Demographics)**: each imports `useRefreshStore` + adds `void refresh.lastRefreshedAt` to the existing `watchEffect`; reuses the existing `reqId` race-guard to discard stale preset-load results during refresh.
3. **[fix] `frontend/src/components/layout/CommentaryCard.vue`**: extracted `pull()` (fetch + startPolling if status==='generating'), `onMounted(pull)` + `watch(refresh.lastRefreshedAt, pull)` — backend regenerates commentary on refresh (`mark_stale_and_regenerate`), frontend now auto re-fetches and polls as needed.

### Verification (English)

1. `vue-tsc --noEmit` 0 errors; `vite build` success (624 modules).
2. Independent review agent confirmed: reactivity correct (`void refresh.lastRefreshedAt` registers the watchEffect dep), reqId race-safe (stale results discarded), CommentaryCard no double-poll (`startPolling` calls `stopPolling` first), no initial-mount double-fetch (non-immediate watch doesn't fire on mount), backend ordering safe (SSE `done` emitted after `run_refresh` returns = subprocess atomic `os.replace` swap + `clear_all_caches`, so refetch reads committed fresh data).

---

### derived_quarterly 杠杆率空列修复（月份约定不匹配根治）

### 修复

1. **[修复] `scripts/02_compute_derived.py`**：季度表改为以 leverage 季频为锚（季末日期经 `dt.to_period("Q").dt.to_timestamp()` 归一到季初），GDP 年频经 `pd.merge_asof(direction="backward")` + `ffill` 填充到各季——根治旧实现 GDP `YYYY-01-01` 与 leverage 季末 `YYYY-{03,06,09,12}` 等值 merge 日期不重叠、derived_quarterly 杠杆率列全 NULL（0/21 → 80/80）。`gdp_yoy_smooth` 改 `rolling(16, min_periods=4)`（季度上等价 4 年；leverage 缺失的 gdp-only 回退分支仍用 `rolling(4)`）。
2. **[修复] `analysis/cycle_merrill.py`**：读 derived_quarterly 后按年去重（`drop_duplicates(subset=["year"], keep="last")`）恢复年频——缓解季度化（21→80 行）后 `rolling(window=4)` 从 4 年窗口退化为 1 年窗口、阶段判定偏向滞胀/衰退的回归。
3. **[文档] `README.md`**：更正「derived_quarterly leverage 列因频率不匹配为空」的误导表述（实为月份约定不匹配，已修复）。
4. **[文档] `frontend/src/pages/DebtCycle.vue`**：同步更新引用该缺陷的注释。

### 验证

1. `02_compute_derived.py` 重算：derived_quarterly 21 行→80 行；household/non_fin_corp/gov_total/gov_central/gov_local/real_economy 全 80/80 非空（旧 0/21）；gdp_yoy 76/80、gdp_yoy_smooth 73/80（首 4 季无前值，边界正确）。
2. `cycle_merrill.py` 阶段健康混合（recovery/overheating/stagflation/recession，非全滞胀衰退）；2024 `gdp_trend=8.425`=(18.9+4.8+4.7+5.3)/4 确认 4 年窗口保留。`cycle_debt.py` 正常分类（手动 backward-fill 循环，约定无关）。
3. 后端 golden test 6/6 无回归。
4. 独立审查 Agent 确认：merge_asof backward 正确（Q4 不窃次年 GDP——2024 各季均得 5.3、2023 Q4 得 4.7）、dedup-by-year 缓解生效、无下游消费者受影响（`/derived/quarterly` 直供、DebtCycle 读 leverage 原始表、`getDerivedQuarterly` 前端无调用方）。

### Fix (English)

1. **[fix] `scripts/02_compute_derived.py`**: quarterly table now anchors on leverage quarterly freq (quarter-end → quarter-start via `dt.to_period("Q").dt.to_timestamp()`), GDP annual freq brought in via `pd.merge_asof(direction="backward")` + `ffill` — root-causes the old equality-merge miss where GDP `YYYY-01-01` vs leverage quarter-end `YYYY-{03,06,09,12}` hit 0 rows, leaving derived_quarterly leverage columns all NULL (0/21 → 80/80). `gdp_yoy_smooth` now `rolling(16, min_periods=4)` (4-year equiv on quarterly; the gdp-only fallback still uses `rolling(4)`).
2. **[fix] `analysis/cycle_merrill.py`**: after reading derived_quarterly, dedup-by-year (`drop_duplicates(subset=["year"], keep="last")`) restores annual granularity — mitigates the regression where `rolling(window=4)` would degrade from a 4-year to a 1-year window on the new 80-row quarterly frame, biasing phase classification toward stagflation/recession.
3. **[doc] `README.md`**: corrected the misleading "derived_quarterly leverage columns empty due to frequency mismatch" note (real cause: month-convention mismatch, now fixed).
4. **[doc] `frontend/src/pages/DebtCycle.vue`**: updated the comment referencing the fixed defect.

### Verification (English)

1. `02_compute_derived.py` recompute: derived_quarterly 21 → 80 rows; household/non_fin_corp/gov_total/gov_central/gov_local/real_economy all 80/80 non-null (was 0/21); gdp_yoy 76/80, gdp_yoy_smooth 73/80 (first 4 quarters have no prior GDP, correct boundary).
2. `cycle_merrill.py` healthy phase mix (recovery/overheating/stagflation/recession, not all stagflation/recession); 2024 `gdp_trend=8.425`=(18.9+4.8+4.7+5.3)/4 confirms 4-year window preserved. `cycle_debt.py` classifies normally (manual backward-fill loop, convention-agnostic).
3. Backend golden test 6/6 no regression.
4. Independent review agent confirmed: merge_asof backward correct (Q4 doesn't steal next-year GDP — 2024 quarters all get 5.3, 2023 Q4 gets 4.7), dedup-by-year mitigation effective, no downstream consumer affected (`/derived/quarterly` serves raw, DebtCycle reads leverage raw, `getDerivedQuarterly` has no frontend caller).

---

### RefreshBar 刷新取消按钮 + 进度条 a11y

### 修复

1. **[修复] `frontend/src/components/layout/RefreshBar.vue`**：刷新进行中暴露「取消」按钮（`v-if="refresh.running"`，`@click="refresh.cancel()"`）——store 早有 `cancel()`（SSE AbortController 中止，commit c0fa543）但 UI 从未暴露，用户此前只能关 tab 取消。
2. **[无障碍] `frontend/src/components/layout/RefreshBar.vue`**：进度条加 `role="progressbar"` + `aria-valuenow/min/max`（progress 0..1→0..100）；结果消息加 `role="status" aria-live="polite"`——SR 可播报刷新进度与完成/取消/失败。

### 验证

1. `vue-tsc --noEmit` 0 error；`vite build` 2.25s 成功。
2. 独立审查 Agent 确认：cancel→AbortError→catch→finally 链产生干净终态（running=false、abortController=null、lastResult='刷新已取消'），取消按钮 v-if 同 tick 卸载；不运行时 `null?.abort()` 幂等无抛；移动端进度条 flex-1 吸收 ~50px 可接受，无需断点隐藏。

### Fix (English)

1. **[fix] `frontend/src/components/layout/RefreshBar.vue`**: expose a "取消" (cancel) button while refreshing (`v-if="refresh.running"`, `@click="refresh.cancel()"`) — the store already had `cancel()` (SSE AbortController abort, commit c0fa543) but the UI never exposed it; users could previously only cancel by closing the tab.
2. **[a11y] `frontend/src/components/layout/RefreshBar.vue`**: progress bar gets `role="progressbar"` + `aria-valuenow/min/max` (progress 0..1→0..100); result message gets `role="status" aria-live="polite"` — SR can announce refresh progress and completion/cancel/failure.

### Verification (English)

1. `vue-tsc --noEmit` 0 errors; `vite build` 2.25s success.
2. Independent review agent confirmed: cancel→AbortError→catch→finally chain yields a clean end state (running=false, abortController=null, lastResult='刷新已取消'), 取消 button v-if unmounts same tick; `null?.abort()` is idempotent no-throw when not running; mobile progress bar (flex-1) absorbs ~50px delta acceptably, no breakpoint hiding needed.

---

### 删除未使用的 baseLine 导出

### 清理

1. **[清理] `frontend/src/design/echarts.theme.ts`**：删除零调用方的 `baseLine` 线序列工厂导出及注释——9 个 builder 与 RealEstate 内联手写 `type:'line',connectNulls:true,...` 均未用此工厂，`grep baseLine frontend/src` 仅定义点无调用。

### 验证

- `vue-tsc --noEmit` 0 error；`vite build` 成功；`grep baseLine frontend/src` 零命中（仅陈旧 worktree 副本残留）。

### Cleanup (English)

1. **[cleanup] `frontend/src/design/echarts.theme.ts`**: removed the zero-caller `baseLine` line-series factory export + comment — the 9 builders + RealEstate inline all hand-write `type:'line',connectNulls:true,...` without this factory; `grep baseLine frontend/src` shows only the definition, no call sites.

### Verification (English)

- `vue-tsc --noEmit` 0 errors; `vite build` success; `grep baseLine frontend/src` zero hits (only the stale worktree copy remains).

---

### 扁平化 _VALUE_COL 死元组

### 清理

1. **[清理] `backend/app/api/v1/cycles.py`**：`_VALUE_COL` 第二元组元素（如 `"credit_impulse"`）从未被读取（仅 `[0]` 访问，全仓无 `[1]`）。扁平化为字符串 dict + `_VALUE_COL[name][0]`→`_VALUE_COL[name]`，移除误导性死数据。

### 验证

- golden test 6/6（覆盖 `/cycles` 端点）；`credit_impulse` 全仓零引用（该列本身在 cycle_credit/signals 由 dataframe 读，与此 dict 无关）；`_VALUE_COL` 模块私有（前导下划线，无外部 import）。

### Cleanup (English)

1. **[cleanup] `backend/app/api/v1/cycles.py`**: `_VALUE_COL`'s second tuple element (e.g. `"credit_impulse"`) was never read (only `[0]` accessed, no `[1]` repo-wide). Flattened to a string dict + `_VALUE_COL[name][0]`→`_VALUE_COL[name]`, removing misleading dead data.

### Verification (English)

- golden test 6/6 (covers `/cycles` endpoints); `credit_impulse` zero refs repo-wide (the column itself is read from dataframes in cycle_credit/signals, unrelated to this dict); `_VALUE_COL` is module-private (leading underscore, no external import).

---

### refresh.py expat 路径改为可覆盖 env var

### 清理

1. **[清理] `backend/app/core/refresh.py`**：`_subprocess_env` 写死的 `/opt/homebrew/opt/expat/lib` 改 `os.getenv("EXPAT_LIB_PATH", "/opt/homebrew/opt/expat/lib")`——Apple Silicon 默认不变（行为保留），加 Intel macs（`/usr/local/opt/expat/lib`）与 Linux（空）覆盖旋钮。直接经 uvicorn/pytest 启动时（绕过 run_app.sh 的 `DYLD_LIBRARY_PATH`）本处是唯一来源，故默认不可空。

### 验证

- 默认与旧值 + `run_app.sh:13` 字节一致（Apple Silicon 行为保留）；`os` 已 import；无测试覆盖（runtime infra，可接受）；独立审查 Agent 通过（无工作流破坏）。

### Cleanup (English)

1. **[cleanup] `backend/app/core/refresh.py`**: `_subprocess_env`'s hardcoded `/opt/homebrew/opt/expat/lib` → `os.getenv("EXPAT_LIB_PATH", "/opt/homebrew/opt/expat/lib")` — Apple-Silicon default unchanged (behavior-preserving), adds an override knob for Intel macs (`/usr/local/opt/expat/lib`) and Linux (empty). When launched directly via uvicorn/pytest (bypassing run_app.sh's `DYLD_LIBRARY_PATH`) this is the sole source, so the default can't be empty.

### Verification (English)

- Default byte-identical to old value + `run_app.sh:13` (Apple-Silicon behavior preserved); `os` already imported; no test coverage (runtime infra, acceptable); independent review agent approved (no workflow break).

---

### 修复 frontend/package-lock.json：resolved URL 由阿里内网源改 registry.npmjs.org

### 修复

1. **[修复] `frontend/package-lock.json`**：211 个 `resolved` URL 由 `registry.anpm.alibaba-inc.com`（阿里内网源，lockfile 在内网机器生成）改 `registry.npmjs.org`（对齐全局 `npm config get registry`）——离内网环境 `npm install` ECONNRESET（`rollup-4.62.0.tgz` TLS 失败）根治。

### 验证

- `npm install --no-audit --no-fund` 成功（991ms，exit 0，无 ECONNRESET）；lockfile JSON 有效；`resolved` 字段总数不变（纯 URL 域名重写，零版本/条目变更）；反向 sed 还原与备份逐字节一致确认仅改域名。

### Fix (English)

1. **[fix] `frontend/package-lock.json`**: 211 `resolved` URLs from `registry.anpm.alibaba-inc.com` (Alibaba intranet registry; lockfile generated on an intranet machine) → `registry.npmjs.org` (aligns with global `npm config get registry`) — root-causes `npm install` ECONNRESET off-intranet (`rollup-4.62.0.tgz` TLS failure).

### Verification (English)

- `npm install --no-audit --no-fund` success (991ms, exit 0, no ECONNRESET); lockfile JSON valid; `resolved` field count unchanged (pure URL-domain rewrite, zero version/entry changes); reverse-sed vs backup byte-identical confirms only the domain changed.

---

### ChartTip ⓘ 键盘/触屏可达

### 无障碍

1. **[无障碍] `frontend/src/components/controls/ChartTip.vue`**：ⓘ 说明图标原仅 `@mouseenter`/`@mouseleave`，键盘用户无法触发、触屏无法悬停。加 `tabindex=0` + `role=button` + `aria-label` + `@focus=show` + `@blur=hide` + `@keydown.escape=hide`；`show` 签名 widen 到 `MouseEvent | FocusEvent`（`@focus` 类型安全）。~25 个 tip（GraphCard + MetricTile）经组件继承全部可达。

### 验证

- `vue-tsc --noEmit` 0 error（签名 widen 由参数逆变保证类型安全）；`vite build` 1.95s 成功；定位纯 `getBoundingClientRect` + 视口数学，鼠标/焦点一致；`hide` 无参，三处调用安全；Esc 保持焦点 Tab 可续；popup `pointer-events:none` 杜绝伪 blur。

### A11y (English)

1. **[a11y] `frontend/src/components/controls/ChartTip.vue`**: the ⓘ info icon had only `@mouseenter`/`@mouseleave` — keyboard users couldn't trigger it, touch users couldn't hover. Added `tabindex=0` + `role=button` + `aria-label` + `@focus=show` + `@blur=hide` + `@keydown.escape=hide`; widened `show` signature to `MouseEvent | FocusEvent` (type-safe for `@focus`). ~25 tips (GraphCard + MetricTile) inherit the fix via the component.

### Verification (English)

- `vue-tsc --noEmit` 0 errors (signature widen type-safe by parameter contravariance); `vite build` 1.95s success; positioning is pure `getBoundingClientRect` + viewport math, identical for mouse/focus; `hide` is arg-agnostic, safe from all 3 callers; Esc keeps focus so Tab continues; popup `pointer-events:none` prevents spurious blur.

---

## 2026-06-20 — 修复图例标记色与曲线颜色不一致

### Bug 修复

- **[修复] `frontend/src/components/charts/options.ts`**: 6 个 builder 凡设 `lineStyle.color` 的线 series，同步设 `itemStyle.color` 同色。**根因**：ECharts 图例标记色取自 `series.itemStyle.color`（非 `lineStyle.color`），此前只设线色不设标记色，导致图例错位——典型如债务堆叠图 `gov_total` 线黄、图例却显示红圆点。涉及：`buildStackedArea`（同时删除硬编码 palette、改用主题 `PALETTE`）、`buildMultiLine`、`buildDualAxisLine`、`buildBarLineCombo`（线 series）、`buildCreditM2Chart`、`buildSpreadChart`
- **[修复] `frontend/src/pages/RealEstate.vue`**: 房价多城市图（inline `priceOption`）同样补 `itemStyle.color`，与线色一致

### 验证

- `vue-tsc --noEmit` 0 error

### Bug Fix (English)

- [fix] `options.ts`: for every line series that sets `lineStyle.color`, also set `itemStyle.color` to the same value. Root cause: ECharts legend marker color comes from `series.itemStyle.color`, not `lineStyle.color` — so a series with only a line color rendered a legend marker in a different color (e.g. debt-stacked gov_total yellow line but a red legend dot). Covers `buildStackedArea` (also dropped the hardcoded palette in favor of the theme `PALETTE`), `buildMultiLine`, `buildDualAxisLine`, `buildBarLineCombo` (the line series), `buildCreditM2Chart`, `buildSpreadChart`
- [fix] `RealEstate.vue`: the inline multi-city price chart (`priceOption`) gets the same `itemStyle.color` = line color treatment

### Verification (English)

- `vue-tsc --noEmit` 0 errors

---

## 2026-06-20 — 概览页 7 个 KPI 指标增加 tooltip（含义 + 取数逻辑）

### 新功能

- **[新功能] `frontend/src/components/layout/MetricTile.vue`**：新增 `tip?: string` prop，label 文字后挂载 `ChartTip`（ⓘ 图标 + Teleport 弹层），与 `GraphCard` 用法一致
- **[新功能] `frontend/src/pages/Overview.vue`**：6 个 KPI 瓦（M2 同比 / CPI 同比 / PMI 官方 / 财新 PMI / M2-M1 剪刀差 / M0 同比）+ 综合信号瓦各配 tooltip，内容为「指标含义 + 取数逻辑」两段：数据源 AKShare 接口 → 原始表 → 是否衍生计算（剪刀差 = m2_yoy − m1_yoy；综合信号 = 四周期 phase 映射 −1/0/+1 求和）→ 取日期范围内最近一期有效值
- **[优化] `frontend/src/components/controls/ChartTip.vue`**：弹层 `white-space: normal → pre-line`，让 tooltip 多段文本换行生效（对现有单行 tip 无影响）

### 验证

- `vue-tsc --noEmit` 0 error

### New Feature

- [feat] `MetricTile.vue`: add `tip?: string` prop; mount `ChartTip` (ⓘ + Teleport popup) after the label, mirroring `GraphCard`
- [feat] `Overview.vue`: add tooltips to 6 KPI tiles (M2/CPI/official PMI/Caixin PMI/M2-M1 spread/M0 YoY) + the composite-signal tile; each tooltip carries two paragraphs — indicator meaning + data logic (AKShare source → raw table → derived formula if any → latest valid value within the date range)
- [opt] `ChartTip.vue`: popup `white-space: normal → pre-line` so multi-paragraph tooltip text wraps (no effect on existing single-line tips)

### Verification

- `vue-tsc --noEmit` 0 errors

---

## 2026-06-18 — 新增 M2−M1 剪刀差图 + 修复 PMI 荣枯线/纵轴

### 新功能

- **[新功能] `frontend/src/components/charts/options.ts`**: 新增 `buildSpreadChart` builder——单 series 面积线 + 0 轴 `markLine`（标「持平」）+ `scale:true`。专用于差值类指标（剪刀差），0 为语义零轴（增速持平）
- **[新功能] `frontend/src/pages/Overview.vue`**: 在「M1 vs M2 同比」图后新增「M2−M1 剪刀差」面积图（`m2_m1_spread`），0 轴标「持平」，`scale` 放大 pp 波动。之前该指标只有 KPI 瓦、无独立图

### Bug 修复

- **[修复] `buildMultiLine` 荣枯线挂在 `series[0]`**：关掉「官方」series 时荣枯线跟着消失。改为挂到**每个 series**（`forEach`）——关任一 series，其余仍带 50 线，线不消失（全关才消失，符合预期）
- **[优化] `buildMultiLine` 纵轴加 `scale:true`**：窄幅指标（PMI 49~52）不再被强制 0 起、压成平线，波动正确放大

### 验证

- `vue-tsc --noEmit` 0 error；剪刀差数据起点 1991-12（align_start 下从有数据处起，359 非空点）

### New Feature (English)

- [feat] `options.ts`: add `buildSpreadChart` builder — single area line + zero-axis `markLine` (labeled 「持平」) + `scale:true`; for spread/difference series where 0 is the semantic axis (growth equal)
- [feat] `Overview.vue`: add "M2−M1 剪刀差" area chart after the M1/M2 chart (`m2_m1_spread`), with a 0 line and scaled axis. Previously only a KPI tile existed, no dedicated chart

### Bug Fix (English)

- [fix] `buildMultiLine` reference line was on `series[0]` — toggling 官方 off hid the 50 line. Now attached to every series (`forEach`) — toggling any one off still leaves the line on the others; only disappears when all hidden (correct)
- [opt] `buildMultiLine` yAxis `scale:true` — narrow-amplitude series (PMI 49~52) no longer forced from 0 into a near-flat line; swings amplified

### Verification (English)

- `vue-tsc --noEmit` 0 errors; spread data starts 1991-12 under align_start (359 non-null points)

---

## 2026-06-18 — 图表起点对齐有数据 + PMI 荣枯线重点突出

### 优化

- **[优化] `backend/app/api/v1/data.py`**: `derived_monthly()` 加 `align_start` 布尔参数。True 时，取请求各值列**同时非空**的最早日期作为切片起点（用户传了 `start` 则取较大者尊重其范围）——图表不再从 1978 一段空白起，省去每次手动拖周期。默认 False，契约（golden）不变
- **[优化] `frontend/src/api/client.ts`**: `getDerivedMonthly` 加 `alignStart` 透传
- **[优化] 3 页面**（Overview/CreditCycle/InventoryCycle）: `getDerivedMonthly` 请求带 `alignStart: true`
- **[优化] `frontend/src/components/charts/options.ts`**: `buildMultiLine` 加 `markLineAt?: number` 参数——在首个 series 画实线参考线 + 标注。概览「PMI 多维」与库存「PMI 官方 vs 财新」传 50，**荣枯线 50 以琥珀实线 + 标注重点突出**（PMI 语义零轴）

### 验证

- `align_start` 各列起点经真实 API 取证正确：LPR1Y→2013-10、财新PMI→2012-01、M2同比→1991-12（印证月度同比从那时才有）、CPI同比+环比→1996-02、社融+存量→2016-01；不传则 1978-01 默认不变
- `vue-tsc --noEmit` 0 error；后端 golden test 6/6 无回归

### Optimization (English)

- [opt] `backend/app/api/v1/data.py`: add `align_start` flag to `derived_monthly()`. When true, the slice starts at the earliest date where all requested value columns are non-null (respects an explicit user `start` by taking the later) — charts no longer begin in 1978 with an empty run, sparing manual slider drags. Defaults false; golden contract unchanged
- [opt] `api/client.ts`: `getDerivedMonthly` passes through `alignStart`
- [opt] Overview/CreditCycle/InventoryCycle: requests send `alignStart: true`
- [opt] `options.ts buildMultiLine`: add `markLineAt?` — draws a solid reference line + label on the first series. Overview "PMI multi-dim" and Inventory "PMI official vs Caixin" pass 50, highlighting the 50 expansion/contraction line as PMI's semantic zero-axis

### Verification (English)

- `align_start` confirmed via real API: LPR1Y→2013-10, Caixin-PMI→2012-01, M2-YoY→1991-12 (monthly YoY starts then), CPI-YoY+MoM→1996-02, social-financing+stock→2016-01; without the flag, default 1978-01 unchanged
- `vue-tsc --noEmit` 0 errors; backend golden test 6/6 no regression

---

## 2026-06-17 — 修复主体布局（侧边栏固定 + main 独立滚动 + 顶部筛选栏撑满）

### Bug 修复

- **[严重] `frontend/src/App.vue`**: 原结构 `flex` + fixed sidebar + 各页 `ml-[200px]` 自相矛盾——fixed 元素不参与 flex、`flex-1` 形同虚设，且页面横向溢出时整篇文档被拖过 fixed 侧边栏，出现双滚动条、内容越过侧边栏。改为：外层去 `flex`；`<main>` 改 `ml-[200px] h-screen overflow-y-auto overflow-x-hidden` → main 成为独立滚动容器（纵向自滚、横向裁剪），与 fixed 侧边栏解耦，内容再溢出也拖不过侧边栏
- **[修复] 6 个页面根 div**（Overview/Credit/Merrill/Inventory/Debt/RealEstate）: 去掉冗余 `ml-[200px]`（现由 main 统一负责偏移，留着会偏移 400px）
- **[修复] `frontend/src/components/layout/RefreshBar.vue`**: 去掉旧布局遗留的 `ml-[200px]`（旧布局 main 全宽、bar 需躲侧边栏；现在 bar 在已偏移的 main 内，再 +200 导致偏右且不填满）→ 顶部筛选栏撑满主区全宽、与下方内容（px-6 ↔ p-6）对齐、`sticky top-0` 吸附滚动容器顶

### 验证

- `vue-tsc --noEmit` 0 error；前后端 HTTP 200；vite HMR 无报错；布局修复后侧边栏钉死、main 独立滚动、顶部栏固定且全宽

### Bug Fix (English)

- [critical] `frontend/src/App.vue`: the old `flex` + fixed sidebar + per-page `ml-[200px]` was self-contradictory — a fixed element doesn't participate in flex (so `flex-1` did nothing), and horizontal overflow dragged the whole document past the fixed sidebar, causing double scrollbars and content crossing the sidebar. Fix: drop `flex` on the root; `<main>` → `ml-[200px] h-screen overflow-y-auto overflow-x-hidden` (independent scroll container, decoupled from the fixed sidebar; content can't cross it)
- [fix] 6 pages (Overview/Credit/Merrill/Inventory/Debt/RealEstate): remove the redundant `ml-[200px]` (now owned by main; keeping it would double the offset to 400px)
- [fix] `RefreshBar.vue`: drop the legacy `ml-[200px]` (made sense when main was full-width; now it's inside the offset main, so it shifted right and didn't fill) → toolbar now spans the main width, aligns with content (px-6 ↔ p-6), and `sticky top-0` sticks to the scroll container

### Verification (English)

- `vue-tsc --noEmit` 0 errors; frontend+backend HTTP 200; vite HMR clean; layout fixed: sidebar pinned, main scrolls independently, toolbar full-width and sticky

---

## 2026-06-17 — 补齐前端缺失指标（社融/利率/信贷/财新PMI/跨指标领先/政府细分）

### 新功能

- **[新功能] `frontend/src/components/charts/options.ts`**: 新增两个可复用 builder——`buildBarLineCombo`（柱+双轴折线）与 `buildMultiLine`（多折线，单列亦可用）
- **[新功能] `frontend/src/pages/CreditCycle.vue`**: 新增 2 图——「社会融资规模：增量与存量增速」（`total` 柱 + `sf_stock_yoy` 线）、「新增人民币贷款与同比」（`new_rmb_loan` 柱 + `loan_yoy` 线）
- **[新功能] `frontend/src/pages/Overview.vue`**: 新增 4 图 + 2 KPI 瓦——「CPI 同比 vs 环比」（`cpi_mom`）、「利率环境」（`lpr_1y`/`lpr_5y`/`real_rate`）、「PMI 多维 官方/财新/非制造业/服务」（`pmi_caixin`/`pmi_non_mfg`/`pmi_caixin_svc`）；新增「财新 PMI」「M0 同比」KPI 瓦；新增「跨指标领先」stat 块（消费 `signals.cross_lags`：M1→PPI、剪刀差→CPI 的最优滞后与相关系数，零额外计算）

### 优化

- **[优化] `frontend/src/pages/InventoryCycle.vue`**: 新增「PMI 官方 vs 财新」图（`pmi_caixin`），财新制造业 PMI 作为领先指标在 PMI 专属页对照官方
- **[优化] `frontend/src/pages/DebtCycle.vue`**: 新增「政府杠杆：中央 vs 地方」堆叠图（`gov_central`/`gov_local`，直读 leverage 表）

### 说明

- 把数据层算了但前端未展示的 ~22 个指标「全部补回」中的主体；`analysis/`、后端、数据管线**零改动**，仅前端扩 `cols` 参数 + 新增图表
- 仍未展示（需额外工作）：`hh_debt_to_income`（居民真实杠杆率，`derived_quarterly` 未物化 + NBS 收入数据常缺）、`ip_cumulative`（与 ip_yoy 冗余，刻意略）、`rmb_loan`/`sf_impulse`/`loan_stock_yoy`（与已展示的社融/信贷主指标冗余）

### 验证

- `vue-tsc --noEmit` 0 error；后端 golden test 6/6 无回归；新引用列经真实 API 取证均有非空值（社融 50535亿、LPR 4.15/4.8、实际利率 -0.35、财新 PMI 51.5 等），`cross_lags` 在场（剪刀差→CPI 领先 10 月 r=0.28）

### New Feature (English)

- [feat] `frontend/src/components/charts/options.ts`: add reusable builders `buildBarLineCombo` (bar + dual-axis line) and `buildMultiLine` (multi-line; works for single series too)
- [feat] `CreditCycle.vue`: add 2 charts — "social financing: increment vs stock growth" (`total` bar + `sf_stock_yoy` line), "new RMB loans vs YoY" (`new_rmb_loan` bar + `loan_yoy` line)
- [feat] `Overview.vue`: add 4 charts + 2 KPI tiles — "CPI YoY vs MoM" (`cpi_mom`), "interest-rate environment" (`lpr_1y`/`lpr_5y`/`real_rate`), "PMI multi-dim: official/Caixin/non-mfg/services" (`pmi_caixin`/`pmi_non_mfg`/`pmi_caixin_svc`); add Caixin-PMI and M0-YoY tiles; add cross-indicator-leading stat block (consumes `signals.cross_lags`: M1→PPI and spread→CPI best lag + correlation, zero extra compute)

### Optimization (English)

- [opt] `InventoryCycle.vue`: add "PMI official vs Caixin" chart (`pmi_caixin`); Caixin as a leading indicator on the PMI-centric page
- [opt] `DebtCycle.vue`: add "government leverage: central vs local" stacked chart (`gov_central`/`gov_local`, reads leverage table)

### Notes (English)

- Brings back the main body of the ~22 computed-but-unshown metrics; `analysis/`, backend, data pipeline untouched (frontend-only: extended `cols` params + new charts)
- Still not surfaced (needs extra work): `hh_debt_to_income` (not materialized in derived_quarterly + NBS income often absent), `ip_cumulative` (redundant with ip_yoy, intentionally omitted), `rmb_loan`/`sf_impulse`/`loan_stock_yoy` (redundant with the social-financing/credit charts now shown)

### Verification (English)

- `vue-tsc --noEmit` 0 errors; backend golden test 6/6 (no regression); new columns confirmed non-null via real API (social financing 50535亿, LPR 4.15/4.8, real rate -0.35, Caixin PMI 51.5, …); `cross_lags` present (spread→CPI leads 10 months, r=0.28)

---

## 2026-06-17 — 修复信用周期页 M2 趋势线不渲染（derived 日期重复列）

### Bug 修复

- **[严重] `backend/app/api/v1/data.py`**: 信用周期页「M2 同比与趋势」的 **M2 趋势线不显示**。根因：`derived_monthly()` 的 `keep = ["date"] + cols.split(",")` 在 `cols='date,m2_yoy'` 时产生**重复 date 列**，使 `df['date']` 退化为 DataFrame（非 Series），`df_to_records` 的 `is_datetime64_any_dtype` 判 False → `strftime('%Y-%m-%d')` 被跳过 → 日期以 ISO `'2020-01-01T00:00:00'` 序列化。而 `/cycles/credit` 的日期是纯 `'2020-01-01'`，前端 `buildCreditM2Chart` 按日期精确字符串 join 取趋势 → **全 miss → 趋势数组全 null → 线不画**。M2 同比不受影响（按数组下标取，不依赖 join）
- **[修复]** `keep` 用 `dict.fromkeys` 去重保序——一处同时修复日期格式化 + payload 重复列

### 验证

- 真实 API：`/derived/monthly?cols=date,m2_yoy` 修复后 `columns=['date','m2_yoy']`（无重复）、`date='2020-01-01'`（纯日期），与 `/cycles/credit` 的 `'2020-01-01'` 一致 → 前端 join 命中
- golden test 6/6 通过（契约 API==db.load 无回归）

### 说明

- 仅改一处（外科原则）；未动 `core/serial.py`（共享序列化器，多端点依赖，风险更大）
- 可选加固（未做）：`serial.df_to_records` 入口加 `out.loc[:, ~out.columns.duplicated()]` 防御性去重，杜绝任何重复列静默降级日期格式

### Bug Fix (English)

- [critical] `backend/app/api/v1/data.py`: M2 trend line in the credit-cycle "M2 trend" chart was not rendering. Root cause: `derived_monthly()` built `keep = ["date"] + cols.split(",")`, so `cols='date,m2_yoy'` produced a duplicate date column; `df['date']` then became a DataFrame (not a Series), `df_to_records`' `is_datetime64_any_dtype` check returned False, `strftime('%Y-%m-%d')` was skipped, and the date serialized as ISO `'2020-01-01T00:00:00'`. Against `/cycles/credit`'s plain `'2020-01-01'`, the frontend's exact-string date-key join in `buildCreditM2Chart` missed every point → trend array all-null → line not drawn. M2 YoY was unaffected (index-aligned, no join)
- [fix] dedupe `keep` with `dict.fromkeys` (order-preserving) — fixes date formatting + the duplicate column in one place

### Verification (English)

- Real API: `/derived/monthly?cols=date,m2_yoy` now returns `columns=['date','m2_yoy']` (no dup) and `date='2020-01-01'` (plain), matching `/cycles/credit`'s `'2020-01-01'` → frontend join hits
- golden test 6/6 pass (no regression to the API==db.load contract)

### Notes (English)

- Single-file surgical fix; `core/serial.py` untouched (shared serializer, broader blast radius)
- Optional hardening (not applied): `out.loc[:, ~out.columns.duplicated()]` at the top of `df_to_records` to defend against any duplicate-column DataFrame silently downgrading date formatting

---

## 2026-06-17 — 下线移除 Dash+Plotly（legacy 清理）

### 清理

- **[移除] `dashboard/`**（18 文件：app/db/refresh/config/components/pages/callbacks）——旧 Dash+Plotly 前端整体删除。取证确认 `analysis/`、`scripts/`、`backend/` 对 `dashboard/` 零真实依赖（`dashboard/db.py`、`refresh.py` 已在 P0 迁为 `backend/app/core/` 独立副本），可安全删
- **[移除] `run_dashboard.sh`** —— Dash 启动脚本；新栈以 `run_app.sh` 为唯一入口
- **[移除] `requirements.txt` Dash 依赖** —— plotly / dash / dash[diskcache] / diskcache / dash-bootstrap-components（5 行）；新栈后端用 `backend/pyproject.toml`，刷新走 SSE 不再需 diskcache。保留 akshare/pandas/numpy/scipy/statsmodels（analysis/scripts 仍需）
- **[变更] `启动面板.command`** —— 双击入口保留，底层改为委托 `run_app.sh`（FastAPI+Vue），体验不变
- **[文档] README** 去掉 legacy Dash 回退说明；changeLog 记录本次下线

### 验证

- `grep import dash/plotly` 残留 = 0（backend/analysis/scripts）
- backend golden test 6/6 仍通过（证明 core 脱离 dashboard 独立工作）
- 前端 build 仍绿

### Removal: retire Dash + Plotly (legacy cleanup)

- [remove] `dashboard/` (18 files) — old Dash+Plotly frontend deleted; verified zero real dependency from analysis/scripts/backend (db.py/refresh.py already migrated to backend/app/core/ as independent copies in P0)
- [remove] `run_dashboard.sh`; `run_app.sh` is now the only entrypoint
- [remove] Dash deps from requirements.txt (plotly/dash/dash[diskcache]/diskcache/dash-bootstrap); new backend uses backend/pyproject.toml, refresh via SSE
- [change] `启动面板.command` keeps the double-click entry, now delegates to run_app.sh (FastAPI+Vue)
- [docs] README drops legacy fallback note; changeLog records the retirement

---

## 2026-06-17 — 架构升级：Dash+Plotly → FastAPI + Vue 3 + ECharts

### 架构

- **[升级]** 按 `docs/architecture-upgrade.md` 全量迁移：前端 **Vue 3 + Vite + TS + ECharts + Pinia**，后端全新 **FastAPI + Pydantic**；`analysis/` 分析核心、`scripts/_pipeline.py` 采集管道、刷新逻辑**零改动保值**
- **[新增]** `backend/app/`：FastAPI（api/v1: data/cycles/signals/refresh/real-estate）+ Pydantic schema 契约 + core(db/cache/refresh 迁自旧 dashboard) + golden test
- **[新增]** `frontend/`：Vue 3 SPA — 6 页视图（Overview/Merrell/Credit/Inventory/Debt/RealEstate）、Pinia 全局联动、ECharts 图表组件（connectNulls 原生跨接断线、markArea 阶段背景与 M2 空洞标注）、useCountUp 微交互、SSE 刷新进度
- **[新增]** `run_app.sh`：一键起 FastAPI(:8000) + Vue preview(:5173)；PWA manifest
- **[保留]** 旧 `dashboard/`(Dash) 作 legacy 回退（`run_dashboard.sh`），未删除——待全量视觉 parity 确认后再下线

### 阶段与验证（每阶段独立 commit）

- **P0 FastAPI 地基**：golden test 6/6（/derived/monthly 与 db.load 逐字节一致）；uvicorn 全端点 200；OpenAPI 导出
- **P1 Vue 骨架 + 旗舰页**：vue-tsc 0 error + Vite 打包 603 模块；信用周期页数据一致 + M2 connectNulls 原生跨接 + 1991–1996 空洞标注在位；FastAPI+Vite E2E
- **P2 其余 5 页**：6 页 parity；7 端点全 200（merrill=recovery/inventory=active_destocking/debt=leveraging_boom/real-estate composite 59.6）；golden 6/6 无回归
- **P3 横切极致**：全局日期联动 + SSE 刷新（15 progress 事件 0→1）+ count-up 微交互 + 路由过渡
- **P4 切换**：Vue 为默认入口、README/启动脚本更新、PWA manifest、最终全量测试

### Architecture upgrade: Dash+Plotly → FastAPI + Vue 3 + ECharts

- [upgrade] full migration per docs/architecture-upgrade.md: Vue 3 + Vite + TS + ECharts + Pinia frontend, new FastAPI + Pydantic backend; analysis core, pipeline, refresh logic unchanged
- [feat] backend/app: FastAPI (data/cycles/signals/refresh/real-estate) + Pydantic schema + core (db/cache/refresh migrated) + golden tests
- [feat] frontend: Vue 3 SPA, 6 pages, Pinia global linking, ECharts (native connectNulls, markArea phase bg + M2 gap marker), useCountUp, SSE refresh
- [feat] run_app.sh one-click (FastAPI :8000 + Vue :5173); PWA manifest
- [keep] legacy dashboard/ (Dash) retained as fallback, not deleted — pending full visual parity

### Phases & verification (separate commit per phase)

- P0 backend: golden 6/6 (/derived/monthly byte-identical to db.load), uvicorn 200, OpenAPI exported
- P1 scaffold + flagship: vue-tsc 0 errors, Vite 603 modules, credit-cycle parity + native connectNulls + 1991-1996 gap marker, FastAPI+Vite E2E
- P2 remaining 5 pages: 6-page parity, 7 endpoints 200, golden 6/6 no regression
- P3 cross-cutting: global date linking + SSE refresh (15 events 0→1) + count-up + route transitions
- P4 cutover: Vue default entry, README/scripts, PWA, final full test

---

## 2026-06-17 — 修复图表范围滑块拖动时主图区逐次变窄

### Bug 修复

- **[修复] `dashboard/config.py`**: `CHART_LAYOUT` 增加 `height=320`。根因：每个图表都开 rangeslider 但 figure 无固定高度、靠 320px 容器 responsive 自适应；拖滑块触发 `relayout` 时 Plotly 重算 y 轴 domain，滑块区逐次蚕食主图 → 内容上滑、高度越来越窄（经典 Plotly rangeslider 自适应反馈环）。固定高度与全仓库唯一的 320px `dcc.Graph`（`make_graph_card`）精确匹配，消除自适应重算

### 验证

- py_compile 通过；`make_range_slider(make_dual_axis_line(...)).layout.height == 320` 断言通过（高度确已固化进 figure）

### Bug Fix (English)

- [fix] `dashboard/config.py`: add `height=320` to `CHART_LAYOUT`. Root cause: every chart enables a rangeslider but no figure had a fixed height (relied on the 320px container's responsive autosize); on slider drag, `relayout` re-derived the y-axis domain and the slider region ate into the plot each cycle, shrinking it. A fixed height matching the repo's single 320px `dcc.Graph` (make_graph_card) breaks the autosize feedback loop

### Verification (English)

- py_compile passes; `make_range_slider(make_dual_axis_line(...)).layout.height == 320` asserted (height baked into figure)

---

## 2026-06-17 — 修复图表断线（connectgaps 统一连线 + M2 空洞标注）

### Bug 修复

- **[严重] 图表线在 NaN 处断开**: 全 dashboard 无任何 trace 设 connectgaps，导致稀疏/早期系列（M2 1992–1996 年度结存段、工业增加值每年 2 月合并发布、cpi/ppi/pmi/lpr 起始前导等）在 NaN 处出现明显断线。根因取证：M2 1992–1995 源（东方财富）只有每年 12 月结存、月度统计 ~1996 才连续；ip_yoy 缺口全在 2 月（NBS 1-2 月合并发布）。实测 3 个 akshare M2 源均无 1992–1995 月度数据 → 真值不可补
- **[修复] `dashboard/components/charts.py`**: 在 `_apply_layout()` 内加 `fig.update_traces(connectgaps=True)`——由于全部 6 页 16 个图构建函数都经此咽喉点，**一处修复全部线图**；新增 `add_gap_marker()` helper，用半透明条+文字标注已知源数据空洞
- **[修复] `dashboard/pages/credit_cycle.py`**: M2 同比主图加 `add_gap_marker('1991-01','1996-12','此段 M2 仅有年度结存，月度源数据缺失')`，让 connectgaps 跨接的真实年度锚点不致被误读为连续月度数据

### 关键设计

- **踩中咽喉点**：connectgaps 是 trace 属性不能全局设，但所有图都走 `_apply_layout` → 在此一处 `update_traces(connectgaps=True)` 覆盖全部 16 图，避免逐 trace 改 20+ 处
- **诚实而非造假**：M2 空洞无法补真值（3 源实测），故用真实存在的 5 个年度锚点连线 + 标注条明示，而非填假数据

### 验证

- 离线：connectgaps 确实注入全部 trace、add_gap_marker 正确渲染 vrect+annotation、M2 图函数含标注、py_compile 通过
- 服务器冒烟：HTTP 200（首页 + _dash-layout），启动无异常

### Bug Fixes

- [critical] chart lines broke at NaN: no trace anywhere set connectgaps, so sparse/early series (M2 annual-snapshot 1992–1996, Feb-combined industrial prints, leading NaN for cpi/ppi/pmi/lpr) rendered broken lines. Forensics: the M2 source only carries year-end snapshots 1992–1995 (monthly begins ~1996); ip_yoy gaps are all February (NBS Jan-Feb combined). All 3 akshare M2 sources lack 1992–1995 monthly → real data is un-backfillable
- [fix] `dashboard/components/charts.py`: add `fig.update_traces(connectgaps=True)` inside `_apply_layout()` — since every figure on all 6 pages flows through this chokepoint, **one line fixes every line chart**; add `add_gap_marker()` helper to disclose known source-data gaps
- [fix] `dashboard/pages/credit_cycle.py`: M2 chart calls `add_gap_marker('1991-01','1996-12','此段 M2 仅年度结存，月度源数据缺失')` so the connectgaps-bridged real annual anchors aren't misread as continuous monthly data

### Key design

- **Chokepoint**: connectgaps is a trace property (not settable globally), but every figure flows through `_apply_layout` → one `update_traces(connectgaps=True)` covers all 16 figures, avoiding 20+ per-trace edits
- **Honest not fabricated**: the M2 void has no real data (verified across 3 sources), so it's bridged with the 5 real annual anchors + a disclosure band, not filled with fabricated data

### Verification

- Offline: connectgaps confirmed injected on all traces, add_gap_marker renders vrect+annotation, M2 chart includes the marker, py_compile passes
- Server smoke: HTTP 200 (home + _dash-layout), clean boot

---

## 2026-06-17 — 自托管 Geist 字体（Sans + Mono）

### 新功能

- **[新功能] `dashboard/assets/fonts/`**: 自托管 Geist Sans（400/500/600/700）+ Geist Mono（400/500/600），共 7 个 latin 子集 woff2（~112KB），来源 `@fontsource/geist@5.2.9` / `@fontsource/geist-mono@5.2.8`
- **[新功能] `dashboard/assets/fonts.css`**: `@font-face` 声明（`font-display: swap` 避免字体加载期文字不可见），Dash 自动加载；保留 CJK 系统回退（PingFang/Noto/YaHei，Geist 仅含 latin）
- **[优化] `dashboard/config.py`**: `FONT` 首选 Geist、`MONO` 首选 Geist Mono，均保留系统回退栈
- **[优化] `dashboard/components/layout.py`**: `make_metric_tile` 数值改用 Geist Mono + `tabular-nums`（fintech 数据等宽对齐），delta 保持 Sans（可能为文案句）

### 说明

- 离线优先：字体随仓库分发，无需运行时联网；jsdelivr 仅首次获取二进制时使用
- 踩坑：jsdelivr 对 `@latest` 的 GET 返回 "Invalid URL"（HEAD 却 200，迷惑），**pinned 版本才正常下载**

### 验证

- py_compile + 导入通过；FONT/MONO 已引用 Geist；服务器 `/assets/fonts.css` 200、woff2 经 Dash 托管后 magic=`wOF2` 真实、HTML 注入 fonts.css link + font-family 含 Geist

### New Feature (English)

- [feat] `dashboard/assets/fonts/`: self-host Geist Sans (400/500/600/700) + Geist Mono (400/500/600), 7 latin-subset woff2 (~112KB), from `@fontsource/geist@5.2.9` / `@fontsource/geist-mono@5.2.8`
- [feat] `dashboard/assets/fonts.css`: @font-face with `font-display: swap` (no invisible-text flash); Dash auto-loads; CJK system fallback retained (Geist is Latin-only)
- [opt] `dashboard/config.py`: FONT leads with Geist, MONO leads with Geist Mono, both keep system fallbacks
- [opt] `dashboard/components/layout.py`: metric-tile value → Geist Mono + tabular-nums (fintech numeric alignment); delta stays Sans

### Notes (English)

- Offline-first: fonts ship with the repo, no runtime network; jsdelivr used only to fetch binaries once
- Gotcha: jsdelivr returns "Invalid URL" for `@latest` GET (but HEAD 200, misleading); a pinned version downloads correctly

### Verification (English)

- py_compile + import pass; FONT/MONO reference Geist; server `/assets/fonts.css` 200, woff2 served with magic=`wOF2`, HTML injects fonts.css link + Geist in font-family

---

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

## 2026-06-17 — 仪表盘「刷新数据」按钮（后台回调 + 真进度 + 缓存失效 + 单飞）

### 新功能

- **[新功能] `dashboard/refresh.py`**: 仪表盘内一键刷新数据。以**子进程**方式调用 `scripts/01_fetch_data.py`（复用闸门管道，绝不 import akshare 进 web 进程）；流式读 stdout 数 `✅` 行 → 真进度回调；成功后清空全部 7 处 lru_cache（`db._load_full` + 6 个 cycle/signals/real_estate 分类器）；`read_manifest_summary()` 把 `last_run.json` 渲染成「已更新 N 表 / 跳过 X」回显
- **[新功能] `dashboard/app.py`**: 侧边栏 footer 加「🔄 刷新数据」按钮 + 状态行 + 进度条（全局、每页可见）；接入 `DiskcacheManager`（`dash[diskcache]` + psutil）做**后台回调**，~30s 采集不阻塞 UI；`running` 禁用按钮 + lockfile 双重**单飞**防重入；刷新完成后 `dcc.Store(data-version)` bump → clientside `window.location.reload()` 强制用清空缓存后的新数据重渲；页面加载时显示「上次刷新」摘要

### 关键设计

- **缓存失效是命脉**：所有 lru_cache 按 db_path 字符串缓存，而原子切换不改路径 → 不清缓存会显示刷新前的旧数据（"成功但没变"）。`clear_all_caches()` 统一清 7 处
- **子进程而非进程内**：隔离崩溃、复用现成管道、akshare/tqdm 不污染 web 进程、app 启动更快
- **真进度**：流式解析 fetcher 的 `✅ table → staging` 日志，进度 0→100% 平滑（非假 spinner）

### 验证

- **离线**：app 导入无异常、DiskcacheManager 接入、refresh-btn 在 sidebar、clear_all_caches 清 7 缓存、manifest 读取正确、lockfile 单飞返回 busy
- **真实 E2E**：`run_refresh` 跑通 22.7s，进度 0.0→1.0 平滑，缓存 1→0 项（清空生效），manifest「已更新 9 表 / 跳过 3（gdp/leverage 季频无新数据 + household_income NBS 403）」闸门正确
- **服务器冒烟**：HTTP 200（首页 + `_dash-layout`），启动日志无异常

### 依赖

- `requirements.txt`: 新增 `dash[diskcache]>=2.14`（含 psutil）、`diskcache>=5.5`

### New Feature

- [feat] `dashboard/refresh.py`: one-click in-dashboard refresh. Spawns `scripts/01_fetch_data.py` as a **subprocess** (reuses the gated pipeline, never imports akshare into the web process); streams stdout and counts `✅` lines for real progress; on success clears all 7 lru_caches (`db._load_full` + 6 cycle/signals/real_estate classifiers); `read_manifest_summary()` renders `last_run.json` as "updated N / skipped X"
- [feat] `dashboard/app.py`: sidebar footer gets a refresh button + status + progress bar (global); `DiskcacheManager` (`dash[diskcache]` + psutil) powers a **background callback** so the ~30s fetch doesn't block the UI; `running` disables the button + a lockfile double-guard **single-flight**; on completion a `dcc.Store(data-version)` bump triggers clientside `window.location.reload()` so the cleared caches repopulate with fresh data; page load shows the last-refresh summary

### Key design

- **Cache invalidation is mandatory**: lru_caches key by the db_path string, which doesn't change on atomic swap → without clearing, the dashboard serves pre-refresh data ("success but unchanged"). `clear_all_caches()` clears all 7
- **Subprocess, not in-process**: crash isolation, reuses the pipeline, keeps akshare/tqdm out of the web process, faster app startup
- **Real progress**: streams fetcher `✅ table → staging` lines, progress 0→100% smooth (not a fake spinner)

### Verification

- **Offline**: app imports cleanly, DiskcacheManager wired, refresh-btn in sidebar, clear_all_caches clears 7 caches, manifest reads correctly, lockfile single-flight returns busy
- **Real E2E**: `run_refresh` runs 22.7s, progress 0.0→1.0 smooth, cache 1→0 items (cleared), manifest "updated 9 / skipped 3 (gdp/leverage quarterly no-new-data + household_income NBS 403)" gate correct
- **Server smoke**: HTTP 200 (home + `_dash-layout`), clean startup log

### Dependencies

- `requirements.txt`: add `dash[diskcache]>=2.14` (includes psutil), `diskcache>=5.5`

---

## 2026-06-17 — 方案 D：暂存快照 + 校验闸门 + 原子切换（根治采集覆写风险）

### 架构

- **[新增] `scripts/_pipeline.py`**: 暂存快照 + 校验闸门 + 原子切换的根因修复。生产库在最终 `os.replace` 原子切换前**一字节不被触碰**：备份 → 复制生产库到暂存库 → fetcher 全部写暂存库(逐表过闸) → 衍生表在暂存库重算 → 原子 rename 暂存→生产 → 写审计 manifest
- **[重构] `scripts/01_fetch_data.py`**: `save_to_db()` 改为**校验闸门出口**（唯一落库路径，零 fetcher 改动覆盖全部 12 表）；`main()` 重写为暂存+原子流程，删散装结果统计

### 治本点

- **校验闸门**：每表 `TABLE_SPECS` 契约（min_rows / required cols / 反缩水）。空结果、低于 min、缺列、关键列全 NaN、distinct-date 萎缩 → 一律拒绝 replace，暂存库保留旧好表
- **反缩水用唯一日期数而非行数**：LPR 原始表有 1534 行但仅 152 个唯一月，按行数判会误拒正确数据；按 distinct dates 对所有表公平（实战验证 lpr/pmi/industrial 均正确放行）
- **崩溃安全**：硬崩溃只损坏暂存文件，生产库未动；事后 `os.replace` 不发生 → 零损失
- **全量备份**：每次采集前归档 `data/backups/macro_data_<ts>.db`，保留最近 10 份
- **可审计**：`data/last_run.json` 记录每表 updated/kept_previous + 行数 + 闸门结果 + akshare 版本 + 时间戳
- **闸门即唯一空处理出口**：移除 5 处 fetcher 内冗余的 `if not result.empty: save_to_db(...)` 散装 guard（social_finance / lpr / house_price / new_credit / household_income），全部改为无条件走 `save_to_db` → 闸门统一裁决。household_income 现在也进 manifest（NBS 403 采空 → kept_previous/empty result），审计覆盖全部 12 表，单一真相源不再并存两套空处理

### 验证

- **离线确定性测试** `scripts/_pipeline_test.py`：15/15 通过（validate 全分支 + 暂存继承好数据 + 空/部分/萎缩采集被拒 + commit 前生产库未动 + 原子切换后正确更新）
- **真实端到端**：11 个可联网表全部 updated，household_income 因 NBS 403 优雅降级（未污染现有数据），衍生表在暂存库重算 581 行，原子切换成功，生产库零回归（derived_monthly 仍 581/581/0 重复）

### 说明

- 问题 1 根因已取证确认：`ak.macro_china_nbs_nation` 返回 HTTP 403，响应体含 `Client IP: 140.205.85.146`——本沙箱**出口 IP 被 NBS 阿里云 WAF 封禁**，与 akshare 代码 / SSL / UA 无关（加浏览器 UA 仍 403；同期东方财富源正常）。换出口 IP 即解封，**代码无需改**。household_income 在 NBS 可达网络跑 `python3 scripts/01_fetch_data.py` 即落库

### Architecture

- [new] `scripts/_pipeline.py`: root-cure for silent data loss via staged snapshot + validation gate + atomic swap. The production DB is touched only by a final atomic `os.replace`; bad/empty/partial/eroded fetches are rejected at the gate so staging keeps the previously-good table
- [refactor] `scripts/01_fetch_data.py`: `save_to_db()` is now the validation-gate write path (sole write path; covers all 12 fetchers with zero per-fetcher changes); `main()` rewritten as staged+atomic flow

### Root-cure details

- **Validation gate**: per-table `TABLE_SPECS` (min_rows / required cols / shrink guard). Empty / below-min / missing-col / all-NaN / distinct-date erosion → reject replace, staging keeps previous good table
- **Shrink guard by distinct dates, not rows**: LPR raw table has 1534 rows but only 152 distinct months — row-count shrink would false-reject correct data; distinct-date basis is grain-fair for all tables (verified: lpr/pmi/industrial correctly admitted)
- **Crash-safe**: a hard crash only damages the staging file; the live DB is untouched until the final atomic rename
- **Backups**: every run snapshots to `data/backups/macro_data_<ts>.db` (keeps last 10)
- **Auditable**: `data/last_run.json` records per-table updated/kept_previous + counts + gate result + akshare version + timestamp

### Verification

- **Offline deterministic test** `scripts/_pipeline_test.py`: 15/15 passed (all validate branches + staging inherits good data + empty/partial/eroded fetches rejected + live untouched pre-commit + atomic commit updates correctly)
- **Real end-to-end**: 11 network-reachable tables updated, household_income gracefully degraded (NBS 403, no corruption), derived recomputed on staging (581 rows), atomic commit succeeded, production DB zero-regression (derived_monthly still 581/581/0 dup)

### Note

- Problem-1 root cause forensically confirmed: `ak.macro_china_nbs_nation` returns HTTP 403 with `Client IP: 140.205.85.146` in the body — the sandbox **egress IP is WAF-blocked by NBS (Alibaba Cloud)**, unrelated to akshare code / SSL / UA (browser UA still 403; eastmoney sources fine in parallel). Changing egress IP unblocks it; **no code change needed**. Run `python3 scripts/01_fetch_data.py` on a network where NBS is reachable to materialize household_income

---

## 2026-06-17 — 修复 derived_monthly 行膨胀、清理死表、补齐 household_income 管道

### Bug 修复

- **[严重] `scripts/02_compute_derived.py`**: `derived_monthly` 因 `on="date"` 的 left merge 命中源表重复日期（pmi 73 行、lpr 1382 行重复）触发笛卡尔积，行数从 581 膨胀到 2651（同日期最多重复 92 次），污染滚动均线 / 阶段分类 / 阶段背景着色。在 `load_table()` 内读取后按 `date` 列 `drop_duplicates(keep="last")` 单点去重，重算后 `derived_monthly` 恢复 581 行、0 重复日期
- **[修复] LPR 列稀疏**: 同一处去重一并修复——LPR（月频、月内多行重复）去重后每个有值月份恰好一行，不再被笛卡尔积污染；`lpr_1y`/`lpr_5y`/`real_rate` 正确反映源覆盖范围（LPR 改革始于 2013/2019，1978–2013 本就无数据）
- **[清理] `data/macro_data.db`**: 删除 `m2_yoy_jin10` 死表（旧版 fetcher 已从代码删除、全仓库零引用，仅在 DB 残留 337 行死数据）。DB 总表数 14 → 13

### 说明

- **`household_income` 采集管道已验证正确但本环境不可达**: 定向调用 `fetch_household_income()` 走通无报错、降级行为符合设计（无崩溃、未污染现有数据）。但 `ak.macro_china_nbs_nation`（国家统计局 data.stats.gov.cn）在本沙箱返回非 JSON 被拦截（0.3s 快速失败），同环境下东方财富等源可正常采集（akshare 1.18.64）。在 NBS 可达的网络运行 `python3 scripts/01_fetch_data.py` + `02_compute_derived.py` 即可让 `derived_quarterly` 出现 `hh_debt_abs`/`hh_income_share`/`hh_debt_to_income`

### Verification

- derived_monthly: 2651 → 581 行，581 distinct dates，dup_groups=0
- 原最差日期 2017-03-01: 92 行 → 1 行
- LPR 去重后有值月份: 152（每月一行）
- m2_yoy_jin10: 已删除

### Bug Fixes

- [critical] `scripts/02_compute_derived.py`: `derived_monthly` inflated 581→2651 rows because date-keyed left merges hit duplicate dates in pmi(73)/lpr(1382), causing cartesian explosion (worst date repeated 92×), polluting rolling means / phase classification / phase background painting. Added `drop_duplicates(keep="last")` by date inside `load_table()` — single-point fix; recompute yields 581 rows, 0 duplicate dates
- [fix] LPR column sparsity: same dedup fixes it — LPR (monthly, duplicated ~10× per month) now has exactly one row per value-month instead of being inflated; `lpr_1y`/`lpr_5y`/`real_rate` correctly reflect source coverage (LPR reform began 2013/2019, no data 1978–2013)
- [chore] `data/macro_data.db`: drop dead `m2_yoy_jin10` table (fetcher removed from code long ago, zero repo references, 337 stale rows). Total tables 14 → 13

### Note

- **`household_income` pipeline verified correct but unreachable in this sandbox**: targeted call to `fetch_household_income()` ran without error and degraded gracefully (no crash, no data corruption). But `ak.macro_china_nbs_nation` (NBS data.stats.gov.cn) returns non-JSON / blocked here (0.3s fast-fail), while eastmoney-style sources fetch fine (akshare 1.18.64). Run `python3 scripts/01_fetch_data.py` + `02_compute_derived.py` on a network where NBS is reachable to materialize `hh_debt_abs`/`hh_income_share`/`hh_debt_to_income` in `derived_quarterly`

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
