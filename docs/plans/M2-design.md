# M2 设计文档 — vintage 快照 + 双源比对 + 财政/外需指标层 + 值域断言与 golden 扩层

> 分支：worktree-macro-roadmap-m123 ｜ 日期：2026-08-09
> 范围纪律：M2 只做四件事——④vintage 快照+diff 工具 ⑤核心序列双源比对 ⑥财政+外需指标层 ⑦TABLE_SPECS 值域断言+golden 扩派生层。
> **不做**：沪深300 PE/估值/情绪指标、回测、AI 周报、信号历史表、事件注记、健康灯逻辑再改动（sources_health 仅按既有 warning→黄 规则多消费一个 dual divergence warning）。
> 约束：零新依赖（requirements.txt / package.json 不动）；复用现有模式（staging 闸门 / manifest / GraphCard+ECharts builder）。

## 0. 连通性探针实测（2026-08-09，akshare 1.18.83）

只选实测通过的接口进入设计。探针方式：`.venv312/bin/python` 一次性脚本逐个 try/except，打印 shape+首末行。

### 通过（进入设计）

| 接口 | shape | 时间覆盖 | 用途 |
|---|---|---|---|
| `ak.macro_china_money_supply` | (222,10) | 2008-01→2026-06（月） | m2_yoy 次源（东财 RPT_ECONOMY_CURRENCY_SUPPLY，**当前在更**） |
| `ak.macro_china_cpi_yearly` | (477,5) | 1986→数据月 2025-07（Jin10 源冻结于 2025-09） | cpi_yoy 次源（滞后，比对取最后公共日期） |
| `ak.macro_china_ppi_yearly` | (363,5) | 1995→数据月 ~2025-07（同上冻结） | ppi_yoy 次源 |
| 东财 `RPT_ECONOMY_GDP` | 30/页，分页可全取 | →2026 第1-2季度 | gdp_yoy 次源（SUM_SAME 累计同比，取「第1季度」行） |
| `ak.bond_zh_us_rate` | (9316,13) | 1990→2026-08-07（日） | 10Y 次源（中国国债收益率10年，日频→月末） |
| NBS 月度「财政 > 国家财政预算收入」 | (2,123) | 2015-02→2026-04 | fiscal 层：收入累计值+累计增长 |
| NBS 月度「财政 > 国家财政预算支出」 | (2,127) | 2015-01→2026-04 | fiscal 层：支出累计值+累计增长 |
| NBS 月度「对外经济 > 货物进出口总额」 | (14,137) | 2015-01→2026-05（美元计价） | external_demand 层：出口/进口/差额 当期值+同比 |
| `ak.macro_usa_ism_pmi` | (671,5) | 1970→数据月 ~2025-08（Jin10 源冻结于 2025-09） | 外需景气：美国 ISM 制造业 PMI |
| `ak.macro_china_exports_yoy` / `macro_china_trade_balance` | (542,5)/(565,5) | 1982/1981→冻结 ~2025 | 备用（深度不及 NBS 口径，未入表） |

### 失败（不进入设计）

| 候选 | 结果 |
|---|---|
| 东财 `RPT_ECONOMY_SHRZGM` 及 4 个变体名（SOCIAL_FINANCE/_FLOW/SOCFINANCE/SF） | 全 EMPTY → **social_finance 无双源**（现 primary 为商务部 mofcom 接口，akshare 内无其他社融接口） |
| `ak.macro_china_fiscal_revenue` / `macro_china_fiscal_expenditure` | akshare 1.18.83 不存在 |
| 东财 `RPT_ECONOMY_FISCAL` | EMPTY（东财财政仅有 `RPT_ECONOMY_TAX` 税收季报，口径不同，不入 fiscal 层） |
| `ak.index_usd_sina` | 不存在；`ak.index_global_hist_em(symbol="美元指数")` 两次 ConnectionError → **美元指数放弃** |

### 实测口径注记（影响设计）

- Jin10 系接口（cpi_yearly/ppi_yearly/usa_ism_pmi/exports_yoy）当前冻结于 2025-09 前后，
  末行为「待发布行」（今值=NaN）。作为次源只比**最后公共日期**，滞后不判任何失败。
