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
| NIFD 宏观杠杆率（居民/非金/政府/中央/地方/实体） | `scripts/01_fetch_data.py` `_NIFD_DATA`；`scripts/03_supplement_leverage.py` `NIFD_DATA`（同内容） | 季度杠杆率(%) | 2026-06 (2026Q2) | §1 Agent 补充 |

**非时序数据（配置/分类逻辑，无需定期更新）**：
- 城市清单 `CITIES`（`frontend/src/pages/RealEstate.vue`）/ `_DEFAULT_CITIES`（`backend/app/api/v1/real_estate.py`）/ `01_fetch_data.py` 房价城市列表 —— 配置。
- `analysis/cycle_*.py`、`real_estate.py` 的 `conditions`/`choices`/`scores` —— 周期分类阈值/逻辑配置。

---

## 1. NIFD 宏观杠杆率（季度）—— 主要手工项

| 项 | 内容 |
|---|---|
| 目标表 | `leverage`（列：`date, household, non_fin_corp, gov_total, gov_central, gov_local, real_economy, fin_asset, fin_liability`） |
| 代码位置 | `scripts/01_fetch_data.py` 的 `_NIFD_DATA` 列表 + `_nifd_supplement_df()` |
| 当前补到 | **2026-03（2026Q1）** |
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

## 自动化边界说明

- **AKShare `macro_cnbs`** 会在 CNBS 更新后自动带上（无需动作），但滞后大（现到 2024-12），不可依赖。
- **不建议**把 NIFD 抓取硬塞进自动刷新：发现最新期 + 解析数字不可靠，静默失败会污染数据库。
- 推荐节奏：每季度 NIFD 报告发布后（约季后 1 个月），由 Agent 按本手册 §1 补充一期。