- live DB 实测：gdp 表为年频（YYYY-01-01，值=该年 Q1 同比）；money_supply 2026-06 m2_yoy=8.0
  与次源最新值一致；bond_yield 2026-08 已含当月部分数据（月末重采样取最后交易日）。

---

## 1. Vintage 快照 + diff 工具

### 1.1 scripts/_pipeline.py 改动

```python
VINTAGE_DIR = PROJECT_ROOT / "data" / "vintages"
MAX_VINTAGES = 12

def snapshot_vintage(db_path=DB_PATH, vintage_dir=VINTAGE_DIR):
    """把当前 live 复制为 vintage（commit 前的旧版本快照）；按文件名排序保留 12 份轮转。
    返回快照 Path；live 不存在返回 None。实现模式照抄 backup_db。"""
```

- `commit_staging(staging_path, db_path, vintage_dir=VINTAGE_DIR)`：在 `os.replace` **之前**
  调 `snapshot_vintage(db_path, vintage_dir)`，并**返回** vintage Path（原返回 None）。
  语义：每次 staging 原子提升都先留下「提升前版本」，vintage 与 live 永远相差一次运行。
  （与 backups 的分工：backups 是运行**开始**前的崩溃恢复点，vintages 是运行**提交**时的
  审计快照，供 diff 回答"这次刷新到底改了什么"。）
- `01_fetch_data.py main()`：`vintage = commit_staging()` 后记
  `_MANIFEST["vintage"] = "data/vintages/macro_data_<ts>.db"`（相对路径；None 则缺省该键）。

### 1.2 scripts/diff_vintage.py（新）

默认比对 **live vs 最近一份 vintage**（vintages 目录按名排序取最新；无 vintage → 打印提示，exit 0）。

- `--vintage <path>` 指定基线；`--json` 输出 JSON，默认人类可读。
- 逐表（两库表名并集，跳过 sqlite_*）：行数 live/vintage/delta。
- 核心序列最新值差（date 列定位，各库取该列最后非空值）：

```
CORE_SERIES = [
    ("money_supply","m2_yoy"), ("cpi","cpi_yoy"), ("ppi","ppi_yoy"),
    ("gdp","gdp_yoy"), ("pmi","pmi_official"), ("social_finance","total"),
    ("bond_yield","y_10y"), ("leverage","household"),
    ("fiscal","revenue_cum"), ("external_demand","exports_yoy"),
]
```

- JSON 形状：

```jsonc
{
  "live": "data/macro_data.db", "vintage": "data/vintages/macro_data_….db",
  "identical": false,
  "tables": {"cpi": {"live_rows": 223, "vintage_rows": 222, "delta": 1}, …},
  "series": {"cpi.cpi_yoy": {"live_date": "2026-07-01", "live_value": 0.5,
              "vintage_date": "2026-06-01", "vintage_value": 1.0, "diff": null}, …}
  // diff = 同日期时 live-vintage；日期不同为 null（新旧月交替不算差异）
}
```

- 人类可读：每表一行 `cpi: 222→223 (+1)`，核心序列一行 `cpi.cpi_yoy: 1.0 @2026-06-01 → 0.5 @2026-07-01`。
- **exit code**：无差异（所有 delta=0 且同日期序列值差为 0/NaN）→ 0，否则 1。
  便于 cron/人工一眼判断"这次刷新有没有真的改数据"。

---

## 2. 双源比对 scripts/dual_sources.py（新）

### 2.1 DUAL_SERIES（6 条序列；social_finance 因探针全失败出局，见 §0）

| 序列 | primary（staging 表.列） | secondary（实测接口） | 比对点 | 容差 |
|---|---|---|---|---|
| m2_yoy | money_supply.m2_yoy | `ak.macro_china_money_supply`（月份→YYYY-MM-01，列「货币和准货币(M2)-同比增长」） | 最后公共日期 | rate |
| cpi_yoy | cpi.cpi_yoy | `ak.macro_china_cpi_yearly`（今值 dropna，日期归一见 §2.2） | 同上 | rate |
| ppi_yoy | ppi.ppi_yoy | `ak.macro_china_ppi_yearly`（同上） | 同上 | rate |
| gdp_yoy | gdp.gdp_yoy（live 实测为年频 YYYY-01-01，值=该年 Q1 同比，如 2020=−6.8/2021=18.9） | 东财 `RPT_ECONOMY_GDP`：TIME 正则 `^(\d{4})年第1季度$` 只取 Q1 行（Q1 累计==当季），SUM_SAME→YYYY-01-01 | 同上 | rate |
| pmi_official | pmi.pmi_official（现 primary 已是东财优先合并） | `ak.macro_china_pmi_yearly`（NBS 口径，滞后约一年） | 同上 | rate |

> 注：pmi_official 的 primary 本身已是「东财+akshare」合并值，故该条是六序列中
> 独立性最弱的一条（比对仅在东财主导的近期月份真正起作用）；保留它是为满足任务
> 的七序列口径（social_finance 出局后为六条），且其次源已在 fetch_pmi 内拉取、零新增请求。
| y_10y | bond_yield.y_10y（月频） | `ak.bond_zh_us_rate` 中国国债收益率10年，日频→resample("ME").last() | 同上 | level |

容差（任务给定）：
- **rate**（同比 %、PMI 点）：`abs(p−s) ≤ 0.3` **或** 相对差 `≤ 2%`（任一满足即通过——
  低基数序列相对差易爆，绝对差兜底；高基数序列反之）。
- **level**（10Y 收益率水平）：相对差 `≤ 2%`。

### 2.2 Jin10 日期归一规则（次源侧统一函数 `_norm_jin10_date`）

Jin10 历史行日期为数据月首日，近期行为**发布日**（如 2025-09-10 发布 7 月 CPI）。
规则：`day == 1` 保留；`day > 1` → 归一到**上个月** 1 日（发布月−1=数据月；1 月发布 → 上年 12 月）。
同时 dropna(今值) 去掉待发布行。离线自检覆盖跨年用例。

### 2.3 流程与 manifest 接线

- **跑点**：`01_fetch_data.py main()` fetch 循环之后、`run_derived` 之前：
  `dual_sources.run_checks(conn, fetched_ok_tables)` —— 只对本次**抓取成功**（ok=True）的
  表跑对应序列；窗口外跳过/抓取失败的表不做双源检查（primary 未更新，比对无意义）。
- **永不覆盖 primary**：run_checks 只读 staging 表 + 拉次源 df，不写任何表。
- 结果合并进 `_MANIFEST["sources"]` 对应表条目（1 表 ≤1 序列，无冲突）：

```jsonc
"dual": {
  "series": "cpi_yoy", "secondary": "ak.macro_china_cpi_yearly",
  "date": "2025-07-01", "primary": 0.0, "secondary": 0.0, "diff": 0.0,
  "divergent": false, "error": null
}
```

- secondary **抓取失败**：`dual.error = "ExceptionType: msg"`（截断 200），divergent=false——
  只记录，不红不黄（检查器自身故障不等于数据有问题）。
- secondary 抓取不设额外超时机制：与现有 fetcher 同款风险敞口（后端 run_refresh 有 300s
  总 deadline 兜底）。

### 2.4 backend/app/core/refresh.py `sources_health` 扩展（一行规则）

既有规则不动，warning 来源新增一支：

```python
# 现状：tab.status == "kept_previous" → warning
# 新增：否则若 s.get("dual", {}).get("divergent") → warning = f"dual-source divergence — {series} {primary} vs {secondary} @ {date}"
```

既有「任一源 warning 非空 → yellow」自动把 divergence 转**黄**；red 判定（2 连败）不受影响。

### 2.5 离线自检 scripts/dual_sources_test.py（新）

风格同 `release_calendar_test.py`（check() + 非零退出码，零网络）：
容差函数 rate 绝对差支路/相对差支路/越界、level 相对差；`_norm_jin10_date`
（day=1 保留 / day>1 退月 / 1 月退到上年 12 月）；GDP TIME 只匹配「第1季度」行。

---

## 3. 财政 + 外需指标层（新表 fiscal / external_demand）

**不进 signals.py、不进 02_compute_derived**——两张原始表直通 `/table/{name}`，前端直读。

### 3.1 fiscal 表

- **源**：NBS 月度数据（`ak.macro_china_nbs_nation`，与 household_income 同款接口，
  M1 后已恢复可用；本次探针实测返回数据）。period 固定 `"2015-"`（实测 123/127 个月）。
- **列定义**（单位照 NBS 口径）：

| 列 | 来源指标 | 单位 |
|---|---|---|
| date | 「2026年4月」→ `2026-04-01` | — |
| revenue_cum | 国家财政收入_累计值 | 亿元 |
| revenue_cum_yoy | 国家财政收入累计增长 | % |
| expenditure_cum | 国家财政支出(不含债务还本)_累计值 | 亿元 |
| expenditure_cum_yoy | 国家财政支出(不含债务还本)累计增长 | % |

- **fetch_fiscal(conn)**：两次 NBS 调用（收入/支出路径），各自指标行→长表转
  `date×指标`，外连接合并、按月排序，`save_to_db(result, "fiscal", conn)` 走既有闸门。
  NBS 不可达时返回空 df → 闸门记 kept_previous（与 household_income 同款降级）。

### 3.2 external_demand 表

- **源**：NBS 月度「对外经济 > 货物进出口总额」（period `"2015-"`，实测 137 个月、
  14 指标、美元计价、至 2026-05）+ `ak.macro_usa_ism_pmi`（外需景气代理）。
- **列定义**（NBS 千美元 → **亿美元**，fetcher 内 ÷1e5 并 round(2)——前端直接可读）：

| 列 | 来源指标 | 单位 |
|---|---|---|
| date | 「2026年5月」→ `2026-05-01` | — |
| exports | 出口总值_当期值 | 亿美元 |
| exports_yoy | 出口总值_同比增长 | % |
| imports | 进口总值_当期值 | 亿美元 |
| imports_yoy | 进口总值_同比增长 | % |
| trade_total_yoy | 进出口总值_同比增长 | % |
| trade_balance | 进出口差额_当期值 | 亿美元 |
| us_ism_pmi | `ak.macro_usa_ism_pmi` 今值（dropna），日期按 §2.2 归一 | 点 |

- **fetch_external_demand(conn)**：NBS 贸易块 + ISM（try/except，失败仅丢该列），
  按 date 外连接合并（ISM 冻结于 2025-08 数据月 → 近期自然为 NaN），`save_to_db(..., "external_demand", ...)`。
- **已知口径注记**（写入前端图注）：Jin10 ISM 近期行日期为发布日，§2.2 归一会把
  「9 月 2 日发布」归到 8 月（数据月），与 NBS 贸易月度对齐。

### 3.3 管线接线

- `_pipeline.TABLE_SPECS` 新增：

```python
"fiscal":           dict(min_rows=100, required=["revenue_cum", "expenditure_cum"],
                         ranges=dict(revenue_cum_yoy=(-30, 40), expenditure_cum_yoy=(-40, 70))),
"external_demand":  dict(min_rows=100, required=["exports_yoy"],
                         ranges=dict(exports_yoy=(-40, 170), imports_yoy=(-40, 70),
                                     trade_total_yoy=(-30, 80))),
```

- `release_calendar.TABLE_CALENDAR` 新增：

```python
# 财政部约每月中旬发布上月财政收支数据（与 NBS 同步）
"fiscal":          dict(kind="release", months=tuple(range(1, 13)), days=[(10, 25)], channel="nbs-akshare"),
# 海关总署约每月 7–14 日发布上月进出口（美元口径）
"external_demand": dict(kind="release", months=tuple(range(1, 13)), days=[(7, 18)], channel="nbs-akshare"),
```

- `01_fetch_data.py` fetchers 列表追加 `fetch_fiscal`、`fetch_external_demand`（14→16）。
- `backend/app/api/v1/data.py` `_ALLOWED_TABLES` += `"fiscal"`, `"external_demand"`
  （无新端点、无新 schema → shared/openapi.json 无需重导）。
- `backend/app/core/refresh.py` `EXPECTED_FETCH_STEPS` 16→**18**（16 fetcher + 2 衍生）。
- `scripts/release_calendar_test.py` 键集断言 14→16。

### 3.4 前端新页 FiscalExternal.vue（仿 DebtCycle 模式）

- **路由** `frontend/src/router/index.ts`：
  `{ path: '/fiscal-external', component: lazy('FiscalExternal'), meta: { title: '财政与外需', icon: '◫' } }`
  （插在 demographics 之后）；`Sidebar.vue` items 同步加一条。
- **数据**：`api.getTable('fiscal', start, end)` + `api.getTable('external_demand', start, end)`，
  `watchEffect(filters.start/end + refresh.lastRefreshedAt)` 重载——完全照抄 DebtCycle 的
  load/reqId/loading/error 骨架。无新 client/types 改动（DerivedFrame 复用）。
- **图表（全部复用既有 builder，零新 builder）**：

| GraphCard | builder | 内容 |
|---|---|---|
| 财政收支累计同比 | `buildMultiLine(fiscal, [revenue_cum_yoy, expenditure_cum_yoy], '%')` | 两条线 |
| 财政收支累计值 | `buildMultiLine(fiscal, [revenue_cum, expenditure_cum], '亿元')` | 两条线 |
| 进出口同比（美元计） | `buildMultiLine(ext, [exports_yoy, imports_yoy], '%', 0, '零线')` | 零线参考 |
| 贸易差额 | `buildSpreadChart(ext, 'trade_balance', '贸易差额', '亿美元', 0)` | 面积+零线 |
| 美国 ISM 制造业 PMI | `buildMultiLine(ext, [{col:'us_ism_pmi', name:'美国ISM制造业PMI'}], '', 50)` | 荣枯线 50 |

- `frontend/src/components/charts/options.ts` `COL_ZH` 追加：
  revenue_cum/财政收入(累计)、revenue_cum_yoy/财政收入累计同比、
  expenditure_cum/财政支出(累计)、expenditure_cum_yoy/财政支出累计同比、
  exports_yoy/出口同比(美元)、imports_yoy/进口同比(美元)、trade_balance/贸易差额、
  us_ism_pmi/美国ISM制造业PMI。

---

## 4. TABLE_SPECS ranges 值域断言

### 4.1 校准依据（live DB 实测 min–max，2026-08-09）

| 表 | 列 | 实测范围 | 采用 ranges（含裕量） |
|---|---|---|---|
| money_supply | m2_yoy | 6.2 – 37.31 | (0, 45)（任务示例 [0,30] 窄于实测 max 37.3，按实测放宽） |
| cpi | cpi_yoy | −1.81 – 8.74 | (−5, 10) |
| ppi | ppi_yoy | −8.22 – 13.5 | (−15, 20) |
| pmi | pmi_official | 35.7 – 59.2 | (30, 70) |
| gdp | gdp_yoy | −6.8 – 18.9 | (−10, 25) |
| social_finance | total | −658 – 72185（亿元） | (−5000, 100000) |
| bond_yield | y_10y | 1.62 – 4.55 | (0, 10) |
| fiscal | 见 §3.3 | 收入 −14.5–25.5 / 支出 −19.9–55.2 | (−30,40)/(−40,70) |
| external_demand | 见 §3.3 | 出口 −25.4–154.9 / 进口 −21.4–51.1 / 总额 −20.8–67.0 | (−40,170)/(−40,70)/(−30,80) |

出口同比上限放到 170：实测 154.9 为春节低基数脉冲（2021-02 量级），留一次同量级脉冲空间。

### 4.2 validate() 改动（_pipeline.py）

```python
# required 列检查之后新增：
for c, (lo, hi) in spec.get("ranges", {}).items():
    if c not in df.columns: continue
    s = df[c].dropna()
    if len(s) and ((s < lo) | (s > hi)).mean() > 0.10:
        return False, f"column {c!r}: >10% of non-null values outside [{lo}, {hi}]"
```

口径：**非空值**越界比例 >10% 判拒收（kept_previous 走既有通道 → 健康灯黄）。
10% 容忍度吸收个别数据修订/口径突变，整表量纲错（如单位×1000）必被拦。

---

## 5. Golden 扩派生层 backend/tests/test_derived_golden.py（新）

目的：锁死「derived_monthly 的派生列 == 02 的函数对原始表的重算」，防止 02 逻辑回归或
staging 半更新造成 raw↔derived 漂移。

```python
SAMPLE_COLS = ["m2_m1_spread", "real_rate", "pmi_ma6"]
EPS = 1e-6

def test_derived_columns_recompute_from_raw():
    stored = 从 live DB 读 derived_monthly[["date"] + SAMPLE_COLS]
    # 复制 live DB 到临时文件（不动生产库），在副本上跑 02 的 compute_derived
    tmp = tempfile.mkstemp(suffix=".db"); shutil.copy2(DB_PATH, tmp)
    conn = sqlite3.connect(tmp)
    mod = importlib 加载 scripts/02_compute_derived.py（同 _pipeline.run_derived 手法）
    monthly, _ = mod.compute_derived(conn)
    merged = stored ⋈ monthly（on date）
    assert len(merged) == len(stored) > 0
    for c in SAMPLE_COLS:
        assert np.allclose(merged[c+"_stored"], merged[c+"_fresh"], atol=EPS, equal_nan=True)
```

选列依据：m2_m1_spread（纯列算术）、real_rate（跨表 lpr−cpi）、pmi_ma6（滚动窗口）——
覆盖 02 三类派生形态。测试前置：live DB 不存在则 pytest.skip（与 test_golden 同款假设）。

---

## 6. 验收标准 + 精确文件清单 + changeLog 草稿

### 验收标准

1. **vintage**：`01_fetch_data.py` 任一成功运行后 `data/vintages/` 恰增 1 份
   `macro_data_<ts>.db`（内容 = 本次提交前的 live）；连跑 13 次后目录内恰 12 份；
   `last_run.json` 含 `vintage` 相对路径。
2. **diff**：`diff_vintage.py` 在刚运行后输出「新增行/核心序列最新值变化」，
   二次运行（无抓取变化场景外）人工改一行 live 数据后 exit 1、`--json` 形状如 §1.2；
   无差异场景 exit 0；无 vintage 时友好提示 exit 0。
3. **双源**：`--full` 实跑后 manifest.sources 中 6 个表条目各含 `dual` 键
   （date/primary/secondary/diff/divergent）；social_finance 无 dual 键；
   人为把 staging cpi_yoy 某公共月改偏 >0.3pp → divergent=true 且
   `GET /api/v1/sources/health` 为 yellow；mock 次源抛异常 → dual.error 有值、健康仍 green；
   primary 数据在任何分支下不被改动（比对前后 hash 一致）。
4. **值域**：`_pipeline_test.py` 新用例——越界 5% 通过、越界 15% 拒收（reason 含列名与区间）；
   全表量纲 ×1000 构造必拒。
5. **fiscal/external_demand**：`--full` 实跑后两表入库（fiscal ≥120 行至 2026-04、
   external_demand ≥130 行至 2026-05，us_ism_pmi 2025-08 后为 NaN）；
   `GET /api/v1/table/fiscal`、`/table/external_demand` 200；窗口外增量运行不抓这两表。
6. **前端**：`/fiscal-external` 页五图渲染、跟随顶栏时间区间与刷新联动；
   `vue-tsc --noEmit` 0 error；侧边栏新条目键盘可达。
7. **golden**：`pytest backend/tests/test_derived_golden.py` 通过（现行数据下三列逐行 ≤1e-6）。
8. **卫生**：`EXPECTED_FETCH_STEPS=18` 进度到 100%；changeLog.md [Unreleased] 同步；
   requirements.txt / package.json / tokens.css 零变化；signals.py、02_compute_derived.py、
   commentary、健康灯组件零触碰。

### 改动文件清单

**新增（6）**
- `docs/plans/M2-design.md`（本文档）
- `scripts/dual_sources.py`
- `scripts/dual_sources_test.py`
- `scripts/diff_vintage.py`
- `backend/tests/test_derived_golden.py`
- `frontend/src/pages/FiscalExternal.vue`

**修改（10）**
- `scripts/_pipeline.py`（snapshot_vintage + commit_staging 接线 + TABLE_SPECS ranges 与两条新表 spec + validate ranges 闸门）
- `scripts/_pipeline_test.py`（ranges 闸门用例 + vintage 快照/轮转用例）
- `scripts/01_fetch_data.py`（fetch_fiscal/fetch_external_demand、fetchers 14→16、dual 接线、manifest.vintage）
- `scripts/release_calendar.py`（fiscal/external_demand 窗口）
- `scripts/release_calendar_test.py`（键集 14→16）
- `backend/app/api/v1/data.py`（_ALLOWED_TABLES += fiscal/external_demand）
- `backend/app/core/refresh.py`（EXPECTED_FETCH_STEPS 16→18、sources_health dual divergence warning）
- `backend/tests/test_sources_health.py`（dual divergence→yellow 用例）
- `frontend/src/router/index.ts`、`frontend/src/components/layout/Sidebar.vue`、`frontend/src/components/charts/options.ts`（路由/侧边栏/COL_ZH——三处小改）
- `changeLog.md`、`README.md`（fetcher 数 14→16、新表与新页一行说明）

**明确不动**：`scripts/02_compute_derived.py`、`scripts/signals*`、`backend/app/core/commentary.py`、
`analysis/`、健康灯 `HealthLight.vue`、`requirements.txt`、`frontend/package.json`、`shared/openapi.json`（无 schema 变化）。

### changeLog 条目草稿（[Unreleased] 下新增 M2 段）

```markdown
### M2：vintage 快照+diff、核心序列双源比对、财政/外需指标层、值域断言与 golden 扩层

### 新功能
1. **[新功能] `scripts/_pipeline.py`**：commit_staging 前把 live 复制进 data/vintages/
   （12 份轮转），manifest 记录 vintage 路径；TABLE_SPECS 增 ranges 值域与 fiscal/
   external_demand 两条 spec；validate() 非空值越界 >10% 拒收
2. **[新功能] `scripts/diff_vintage.py`**：live vs 最近 vintage 逐表行数差+核心序列
   最新值差，JSON/人类可读双输出，无差异 exit 0
3. **[新功能] `scripts/dual_sources.py`**：m2_yoy/cpi_yoy/ppi_yoy/gdp_yoy/pmi_official/
   y_10y 六序列 primary vs 独立次源比对（rate 绝对差≤0.3pp 或相对≤2%，level 相对≤2%），
   divergence 写 sources[table].dual 并自动转黄灯；次源失败只记录；永不覆盖 primary；
   social_finance 次源（东财 SHRZGM 及 4 变体）实测全 EMPTY，本期不纳入
4. **[新功能] 财政+外需层**：fetch_fiscal（NBS 月度预算收入/支出，2015- 起）、
   fetch_external_demand（NBS 货物进出口美元口径 + 美国 ISM PMI），release_calendar
   新增两表窗口，/table 白名单放行，前端新页「财政与外需」
   （复用 buildMultiLine/buildSpreadChart，无新 builder）
5. **[新功能] `backend/tests/test_derived_golden.py`**：derived_monthly 抽样列
   （m2_m1_spread/real_rate/pmi_ma6）用 02 的函数从原始表重算 vs 存储值逐行相等（eps 1e-6）

### 验证
- ✅ scripts/dual_sources_test.py、_pipeline_test.py、release_calendar_test.py 全过
- ✅ backend pytest（含 test_derived_golden、test_sources_health 新用例）全绿
- ✅ --full 实跑：vintage 恰增 1 份、diff 输出正确、6 序列 dual 键齐全、两新表入库
- ✅ vue-tsc --noEmit 0 error；requirements.txt/package.json 零变化

### M2: Vintage Snapshots + Dual-Source Checks + Fiscal/External-Demand Layers + Range Assertions & Golden Derived Tests (English)
1. **[feat] `_pipeline.py`**: pre-commit live snapshot into data/vintages/ (rotate 12),
   manifest records the vintage path; TABLE_SPECS gains value-ranges + fiscal/
   external_demand specs; validate() rejects when >10% of non-null values fall outside range
2. **[feat] `diff_vintage.py`**: live vs latest vintage — per-table row deltas + latest-value
   deltas of core series; JSON + human-readable; exit 0 when identical
3. **[feat] `dual_sources.py`**: six core series cross-checked against independent secondary
   sources (rate: ≤0.3pp abs or ≤2% rel; level: ≤2% rel); divergence recorded in
   sources[table].dual and auto-yellows the health light; secondary failures only logged;
   primary never overwritten; social_finance excluded (all EM SHRZGM probes EMPTY)
4. **[feat] fiscal + external-demand layers**: NBS monthly budget revenue/expenditure
   (since 2015) and NBS USD-denominated trade + US ISM PMI; calendar windows, /table
   whitelist, new frontend page "财政与外需" (reuses existing ECharts builders)
5. **[feat] `test_derived_golden.py`**: sampled derived_monthly columns recomputed from raw
   tables via 02's functions must equal stored values row-by-row (eps 1e-6)
```
