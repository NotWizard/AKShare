# Change Log

## [Unreleased]

## [1.2.0] — 2026-08-24 — 空图表/报错修复 + 数据全量刷新至最新 + 前端单测基建

### CI 绿灯修复 + 版本号四处对齐（发布前置）

概述：发布 1.2.0 前修复长期红灯的 CI 与版本漂移。
变更：
  1. **[CI｜前端]** 前端 CI 的 `npm ci` 在 runner 上静默挂起约 8 分钟后崩溃（"Exit handler never called"）、node_modules 不全致 `vue-tsc` 找不到。**真因**：`package-lock.json` 有 34 个包（vitest 系新增）的 `resolved` 指向阿里内网源 `registry.anpm.alibaba-inc.com`（本机默认源，装 vitest 时被写入），GitHub 公共 runner 不可达 → 拉取卡死至超时。**修复**：把这 34 处 `resolved` 主机改回公共 `registry.npmjs.org`（仅改主机、`integrity` 哈希不变——anpm 系 npmjs 镜像、tarball 逐字节一致）。工作流一并加固：`npm ci --no-audit --no-fund --ignore-scripts`（省去易挂起的 audit/fund 与非必需 postinstall；esbuild/rollup 二进制来自 lockfile optionalDependencies）、Node 20→22。
  2. **[CI｜后端]** 3 个日期切片测试（test_golden/test_date_params）硬编码 2020 区间，而 CI 用的 fixture 月频仅 2023-2025 → 切片空。改为 2024（fixture 与 live 均覆盖），保持"有效区间应返回行并收窄全表"的原意。
  3. **[版本]** 补齐 1.2.0：`backend/pyproject.toml`、`backend/app/main.py`、`shared/openapi.json`（重生）与 `frontend/package.json` 四处一致（有 `test_openapi_drift` 守）。
验证：本地全绿——后端 320 passed、`_pipeline_test`、vue-tsc 0、vitest 42、`vite build` ✓；并按 CI 场景（挪走 live 库让 conftest 播种 fixture）实测 3 个切片测试通过。

### CI green-up + version alignment across four manifests (release prerequisite)

Summary: Before cutting 1.2.0, fix the long-red CI and version drift.
Changes:
  1. **[CI｜frontend]** The frontend CI `npm ci` hung silently ~8 min on the runner then crashed ("Exit handler never called"), leaving node_modules incomplete so `vue-tsc` was not found. **Real cause**: 34 packages (the vitest-era additions) in `package-lock.json` had `resolved` URLs pointing to Alibaba's internal registry `registry.anpm.alibaba-inc.com` (this machine's default, baked in when vitest was installed), which GitHub's public runners cannot reach → the fetch hung until timeout. **Fix**: rewrite those 34 `resolved` hosts back to the public `registry.npmjs.org` (host only; `integrity` hashes unchanged since anpm mirrors npmjs with byte-identical tarballs). The workflow was also hardened: `npm ci --no-audit --no-fund --ignore-scripts` (drops the hang-prone audit/fund and non-essential postinstalls; esbuild/rollup binaries come from lockfile optionalDependencies) and Node 20→22.
  2. **[CI｜backend]** Three date-slice tests (test_golden/test_date_params) hardcoded a 2020 range, but the CI fixture's monthly tables span only 2023-2025 → empty slice. Changed to 2024 (covered by both the fixture and the live DB), preserving the "a valid range returns rows and narrows the table" intent.
  3. **[version]** Completed the 1.2.0 bump across `backend/pyproject.toml`, `backend/app/main.py`, a regenerated `shared/openapi.json`, and `frontend/package.json` (guarded by `test_openapi_drift`).
Verification: all green locally — backend 320 passed, `_pipeline_test`, vue-tsc 0, vitest 42, `vite build` ✓; and the 3 slice tests verified against the CI scenario (moving the live DB aside so conftest seeds the fixture).

### 数据刷新至最新 + 库快照入库：全表复核全部当期，杠杆率补 2026Q2

概述：应「确定所有数据都刷成最新」的要求，跑通全量重采 + 两处补充，并派多个 Agent 交叉复核确认**全部 18 张数据表均已到达各自真实的最新可得值**。
变更：
  1. **[数据｜杠杆率]** 跑 `03_supplement_leverage.py` 把 NIFD 2026Q2（2026-06）补入 `leverage`（85→86 行），`derived_quarterly` 同批重算（含 `hh_debt_to_income`）。
  2. **[数据｜全量重采]** `01_fetch_data.py --full`：14 表 updated（cpi 经修复后的闸门首次前进、pmi/lpr/social_finance 等至 2026-07/08）、2 表 kept_previous（leverage 因 CNBS `[Errno 9]` 网络抖动保留 03 补的 2026-06；bond_yield 因源抖动保留既有 2026-08）——闸门保护，无回归。
  3. **[快照]** 把最终一致的库快照 `data/vintages/macro_data_20260824_181018.db`（VACUUM 干净副本）纳入版本，取代旧的 `_170759`（同表结构但杠杆/社融陈旧）；`.gitignore` 白名单相应更新。
验证（跨 Agent 复核，全 PASS）：全表 `MAX(date)` 与真实发布节奏逐一对齐——月频齐至 2026-07、lpr/bond 至 2026-08、gdp Q2、杠杆/派生季频 2026-06、fiscal 至 NBS 源封顶 2026-05、demographics/household_income 为最新年报 2025；社融与 `new_credit`/`money_supply` 同期一致。

### Data refreshed to latest + DB snapshot committed: full-table re-audit confirms every series current, leverage folded to 2026 Q2

Summary: In response to the "make sure all data is refreshed to latest" request, a full re-collection plus two supplements were run, and multiple cross-review agents independently confirmed **all 18 data tables are at their genuine latest-available value**.
Changes:
  1. **[data｜leverage]** Ran `03_supplement_leverage.py` to fold NIFD 2026 Q2 (2026-06) into `leverage` (85→86 rows); `derived_quarterly` recomputed in the same batch (incl. `hh_debt_to_income`).
  2. **[data｜full re-collection]** `01_fetch_data.py --full`: 14 tables updated (cpi advanced for the first time through the fixed gate; pmi/lpr/social_finance etc. to 2026-07/08), 2 kept_previous (leverage kept the 03-folded 2026-06 through a CNBS `[Errno 9]` network blip; bond_yield kept its existing 2026-08 through a source blip) — gate-protected, no regression.
  3. **[snapshot]** Committed the final consistent DB snapshot `data/vintages/macro_data_20260824_181018.db` (a clean VACUUM copy), replacing the older `_170759` (same schema but stale leverage/social finance); the `.gitignore` whitelist is updated accordingly.
Verification (cross-agent reviewed, all PASS): every table's `MAX(date)` lines up with its real release cadence — monthlies at 2026-07, lpr/bond at 2026-08, gdp Q2, leverage/derived quarterly 2026-06, fiscal at the NBS source cap 2026-05, demographics/household_income at the latest annual 2025; social finance consistent with `new_credit`/`money_supply`.

### CPI 校验闸门过窄修复：合并历史高通胀行被拦 → CPI 永久刷不进（根因）

概述：承上一条「空图表排查」里记为 `cpi kept_previous` 的悬案——`cpi` 每次重采都被验证闸门拒收、永远停在旧值。根因是 `_pipeline.py` 的 `cpi_yoy` 值域上限设为 10，而 `fetch_cpi` 会把东财新序列与库内历史合并，库内含 1989-03≈28.4%、1994-11≈27.7% 的真实高通胀月（全序列约 12% 的行 > 10），于是**每一帧合并结果都有行越界 → 整表 replace 被拒 → CPI 冻结**。属护栏误配，非数据问题。

变更：
  1. `scripts/_pipeline.py`：`cpi` 值域 `cpi_yoy` 上限 10 → 30，覆盖中国 CPI 同比历史峰值（1989/1994 两位数通胀），附注根因。此为校准纠偏、非放松（30 仍能拦下解析错位的天文值）。同时补 `max_date_lag=200`（对齐 ppi）——跨监督复核指出 cpi 原无新鲜度灯、源若将来静默冻结无从告警，现已补上。
  2. 同步两处硬编码断言 `backend/tests/test_ranges.py`、`scripts/_pipeline_test.py`（reason 字符串 `[-5, 10]` → `[-5, 30]`）。
验证：`01_fetch_data.py --full` 实跑，`cpi` 首次穿过闸门（486 行 → staging，prev 486）、live 现 2026-07；后端 320 passed、`_pipeline_test.py` 全绿。

### Fix: CPI validation gate too narrow — merged historical high-inflation rows rejected → CPI could never refresh (root cause)

Summary: resolves the `cpi kept_previous` mystery flagged in the previous "empty charts" entry — every CPI re-fetch was rejected by the validation gate and frozen at the old value. Root cause: `_pipeline.py` capped `cpi_yoy` at 10, but `fetch_cpi` merges the fresh Eastmoney series with historical DB rows that include real high-inflation months (1989-03≈28.4%, 1994-11≈27.7%; ~12% of the series exceeds 10), so **every merged frame had out-of-range rows → the whole-table replace was rejected → CPI stuck**. A misconfigured guardrail, not a data problem.

Changes:
  1. `scripts/_pipeline.py`: `cpi_yoy` upper bound 10 → 30, covering China's historical CPI YoY peaks (1989/1994 double-digit inflation), with the root cause noted. A calibration fix, not a loosening (30 still rejects parse-misalignment astronomical values). Also adds `max_date_lag=200` (matching ppi) — the cross-review noted cpi had no freshness lamp, so a future silent source-freeze couldn't raise an alert; now it can.
  2. Updated the two hardcoded assertions in `backend/tests/test_ranges.py` and `scripts/_pipeline_test.py` (reason string `[-5, 10]` → `[-5, 30]`).
Verification: a live `01_fetch_data.py --full` run shows `cpi` clearing the gate for the first time (486 rows → staging, prev 486); live is now 2026-07; backend 320 passed, `_pipeline_test.py` all green.

### 社会融资规模补齐到 2026-07：PBoC 备用源抽为单一真相源 + 独立补充脚本（04）

概述：`social_finance` 停在 2026-04（akshare `macro_china_shrzgm` 源封顶），而 PBoC 官方 XLSX 已有 05/06/07。主管线里社融排在 `leverage`（`ak.macro_cnbs` 走线程超时封装）之后，CNBS 超时的被弃线程会损坏进程 socket fd（`[Errno 9] Bad file descriptor` 级联），紧随其后的 PBoC `requests` 也失败并被静默吞空 → 社融永远补不进。

变更：
  1. **[抽取单一真相源]** 把 PBoC 社融 XLSX 抓取从 `01_fetch_data.py` 私有函数抽到新模块 `scripts/pbc_shrzgm.py`（`pbc_shrzgm_supplement_df`），对照 `nifd_leverage.py` 先例；`01` 改为 import 复用，`fetch_social_finance` 行为不变。
  2. **[新增 `scripts/04_supplement_social_finance.py`]** 对照 `03_supplement_leverage.py`：脱离主管线级联，单独 backup→staging→合并（仅追加 date>现有max 且 total 非空的 PBoC 月，未发布 NaN 月不追加）→ `validate()` 闸门 → enforce_indexes + run_derived → 原子交换；任何失败丢弃暂存、live 逐字节不动。
  3. **[新增 `backend/tests/test_social_finance_supplement.py`（4 例）]** 覆盖 fold+丢 NaN、闸门拒收 live 不动、无新增 noop、缺库报错；变异测试（禁用 dropna）精确打中 1 例 FAIL 证明有牙。
验证：跑 04 → 补 05/06/07 三行、`social_finance` 139 行 @2026-07、`derived_monthly` 同批重算；后端 320 passed（含新 4 例）；全表新鲜度复核：所有月频表齐至 2026-07，社融与 `new_credit`/`money_supply` 同期一致。

### Social financing brought current to 2026-07: PBoC fallback extracted to a single source + standalone supplement script (04)

Summary: `social_finance` was stuck at 2026-04 (akshare's `macro_china_shrzgm` source caps there) while the official PBoC XLSX already has 05/06/07. In the main pipeline social finance runs after `fetch_leverage`, whose `ak.macro_cnbs()` timeout abandons a thread that corrupts the process socket fd (`[Errno 9] Bad file descriptor` cascade), so the subsequent PBoC `requests` call also fails and is swallowed to empty → social financing never advances.

Changes:
  1. **[extracted a single source of truth]** Moved the PBoC social-finance XLSX scraper out of a private function in `01_fetch_data.py` into a new module `scripts/pbc_shrzgm.py` (`pbc_shrzgm_supplement_df`), mirroring the `nifd_leverage.py` precedent; `01` now imports it, `fetch_social_finance` behavior unchanged.
  2. **[new `scripts/04_supplement_social_finance.py`]** Modeled on `03_supplement_leverage.py`: runs outside the pipeline cascade — backup→staging→merge (append only PBoC months with date > current max and non-null total; unpublished NaN months are not appended) → `validate()` gate → enforce_indexes + run_derived → atomic swap; any failure discards staging and leaves live byte-identical.
  3. **[new `backend/tests/test_social_finance_supplement.py` (4 cases)]** Covers the fold + NaN-drop, gate rejection leaving live untouched, the no-op case, and the missing-DB error; mutation-testing (disabling the NaN-drop) fails exactly one case, proving teeth.
Verification: running 04 folds 05/06/07 (three rows), `social_finance` is 139 rows @2026-07 with `derived_monthly` recomputed in the same batch; backend 320 passed (incl. the 4 new cases); a full freshness re-audit shows all monthly tables current to 2026-07, with social financing consistent with `new_credit`/`money_supply`.

### 空图表 / 报错页面排查 + 数据补全（前端反馈）

概述：用户在浏览器发现「财政与外需」整页报错、「债务周期」个别图为空、多页指标陈旧。逐页 + 数据库 + 代码三方排查后定位并修复；同时核查数据文档要求的"手工补充"数据——**经查 NIFD/ISM/出生率/CRCL 全部已是最新、零缺口**（唯一 stale 是 runbook 文档一行，已修）。真正根因是数据陈旧 + 一处依赖锁定 + 一处代码不健壮：

变更：
  1. **[G-fix｜/table 缺表健壮性]** `backend/app/core/db.py::_load_full_versioned` 对"表不存在"优雅降级返回空帧，而非让 `OperationalError` 冒泡成 HTTP 500——白名单内但尚未采集的表（如 `fiscal`/`external_demand`）前端显示"暂无数据"而非整页错误卡。新增 `test_missing_table.py`（5 例，变异验证有牙）。改一处覆盖所有走 `db.load` 的端点。
  2. **[数据｜派生重算]** `derived_quarterly` 是旧年频产物（21 行、9 个杠杆列全 NULL），而 `leverage` 源表齐全（85 行到 2026-03）；重跑 `02_compute_derived.py` → 85 行季频、`household` 等填充 → 修「债务周期·居民真实杠杆空间」空图。
  3. **[依赖｜akshare 1.18.64 → 1.18.83]** **根因**：`fiscal`/`external_demand`/`household_income` 三表恒空 → `/table/*` 500 → 财政外需页整页错误卡，因为 1.18.64 内部仍调被 WAF 封禁的旧 NBS 端点 `easyquery.htm`（实测 **403**）；1.18.83 重写 `macro_china_nbs_nation()` 走新站 `queryIndexTreeAsync` API。升级前备份 live 库、升级后按 `requirements.txt` 要求跑回归（pytest 316 + pipeline 全绿），实测五个生产路径（财政收入/支出、货物进出口、居民收入、总人口）**5/5 可取数**。同步 `requirements.lock`。
  4. **[数据｜全量重采]** 用 1.18.83 跑 `01_fetch_data.py --full`：新建 `fiscal`(128 行)/`external_demand`(139 行)/`household_income`(30 行)，`pmi` 前进到 2026-07、`lpr` 去重到 155 行、`social_finance`/`gdp`(21→82 累计季度) 前进；13 表 updated / 3 kept_previous（`money_supply`/`cpi`/`leverage` 无变化或值域校验拦下，非丢失）。`derived_quarterly.hh_debt_to_income` 现非空（2026-03=135.7，落在校验区间 120-140）。
  5. **[文档]** `docs/data-sources-guide.md` §十一 补 2026-08-24 时间线，点明 NBS 修复依赖 `akshare>=1.18.83`（教训：爬虫库精确锁定会把失效上游一同冻死）；`docs/data-supplement-runbook.md` §0/§1 修正 NIFD 单一源与 2026Q2 现状。
验证：`/table/fiscal|external_demand|household_income` 均 200 有数据；`/derived/quarterly` 85 行含 `hh_debt_to_income`；财政外需页 5 图渲染、债务页无空图；pytest 316 + pipeline 全绿；playwright 逐页无 red error（Qoder 注入的 MutationObserver 除外）。

### 前端单测补齐：引入 vitest，覆盖 client/stores/composables/图表 builder（收口 G18 缺口）

概述：v1.1.0 时 G18 唯一的诚实缺口——前端无 test runner、`client.ts`/`options.ts` 等逻辑无单测——现已补齐：引入 **vitest**（唯一新增 devDep），对本轮审计改动过的前端逻辑热区写了 **42 个单测**，并接入 CI。

变更：
  1. [基建] 新增 `frontend/vitest.config.ts`（复用 vite 的 `@` alias、node 环境；**不引入 jsdom**——待测逻辑用 mock `fetch` + stub `rAF` 即可，避免多余依赖）；`package.json` 加 `test`/`test:run`；`.github/workflows/ci.yml` 的 frontend job 在 typecheck 与 build 之间插入 `npm run test:run`（逻辑回归先于慢构建暴露）。
  2. [测试｜42 例] `client.ts`：GET 指数退避重试(408/429/5xx)、4xx 不重试、传输失败重试到上限、错误分类(`unreachable/timeout/aborted/server/client`)、TTL 缓存 + `invalidateCache`、in-flight 去重、`NO_CACHE` 端点、POST 带令牌与 **401→重取令牌重放一次**、`qs` 丢弃 undefined；`filters`(FE-L1 时区：`setSystemTime` 到 7 月锁定，断言按本地日历部件构造、日恒 `01`)；`useCountUp`(FE-L6：`0` 显示 `0.0` 而非 `—`)；`useAsyncData`(FE-H2：`ok/error`、自身 `aborted` 不算错、superseded 与作用域销毁后不改态)；`refresh` store(FE-H4/L2：SSE 分帧、progress、`done→markRefreshed`、macro/crcl 独立 bump、`job_id=null` 不订阅、单个畸形事件不杀流、无 `done` 不谎报成功)；`options` 9 个 builder(FE-L7：`markLine` 挂到**每个** series 而非仅 `[0]`；phase 分组；缺字段回退)。
  3. [有牙实证] 变异测试三处关键点各精确打中 1 例并 FAIL：`useCountUp` 退化为 truthy 判空、`markLine` 仅挂 `series[0]`、禁用 401 重放——恢复后 42 passed。
验证：`vitest` 42 passed（7 文件）；`vue-tsc` 0；后端 311 passed；`_pipeline_test.py` ALL CHECKS PASSED。

### frontend unit tests added: vitest covering client/stores/composables/chart builders (closes G18's gap)

Summary: G18's one honest gap at v1.1.0 — the frontend had no test runner, so `client.ts`/`options.ts` and friends had no unit tests — is now closed: **vitest** was introduced (the single new devDep), **42 unit tests** cover the frontend logic this audit touched, and they run in CI.

Changes:
  1. [infra] Adds `frontend/vitest.config.ts` (reuses vite's `@` alias, node environment; **no jsdom** — the logic under test is exercised with a mocked `fetch` + stubbed `rAF`, so no extra dependency); `package.json` gains `test`/`test:run`; the frontend CI job runs `npm run test:run` between type-check and build (logic regressions fail before the slower build).
  2. [tests｜42] `client.ts`: GET exponential-backoff retry (408/429/5xx), no retry on 4xx, retry-to-limit on transport failure, error classification (`unreachable/timeout/aborted/server/client`), TTL cache + `invalidateCache`, in-flight dedupe, `NO_CACHE` endpoints, POST token + **401→refetch-token-and-replay-once**, `qs` dropping undefined; `filters` (FE-L1 timezone: `setSystemTime` to July, asserting local-calendar-part construction with the day always `01`); `useCountUp` (FE-L6: `0` renders `0.0`, not `—`); `useAsyncData` (FE-H2: `ok/error`, a self-inflicted `aborted` is not an error, superseded/disposed runs don't mutate state); `refresh` store (FE-H4/L2: SSE framing, progress, `done→markRefreshed`, independent macro/crcl bumps, `job_id=null` doesn't subscribe, one malformed event doesn't kill the stream, no `done` doesn't fake success); the 9 `options` builders (FE-L7: `markLine` attached to **every** series, not just `[0]`; phase grouping; missing-field fallback).
  3. [proven to have teeth] Mutation-testing three key points each failed exactly one case: `useCountUp` degraded to a truthy check, `markLine` attached only to `series[0]`, and the 401 replay disabled — restored → 42 passed.
Verification: `vitest` 42 passed (7 files); `vue-tsc` 0; backend 311 passed; `_pipeline_test.py` ALL CHECKS PASSED.

### 收口 v1.1.0 遗留：联网 e2e 全年重放（G30 / P-L）

概述：v1.1.0 发布时唯一挂账的「联网 e2e 全年重放未复跑」现已**真实执行完毕**，并顺带修掉验证器自身两处缺陷与一处 gitignore 漏项。

变更：
  1. **[验证｜已实跑]** 真实联网跑通全年重放：TLS 默认 CA 直连 **HTTP 200**（正文 150214 字节）→ 认表命中（页面 2 张表、数据表 474 行）→ 21 年并发抓取 → 月频重采样 **246 个月**，最新 `2026-08-01 = 1.6839`，收益率区间 1.6243–4.5518 → `validate()` 闸门 **`status=updated, new_rows=246, unique_index=ux_bond_yield_date, checks=pass`** → UNIQUE 索引重建。全程只写临时库，`data/macro_data.db` **逐字节未动**（`git status data/` 干净）。
  2. **[验证｜意外增益]** 第二次重放时环境网络中途断开（2024–2026 三年失败），恰好在真实场景验证了两项修复的保护行为：`2a3b8a0` 的**逐年 ⚠️ 告警**如实记录三次 `ConnectionError`（改前会静默返回空表、无人知晓），而 P-M7 的**新鲜度闸门**据此算出 `newest date 2023-12-01 is 997d behind > max_date_lag 200d` 并**拒收**（`kept_previous`），保住了既有好数据。同时 **214 个已收官月与 live 库数值完全一致（最大差 0.0000）**，证明解析链路零回归。
  3. **[新增] `backend/tests/test_bond_yield_e2e.py`（3 例）**：离线**全链路**重放——除 socket（`mod.requests`）外全为真代码（真 `ThreadPoolExecutor` 并发、真 `read_html`、真 `resample("ME").last()`、真 `save_to_db`→`validate()`→`to_sql`→UNIQUE 索引）。夹具按实测真实结构构造（表单表同样带「曲线名称」列、数据表混入需筛掉的其它曲线且其值 99.0 会打爆闸门 ranges）。覆盖：21 年抓取覆盖面、调用方不得再传 `verify`、月末值取 last 而非 first/mean、闸门 updated + 索引重建、上游整体冻结时拒收、页面改版时逐年留痕含 `LookupError`。**变异测试证明有牙**：把 `.resample("ME").last()` 改成 `.first()` → 失败，恢复 → 3 passed。
  4. **[新增] `scripts/verify_bond_yield_e2e.py`**：可复用的联网验证器（四步、带断言与退出码），供任意有网机器一条命令闭环；只写 `tempfile`、以 `mode=ro` 只读比对 live，**绝不触碰 live 库**。
  5. **[修复] 验证器自身两处缺陷**（首跑即暴露）：(a) 回归比对未排除 live 的**未收官月**——live 采集于 2026-07-21（7 月未结束），`resample last` 当时只能取到月中最后交易日 1.7453，7 月收官后正常修订为 1.7141，验证器却把这 0.0312 报成回归；现改为排除未收官月并单独提示。(b) 把「网络抖动导致部分年份失败」与「代码缺陷」混判——现统计失败年份数，序列不完整时按「预期拒收」断言，只在 0 年失败时才要求闸门 `updated`。
  6. **[修复] `.gitignore` 漏项**：G09 新增的 CRCL 单飞锁 `data/.crcl_collect.lock` 未被忽略（此前只列了 `data/.refresh.lock`），每次跑完都冒出未跟踪文件；改为通配 `data/*.lock` 一并覆盖。

验证：
  1. 全套 **311 passed**（v1.1.0 的 308 + 本次 3 例）；`scripts/_pipeline_test.py` ALL CHECKS PASSED。
  2. 联网验证器在有网时四步全绿、断网时第 1 步即优雅退出并明确报因（退出码 1），两种路径均实测。

### Closing the v1.1.0 leftover: networked full-year e2e replay (G30 / P-L)

Summary: the single item left open at v1.1.0 — "the networked full-year e2e replay could not be re-run" — has now **actually been executed**, and doing so also surfaced two defects in the verifier itself plus a gitignore gap.

Changes:
  1. **[verification｜executed for real]** The live full-year replay passed end to end: a default-CA connection returned **HTTP 200** (150214-byte body) → table picked correctly (2 tables on the page, 474 data rows) → 21 years fetched concurrently → resampled to **246 monthly points**, latest `2026-08-01 = 1.6839`, yields spanning 1.6243–4.5518 → the `validate()` gate reported **`status=updated, new_rows=246, unique_index=ux_bond_yield_date, checks=pass`** → the UNIQUE index was rebuilt. Only a temporary database was written; `data/macro_data.db` was **left byte-identical** (`git status data/` clean).
  2. **[verification｜unexpected upside]** A second replay hit a mid-run network drop (2024–2026 failed), which happened to validate both fixes' protective behaviour against reality: the **per-year ⚠️ warnings** from `2a3b8a0` faithfully recorded three `ConnectionError`s (previously these years returned an empty frame with nobody the wiser), and P-M7's **freshness gate** consequently computed `newest date 2023-12-01 is 997d behind > max_date_lag 200d` and **rejected** the write (`kept_previous`), preserving the good data. Meanwhile **all 214 closed months matched the live database exactly (max diff 0.0000)**, showing the parsing chain has no regression.
  3. **[added] `backend/tests/test_bond_yield_e2e.py` (3 cases)**: an offline **full-chain** replay in which only the socket (`mod.requests`) is faked — everything else is real code (real `ThreadPoolExecutor` concurrency, real `read_html`, real `resample("ME").last()`, real `save_to_db`→`validate()`→`to_sql`→UNIQUE index). Fixtures mirror the measured page structure (the form table also carries a 曲线名称 column; the data table mixes in another curve whose 99.0 value would blow the gate's ranges if not filtered). Coverage: the 2006→current fetch span, the caller no longer passing `verify`, month-end values taken by last rather than first/mean, gate `updated` + index rebuild, rejection when the upstream is wholly frozen, and per-year traces containing `LookupError` when the page is redesigned. **Mutation-tested for teeth**: switching `.resample("ME").last()` to `.first()` makes it fail; restored → 3 passed.
  4. **[added] `scripts/verify_bond_yield_e2e.py`**: a reusable networked verifier (four steps, assertions and an exit code) so any connected machine can close the loop with one command; it writes only to `tempfile` and compares against live read-only (`mode=ro`), **never touching the live database**.
  5. **[fixed] two defects in the verifier itself**, both exposed on its first run: (a) the regression comparison did not exclude live's **open (incomplete) month** — live was collected on 2026-07-21 while July was still running, so `resample last` could only reach the mid-month trading day at 1.7453, which legitimately revised to 1.7141 once July closed; the verifier reported that 0.0312 as a regression. It now excludes the open month and reports it separately. (b) It conflated "a flaky network failing some years" with "a code defect"; it now counts failed years and, when the series is incomplete, asserts the gate's *expected rejection* instead, requiring `updated` only when zero years failed.
  6. **[fixed] `.gitignore` gap**: the CRCL single-flight lock `data/.crcl_collect.lock` added by G09 was never ignored (only `data/.refresh.lock` was listed), so every run left an untracked file behind; both are now covered by a `data/*.lock` glob.

Verification:
  1. Full suite **311 passed** (v1.1.0's 308 plus these 3); `scripts/_pipeline_test.py` ALL CHECKS PASSED.
  2. The networked verifier was exercised on both paths: all four steps green with connectivity, and a graceful step-1 exit with an explicit reason (exit code 1) without it.


## [1.1.0] — 2026-08-24 — 代码审计修复批次 + 数据源参考手册交叉验证与修正

### 代码审计修复批次（v1.1.0）

概述：基于 2026-08 五模块代码审计，逐个功能点修复约 40 处缺陷（正确性 / 稳定性 / 安全 / 交互 / 工程），进度账本见 `docs/AUDIT_FIXES.md`。以下按功能点滚动追加。

变更：
  1. [基础设施] 新增 `docs/AUDIT_FIXES.md` 审计修复账本（30 个修复组，含严重度 / 位置 / 根因方案 / 复核人 / 提交 / 证据，供断点续跑）；`.gitignore` 补忽略 `.playwright-mcp/`、`backtest_hshylv/`、根目录截图 PNG，避免误入后续提交。
  2. [G19｜F9 High] 日期参数类型化：`/derived/monthly`、`/derived/quarterly`、`/table/{name}`、`/cycles/{name}` 的 `start`/`end` 声明为 `date | None`，非法日期在进入处理器前即返回 422；删除 `db.load` 静默的 `try/except`。修复此前非法 `start` 在月度端点静默返回全表（口径错误）、在周期端点抛 500 的不一致。新增 `test_date_params.py`（6 例，改前 3 例失败）。
  3. [G04｜F5 High] JSON 非有限值安全：新增全局 `SafeJSONResponse`（`default_response_class`），递归将 `NaN`/`±Inf` 转 `null`；`serial` 改用 `isfinite` 兼顾 ±inf；`crcl_db.set_snapshot` 落库前清洗，避免 `NaN` 字面量写入 SQLite。修复此前无 `response_model` 的端点（全部 `crcl/*`、`real-estate`）遇 yfinance `NaN` 直接 HTTP 500 且坏值持久化到库。新增 `test_json_safety.py`（3 例，改前失败）。
  4. [G01｜A-C1 Critical] 美林时钟判据重构：`gdp_trend` 由对异常值敏感的滚动均值改为滚动中位数（对 2020/2021 基数效应稳健），并加入迟滞（0.5pp 死区 + 连续 2 期持续），消除"相对自身趋势"误判。真实数据 +5% 增长、低 CPI 由 recession 纠正为 recovery，composite 由 −2 回到 0（中性）。`02_compute_derived.py` 保持不动（原始 gdp 每年仅 Q1 单季行，全年 YoY 无法从库重建，故在分类器侧稳健化）。新增 `test_merrill_phase.py`（8 例，改前 6 例失败）。
  5. [G02｜F1/F2/F8 Critical] 刷新锁改 `fcntl.flock` 原子互斥：消除"检查-占用"竞态（两个刷新并发写同一 staging → 生产库损坏）；超时改用独立墙钟 deadline + 读线程，静默挂死的采集子进程能被真正 kill（此前超时判断在 `for line in proc.stdout` 内，无输出即永不触发）；`is_running()` 改为无副作用探测（不再 unlink 运行中的锁）；CLI(`01_fetch_data.py`) 与 API 共享同一锁。新增 `test_refresh_lock.py`（5 例）。
  6. [G07｜FE-C1/FE-H1 Critical] 前端图表渲染重构：大序列数据改 `shallowRef`+`markRaw`，option 由模板表达式移入 `markRaw` 的 `computed`，`EChart` 用 `notMerge:false`+`lazyUpdate` 增量合并（缩放/图例跨刷新保留）；`GraphCard` 停止 `v-if` 卸载图表、改绝对定位遮罩 + `min-height` + `@retry`。附带修复：象限/散点图（美林、库存四象限）加 `:not-merge="true"` 避免相位集收窄时的残影序列。`vue-tsc --noEmit` 0 error。
  7. [G05｜O-C2 Critical] FastAPI 托管前端 + run_app.sh 单进程化：SPA 由 FastAPI 提供（`/assets` 静态挂载 + 404 兜底回退 index.html，未命中的 `/api/*` 仍返回 JSON 404 而非 HTML 壳，带路径穿越防护），移除 `vite preview` 双进程；`run_app.sh` 改单进程 uvicorn、按 `frontend/src`+lockfile 指纹重建 dist、`npm ci`、就绪失败 `exit 1` 不再假报成功、`cleanup() { set +e; }` 稳健回收。修复此前 cleanup 断裂/端口漂移导致的旧构建残留。新增 `test_static_serving.py`（10 例）。
  8. [G03｜F3 High] 缓存按数据版本失效：`db._load_full`/`compute_signals` 的 lru_cache 键纳入 `_db_version()=(mtime_ns,size)`，任何来源（API/CLI/cron）`os.replace` 换库后自动失效并重读，不再依赖"仅 run_refresh 成功时清缓存"的调用路径（此前 CLI/cron 换库或提交后异常 → API 永久返回旧数据）；`clear_all_caches()` 保留为内存回收助手。新增 `test_cache_version.py`（3 例，改前"换库仍返回旧 DataFrame"失败）。
  9. [G06｜O-C1/B1 Critical + P-H2] 健康端点说真话 + 采集非零退出：`sources_health` 对空 sources 由 green 改判 `unknown`（灰），并新增新鲜度规则（manifest 过期 → 黄/红），不再"空即绿 / 永不过期"；`01_fetch_data.py` 汇总退出码，任一表因失败落 `kept_previous` 即非零退出（区别于窗口外跳过），使 cron/launchd 能感知局部失败；引入 logging。新增 `test_health_truthfulness.py`，并将 `test_sources_health` 的"空→green"断言更正为"空→unknown"（口径修正非弱化）。
  10. [G22｜A-M4 Medium] 手工 JSON schema 校验：`/crcl/events`、`/crcl/fundamentals` 加载时以 pydantic 校验字段类型/日期格式/枚举，语义错误（数字写成字符串、坏日期）不再静默透传前端或被伪装成"评估异常"，改为明确报错并记日志；`crcl_alerts` 数值比较前强制数值化，`_eval_y_nonreserve_stagnant` 要求相邻两季而非任意两非空季。新增 `test_crcl_json_schema.py`。
  11. [G24a｜F13 Medium] 信号历史读取只吞良性错误：`read_history` 由 `except sqlite3.Error: return []`（吞掉一切）改为仅在"表不存在"（全新安装）时返回空，schema 漂移 / 库损坏等其余错误一律冒泡，不再把"读取失败"伪装成"暂无数据"。新增 `test_signal_history_errors.py`（2 例，schema 漂移改前静默返回 [] 失败）。
  12. [G17+G27｜O-H2/O-M2/O-M3/O-M6/O-L3] 依赖锁定与运维卫生：`akshare` 由 `>=1.14.0` 改为**精确锁 `==1.18.64`**（爬虫库 minor 升级会静默改列名，与 `data/last_run.json` 记录版本对齐，并在注释里写明升级前须跑 `diff_vintage`/`dual_sources` 回归）；其余依赖下界全部对齐实测在用版本并加大版本上界（原 `pandas>=1.5`/`numpy>=1.24` 跨大版本、按下界解出的组合根本跑不通）；新增 `requirements.lock`（离线由 `pip list --format=freeze` 生成的传递闭包，不伪造 hash）；`backend/pyproject.toml` 不再另列一份分析依赖，改以 `requirements.txt` 为唯一权威；`run_app.sh` 解释器改按 `PYTHON`/`VENV` 覆盖 → `.venv312` → `.venv` → `python3` 解析并在缺依赖时给出可执行的引导信息（此前新克隆第一行就因硬编码 `.venv312` 而死），uvicorn 日志由 `/tmp` 移到 `data/logs/`；新增 `.env.example`（仅占位值，含 `COMMENTARY_*`/`REFRESH_TIMEOUT_S`/`HEALTH_STALE_DAYS`，且确认未被 gitignore）；`README.md` 纠正三处失实陈述（`.venv312` 实为 Python 3.12.14 而非 3.14.6、`_pipeline_test.py` 不会被 pytest 收集、OpenAPI 契约并未防住 CRCL 类型漂移）并改写为单进程 `:8000` 启动说明。
  13. [G23+G03b｜A-H1/A-H2/A-H3/A-M5 + F3 余项/F15] 信号鲁棒性与缓存版本键：composite 聚合前做 as-of 对齐并暴露各子信号自身日期，缺失子信号从"按 0 计入"改为剔除后按可用项归一（此前缺数据被当中性、且 `iloc[-1]` 遇空表直接 `IndexError` 让 `/signals` 500）；`cycle_inventory` 不再要求 `pmi_official` 与 `ip_yoy` 同时非空——此前 pmi 只到 2025-08 而 ip_yoy 到 2026-06，导致库存信号被钉在 10 个月前却与最新信贷相加；`real_estate` 价格动量缺失时回退中性而非 `0.0`（旧值经打分算出最偏空分，等于"缺数据=强看空"）；`cycle_debt` 由"任一部门去杠杆即 beautiful_deleveraging"改为按净/多数部门方向判定，并把 `gdp_yoy > 0`（对中国近乎恒真、使三个偏空分支不可达）换成与美林一致的相对趋势判据；`cycle_credit` 对脉冲加平滑 + 死区 + 持续期，消除 0.04↔0.05 级噪声引起的 easing/neutral 抖动。G03b：`classify_*` 与 `_analyze_real_estate_cached` 的 lru_cache 键纳入 DB 版本，CLI/cron 换库后 `/cycles/{name}`、`/real-estate` 不再滞留旧值（此前只有先打 `/signals` 才会顺带刷新）；`real_estate` 缓存键按 `tuple(sorted(set(cities)))` 归一（F15，消除顺序/重复造成的缓存抖动）。新增 `test_signal_robustness.py`（24 例，改前 22 例失败）。
  14. [G11+G12+G20+G21｜P-H1/P-H3/P-M1-M4/P-M6 + A-M2/A-M3] 管线健壮与口径：每张表加可执行的单表超时 + 有界重试退避 + 表间限速，并设整轮墙钟上限——此前 `ak.macro_china_*` 走 akshare 内部无 timeout 的 `requests.get`，一个黑洞主机即可让整轮永久挂起（且 launchd 不会再起第二实例，等于计划任务静默停摆）；`house_price` 反缩水闸门由 distinct **date** 改为 distinct (date, category) 并要求真实价格列——此前掉 7/10 城市时行数骤降但日期集合不变，闸门不触发、`min_rows` 仍过，`if_exists="replace"` 直接删掉 7 城历史却记 `status="updated"`；`sf_stock_yoy` 的 `rolling(12, min_periods=1)` 改 `min_periods=12`（头部 12 点此前是"12 月和 ÷ 1 月值"的伪同比）；月频/季频衍生统一 reindex 到连续日历再位移，缺一个月不再变成 11/13 月同比；年度居民收入改按可得日打戳，消除 `merge_asof` 回填造成的约 12 个月 look-ahead；`run_derived` 失败改为 `discard_staging()` 而非无条件 `commit_staging()`（此前 live 会变成"新原始 + 旧派生"的不一致快照，信号即基于它计算）；写库改带 PK/UNIQUE 与索引的 upsert 并在写前去重、`validate()` 增重复日期拒收（此前 `to_sql(replace)` 使库中 0 索引，`lpr` 1536 行仅 154 个日期、`pmi` 有同日不同值）。新增 `test_pipeline_guards.py`、`test_derived_calc.py`。
  15. [G13+G14+G15+G25｜FE-H2/FE-H3/FE-H4/FE-M1-M11 + F10] 前端交互、生命周期与可达性：新增 `composables/useAsyncData.ts` + `components/layout/PageState.vue`，把"加载/错误/空态"变成必须显式渲染的结构，`Overview.vue`（`/` 重定向后的首屏）不再吞掉 `error`——此前后端不可达时呈现结构完整但全空的页面并显示"暂无历史"，主动误导为"数据还没生成"；`api/client.ts` 支持外部 `signal` 并用 `AbortSignal.any([timeout, external])` 让超时覆盖响应体下载（此前 `clearTimeout` 在响应头到达即触发），幂等 GET 加分类退避重试，并加入 in-flight 去重 + TTL 缓存（顺带修掉启动时 `/sources/health` 被请求两次）；`CommentaryCard` 轮询改 `setTimeout` 链 + 总时限，瞬时网络错误不再永久停表（此前一次抖动即把卡片永久钉在"生成失败"），后端 `core/commentary.py` 删除与 `_gen_lock` 失步的 `_busy` 标志、改由锁自身派生忙态（F10：交错可致 `_busy` 永久置位 → `get_current()` 永远返回 generating，叠加前端 2 秒轮询成永不停歇的请求风暴）；`CrclMonitor` 采集状态提升到 store 复用 AbortController，路由 meta 声明能力使顶栏不再显示对该页无效的"死控件"；另修 `useCountUp` 小数位（EPS 0.18 此前显示 0.2）、`sampling:'lttb'`、`filters.ts` 时区 off-by-one、`router.onError` 陈旧 chunk 兜底、`ChartTip` a11y 与对比度 token。
  16. [G09+G10+G24rest｜F6/F7/F11/F12 + A-M1] 并发与端点加固：SSE 改 `async def` 生成器，不再占用 AnyIO 线程池令牌（此前每条连接约占 1 个、40 条即可饿死含 `/health` 的全部端点），工作交给有界 `ThreadPoolExecutor`，CRCL worker 补 `stop_event`；CRCL 采集加独立单飞锁 `data/.crcl_collect.lock`，并把 akshare/yfinance 无 timeout 的阻塞调用置于可执行超时之下；`core/db.py` 统一连接工厂设 `journal_mode=WAL` + `busy_timeout` + `synchronous=NORMAL` 并显式关闭，`crcl_db` 复用（读者不再被写者阻塞，消除 `database is locked` 冒成 500）；F11：`/crcl/metrics` 的 `keys` 按 `METRIC_LABELS` 白名单过滤并加 `max_points` 上限，`/crcl/logs` 的 `limit` 补下界（此前 `?limit=-1` 被 SQLite 当无限制倒出全表）；F12：错误落日志只回 8 位 `error_id`，不再外泄 traceback 与绝对路径，采集子进程环境改白名单。新增 `test_crcl_concurrency.py`、`test_sqlite_pragmas.py`、`test_endpoint_hardening.py`。
  17. [收口｜WAL × 整库交换的数据丢失风险] 启用 `journal_mode=WAL`（第 16 项）后，`scripts/_pipeline.py` 仍用 `shutil.copy2` + `os.replace` 搬整个库文件，而 **copy2 不会带走 `-wal` 边车**：`open_staging()` 不先 checkpoint 会让 staging 丢掉仍留在 WAL 中的已提交事务；`commit_staging()` 交换后若残留旧 inode 的 `-wal`，SQLite 可能把它恢复到新文件上。现新增 `_checkpoint_wal()`（`PRAGMA wal_checkpoint(TRUNCATE)`，非 WAL/只读/损坏库静默跳过）与 `_drop_wal_sidecars()`：复制前 checkpoint 活库、交换前 checkpoint staging、交换后清掉旧 inode 的 `-wal`/`-shm`。新增 `test_pipeline_wal_swap.py`（2 例，改前均失败：staging 读不到写入行 / 交换后残留边车）。
  18. [可读性｜G23 收尾] `analysis/cycle_debt.py` 的 GDP as-of 合并由多行三元表达式改为显式 `if/else`，并补注释说明 `merge_asof` 要求两侧非空、任一侧缺失时该季度即无增长观测（落到 `insufficient_data`）。**行为零变化**：实测 85 行、最新 2026-03 仍为 `leveraging_boom`（`net_change` +10.9pp），与 G23 提交时一致；全套 222 passed。

### Code-audit fix batch (targeting v1.1.0)

Summary: Based on the Aug-2026 five-module audit, fixing ~40 findings one feature point at a time (correctness / stability / security / UX / engineering). Progress ledger in `docs/AUDIT_FIXES.md`; entries appended per feature point below.

Changes:
  1. [infra] Add `docs/AUDIT_FIXES.md` remediation ledger (30 fix groups with severity / location / root-cause fix / reviewer / commit / evidence for durable resume); extend `.gitignore` to cover `.playwright-mcp/`, `backtest_hshylv/`, root screenshot PNGs so they cannot slip into later commits.
  2. [G19｜F9 High] Typed date params: `start`/`end` on `/derived/monthly`, `/derived/quarterly`, `/table/{name}`, `/cycles/{name}` are now `date | None`, so a malformed date returns 422 before the handler runs; removed `db.load`'s silent `try/except`. Fixes the inconsistency where a bad `start` silently returned the full table (wrong scope) on the monthly endpoint and 500'd on the cycles endpoint. Adds `test_date_params.py` (6 cases, 3 failed pre-fix).
  3. [G04｜F5 High] JSON non-finite safety: a global `SafeJSONResponse` (`default_response_class`) recursively converts `NaN`/`±Inf` to `null`; `serial` now uses `isfinite` to also catch ±inf; `crcl_db.set_snapshot` sanitizes before persistence so no `NaN` literal reaches SQLite. Fixes response_model-less endpoints (all `crcl/*`, `real-estate`) hard-500'ing on a yfinance `NaN` with the poison persisted. Adds `test_json_safety.py` (3 cases, failed pre-fix).
  4. [G01｜A-C1 Critical] Merrill-clock re-model: `gdp_trend` switches from an outlier-sensitive rolling mean to a rolling median (robust to the 2020/2021 base-effect), plus hysteresis (0.5pp dead-zone + 2-period persistence), removing the relative-to-own-trend misclassification. On real data, +5% growth with low CPI is corrected from recession to recovery and the composite moves from −2 back to 0 (Neutral). `02_compute_derived.py` is intentionally untouched (raw gdp has only a Q1 single-quarter row per year, so full-year YoY is unreconstructable — hence the robust classifier-side fix). Adds `test_merrill_phase.py` (8 cases, 6 failed pre-fix).
  5. [G02｜F1/F2/F8 Critical] Refresh lock via `fcntl.flock` atomic mutex: removes the check-then-touch race (two refreshes writing the same staging DB → production corruption); the timeout now uses an independent wall-clock deadline + reader thread so a silently-hung collector subprocess is actually killed (previously the deadline was checked inside `for line in proc.stdout`, so no output = never fired); `is_running()` is a side-effect-free probe (no longer unlinks a live lock); the CLI (`01_fetch_data.py`) shares the same lock as the API. Adds `test_refresh_lock.py` (5 cases).
  6. [G07｜FE-C1/FE-H1 Critical] Frontend chart-render rework: large series held in `shallowRef`+`markRaw`; options moved from template expressions into `markRaw` `computed`s; `EChart` merges incrementally (`notMerge:false`+`lazyUpdate`) so zoom/legend survive refreshes; `GraphCard` no longer `v-if`-unmounts the chart — loading/error are absolute overlays with `min-height` + `@retry`. Follow-up fix: the per-phase scatter/quadrant charts (Merrill, inventory quadrant) pass `:not-merge="true"` to avoid ghost series when the visible phase set narrows. `vue-tsc --noEmit` 0 errors.
  7. [G05｜O-C2 Critical] FastAPI serves the SPA + single-process run_app.sh: the built SPA is served by FastAPI (`/assets` static mount + a 404 fallback to index.html; unmatched `/api/*` still returns JSON 404, not the HTML shell; path-traversal guarded), removing the `vite preview` second process; `run_app.sh` runs a single uvicorn, rebuilds dist by a `frontend/src`+lockfile fingerprint, uses `npm ci`, `exit 1`s on readiness failure instead of a false success banner, and reaps robustly with `cleanup() { set +e; }`. Fixes the stale-bundle-served bug from the broken cleanup/port-drift. Adds `test_static_serving.py` (10 cases).
  8. [G03｜F3 High] Version-keyed cache invalidation: the lru_cache keys for `db._load_full`/`compute_signals` now include `_db_version()=(mtime_ns,size)`, so any `os.replace` DB swap (API/CLI/cron) auto-invalidates and re-reads — no longer relying on the "only clear on run_refresh success" call path (previously a CLI/cron swap or a post-commit error left the API serving stale data forever); `clear_all_caches()` is kept as a memory-reclaim helper. Adds `test_cache_version.py` (3 cases; pre-fix the swap-returns-stale-DataFrame case failed).
  9. [G06｜O-C1/B1 Critical + P-H2] Truthful health endpoints + nonzero collector exit: `sources_health` returns `unknown` (gray) for an empty sources list instead of `green`, and adds a staleness rule (stale manifest → yellow/red, default 40/80 days), ending the "empty means green / never stale" lie; `01_fetch_data.py` aggregates an exit code and exits nonzero when any table fell back to `kept_previous` due to a failure (distinct from an out-of-window skip), so cron/launchd can see partial failure; stderr + rotating-file logging added. Adds `test_health_truthfulness.py` (9 cases) and corrects `test_sources_health`'s "empty→green" assertion to "empty→unknown" (a spec fix, not a weakening). Note: `run_refresh` now reports error on any failed table (intended loudness).
  10. [G22｜A-M4 Medium] Hand-maintained JSON schema validation: `/crcl/events` and `/crcl/fundamentals` are validated on load with pydantic (field types, date format, enums), so a semantic mistake (number-as-string, bad date) no longer slips silently to the frontend or masquerades as an "evaluation error" — it fails with a clear, logged message; `crcl_alerts` coerces to numeric before comparison and `_eval_y_nonreserve_stagnant` now requires two ADJACENT quarters, not any two non-null ones. Adds `test_crcl_json_schema.py`.
  11. [G24a｜F13 Medium] signal-history read swallows only the benign case: `read_history` changes from `except sqlite3.Error: return []` (swallowed everything) to returning empty only when the table is missing (fresh install); schema drift / DB corruption now surfaces instead of masquerading as "no data". Adds `test_signal_history_errors.py` (2 cases; the schema-drift case silently returned [] pre-fix).
  12. [G17+G27｜O-H2/O-M2/O-M3/O-M6/O-L3] Dependency locking + ops hygiene: `akshare` moves from `>=1.14.0` to an **exact `==1.18.64`** pin (a scraper library whose minor bumps silently rename columns; aligned with the version recorded in `data/last_run.json`, with a comment requiring a `diff_vintage`/`dual_sources` regression run before any upgrade); every other floor is aligned to the actually-installed version with a major-version ceiling (the old `pandas>=1.5`/`numpy>=1.24` spanned major versions and the floor-resolved combination simply cannot run this code); adds `requirements.lock` (the transitive closure captured offline via `pip list --format=freeze`, with no fabricated hashes); `backend/pyproject.toml` no longer restates the analysis deps — `requirements.txt` is the single source of truth; `run_app.sh` now resolves its interpreter as `PYTHON`/`VENV` override → `.venv312` → `.venv` → `python3` with an actionable bootstrap message when deps are missing (a fresh clone previously died on the very first hardcoded `.venv312` call), and the uvicorn log moves from `/tmp` to `data/logs/`; adds `.env.example` (placeholders only, covering `COMMENTARY_*`/`REFRESH_TIMEOUT_S`/`HEALTH_STALE_DAYS`, verified not gitignored); `README.md` corrects three false statements (`.venv312` is Python 3.12.14 not 3.14.6; `_pipeline_test.py` is never collected by pytest; the OpenAPI contract did not prevent CRCL type drift) and documents the single-process `:8000` launch.
  13. [G23+G03b｜A-H1/A-H2/A-H3/A-M5 + remaining F3/F15] Signal robustness + cache version keys: the composite now aligns sub-signals to a common as-of and exposes each one's own date, and a missing sub-signal is EXCLUDED and the composite renormalised over what's available instead of being counted as 0 (previously missing data read as neutral, and `iloc[-1]` on an empty frame raised `IndexError`, 500-ing `/signals`); `cycle_inventory` no longer requires `pmi_official` and `ip_yoy` to be non-null in the same row — pmi ended 2025-08 while ip_yoy ran to 2026-06, pinning the inventory signal 10 months in the past while it was summed with the latest credit reading; `real_estate` falls back to neutral when price momentum is missing instead of `0.0` (which scored as the MOST bearish value, making "missing data" mean "strongly bearish"); `cycle_debt` switches from "any sector deleveraging ⇒ beautiful_deleveraging" to a net/majority sector direction, and replaces `gdp_yoy > 0` (near-always true for China, making all three bearish branches unreachable) with the same relative-trend test as the Merrill fix; `cycle_credit` smooths the impulse and adds a dead-zone plus persistence, killing the easing/neutral chatter driven by 0.04↔0.05 noise. G03b: the `classify_*` and `_analyze_real_estate_cached` lru_cache keys now include the DB version, so after a CLI/cron swap `/cycles/{name}` and `/real-estate` no longer serve stale values (previously they only refreshed if `/signals` happened to be hit first); the real-estate cache key is normalised to `tuple(sorted(set(cities)))` (F15, removing order/duplicate cache thrash). Adds `test_signal_robustness.py` (24 cases, 22 failed pre-fix).
  14. [G11+G12+G20+G21｜P-H1/P-H3/P-M1-M4/P-M6 + A-M2/A-M3] Pipeline robustness + conventions: each table gains an enforceable timeout, bounded backoff retry, an inter-table gap and an overall run budget — previously `ak.macro_china_*` used akshare's internal timeout-less `requests.get`, so one black-holed host hung the whole run forever and launchd would not start a second instance (a silently dead schedule); the `house_price` anti-shrink gate moves from distinct **date** to distinct (date, city) with a `min_groups` floor and a real price column required — previously losing 7 of 10 cities left the date set unchanged so the gate never fired, `min_rows` still passed, and `replace` deleted 7 cities' history while recording `status="updated"`; `rolling(12, min_periods=1)` becomes `min_periods=12` for both 12-month sums; monthly/quarterly derivations reindex to a continuous calendar before shifting so a gap yields NaN instead of an 11/13-month "YoY"; annual household income is stamped `available_from = Y+1-01-01` and joined by `merge_asof`, removing the ~12-month look-ahead; a `run_derived` failure now discards staging (exit code 3) instead of committing a "new raw + old derived" snapshot; and a unique index is re-created after every load with `validate()` rejecting duplicate grain keys (previously `to_sql(replace)` left 0 indexes, `lpr` at 1536 rows for 154 dates, `pmi` with same-date differing values). Adds `test_pipeline_guards.py` and `test_derived_calc.py`.
  15. [G13+G14+G15+G25｜FE-H2/FE-H3/FE-H4/FE-M1-M11 + F10] Frontend interaction, lifecycle and accessibility: new `composables/useAsyncData.ts` + `components/layout/PageState.vue` make loading/error/empty states structurally unavoidable (`state` is a required prop and content lives in its slot, so omitting the wrapper deletes the content rather than silently rendering a `—` skeleton); all 9 pages converted; `Overview.vue` (the first screen after the `/` redirect) no longer swallows `error` — previously an unreachable backend rendered a complete-looking but empty page saying "no history yet", misrepresenting a failed request as "data not generated yet"; `api/client.ts` accepts an external `signal` and uses `AbortSignal.any([timeout, external])` so the deadline covers body download, retries GETs only (2 attempts, 408/429/5xx or transport failure) and adds in-flight dedupe + a 15s TTL cache invalidated on refresh completion (which also fixes `/sources/health` being fetched twice at startup); `CommentaryCard` polling becomes a `setTimeout` chain with a 2-minute deadline where transient failures keep polling instead of latching "生成失败"; backend `core/commentary.py` deletes the `_busy` flag and derives busy-ness from `_gen_lock`, returning the previous commentary while regenerating (F10); CRCL collection state moves into the store with route-meta capability declarations so the top bar stops showing dead controls; plus `useCountUp` digits, `sampling:'lttb'`, the `filters.ts` timezone off-by-one, `router.onError` stale-chunk recovery, `ChartTip` `role="tooltip"`/`aria-describedby`/Escape, and a `text-4` contrast token measured at 4.83:1.
  16. [G09+G10+G24rest｜F6/F7/F11/F12 + A-M1] Concurrency + endpoint hardening: both SSE endpoints become `async def` generators driven by an `asyncio.Queue`, consuming zero threadpool tokens (previously each open connection held about one and ~40 could starve every endpoint including `/health`); work goes to one bounded `ThreadPoolExecutor` behind a semaphore that reports busy instead of queueing, and the CRCL worker gains the `stop_event` the macro refresh already had; CRCL collection gets its own single-flight lock at `data/.crcl_collect.lock`, and the timeout-less akshare/yfinance calls are wrapped in an enforceable timeout; `core/db.py` centralises a connection factory (`journal_mode=WAL` + `busy_timeout` + `synchronous=NORMAL`, explicit close) reused by `crcl_db`, so readers no longer block on a writer; F11: `/crcl/metrics` filters `keys` against the `METRIC_LABELS` whitelist and adds `since`/`max_points`, `/crcl/logs` gains a lower bound on `limit` (previously `?limit=-1` dumped the whole table); F12: errors are logged server-side and only an 8-char `error_id` is returned, and the collector subprocess env is allowlisted. Adds `test_crcl_concurrency.py`, `test_sqlite_pragmas.py` and `test_endpoint_hardening.py`.
  17. [follow-up｜WAL × whole-file swap data-loss risk] After item 16 enabled `journal_mode=WAL`, `scripts/_pipeline.py` still moved the whole DB file with `shutil.copy2` + `os.replace`, and **copy2 does not carry the `-wal` sidecar**: without a checkpoint first, `open_staging()` loses commits still sitting in the WAL, and a stale `-wal` from the replaced inode surviving `commit_staging()` could be recovered against the new file. Adds `_checkpoint_wal()` (`PRAGMA wal_checkpoint(TRUNCATE)`, silently skipped for non-WAL/read-only/corrupt DBs) and `_drop_wal_sidecars()`: checkpoint the live DB before the copy, checkpoint staging before the swap, and delete the old inode's `-wal`/`-shm` after it. Adds `test_pipeline_wal_swap.py` (2 cases, both failing pre-fix: staging missing the written row / stale sidecar left after the swap).
  18. [readability｜G23 tail] The GDP as-of merge in `analysis/cycle_debt.py` goes from a multi-line ternary to an explicit `if/else`, with a comment stating that `merge_asof` requires both sides non-empty and that a missing side simply means the quarter has no growth observation (falling through to `insufficient_data`). **Zero behaviour change**: measured 85 rows, latest 2026-03 still `leveraging_boom` (`net_change` +10.9pp), identical to the values recorded when G23 landed; full suite 222 passed.
  19. [遗留收口 5-8｜F13-rest / A-M1-rest / G23 透明字段 / 启动器] 四个尾项一并收口：(a) `core/commentary.py` 的 `get_current` 把裸 `except Exception → {status:empty}` 收窄为只吞 `sqlite3.OperationalError` 且消息含 "no such table"（全新安装不 500），其余（`AttributeError`/`KeyError`/镜像损坏）冒泡为可见 500，与 `signal_history.read_history` 同款；顺带修掉错误路径上的 fd 泄漏（旧代码 `conn.close()` 在 `try` 内，一抛异常就跳过）。(b) `core/commentary.py` 与 `core/signal_history.py` 的裸 `sqlite3.connect(...)` 改走 `core/db.connect()` 工厂——WAL 是文件属性照旧继承，但 `busy_timeout` 是连接属性、默认 0，改前一遇并发写入者即 `database is locked` 而非按 `BUSY_TIMEOUT_MS` 等待。(c) `schemas/signals.SignalSummary` 补 `as_of/included/excluded/stale/composite_raw` 五个可选字段——G23「缺失子信号剔除并重新归一」的可观测面此前被 `response_model` 静默过滤，HTTP 客户端看不到覆盖面/as-of（实测 `/signals`：as_of=2026-06、included 四框架、stale=[inventory]、composite_raw=2.29）。(d) `启动面板.command` 头注与打印 URL 由 :5173 更正为 :8000（vite preview 已下线）。新增 `test_commentary_errors.py` / `test_db_factory_callers.py` / `test_signals_schema_fields.py`（改前 6 failed，改后 12 passed）。
      [Residuals 5-8｜F13-rest / A-M1-rest / G23 transparency fields / launcher] Four tail items closed together: (a) `get_current` in `core/commentary.py` narrows a bare `except Exception → {status:empty}` to swallow only `sqlite3.OperationalError` whose message contains "no such table" (fresh install, no 500) and re-raises everything else (`AttributeError`/`KeyError`/corruption) as a visible 500, mirroring `signal_history.read_history`; it also fixes an fd leak on the error path (the old `conn.close()` lived inside the `try`, so any read error skipped it). (b) The bare `sqlite3.connect(...)` in `core/commentary.py` and `core/signal_history.py` now goes through the `core/db.connect()` factory — WAL is a file attribute so it was inherited anyway, but `busy_timeout` is a *connection* attribute defaulting to 0, so before the fix either module raised `database is locked` the instant a concurrent writer held the lock instead of waiting `BUSY_TIMEOUT_MS`. (c) `schemas/signals.SignalSummary` gains five optional fields `as_of/included/excluded/stale/composite_raw` — G23's "missing sub-signal is excluded and the composite renormalised" was being silently filtered out by `response_model`, so HTTP clients never saw coverage/as-of (measured `/signals`: as_of=2026-06, all four frameworks included, stale=[inventory], composite_raw=2.29). (d) `启动面板.command` header comment and printed URL corrected from :5173 to :8000 (vite preview retired). Adds `test_commentary_errors.py` / `test_db_factory_callers.py` / `test_signals_schema_fields.py` (6 failed pre-fix, 12 passed after).
  20. [G08｜F4 变更端点鉴权 + GET 收回 POST]（Critical）localhost CSRF 根治：uvicorn 虽绑 127.0.0.1，但任意网页可用 `<img src=".../crcl/refresh/stream">` 或 `fetch(POST, mode:no-cors)` 触发全量采集与付费 LLM 调用。根因两半：(a) 变更语义从 GET 收回 POST——`POST /api/v1/refresh`、`POST /api/v1/crcl/refresh`、评述再生 POST 经 `create_job()` 提交到既有有界线程池并返回不可猜的 `uuid4` `job_id`；SSE `GET …/stream?job_id=` 只 `get_job()` 查表、绝不启动工作，缺 `job_id`→422、未知/过期→404，故 `<img>`/预取 GET 无法凭空造出 `job_id`。(b) 能力令牌：`secrets.token_urlsafe(32)` 于 lifespan 生成、写 `data/.api_token`（0600、gitignore、不记日志），同源 SPA 经 `GET /api/v1/session`（`no-store`）取用并在每个 POST 带 `X-API-Token`、遇 401/403 重取重放一次；`require_token` 用 `compare_digest`，缺令牌 401、错令牌 403，绝不 500。job 注册表 `subscribe`/`emit` 同锁收发、晚到订阅者靠 4096 环形重放缓冲不丢 tick，`_prune_jobs` 永不优先淘汰在跑的 job。新增 `test_mutation_auth.py`（24 例，改前 21 failed）；`test_endpoint_hardening.py` 若干断言改为 POST/GET 拆分后的等价校验（饱和忙态断言移到 POST，SSE 线格式/异步生成器/`stop_event` 不变，且 `test_submit_job_refuses_instead_of_queueing` 单元级仍守准入）。`.gitignore` 补 `data/.api_token`（并顺带补 WAL 边车 `*.db-wal`/`*.db-shm`，item 17 收尾）。
      [G08｜F4 auth on mutating endpoints + GET demoted to POST] (Critical) Root-causes localhost CSRF: uvicorn binds 127.0.0.1, but any page the user browses can fire `<img src=".../crcl/refresh/stream">` or `fetch(POST, mode:no-cors)` to trigger a full collection and a paid LLM call. Two halves: (a) the mutation moves off GET back onto POST — `POST /api/v1/refresh`, `POST /api/v1/crcl/refresh`, and the commentary regenerate POST submit via `create_job()` to the existing bounded pool and return an unguessable `uuid4` `job_id`; the SSE `GET …/stream?job_id=` only does a `get_job()` lookup and never starts work (missing `job_id`→422, unknown/expired→404), so an `<img>`/prefetch GET cannot mint a `job_id`. (b) Capability token: `secrets.token_urlsafe(32)` generated in the lifespan, written to `data/.api_token` (0600, gitignored, never logged); the same-origin SPA reads it from `GET /api/v1/session` (`no-store`) and sends `X-API-Token` on every POST, re-fetching+replaying once on 401/403; `require_token` uses `compare_digest`, returns 401 (absent)/403 (wrong), never 500. The job registry's `subscribe`/`emit` share one lock so a late subscriber loses no tick (4096-entry replay buffer), and `_prune_jobs` never evicts a running job. Adds `test_mutation_auth.py` (24 cases, 21 failed pre-fix); several `test_endpoint_hardening.py` assertions become the POST/GET-split equivalents (busy/saturation asserted on the POST; SSE wire format / async-generator / `stop_event` unchanged; and `test_submit_job_refuses_instead_of_queueing` still guards admission at the unit level). `.gitignore` gains `data/.api_token` (plus the WAL sidecars `*.db-wal`/`*.db-shm`, closing item 17).
  21. [G28-G30 低危批次｜A-L2 / F17 / FE-L3 / FE-L5 / FE-L7 / FE-L8] (a) A-L2 `analysis/cross_indicator.py`：`_best_lag_corr` 原按 `abs().idxmax()` 选滞后却返回**带符号** r——强负相关被贴上「领先 k 月」的正向标签，与文档「最高正相关」自相矛盾；改为 `idxmax()`（最正 r），docstring 讲明这是**全样本/样本内**描述性统计、仅供历史展示、非实时可交易信号。实测无用户可见变化（两对最强相关本就为正：M1→PPI lag0 r≈0.214、spread→CPI lag11 r≈0.286），仅修正「最强为负」被误标的情形。(b) F17 `backend/app/core/serial.py`：新增 `_FLOAT_DP=4` + `_clean_record_float`，`df_to_records` 单遍重建时把有限浮点 round 到 4 位、非有限置 None；与快照持久化用的 `_finite_or_none` **分开**（后者须保全精度），只有 DataFrame 传输层收敛。(c) 前端：FE-L3 `Sidebar.vue` `isActive` 由每渲染造 9 个不回收 `computed` 的工厂改为纯布尔函数；FE-L5 `CrclMonitor.vue` `PALETTE1/2` 上移到首次使用前消除 TDZ 隐患；FE-L8 `seriesDelta` 最近点循环每点只 parse 一次日期、以 `bestDiff` 携带最优距离，消除 ~3187 点序列上数千次冗余 `new Date()`；FE-L7 `EChart.vue` 的 `option` prop `Record<string,any>`→`EChartsOption`，`options.ts` 引入 `themed()` 类型缝、9 个 builder 全部返回 `EChartsOption`（拼错键触发 TS2322，已实测）。新增 `test_serial_precision.py` / `test_cross_lag_semantics.py`（改前 3 failed：8.3 二进制噪声未消 / 有限值未 round / 反相关对报 −1.0>0 → 改后 7 passed）；全套 279 passed、typecheck 0。
      [G28-G30 low-severity batch｜A-L2 / F17 / FE-L3 / FE-L5 / FE-L7 / FE-L8] (a) A-L2 `analysis/cross_indicator.py`: `_best_lag_corr` selected the lag by `abs().idxmax()` but returned the **signed** r, so a strong negative relationship got a "leads by k months" positive label, contradicting the docstring's "highest positive correlation"; switched to `idxmax()` (most-positive r), with docstrings stating this is a **full-sample/in-sample** descriptive statistic for historical display, not a real-time tradable signal. No user-visible change on real data (both pairs' strongest correlation is already positive: M1→PPI lag0 r≈0.214, spread→CPI lag11 r≈0.286); only the flagged "strongest-is-negative" mislabel case changes. (b) F17 `backend/app/core/serial.py`: adds `_FLOAT_DP=4` + `_clean_record_float`, so `df_to_records`'s single-pass rebuild rounds finite floats to 4 dp and nulls non-finite — kept **separate** from the snapshot-persistence `_finite_or_none` (which must keep full precision), so only the DataFrame transport rounds. (c) Frontend: FE-L3 `Sidebar.vue` `isActive` goes from a `computed`-factory (9 never-disposed refs per render) to a plain boolean fn; FE-L5 `CrclMonitor.vue` moves `PALETTE1/2` above first use to remove a TDZ hazard; FE-L8 `seriesDelta` parses each point's date once, carrying the running best in `bestDiff`, killing thousands of redundant `new Date()` parses on the ~3187-point series; FE-L7 `EChart.vue`'s `option` prop `Record<string,any>`→`EChartsOption` and `options.ts` adds a `themed()` typed seam so all 9 builders return `EChartsOption` (a misspelled key now raises TS2322, verified). Adds `test_serial_precision.py` / `test_cross_lag_semantics.py` (3 failed pre-fix: 8.3 binary noise / finite value un-rounded / inverse pair reporting −1.0>0 → 7 passed after); full suite 279 passed, typecheck 0.
  22. [G26 管线中危｜P-M7 / P-M8 / P-M9；P-M10 评估后不做] (a) P-M7 `scripts/_pipeline.py` 的 `validate()` 增 **dtype 门**（必填非 date 列须数值）与**新鲜度门**（`max_date_lag` 天，注入式 `today`）——此前源静默冻结（最新日期不前进）或改形（数值列变字符串）时行数/值域/粒度门全过、陈旧或垃圾照样覆盖好数据；给 8 张月/季表设 `max_date_lag`（gdp 400；ppi/industrial/social_finance/new_credit/bond_yield 200；fiscal/external_demand 220），刻意不设 cpi/money_supply/pmi/lpr/house_price（合成日期老测试）与年表。(b) P-M8 NIFD 杠杆数据原重复在两处、且 `03_supplement_leverage.py` 裸 `INSERT` 直写活库（绕过 `validate`/UNIQUE/备份/vintage/原子交换/派生重算 → 生熟不一致）；新增 `scripts/nifd_leverage.py` 单一来源，`01`/`03` 均 import；`03` 改走 staging 路径（`open_staging`→gated `validate`→`enforce_indexes`→`run_derived`→原子 `commit_staging`，任何失败弃 staging、活库字节不变），`__main__` 取共享 flock。(c) P-M9 `scripts/_specs.py`：把 ~7 个结构相同的 fetcher、~8 个近重复日期解析器、50+ 次 `pd.to_numeric(errors="coerce")` 收敛为声明式 `FETCH_SPECS` + `DATE_PARSERS` + `to_num`（依赖轻、仅 pandas，测试可 stub akshare），`01` 用一个通用循环消费；不规则 fetcher 仍 bespoke。**P-M10（顶层并发抓取）评估后不做**：与 G11 的 `FETCH_GAP_S=1.5s` WAF 限速相冲，唯一慢表 `bond_yield` 已内部按年并行，收益微而封禁风险实。新增 `test_pipeline_freshness.py`(8)、`test_pipeline_supplement.py`(6)；fail→pass：P-M7 手工中和双门→4 failed、P-M8 重建旧直写路径→5 failed，恢复后各 8/6 passed；全套 279 passed、`_pipeline_test.py` ALL CHECKS PASSED。P-M9 为编排者独立复核（行为保持的声明式重构，绿套 + pipeline 自检佐证）。
      [G26 pipeline-medium｜P-M7 / P-M8 / P-M9; P-M10 declined] (a) P-M7 `validate()` in `scripts/_pipeline.py` gains a **dtype gate** (required non-date cols must be numeric) and a **freshness gate** (`max_date_lag` days, injectable `today`) — previously a source that silently froze (newest date stops advancing) or reshaped (numeric column arrives as strings) passed the row-count/range/grain gates and stale/garbage overwrote good data; `max_date_lag` set on 8 monthly/quarterly specs (gdp 400; ppi/industrial/social_finance/new_credit/bond_yield 200; fiscal/external_demand 220), deliberately not on cpi/money_supply/pmi/lpr/house_price (old synthetic-date tests) or annual tables. (b) P-M8: NIFD leverage data was duplicated in two files and `03_supplement_leverage.py` raw-`INSERT`ed straight into the live DB (bypassing `validate`/UNIQUE/backup/vintage/atomic-swap/derived-recompute → raw↔derived drift); new `scripts/nifd_leverage.py` is the single source imported by `01`/`03`, and `03` now runs the staged path (`open_staging`→gated `validate`→`enforce_indexes`→`run_derived`→atomic `commit_staging`; any failure discards staging, live byte-identical) under the shared flock. (c) P-M9 `scripts/_specs.py` collapses ~7 structurally identical fetchers, ~8 near-duplicate date parsers and 50+ `pd.to_numeric(errors="coerce")` calls into a declarative `FETCH_SPECS` + `DATE_PARSERS` + `to_num` (pandas-only, akshare-stubbable), consumed by one generic loop in `01`; irregular fetchers stay bespoke. **P-M10 (top-level concurrent fetch) declined**: it conflicts with G11's `FETCH_GAP_S=1.5s` WAF rate-limiting, the only slow table (`bond_yield`) already parallelizes internally, and the marginal wall-clock gain is not worth the ban risk. Adds `test_pipeline_freshness.py` (8) / `test_pipeline_supplement.py` (6); fail→pass: neutralizing both P-M7 gates → 4 failed, reconstructing P-M8's old direct-write path → 5 failed, restored → 8/6 passed; full suite 279 passed, `_pipeline_test.py` ALL CHECKS PASSED. P-M9 was independently reviewed by the orchestrator (behavior-preserving declarative refactor, corroborated by the green suite + pipeline self-test).
  23. [G26 收尾｜03 staged-path 细化 + P-M9 契约测试] `03_supplement_leverage.py` 的 staged 路径显式化：合并前 `backup_db` 快照 live、暂存库上 `enforce_indexes` 重建 UNIQUE 索引再 `run_derived`，`backup_dir` 提为可注入参数（默认 `BACKUP_DIR`，向后兼容——旧调用不变）。新增 `backend/tests/test_pm9_declarative_fetch.py`（9 例）：以 stubbed akshare 断言 `_specs.py` 的 `FETCH_SPECS`/`DATE_PARSERS`/`to_num` 声明式路径与旧逐个 fetcher **行为等价**（列重命名、数值强制、日期解析、dropna/sort）。全套 288 passed、`_pipeline_test.py` ALL CHECKS PASSED、typecheck 0。
      [G26 tail｜03 staged-path refinement + P-M9 contract test] The staged path in `03_supplement_leverage.py` is made explicit: a `backup_db` snapshot of live before the merge, `enforce_indexes` rebuilding the UNIQUE index on staging before `run_derived`, and `backup_dir` promoted to an injectable parameter (default `BACKUP_DIR`, backward-compatible — old calls unchanged). Adds `backend/tests/test_pm9_declarative_fetch.py` (9 cases) asserting, with a stubbed akshare, that `_specs.py`'s `FETCH_SPECS`/`DATE_PARSERS`/`to_num` declarative path is **behavior-equivalent** to the old per-fetcher bodies (column rename, numeric coercion, date parsing, dropna/sort). Full suite 288 passed, `_pipeline_test.py` ALL CHECKS PASSED, typecheck 0.
  24. [G26 P-M7 收尾｜TABLE_SPECS 收紧] `scripts/_pipeline.py` 的 `validate()` 规格收紧：`household_income` 的 `required` 加 `income_abs`、`demographics` 的 `required` 加 `population` 并补值域（城镇化率 0–100、出生率 0–60），`leverage`/`lpr`/`industrial` 按 live min–max 补值域——把「必需列缺失/量纲错」从此前只靠行数/新鲜度兜底收紧为显式拒收。实测 live 全过：leverage 85 行 / industrial 203 / demographics 66 / 去重后 lpr 154，均 `ok=True`；全套 288 passed、`_pipeline_test.py` ALL CHECKS PASSED。
      [G26 P-M7 tail｜TABLE_SPECS tightening] `validate()` in `scripts/_pipeline.py` tightens the specs: `household_income` `required` gains `income_abs`; `demographics` `required` gains `population` plus ranges (urbanization 0–100, birth 0–60); `leverage`/`lpr`/`industrial` gain value-ranges calibrated on live min–max — turning "missing required column / wrong magnitude" from something only the row-count/freshness gates might catch into an explicit rejection. Live data still passes: leverage 85 rows / industrial 203 / demographics 66 / deduped lpr 154, all `ok=True`; full suite 288 passed, `_pipeline_test.py` ALL CHECKS PASSED.
  25. [G16+G18｜CI + 夹具库 + openapi 漂移门禁 + 契约测试] **G16**：新增 `.github/workflows/ci.yml`（backend：py3.12 → `pytest backend/tests` + `_pipeline_test.py`；frontend：node20 → `typecheck` + `build`）；`scripts/gen_fixture_db.py` 合成原始表并跑**真** `compute_derived` 生成 raw 一致的派生表 → `backend/tests/fixtures/{macro_data,crcl_monitor}.db`；`backend/tests/conftest.py` **仅在真库缺失时**播种夹具、teardown 只删自建（真库在场即 no-op，288 基线不动）；`scripts/gen_openapi.py` 重生 `shared/openapi.json`（14→23 路径，补齐全部 `/crcl/*` + `/api/v1/session` + refresh POST/GET 拆分）；`backend/tests/test_openapi_drift.py`（3 例，子进程取干净 schema、`info.version` 归一以容后续 bump——`1.0.0↔1.1.0` 判等而真实路径漂移仍失败）。**G18**：`backend/tests/test_api_contract.py`（8 例：`/signals`→`SignalSummary`、`/derived/monthly`、`/cycles/{name}`×4、`/crcl/overview` + 运行时↔openapi `$ref` 校验）；量化测试已存在（`test_merrill_phase`/`test_signal_robustness`）不重复；前端单测因 `package.json` 无 runner **跳过（诚实缺口，未擅自加依赖）**。G29/G30 复核：FE-L2/L4/L6/L9/L10、A-L2 均已在此前提交修复；A-L3(`SELECT *` 仅通用整表加载)/A-L4(缓存已版本键+cities 元组归一)/P-L(plist expat 路径匹配、备份/vintage/staging 三者独立、无未用 import) 判定**非开放**（附理由）。**两条网络依赖 P-L 残留据实保留**：`01_fetch_data.py:874/877` 的 TLS `verify=False` 与 `dfs[1]` 位置式，位于异常吞没的联网 fetcher 内、离线不可测，盲改有冻结 `bond_yield` 之险——报告而非症状式修补，待联网环境复核。全套 **299 passed**、`_pipeline_test.py` ALL CHECKS PASSED、`typecheck` 0、`npm build` ✓。
      [G16+G18｜CI + fixture DB + OpenAPI drift gate + contract tests] **G16**: adds `.github/workflows/ci.yml` (backend: py3.12 → `pytest backend/tests` + `_pipeline_test.py`; frontend: node20 → `typecheck` + `build`); `scripts/gen_fixture_db.py` synthesises raw tables and runs the **real** `compute_derived` so derived tables are raw-consistent → `backend/tests/fixtures/{macro_data,crcl_monitor}.db`; `backend/tests/conftest.py` seeds those **only when the real DB is absent** and on teardown deletes only what it created (a strict no-op when real DBs exist, so the 288 baseline is untouched); `scripts/gen_openapi.py` regenerates `shared/openapi.json` (14→23 paths, adding all `/crcl/*` + `/api/v1/session` + the refresh POST/GET split); `backend/tests/test_openapi_drift.py` (3 cases, comparing against a subprocess-clean live schema with `info.version` normalised so a later `1.0.0↔1.1.0` bump compares equal while a real path drift still fails). **G18**: `backend/tests/test_api_contract.py` (8 cases: `/signals`→`SignalSummary`, `/derived/monthly`, `/cycles/{name}`×4, `/crcl/overview` + a runtime↔OpenAPI `$ref` check); quant tests already exist (`test_merrill_phase`/`test_signal_robustness`), not duplicated; a frontend unit test is **skipped (honest gap — `package.json` has no runner, no dependency added)**. G29/G30 re-check: FE-L2/L4/L6/L9/L10 and A-L2 were already fixed in earlier commits; A-L3 (`SELECT *` only in generic full-table loaders) / A-L4 (caches are version-keyed + cities tuple-normalised) / P-L (plist expat path matches, backup/vintage/staging are distinct, no unused imports) judged **not-open** with reasons. **Two network-dependent P-L residuals are left in place, reported not patched**: the TLS `verify=False` and positional `dfs[1]` at `01_fetch_data.py:874/877` live inside an exception-swallowing networked fetcher that cannot be tested offline, and flipping either blind risks silently freezing `bond_yield` — to be reviewed in a networked environment. Full suite **299 passed**, `_pipeline_test.py` ALL CHECKS PASSED, `typecheck` 0, `npm build` ✓.
  26. [P-L 残留收口｜国债收益率 fetcher 的 TLS 与取表] 上一条留待联网复核的两项已实测修复（`scripts/01_fetch_data.py` 的 `fetch_bond_yield._fetch_year`）：(a) **删掉 `verify=False`**——实测中债站点用 certifi 默认 CA 即返回 HTTP 200（`verify=True` 与显式 `verify=certifi.where()` 均 200、正文 150214 字节），故关闭校验纯属无谓地把该抓取暴露给中间人攻击，直接删参数即恢复校验。(b) **位置式 `dfs[1]` 改为按列特征认表**：新增 `scripts/_specs.py` 的 `pick_curve_table()`，要求「曲线名称+日期+10年」三列同时存在——实测该页 `read_html` 出 2 张表，第 0 张查询表单**同样带「曲线名称」列**（故不能只判一列），只有第 1 张是数据表（474 行）；上游一旦多插一张表，旧的 `dfs[1]` 就会静默取错表。认不出则抛 `LookupError`。(c) 顺带修掉让上述两项长期隐形的根因：裸 `except: return 空表` 改为按年记 `⚠️` 告警（含异常类型，不含 `✅`——`refresh.py` 用 `✅` 行数算进度），此前 TLS 拒绝与取错表都被伪装成「本年无数据」，直到所有年份全空才报一条笼统告警。新增 `backend/tests/test_bond_yield_parse.py`（8 例：表单诱饵不被误认、上游多插表仍认对、彻底改版抛错、三列缺一即拒、源码不含 `verify=False`/`dfs[1]`、逐年失败留痕）；改前 3 failed → 改后 8 passed，全套 **307 passed**、`_pipeline_test.py` ALL CHECKS PASSED。诚实声明：联网 e2e 全年重放在会话中途因环境断网无法复跑，但上述 TLS 200 与两表结构均为断网前实测所得。
      [P-L residuals closed｜bond-yield fetcher TLS + table selection] The two items item 25 deferred for a networked review are now measured and fixed (`fetch_bond_yield._fetch_year` in `scripts/01_fetch_data.py`): (a) **`verify=False` removed** — measured: the chinabond endpoint returns HTTP 200 under certifi's default CA (both `verify=True` and an explicit `verify=certifi.where()` returned 200, body 150214 bytes), so disabling verification merely exposed the fetch to MITM for no benefit; dropping the argument restores it. (b) **positional `dfs[1]` replaced by content-based selection**: new `pick_curve_table()` in `scripts/_specs.py` requires 曲线名称+日期+10年 to all be present — measured, the page yields 2 tables and table 0 (the query form) **also carries a 曲线名称 column** (so a single-column test would still mis-pick), with only table 1 holding data (474 rows); one extra upstream table would have made the old `dfs[1]` silently grab the wrong one. No match now raises `LookupError`. (c) Also fixes the root cause that kept both invisible: the bare `except: return empty` now logs a per-year `⚠️` warning with the exception type (never `✅`, which `refresh.py` counts for progress) — previously a TLS refusal and a wrong-table pick were both disguised as "no data this year" until every year came back empty. Adds `backend/tests/test_bond_yield_parse.py` (8 cases: the form decoy is never accepted, an extra inserted table still resolves, a full redesign raises, dropping any one of the three columns rejects, the source contains no `verify=False`/`dfs[1]`, per-year failures leave a trace); 3 failed pre-fix → 8 passed, full suite **307 passed**, `_pipeline_test.py` ALL CHECKS PASSED. Honest caveat: the full multi-year live e2e replay could not be re-run after the sandbox lost network mid-session, but the TLS-200 and two-table findings above were both measured live before that.

### M3：信号历史表 + Overview 相位翻转高亮

### 新功能

1. **[新功能] `scripts/signal_history.py`**：signal_history 表（ts/data_as_of/composite/merrill/credit/inventory/debt，append-only，无主键不去重）；`01_fetch_data.py` main() 成功提交写 manifest 后追加一行 composite+四相位快照（ts 复用本次 manifest、data_as_of=derived_monthly MAX(date) 取 YYYY-MM，口径同 commentary），空计划提前返回不写、写入失败仅 ⚠️ 告警不影响已提交数据；不进 TABLE_SPECS 闸门（提交后派生快照），/table 白名单放行浏览；日志行用 📈 不含 ✅（refresh.py 进度计数依赖 ✅ 行数）
2. **[新功能] `GET /api/v1/signals/history`**：倒序（rowid DESC）limit（默认 60，1–500），多取 1 行保证窗口内最旧一行也能对到前值；行附 flips 翻转标注（任一框架相位相对相邻更早一行变化，framework/prev/curr，None 参与比较）；表缺失 → `{"items": []}` 不 500（fresh install）；Pydantic 三新 schema（PhaseFlip/SignalHistoryRow/SignalHistory），`schemas/__init__` 导出 SignalHistory，shared/openapi.json 重导
3. **[新功能] Overview「信号与相位历史」卡片**：load() Promise.all 增第三路 `getSignalHistory()`，随 `refresh.lastRefreshedAt` 自动重载；每行日期+composite（符号着色 up/down）+四相位 chip（复用 phaseLabel/phaseColor）；翻转行 warn 细环高亮（ring-warn/40 bg-warn/5）、变化 chip 边框加深（border-warn/60）、「仅看翻转」原生 checkbox 过滤；role=list、翻转行 tabindex=0 + aria-label 播报 from→to（中文相位）、非翻转行不设假焦点；`phases.ts` PHASE_LABELS 补 4 个 debt 相位中文（leveraging_boom/stable_growth/leveraging_bust/stable_contraction）；零新依赖
4. **[新功能] `backend/tests/test_signal_history.py`**：翻转检测构造序列单测（无翻转/单框架方向/同帧多框架/None↔值/窗口最旧行 flips=[]）、live 副本临时库两次写入落两行（ts 有序、composite/四相位与 compute_signals 一致、data_as_of YYYY-MM）、端点 shape（倒序/7 存储字段+flips/flips 与相邻差分一致）+ limit（1 生效/0→422）+ 临时空库 read_history → []

### 验证

- ✅ `scripts/_pipeline_test.py` 全过；`backend/tests` pytest 54 passed（新增 test_signal_history 7 例：翻转检测 3 + 两写两行 1 + 端点 shape/limit/缺表 3）
- ✅ worktree 内增量实跑：7 表 updated / 0 kept_previous，signal_history +1 行（ts=2026-08-09T22:35:05 == manifest.ts；data_as_of=2026-06；composite 0 + recession/tightening/active_restocking/beautiful_deleveraging 与 `GET /api/v1/signals` 逐项一致）；临时库单测连写两次 → 恰 2 行不去重
- ✅ `GET /api/v1/signals/history` 200 倒序、flips 标注与相邻差分一致、`?limit=1` ≤1 行、`?limit=0` 422、临时空库 read_history → []；`GET /api/v1/table/signal_history` 200 可浏览；TABLE_SPECS/validate() 零改动
- ✅ `vue-tsc --noEmit` 0 error；requirements.txt / package.json / tokens.css 零变化；analysis/、commentary、HealthLight.vue、release_calendar、vintage/双源逻辑零触碰；新增日志行不含 ✅

### M3: Signal History Table + Phase-Flip Highlights (English)

### New Features

1. **[feat] `scripts/signal_history.py`**: append-only signal_history table (ts/data_as_of/composite + four phases, no PK, no dedup); `01_fetch_data.py` main() appends one composite+four-phase snapshot row after a successful commit + manifest write (reuses manifest ts; data_as_of = derived_monthly MAX(date) as YYYY-MM, same convention as commentary); skipped on empty incremental plan, failure only warns (⚠️) without affecting committed data; outside TABLE_SPECS gating (post-commit derived snapshot), browsable via /table whitelist; log line uses 📈, never ✅ (refresh.py progress counts ✅ lines)
2. **[feat] `GET /api/v1/signals/history`**: newest-first (rowid DESC) with limit (default 60, 1–500), fetches limit+1 rows so even the oldest in-window row has a predecessor to diff against; rows annotated with flips (any framework phase changed vs the adjacent older row: framework/prev/curr, None participates); missing table → `{"items": []}` not 500 (fresh install); three new Pydantic schemas (PhaseFlip/SignalHistoryRow/SignalHistory), SignalHistory exported from `schemas/__init__`, shared/openapi.json re-exported
3. **[feat] Overview "信号与相位历史" card**: load()'s Promise.all gains a third leg `getSignalHistory()`, auto-reloads with `refresh.lastRefreshedAt`; each row = date + composite (sign-colored up/down) + four phase chips (reuses phaseLabel/phaseColor); flip rows get a warn ring (ring-warn/40 bg-warn/5), changed chips a deeper border (border-warn/60), native "仅看翻转" checkbox filter; role=list, flip rows tabindex=0 + aria-label announcing from→to (Chinese phase names), no fake focus on non-flip rows; `phases.ts` PHASE_LABELS gains the 4 debt phases (leveraging_boom/stable_growth/leveraging_bust/stable_contraction); zero new deps
4. **[feat] `backend/tests/test_signal_history.py`**: constructed-sequence flip-detection unit tests (no-flip / single-framework direction / multi-framework same frame / None↔value / oldest-in-window flips=[]), two-writes-two-rows on a temp copy of the live DB (ts order, composite+phases match compute_signals, data_as_of YYYY-MM), endpoint shape (newest-first / 7 stored fields + flips / flips consistent with adjacent diffs) + limit (1 honored / 0→422) + read_history on an empty temp DB → []

### Verification

- ✅ `scripts/_pipeline_test.py` all pass; `backend/tests` pytest 54 passed (new: 7 test_signal_history cases — 3 flip detection + 1 two-writes-two-rows + 3 endpoint shape/limit/missing-table)
- ✅ in-worktree incremental live run: 7 tables updated / 0 kept_previous, signal_history +1 row (ts=2026-08-09T22:35:05 == manifest.ts; data_as_of=2026-06; composite 0 + recession/tightening/active_restocking/beautiful_deleveraging field-for-field equal to `GET /api/v1/signals`); unit test writing twice to a temp DB → exactly 2 rows, no dedup
- ✅ `GET /api/v1/signals/history` 200 newest-first, flips consistent with adjacent diffs, `?limit=1` ≤1 row, `?limit=0` 422, read_history on empty temp DB → []; `GET /api/v1/table/signal_history` 200 browsable; TABLE_SPECS/validate() untouched
- ✅ `vue-tsc --noEmit` 0 errors; requirements.txt / package.json / tokens.css unchanged; analysis/, commentary, HealthLight.vue, release_calendar, vintage/dual-source logic untouched; new log lines contain no ✅

### M2：vintage 快照+diff、核心序列双源比对、财政/外需指标层、值域断言与 golden 扩层

### 新功能

1. **[新功能] `scripts/_pipeline.py`**：`snapshot_vintage()` + `commit_staging()` 在原子提升前把 live 复制进 `data/vintages/`（12 份轮转，返回快照 Path），`01_fetch_data.py` 把相对路径记入 manifest.vintage；`TABLE_SPECS` 增 `ranges` 值域（money_supply/cpi/ppi/pmi/gdp/social_finance/bond_yield 按 live 实测 min–max 校准）与 fiscal/external_demand 两条新 spec；`validate()` 非空值越界 >10% 拒收（整表量纲错必拦、个别修订吸收）
2. **[新功能] `scripts/diff_vintage.py`**：live vs 最近 vintage（可 `--vintage` 指定基线）逐表行数差 + 10 条核心序列最新值差；JSON/人类可读双输出；无差异 exit 0、有差异 exit 1；无 vintage 友好提示 exit 0
3. **[新功能] `scripts/dual_sources.py`**：m2_yoy/cpi_yoy/ppi_yoy/gdp_yoy/pmi_official/y_10y 六序列 primary vs 独立次源比对（rate：绝对差≤0.3pp 或相对≤2%；level：相对≤2%；含浮点边界 ε），只对本次抓取成功的表跑、只读 staging 永不覆盖 primary；结果写 `sources[table].dual`（series/source/date/primary/secondary/diff/divergent/error），次源失败只记 error 不红不黄；`refresh.py sources_health` 新增一支 warning：dual divergence→黄灯；social_finance 次源（东财 SHRZGM 及 4 变体）实测全 EMPTY 不纳入
4. **[新功能] 财政+外需层**：`fetch_fiscal`（NBS 月度预算收入/支出，2015- 起，指标行→长表按月外连接）、`fetch_external_demand`（NBS 货物进出口千美元→亿美元 ÷1e5 round(2) + 美国 ISM 制造业 PMI），fetchers 14→16；`release_calendar.py` 新增两表发布窗口；`/table` 白名单放行；`EXPECTED_FETCH_STEPS` 16→18；前端新页「财政与外需」（`/fiscal-external`，router+sidebar 可达，复用 buildMultiLine/buildSpreadChart，零新 builder，COL_ZH +8 词）
5. **[新功能] `backend/tests/test_derived_golden.py`**：derived_monthly 抽样列（m2_m1_spread/real_rate/pmi_ma6）在 live DB 副本上用 02 的 compute_derived 重算，与存储值逐行相等（eps 1e-6，DB 缺失自动 skip）

### 调整

1. **[调整] ISM 日期归一**：实测 jin10 ISM 日期**恒为发布日**（月初首个工作日，含 1 日），设计 §2.2 的 day==1 保留规则会把「8 月 1 日发布」留在 8 月并与「9 月 2 日发布→8 月」撞出 120 个重复日期；改用独立 `_norm_ism_date`（数据月恒为上月），重建后 0 重复、2025-08 数据月=48.7 与冻结现状一致

### 验证

- ✅ `scripts/_pipeline_test.py` 全过（新增 ranges 5% 通过/15% 拒收/×1000 拒收 + vintage 快照/12 份轮转/commit 返回快照）；`scripts/dual_sources_test.py` 全过（容差三支路、jin10/ISM 归一含跨年、GDP 只匹配第1季度）；`scripts/release_calendar_test.py` 全过（键集 14→16 + 新窗口用例）
- ✅ `backend/tests` pytest 29 passed（新增 test_derived_golden 1 例、test_sources_health dual divergence→yellow / match+error 仍 green 2 例）
- ✅ worktree 内 `--full` 实跑 ×2：16 表 updated / 0 kept_previous；vintage 每次恰增 1 份；manifest.sources 6 表含 dual 且全 convergent（m2_yoy 8.0=8.0、gdp_yoy 5.0=5.0、cpi_yoy 0.0=0.0@2025-07-01、ppi_yoy −3.6=−3.6@2025-07-01、pmi_official 49.4=49.4@2025-08-01、y_10y 1.7114=1.7114@2026-08-01），social_finance 无 dual 键；`GET /api/v1/sources/health` green
- ✅ `fiscal` 127 行至 2026-04、`external_demand` 678 行（贸易块 137 月至 2026-05，ISM 冻结 2025-08 数据月后为 NaN）；`GET /api/v1/table/fiscal`、`/table/external_demand` 200
- ✅ `diff_vintage.py`：首跑正确报新表/新增行（exit 1）、二跑准确捕获 external_demand 713→678（−35，ISM 修复）、自比对 identical exit 0、`--json` 形状符合设计
- ✅ 前端 `vue-tsc --noEmit` 0 error；requirements.txt / package.json / tokens.css 零变化；signals.py、02_compute_derived.py、commentary、HealthLight.vue 零触碰

### M2: Vintage Snapshots + Diff, Dual-Source Checks, Fiscal/External-Demand Layers, Range Assertions & Golden Derived Tests (English)

### New Features

1. **[feat] `scripts/_pipeline.py`**: `snapshot_vintage()` + `commit_staging()` copy the live DB into `data/vintages/` before the atomic promotion (rotate 12, returns the snapshot Path); the relative path is recorded as manifest.vintage; `TABLE_SPECS` gains `ranges` value domains (calibrated on live DB min–max) plus fiscal/external_demand specs; `validate()` rejects when >10% of non-null values fall outside range (whole-table unit errors blocked, isolated revisions absorbed)
2. **[feat] `scripts/diff_vintage.py`**: live vs latest vintage (or `--vintage` baseline) — per-table row deltas + latest-value deltas of 10 core series; JSON + human-readable; exit 0 when identical, 1 when changed; friendly exit 0 when no vintage exists
3. **[feat] `scripts/dual_sources.py`**: six series (m2_yoy/cpi_yoy/ppi_yoy/gdp_yoy/pmi_official/y_10y) cross-checked against independent secondaries (rate: ≤0.3pp abs or ≤2% rel; level: ≤2% rel; float-boundary ε), only for tables fetched OK, read-only on staging, primary never overwritten; results in `sources[table].dual`, secondary failures only logged; `sources_health` gains dual-divergence → yellow; social_finance excluded (all EM SHRZGM probes EMPTY)
4. **[feat] fiscal + external-demand layers**: `fetch_fiscal` (NBS monthly budget revenue/expenditure since 2015) and `fetch_external_demand` (NBS USD trade, thousand→hundred-million ÷1e5, + US ISM PMI); fetchers 14→16, calendar windows, `/table` whitelist, `EXPECTED_FETCH_STEPS` 16→18; new frontend page 财政与外需 (`/fiscal-external`, router+sidebar, reuses existing builders, zero new builder, COL_ZH +8)
5. **[feat] `backend/tests/test_derived_golden.py`**: sampled derived_monthly columns (m2_m1_spread/real_rate/pmi_ma6) recomputed via 02's compute_derived on a copy of the live DB must equal stored values row-by-row (eps 1e-6, skips when DB absent)

### Adjustments

1. **[adjust] ISM date normalization**: jin10 ISM dates are ALWAYS release dates (first business day, including the 1st); the design's day==1-keep rule produced 120 duplicate dates; dedicated `_norm_ism_date` (data month is always the previous month) — 0 duplicates after rebuild, 2025-08 data month = 48.7 matching the frozen source

### Verification

- ✅ `scripts/_pipeline_test.py` all pass (new: ranges 5% pass / 15% reject / ×1000 reject + vintage snapshot/rotation/commit-return); `scripts/dual_sources_test.py` all pass; `scripts/release_calendar_test.py` all pass (16-table key set + new windows)
- ✅ `backend/tests` pytest 29 passed (new: test_derived_golden + 2 dual-divergence health cases)
- ✅ two real `--full` runs in the worktree: 16 tables updated / 0 kept_previous; exactly one new vintage per run; six dual records all convergent (e.g. m2_yoy 8.0=8.0, y_10y 1.7114=1.7114@2026-08-01); social_finance has no dual key; health green
- ✅ `fiscal` 127 rows to 2026-04, `external_demand` 678 rows (trade to 2026-05, ISM NaN after frozen 2025-08); both `/table` endpoints 200
- ✅ `diff_vintage.py` reported first-run additions (exit 1), then exactly the ISM rebuild (external_demand 713→678), self-compare identical exit 0, JSON shape per design
- ✅ `vue-tsc --noEmit` 0 errors; requirements.txt / package.json / tokens.css untouched; signals.py, 02_compute_derived.py, commentary, HealthLight.vue untouched

### M1：数据源健康探针 + 发布日历增量抓取 + 可选 launchd 调度

### 新功能

1. **[新功能] `scripts/release_calendar.py`**：发布日历字典 `TABLE_CALENDAR`（14 表 kind/months/days 窗口/channel 及依据注释）+ 纯函数 `should_fetch(table, today, force)`——release 型表只在发布窗口内抓（宁宽勿窄），market 型（bond_yield）恒抓，未知表 fail-open
2. **[新功能] `scripts/01_fetch_data.py`**：`--full` 参数绕过日历；计划行 `📋 计划抓取 K/N 表（全量|增量）`；窗口内零表时提前返回（不 backup、不开 staging、不写 manifest）；`_MANIFEST` 新增 `sources` 键（14 fetcher 有序列表：table/channel/ok/elapsed_s/error/consecutive_failures/last_success），连败计数读上次 last_run.json 递增/清零，窗口外跳过的表整条沿用
3. **[新功能] `backend/app/core/refresh.py`**：纯函数 `sources_health(manifest)`（任一源 2 连败→red；1 连败或 kept_previous warning→yellow；其余→green；无 sources→green+updated_at=null）+ `read_sources_health()`（永不抛异常）；`run_refresh(full=False)` 子进程追加 `--full`；进度解析 `计划抓取 (\d+)/` 自适应 expected=K+2；`EXPECTED_FETCH_STEPS` 修正 15→16（14 fetcher + 2 衍生）
4. **[新功能] `backend/app/api/v1/sources.py` + `schemas/sources.py`**：`GET /api/v1/sources/health` 恒 200，形状 = SourcesHealth（SourceHealth 列表），只读 manifest 请求时推导、无缓存无新存储
5. **[新功能] `backend/app/api/v1/refresh.py`**：`POST /refresh` 与 `GET /refresh/stream` 新增查询参数 `full: bool`，透传 run_refresh
6. **[新功能] `frontend/src/components/layout/HealthLight.vue`**：RefreshBar 健康灯——绿/黄/红取 up/warn/down 令牌（红加细环）、无运行记录灰点；popover 列 14 源（表名/通道/最后成功/✓/warning/error）+「全量刷新」次按钮 + 增量提示；role=status aria-label 随状态播报，dialog Esc 关闭焦点归还，@vueuse/core onClickOutside 点击外部关闭（零新依赖）
7. **[新功能] `frontend/src/stores/refresh.ts`**：`health`/`loadHealth()`（失败静默→灰点），`stream(full)` 追加 `?full=1`、done 后刷新健康；`client.ts` 增 `getSourcesHealth()`/`triggerRefresh(full?)`；`types.ts` 增 SourceHealth/SourcesHealth 接口
8. **[新功能] `scripts/schedule/`**：launchd 三件套（com.macro.refresh.plist 模板 + install/uninstall 脚本），每日 10:07 触发，默认不安装，日志落 `data/refresh_schedule.log`

### 调整

1. **[调整] `scripts/_pipeline.py`**：cpi/ppi `min_rows` 300/250 → 200/200——东财当前全国 CPI/PPI 序列约 223/246 行（较早期覆盖缩短），旧下限导致新库永远拒收；对已有表的缩水防护仍由 distinct-date 反缩水县闸承担

### 验证

- ✅ `scripts/_pipeline_test.py` 全过；`scripts/release_calendar_test.py` 全过（2026-08-09 复跑确认）
- ✅ `backend/tests` pytest 26 passed（含新增 test_sources_health.py 红/黄/绿/沿用/无 manifest + TestClient 端点形状）
- ✅ worktree 内 `01_fetch_data.py` 增量/`--full` 实跑：manifest.sources 14 条、窗口 skip、空计划提前返回
- ✅ 前端 `vue-tsc --noEmit` 0 error（2026-08-09 复跑确认）；健康灯键盘可达（Tab/Enter/Esc/焦点归还）
- ✅ shared/openapi.json 与 live app 一致（`app.openapi()` 与盘上文件逐字段比对相等）；requirements.txt / package.json 零变化

### M1: Source Health Probe + Calendar-Driven Incremental Fetch + Optional launchd Schedule (English)

### New Features (English)

1. **[feat] `scripts/release_calendar.py`**: `TABLE_CALENDAR` dict (14 tables: kind/months/day-windows/channel with rationale) + pure `should_fetch(table, today, force)` — release tables only fetched inside their release window (wide over narrow), market table (bond_yield) always fetched, unknown tables fail-open
2. **[feat] `scripts/01_fetch_data.py`**: `--full` bypasses the calendar; plan line `📋 计划抓取 K/N 表（全量|增量）`; zero tables in window → early return (no backup/staging/manifest); `_MANIFEST` gains `sources` (ordered 14-fetcher list: table/channel/ok/elapsed_s/error/consecutive_failures/last_success), failure counters incremented/reset from previous last_run.json, window-skipped tables carried over verbatim
3. **[feat] `backend/app/core/refresh.py`**: pure `sources_health(manifest)` (any source ≥2 consecutive failures → red; 1 failure or kept_previous warning → yellow; else green; no sources → green + updated_at=null) + never-raising `read_sources_health()`; `run_refresh(full=False)` appends `--full`; progress parses `计划抓取 (\d+)/` to adapt expected=K+2; `EXPECTED_FETCH_STEPS` corrected 15→16 (14 fetchers + 2 derived)
4. **[feat] `backend/app/api/v1/sources.py` + `schemas/sources.py`**: `GET /api/v1/sources/health` always 200, shape = SourcesHealth; reads manifest on request, no cache, no new storage
5. **[feat] `backend/app/api/v1/refresh.py`**: `POST /refresh` and `GET /refresh/stream` gain `full: bool` query param, passed through to run_refresh
6. **[feat] `frontend/src/components/layout/HealthLight.vue`**: RefreshBar health light — green/yellow/red from up/warn/down tokens (red gets a thin ring), grey dot when no run record; popover lists 14 sources (table/channel/last-success/✓/warning/error) + secondary "全量刷新" button + incremental hint; role=status aria-label announces state changes, dialog Esc closes with focus return, @vueuse/core onClickOutside (zero new deps)
7. **[feat] `frontend/src/stores/refresh.ts`**: `health`/`loadHealth()` (silent failure → grey dot), `stream(full)` appends `?full=1` and reloads health on done; `client.ts` adds `getSourcesHealth()`/`triggerRefresh(full?)`; `types.ts` adds SourceHealth/SourcesHealth
8. **[feat] `scripts/schedule/`**: launchd trio (com.macro.refresh.plist template + install/uninstall scripts), daily 10:07, NOT installed by default, logs to `data/refresh_schedule.log`

### Adjustments (English)

1. **[adjust] `scripts/_pipeline.py`**: cpi/ppi `min_rows` 300/250 → 200/200 — eastmoney's current national CPI/PPI series is ~223/246 rows (shorter than the historical coverage the old floors were calibrated on), which permanently rejected them on a fresh DB; erosion protection for existing tables remains the distinct-date shrink guard

### Verification (English)

- ✅ `scripts/_pipeline_test.py` all pass; `scripts/release_calendar_test.py` all pass (re-run 2026-08-09)
- ✅ `backend/tests` pytest 26 passed (incl. new test_sources_health.py red/yellow/green/carry-over/no-manifest + TestClient endpoint shape)
- ✅ in-worktree `01_fetch_data.py` incremental/`--full` live runs: manifest.sources 14 entries, window skips, empty-plan early return
- ✅ frontend `vue-tsc --noEmit` 0 errors (re-run 2026-08-09); health light keyboard-accessible (Tab/Enter/Esc/focus return)
- ✅ shared/openapi.json matches the live app (`app.openapi()` vs on-disk file, field-by-field equal); requirements.txt / package.json unchanged

### 修复

1. **[修复] `scripts/01_fetch_data.py`**：NBS「居民人均可支配收入」采集路径适配国家统计局目录树改版——`人民生活 > 居民人均可支配收入` → `人民生活 > 全国居民人均收入情况`（原二级指标节点已被收进三级分类，新路径一次返回 12 个指标行），行筛选同步排除「中位数/增长/累计」变体，确保取到绝对值行；22 项数据源连通性测试全部通过
2. **[修复] `scripts/01_fetch_data.py`**：世界银行 API 超时 15s → 60s——该端点首个请求响应慢，15s 必然超时；60s 实测稳定（CHN 人口指标 66 年数据，至 2025）
3. **[文档] `docs/data-sources-guide.md`**（v1.3→v1.4）：NBS 节由"失效"更新为"已恢复"（akshare 1.18.x 切换新站 API，2026-08-09 实测可用；指标目录重构，人均可支配收入路径改为 `人民生活 > 全国居民人均收入情况`）；修正货币供应量接口描述（`macro_china_supply_of_money` 现存在且生产在用）；新增世界银行超时注意与 22/22 全量连通性实测记录
4. **[文档] `README.md`**：数据流水线 12→14 fetcher（补 `bond_yield`/`demographics` 两表及数据源说明）、`household_income` 状态更新、Python 版本 3.12→3.12+（实测 3.14.6）、手动采集命令改用 venv 解释器、数据库表数与徽章同步
5. **[文档] `docs/architecture-upgrade.md`**：顶部加"迁移已完成、历史存档"状态横幅（迁移早已落地，避免误读为进行中方案）
6. **[修复] `frontend/src/components/charts/options.ts`**：PMI 荣枯线 50 由琥珀实线 1.5px 改为隐晦灰色细虚线（`text3` #64748b @80%、1px、dashed）+ 同灰小字标注——退为背景维度参考，不再与「服务」序列（琥珀）撞色争焦；与四象限十字线、剪刀差零线统一参考线语汇。`markLineName` 参数化，顺带修正人口页 0 线误标「荣枯线 0」→「零线」
7. **[文档] `README.md`**：PMI 荣枯线样式描述与设计系统 warn 用途同步实际实现

### 说明

- **环境修复（非代码）**：本机 `.venv312` 缺失 requirements.txt 声明的 akshare/requests，已按 requirements 补装（akshare 1.18.83 / requests 2.34.2，Python 3.14.6 下 import 与运行正常）——这是管道此前无法运行的直接原因

### 验证

- 浏览器截图对比（库存周期「PMI 多维」图）：改前琥珀实线醒目撞色 → 改后灰色细虚线隐晦可寻；人口页 0 线标签改「零线」

### Fix (English)

1. **[fix] `scripts/01_fetch_data.py`**: adapt NBS household-income path to the NBS catalog restructure — `人民生活 > 居民人均可支配收入` → `人民生活 > 全国居民人均收入情况` (the indicator moved into a 3rd-level catalog that now returns 12 indicator rows); row filter additionally excludes median/growth/cumulative variants to keep the absolute-value row; all 22 datasource connectivity tests pass
2. **[fix] `scripts/01_fetch_data.py`**: World Bank API timeout 15s → 60s — first request to the endpoint is slow, 15s always timed out; 60s verified stable (66 years of CHN population data, through 2025)
3. **[docs] `docs/data-sources-guide.md`** (v1.3→v1.4): NBS section updated from "unavailable" to "recovered" (akshare 1.18.x switched to the new-site API, verified working 2026-08-09; catalog restructured, household-income path now `人民生活 > 全国居民人均收入情况`); corrected money-supply interface description (`macro_china_supply_of_money` now exists and is used in production); added World Bank timeout note and the 22/22 full connectivity test record
4. **[docs] `README.md`**: data pipeline 12→14 fetchers (added `bond_yield`/`demographics` tables + source notes), `household_income` status updated, Python version 3.12→3.12+ (verified on 3.14.6), manual fetch commands now use the venv interpreter, DB table counts & badge synced
5. **[docs] `docs/architecture-upgrade.md`**: added "migration completed, historical archive" status banner at top (the migration landed long ago; avoids misreading it as an in-flight plan)
6. **[fix] `frontend/src/components/charts/options.ts`**: PMI 50 threshold restyled from bright amber solid 1.5px to a subdued thin dashed slate line (`text3` @80%, 1px, dashed) with a small same-gray label — recedes to a background dimension, no longer clashes with the amber 服务 series; matches the quadrant cross-hair / spread zero-line reference vocabulary. `markLineName` parameterized; also fixes the demographics zero line mislabeled "荣枯线 0" → "零线"
7. **[docs] `README.md`**: PMI threshold style description + warn token usage synced with the implementation

### Notes (English)

- **Env fix (non-code)**: local `.venv312` was missing akshare/requests declared in requirements.txt; installed per requirements (akshare 1.18.83 / requests 2.34.2, imports & runs fine on Python 3.14.6) — this was the direct cause of the pipeline being unrunnable

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

### text-3 对比度达 WCAG AA（保 3 级层级）

### 无障碍

1. **[无障碍] `frontend/src/design/tokens.css` + `echarts.theme.ts` + `tailwind.config.ts`**：`--text-3` / `text3` / `'text-3'` 由 `#64748b`（slate-500，card 上 3.3:1、surface 4.0:1 不达 AA）改 `#8294a8`（card 5.07:1、surface 5.70:1、bg 6.20:1 全达 AA）。验证指出 scan 原推荐 `#94a3b8` 会与 `text-2`（同值）撞色、3 级层级塌成 2 级；`#8294a8` 亮度更低（L=0.2875 < text-2 的 0.3595）保 3 级阶梯。MetricTile 标签、轴标签、小字注全面提升低视力可读性。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；3 处 token 同改（CSS var / ECharts / Tailwind 不漂移）；无其他文字色误改；`phases.ts` neutral 与 `style.css` scrollbar 的 `#64748b` 独立语义不在本项范围（正确留外）。

### A11y (English)

1. **[a11y] `frontend/src/design/tokens.css` + `echarts.theme.ts` + `tailwind.config.ts`**: `--text-3` / `text3` / `'text-3'` from `#64748b` (slate-500, 3.3:1 on card / 4.0:1 on surface, failing AA) → `#8294a8` (5.07:1 card / 5.70:1 surface / 6.20:1 bg, all pass AA). Validation found the scan's proposed `#94a3b8` would collide with `text-2` (same value), flattening the 3-tier hierarchy; `#8294a8` has lower luminance (L=0.2875 < text-2's 0.3595), preserving the 3-tier step. MetricTile labels, axis labels, and small captions all improve low-vision readability.

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; all 3 token sites changed together (CSS var / ECharts / Tailwind, no drift); no other text color touched; the `#64748b` in `phases.ts` neutral + `style.css` scrollbar are independent semantics, out of scope (correctly left).

---

### App skip-link + main id（WCAG 2.4.1 跳过导航）

### 无障碍

1. **[无障碍] `frontend/src/App.vue`**：root div 首子加 `<a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[200] focus:bg-surface focus:text-text focus:px-3 focus:py-2 focus:rounded">跳到主内容</a>` + `<main id="main">`——键盘/SR 用户可跳过 7 项侧栏直达主内容（WCAG 2.4.1 Bypass Blocks）。`z-[200]` > sidebar `z-[100]`，焦点时浮于其上。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；skip-link 是 root 首子（Sidebar 前）；`href="#main"` 匹配 `main` 的 `id`；`sr-only` / `focus:not-sr-only` 可用。

### A11y (English)

1. **[a11y] `frontend/src/App.vue`**: added `<a href="#main" ...>跳到主内容</a>` as the first child of the root div + `id="main"` on `<main>` — keyboard/SR users skip the 7 sidebar links to reach main content (WCAG 2.4.1 Bypass Blocks). `z-[200]` > sidebar's `z-[100]`, so it floats above when focused.

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; skip-link is the root's first child (before Sidebar); `href="#main"` matches `main`'s `id`; `sr-only` / `focus:not-sr-only` available.

---

### 交互元素 focus-visible 焦点环（WCAG 2.4.7）

### 无障碍

1. **[无障碍] `frontend/src/components/layout/Sidebar.vue` + `RefreshBar.vue` + `CommentaryCard.vue`**：RouterLink + preset / refresh / cancel / 重新分析 按钮加 `focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2`——键盘 Tab 有可见焦点环（鼠标点击不显示，无视觉回归）。WCAG 2.4.7 Focus Visible。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；5 处交互元素全覆盖（含 UX-04 加的 cancel 按钮）；`outline-accent` 解析（`accent: #6366f1`）。

### A11y (English)

1. **[a11y] `frontend/src/components/layout/Sidebar.vue` + `RefreshBar.vue` + `CommentaryCard.vue`**: RouterLink + preset / refresh / cancel / regenerate buttons get `focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2` — keyboard Tab shows a visible focus ring (mouse clicks don't, no visual regression). WCAG 2.4.7 Focus Visible.

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; all 5 interactive elements covered (incl. the UX-04 cancel button); `outline-accent` resolves (`accent: #6366f1`).

---

### Sidebar 装饰图标 aria-hidden

### 无障碍

1. **[无障碍] `frontend/src/components/layout/Sidebar.vue`**：导航项的装饰性 unicode 图标 glyph（◉ ◐ ◈ ▣ ◆ ▧ ◎）加 `aria-hidden="true"`——避免 SR 读出 "circled bullet" 等噪音；标签文字已承载语义。MACRO 品牌名与「中国经济分析平台」副标题是有意义文字，不加 aria-hidden（验证强调）。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；仅 icon span 改动（MACRO / 副标题未动）；1 属性最小改动。

### A11y (English)

1. **[a11y] `frontend/src/components/layout/Sidebar.vue`**: decorative unicode icon glyphs (◉ ◐ ◈ ▣ ◆ ▧ ◎) get `aria-hidden="true"` — prevents SR reading "circled bullet" noise; the label span carries meaning. MACRO brand + subline are meaningful text, NOT aria-hidden (validation emphasized).

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; only the icon span changed (MACRO/subline untouched); 1 attribute minimal.

---

### commentary 生成/轮询开销削减（BE-PERF-02 + BE-PERF-03）

### 性能

1. **[性能] `backend/app/core/commentary.py`** `get_current`：模块级 `_table_ready` 标志，首次 `_ensure_table` 成功后置 True，`get_current` 按标志跳过——消除每 2s 轮询的 `CREATE TABLE IF NOT EXISTS` + `commit`（写路径 `_persist` / `mark_stale_and_regenerate` / `ensure_on_startup` 仍调用，保 create-on-first-access 契约）。
2. **[性能] `backend/app/core/commentary.py`** `_latest_data_date`：改复用 `_load_full("derived_monthly")` lru_cache DataFrame（lifespan 预热、refresh 前 `clear_all_caches` 清）取 `df["date"].max()`，免每 generate 开新 sqlite 连接；`pd.notna` 守卫空/NaT 返回 None（不返 'Na'）。

### 验证

- golden test 6/6（commentary 经 app 启动链）；smoke：`_table_ready` False→True 首次 `get_current` 后置位、2nd 跳过 `_ensure_table`；`_latest_data_date` 返 '2026-05'；缓存失效顺序正确（refresh `clear_all_caches` 在 `mark_stale_and_regenerate` 前）。

### Performance (English)

1. **[perf] `backend/app/core/commentary.py`** `get_current`: module-level `_table_ready` flag set after first `_ensure_table` success; `get_current` skips when set — eliminates per-2s-poll `CREATE TABLE IF NOT EXISTS` + `commit` (write paths `_persist` / `mark_stale_and_regenerate` / `ensure_on_startup` still call it, preserving create-on-first-access).
2. **[perf] `backend/app/core/commentary.py`** `_latest_data_date`: reuses `_load_full("derived_monthly")` lru_cache DataFrame (lifespan preload, cleared via `clear_all_caches` before refresh) for `df["date"].max()`, avoiding a fresh sqlite connection per generate; `pd.notna` guard returns None (not 'Na') on empty/NaT.

### Verification (English)

- golden test 6/6 (commentary via app startup chain); smoke: `_table_ready` False→True after first `get_current`, 2nd skips `_ensure_table`; `_latest_data_date` returns '2026-05'; cache invalidation order correct (refresh `clear_all_caches` before `mark_stale_and_regenerate`).

---

### refresh SSE URL 复用 BASE 常量

### 重构

1. **[重构] `frontend/src/api/client.ts` + `stores/refresh.ts`**：`BASE` 由模块私有改 `export`；refresh.ts 的 SSE stream fetch 由写死 `'/api/v1/refresh/stream'` 改 `` `${BASE}/refresh/stream` ``——单一 URL 真相源，API 版本变更不漏改（此前 refresh.ts 是唯一绕过 `api` 对象、写死 `/api/v1` 的 fetch）。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；URL 字节级与旧值一致（`/api/v1` + `/refresh/stream` = 旧字面量），无运行时行为变更。

### Refactor (English)

1. **[refactor] `frontend/src/api/client.ts` + `stores/refresh.ts`**: `BASE` from module-private to `export`; refresh.ts SSE stream fetch from hardcoded `'/api/v1/refresh/stream'` to `` `${BASE}/refresh/stream` `` — single URL source of truth, no missed update on API version change (refresh.ts was the only fetch bypassing the `api` object with a hardcoded `/api/v1`).

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; URL byte-identical to prior (`/api/v1` + `/refresh/stream` = old literal), no runtime behavior change.

---

### 路由切换更新 document.title

### 修复

1. **[修复] `frontend/src/router/index.ts`**：7 条路由的 `meta.title`（「综合概览」等）原无人消费，tab / 书签 / SR 全显示静态 title。加 `router.afterEach` 设 `document.title = `${to.meta.title} · 宏观经济分析平台``；补 `declare module 'vue-router' { interface RouteMeta { title?: string; icon?: string } }` 类型增强（strict 下 `to.meta.title` 与 `meta.icon` 类型安全）。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；`afterEach` 在重定向解析后的目标路由触发（`/` → `/overview` 也更新 title 为「综合概览 · 宏观经济分析平台」）。

### Fix (English)

1. **[fix] `frontend/src/router/index.ts`**: the 7 routes' `meta.title` ("综合概览" etc.) was never consumed; tab/bookmarks/SR showed the static title. Added `router.afterEach` setting `document.title = `${to.meta.title} · 宏观经济分析平台``; added `declare module 'vue-router' { interface RouteMeta { title?: string; icon?: string } }` augmentation (type-safe `to.meta.title` and `meta.icon` under strict).

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; `afterEach` fires on the resolved route after redirects (`/` → `/overview` also updates the title to "综合概览 · 宏观经济分析平台").

---

### GraphCard 数据拉取失败显示错误（修空白图 + 未处理 rejection）

### 修复

1. **[修复] `frontend/src/components/layout/GraphCard.vue`**：加 `error?: string | null` prop + `v-else-if="error"` 分支（`role="alert"`，text-red-400），置于 loading 与 slot 之间。
2. **[修复] `frontend/src/pages/*.vue`（7 页：MerrillClock/CreditCycle/DebtCycle/InventoryCycle/RealEstate/Demographics/Overview）**：各加 `error` ref + `load()` 起 `error.value = null` 重置 + `catch (e) { if (mine === reqId) error.value = (e as Error).message }`（带 reqId race-guard 镜像既有 finally guard，防陈旧失败请求覆盖新请求 error 态）；6 个 GraphCard 页传 `:error="error"`（21 张图全覆盖）；Overview 无 GraphCard 故 error 捕获（修未处理 rejection）但不显示（"静默空瓦"，前向兼容）。
- 修：`api.*` 拒绝（后端挂 / 5xx / 30s 超时）时不再渲染空白图、控制台无未处理 promise rejection；显示 `client.ts` 抛出的有意义中文 / HTTP 错误文本。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 1.98s 成功；7 页 reset + catch + reqId guard 一致；21/21 GraphCard 接 `:error`；Overview `const A`/`void A` 死码（CQ-02）未动；独立审查 Agent 通过。

### Fix (English)

1. **[fix] `frontend/src/components/layout/GraphCard.vue`**: added `error?: string | null` prop + `v-else-if="error"` branch (`role="alert"`, text-red-400) between the loading branch and the slot.
2. **[fix] `frontend/src/pages/*.vue` (7 pages: MerrillClock/CreditCycle/DebtCycle/InventoryCycle/RealEstate/Demographics/Overview)**: each adds an `error` ref + `error.value = null` reset at `load()` start + `catch (e) { if (mine === reqId) error.value = (e as Error).message }` (with the reqId race-guard mirroring the existing finally guard, preventing a stale failed request from overwriting a newer in-flight error state); the 6 GraphCard pages pass `:error="error"` (all 21 charts covered); Overview has no GraphCard so the error is captured (fixes unhandled rejection) but not displayed ("silent empty tiles", forward-compatible).
- Fixes: on `api.*` rejection (backend down / 5xx / 30s timeout) no longer renders a blank chart and no console unhandled promise rejection; shows `client.ts`'s meaningful Chinese / HTTP error text.

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` 1.98s success; 7 pages' reset + catch + reqId guard consistent; 21/21 GraphCards receive `:error`; Overview's `const A`/`void A` dead code (CQ-02) untouched; independent review agent approved.

---

### useCountUp 从上次显示值平滑过渡（不再每次从 0 重数）

### 修复

1. **[修复] `frontend/src/composables/useCountUp.ts`**：`const from = 0` 改 `let from = parseFloat(display.value); if (Number.isNaN(from)) from = 0`——preset 切换 / 数据更新时 count-up 从上次显示值平滑过渡到新值，不再每次从 0 重滚（6 个 KPI 瓦 + 综合信号）。首次 `display='—'` → `parseFloat` NaN → `from = 0`，首跑行为不变。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；首跑 NaN→0 保留；animate 循环 `const val = from + (target - from) * eased` unbroken（`from` 在循环内不重赋）；唯一调用方 `MetricTile.vue` 传 `number | null | undefined` 匹配 fallback 意图。

### Fix (English)

1. **[fix] `frontend/src/composables/useCountUp.ts`**: `const from = 0` → `let from = parseFloat(display.value); if (Number.isNaN(from)) from = 0` — count-up animates from the previously-displayed value to the new one on preset switch / data update, no longer re-rolling from 0 each time (6 KPI tiles + composite signal). First run `display='—'` → `parseFloat` NaN → `from = 0`, first-run behavior unchanged.

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; first-run NaN→0 preserved; animate loop `const val = from + (target - from) * eased` unbroken (`from` not reassigned in loop); sole caller `MetricTile.vue` passes `number | null | undefined` matching the fallback intent.

---

### 刷新后 re-warm 4 张热表（免首请求冷缓存）

### 性能

1. **[性能] `backend/app/core/refresh.py`**：`clear_all_caches()` 后补 re-warm 4 张热表（`derived_monthly` / `derived_quarterly` / `leverage` / `house_price`，镜像 `main.py` lifespan preload）——刷新后首请求不再冷缓存（~11ms → ~2ms / 端点）。subprocess 已 `proc.wait()` 完成无死锁；best-effort（失败则退回原冷缓存行为，无数据损失）。

### 验证

- golden test 6/6（refresh.py 导入链）；re-warm 顺序正确（`clear_all_caches` 后、`commentary.mark_stale_and_regenerate` / `return` 前）；无循环 import（db.py 仅 stdlib + pandas）；4 表元组与 lifespan 字节一致。

### Performance (English)

1. **[perf] `backend/app/core/refresh.py`**: after `clear_all_caches()` add a re-warm of the 4 hot tables (`derived_monthly` / `derived_quarterly` / `leverage` / `house_price`, mirrors `main.py` lifespan preload) — first post-refresh request no longer cold-cache (~11ms → ~2ms / endpoint). Subprocess already `proc.wait()`-complete, no deadlock; best-effort (failure falls back to original cold-cache, no data loss).

### Verification (English)

- golden test 6/6 (refresh.py import chain); re-warm order correct (after `clear_all_caches`, before `commentary.mark_stale_and_regenerate` / `return`); no circular import (db.py only stdlib + pandas); 4-table tuple byte-identical to lifespan.

---

### ECharts 图表 a11y（AriaComponent 注册 + aria 配置）

### 无障碍

1. **[无障碍] `frontend/src/components/charts/EChart.vue` + `design/echarts.theme.ts`**：注册 `AriaComponent`（`echarts/components` 导出但原未注册，故 `option.aria` 静默失效——两处都须改）+ `applyTheme` 的 `base` 加 `aria: { enabled: true, label: { description: '时间序列图表，详见 tooltip 与图例' } }`——ECharts 自动在 ~21 张图表根 DOM 生成 `role="img"` + `aria-label`（WCAG 1.1.1 / 4.1.2，零逐调用方改动）。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；vendor-echarts +1.18KB gzip（AriaComponent 预期）；`aria` 注册于 import + `use([...])` 两处；`base.aria` 经 `{...base, ...option}` 传播到全部图表（无 chart 覆盖 `aria`）。非阻塞观察：scatter/radar 的 label 文本略偏（仍满足 WCAG）、`aria` 未 deep-merge（latent，无 chart 覆盖故不触发）。

### A11y (English)

1. **[a11y] `frontend/src/components/charts/EChart.vue` + `design/echarts.theme.ts`**: registered `AriaComponent` (exported from `echarts/components` but previously NOT registered, so `option.aria` silently failed — both edits required) + added `aria: { enabled: true, label: { description: '...' } }` to `applyTheme`'s `base` — ECharts auto-generates `role="img"` + `aria-label` on all ~21 charts' root DOM (WCAG 1.1.1 / 4.1.2, zero per-caller changes).

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; vendor-echarts +1.18KB gzip (AriaComponent expected); `aria` registered in both import + `use([...])`; `base.aria` propagates to all charts via `{...base, ...option}` (no chart overrides `aria`). Non-blocking notes: scatter/radar label text slightly off (still WCAG-compliant), `aria` not deep-merged (latent, no chart overrides so not triggered).

---

### run_app.sh 启动自检补 akshare（防刷新 exit 1 复发）

### 修复

1. **[修复] `run_app.sh`**：后端依赖自检之后新增采集依赖自检——`import akshare` 失败时 `pip install -q -r requirements.txt`。后端本身不 import akshare，但「刷新数据」的采集子进程（`scripts/01_fetch_data.py`）必须 import；缺它导致刷新 exit 1（`ModuleNotFoundError: akshare`）。重建 venv 后启动脚本自动补齐，防复发。

### 验证

- `bash -n run_app.sh` 语法 OK；akshare 已装时检查返回 0 跳过安装分支；未装时触发 `pip install -r requirements.txt`。

### Fix (English)

1. **[fix] `run_app.sh`**: after the backend-dependency self-check, add a collection-dependency self-check — on `import akshare` failure run `pip install -q -r requirements.txt`. The FastAPI backend does not import akshare, but the refresh collection subprocess (`scripts/01_fetch_data.py`) must; missing it made refresh exit 1 (`ModuleNotFoundError: akshare`). After a venv rebuild the startup script auto-installs it, preventing recurrence.

### Verification (English)

- `bash -n run_app.sh` OK; with akshare installed the check returns 0 (skips install); when missing it triggers `pip install -r requirements.txt`.

---

### 美林时钟新增「PPI 同比」图（源数据，无自加工）

### 新功能

1. **[新功能] `frontend/src/pages/MerrillClock.vue`**：新增「PPI 同比」GraphCard，`buildMultiLine(cpiPpi, [{ col: 'ppi_yoy', name: 'PPI同比' }], '%', 0)` 带 0 荣枯线（正=出厂价上行、负=下行）；复用现有 `cpiPpi` 取数（`derived_monthly.ppi_yoy` 为东财 `BASE_SAME` 源数据）。**零数据加工、零采集/衍生改动**（应需求不自行推导环比，只放源数据同比），样式与现有图一致。

### 验证

- `vue-tsc --noEmit` 0 error + `vite build` 成功；DOM 确认新卡渲染（ECharts canvas + aria 标签）；浏览器截图核对样式与现有多线/双轴图一致。

### New Feature (English)

1. **[feat] `frontend/src/pages/MerrillClock.vue`**: added a "PPI 同比" (PPI YoY) GraphCard via `buildMultiLine(cpiPpi, [{ col: 'ppi_yoy', name: 'PPI同比' }], '%', 0)` with a 0 boom/bust line; reuses the existing `cpiPpi` fetch (`derived_monthly.ppi_yoy` = eastmoney `BASE_SAME` source data). **Zero self-computation, zero fetch/derived changes** (per requirement, no self-derived MoM — source-provided YoY only); style consistent with existing charts.

### Verification (English)

- `vue-tsc --noEmit` 0 errors + `vite build` success; DOM confirms the new card renders (ECharts canvas + aria label); browser screenshot verifies style matches existing multi/dual-line charts.

---

### 杠杆率折进 NIFD 补充走闸门（补到 2026-03）

### 修复

1. **[修复] `scripts/01_fetch_data.py`**：`fetch_leverage` 折进 NIFD 季度杠杆率（官方报告提取值，非自算）——`ak.macro_cnbs()` 滞后到 2024-12，而 NIFD 已发布 2025Q1–2026Q1。用 `date > cnbs_max` 过滤补齐滞后季度，并保证 AKShare 追上后 CNBS 自动取代；经 `save_to_db` 闸门落库；替换原"读 DB 保留行"逻辑。
   （本提交同时包含此前工作区未提交的：`household_income` NBS 目录路径修正、`demographics` WorldBank 超时 15→60s。）

### 验证

- 临时库副本：85 行（80 CNBS + 5 NIFD）、max 2026-03、闸门接受（85>80 非缩水）；真实刷新后生产库 `leverage` max=2026-03，2025+ 五期齐全。

### Fix (English)

1. **[fix] `scripts/01_fetch_data.py`**: `fetch_leverage` folds in NIFD quarterly leverage (official report values, not self-computed) — `ak.macro_cnbs()` lags at 2024-12 while NIFD has published 2025Q1–2026Q1. A `date > cnbs_max` filter backfills the lagging quarters and lets fresher CNBS data supersede once AKShare catches up; goes through the gated `save_to_db`; replaces the old "preserve DB rows" logic.
   (This commit also includes previously-uncommitted: `household_income` NBS path fix, `demographics` WorldBank timeout 15→60s.)

### Verification (English)

- Temp-copy test: 85 rows (80 CNBS + 5 NIFD), max 2026-03, gate accepted (85>80, not a shrink); after a real refresh the live `leverage` max=2026-03 with all five 2025+ quarters.

---

### PMI 切东财补到 2026-07（源滞后修复）

### 修复

1. **[修复] `scripts/01_fetch_data.py`**：`fetch_pmi` 官方/非制造业改东财 `RPT_ECONOMY_PMI`（`MAKE_INDEX`→pmi_official、`NMAKE_INDEX`→pmi_non_mfg，实测到 2026-07；akshare 官方滞后约一年，与杠杆率同款"源滞后"），复用 `_fetch_eastmoney`，东财无数据回退 akshare；财新/财新服务东财无口径仍用 akshare。
2. **排查结论**：GDP 为年度序列（`2026-01-01` 即最新年度点，2026-Q2 是年内季度非新年度点）不滞后、不切换；社融无免费当前源（东财无对应 reportName），滞后 2-3 月属正常发布滞后，接受。

### 验证

- 临时库 281 行、max 2026-07、列齐全、闸门接受（281>248 非缩水）；真实刷新后生产库 pmi max=2026-07，2026 全年 7 期官方值齐全。

### Fix (English)

1. **[fix] `scripts/01_fetch_data.py`**: `fetch_pmi` official/non-mfg switched to eastmoney `RPT_ECONOMY_PMI` (`MAKE_INDEX`→pmi_official, `NMAKE_INDEX`→pmi_non_mfg, current to 2026-07; akshare official lagged ~1yr, same "source lag" as leverage), reusing `_fetch_eastmoney` with akshare fallback; caixin/caixin-svc stay on akshare (eastmoney has no caixin).
2. **Audit conclusion**: GDP is an annual series (`2026-01-01` = latest annual point; 2026-Q2 is intra-year, not a new annual point) — not stale, not switched; social financing has no free current source (eastmoney lacks the reportName), 2-3 month lag is normal publication lag — accepted.

### Verification (English)

- Temp-copy 281 rows, max 2026-07, columns intact, gate accepted (281>248, not a shrink); after real refresh live pmi max=2026-07 with all 7 official 2026 months.

---

### PMI 切东财保留 2008 前历史（修复审查发现的历史丢失）

### 修复

1. **[修复] `scripts/01_fetch_data.py`**：`fetch_pmi` 改为 akshare 全历史（2005+）为底 + 东财（2008+ 更当前）`combine_first` 覆盖近期——修复上一提交切源时丢掉 2005-02..2007-12 共 35 个月历史的回归（东财序列自 2008-01 起；缩水闸门 0.8 地板未拦住 14% 侵蚀，独立审查发现）。

### 验证

- 临时库 331 行、min 2005-02、max 2026-07、2005-07 官方 35 期恢复；真实刷新后生产库 pmi min=2005-02 / max=2026-07。

### Fix (English)

1. **[fix] `scripts/01_fetch_data.py`**: `fetch_pmi` now uses akshare full-history (2005+) as base + eastmoney (2008+, more current) overlaid via `combine_first` — fixes the prior commit's regression that dropped 35 months (2005-02..2007-12) because eastmoney's series starts 2008-01 and the 0.8 shrink floor didn't catch the 14% erosion (found by independent review).

### Verification (English)

- Temp-copy 331 rows, min 2005-02, max 2026-07, 35 official 2005-07 rows restored; after real refresh live pmi min=2005-02 / max=2026-07.

---

### 美林页两图合一为「CPI vs PPI 环比」+ PPI 环比推导

### 重构

1. **[重构] `frontend/src/pages/MerrillClock.vue`**：删冗余「单独 PPI 同比」（ppi_yoy 已在「CPI vs PPI 同比」）与「CPI 同比 vs 环比」，合并为一张「CPI vs PPI 环比」双轴图，与同比图呼应（一张同比、一张环比）。行业调研：美林时钟轴用 CPI 同比；环比作领先/动能指标被行业广泛使用，故保留环比视图。
2. **[新功能] `scripts/01_fetch_data.py`**：新增 `_derive_ppi_mom`——东财/akshare 均无免费 PPI 环比源（东财仅同比 BASE_SAME），由同比重建定基指数再求环比（行业标准推导，图注标明"推导值"）；ppi 表加 `ppi_mom` 列。
3. **[新功能] `scripts/02_compute_derived.py`**：derived_monthly 合并 `ppi_mom`（列存在才并，兼容旧表）。

### 验证

- 推导值符号/量级随同比趋势一致（2026-03 +0.69 / 04 +2.36 / 06 −0.75）；刷新后 derived_monthly 含 ppi_mom；`vue-tsc` 0 + `vite build` 成功。

### Refactor (English)

1. **[refactor] `frontend/src/pages/MerrillClock.vue`**: removed redundant "PPI YoY" (ppi_yoy already in "CPI vs PPI YoY") and "CPI YoY vs MoM", combined into one "CPI vs PPI MoM" dual-axis chart echoing the YoY chart (one YoY, one MoM). Industry research: the Merrill clock axis uses CPI YoY; MoM is widely watched as a leading/momentum indicator, so the MoM view is kept.
2. **[feat] `scripts/01_fetch_data.py`**: added `_derive_ppi_mom` — no free PPI-MoM source exists (eastmoney only has YoY BASE_SAME), so derive MoM from YoY via base-index reconstruction (industry-standard, labeled "derived"); ppi table gains `ppi_mom`.
3. **[feat] `scripts/02_compute_derived.py`**: derived_monthly merges `ppi_mom` (only if the column exists, backward-compatible).

### Verification (English)

- Derived MoM sign/magnitude track the YoY trend (2026-03 +0.69 / 04 +2.36 / 06 −0.75); after refresh derived_monthly contains ppi_mom; `vue-tsc` 0 + `vite build` success.

---

### 图表图例统一中文化

### 优化

1. **[优化] `frontend/src/components/charts/options.ts`**：新增集中「列 key→中文图例名」映射 `COL_ZH`（采用 NBS/央行/NIFD 官方术语；CPI/PPI/M2/M1/PMI/LPR/GDP 等特有名词保留英文缩语，未收录 key 原样回退）；`buildDualAxisLine` 与 `buildStackedArea` 的序列名/双轴名改经 `zh()` 翻译——此前这两类图图例直接显示列 key（`cpi_yoy`/`household`/`non_fin_corp` 等英文）。全部调用点无需改动。
2. **[优化] `frontend/src/pages/DebtCycle.vue`**：利率环境图「10Y国债」统一为「10年期国债」。

### 验证

- 债务周期图例=居民部门/非金融企业部门/政府部门、中央政府/地方政府；美林双轴=CPI同比/PPI同比、CPI环比/PPI环比（截图确认，轴名同步中文化）；`vue-tsc` 0 + `vite build` 成功。

### Optimization (English)

1. **[opt] `frontend/src/components/charts/options.ts`**: added a central col-key→Chinese-legend map `COL_ZH` (official NBS/PBoC/NIFD terminology; CPI/PPI/M2/M1/PMI/LPR/GDP keep English abbreviations; unmapped keys fall back to the raw key); `buildDualAxisLine` + `buildStackedArea` series/axis names now go through `zh()` — previously these charts showed raw column keys (`cpi_yoy`/`household`/`non_fin_corp`) as English legends. No call-site changes needed.
2. **[opt] `frontend/src/pages/DebtCycle.vue`**: rate-env chart "10Y国债" → "10年期国债".

### Verification (English)

- Debt-cycle legends = 居民部门/非金融企业部门/政府部门 and 中央政府/地方政府; Merrill dual-axis = CPI同比/PPI同比 and CPI环比/PPI环比 (screenshot-verified, axis names localized too); `vue-tsc` 0 + `vite build` success.

---

### 债务周期新增「居民真实杠杆空间」图 + 修正债务收入比口径

### 新功能

1. **[新功能] `frontend/src/pages/DebtCycle.vue`**：新增「居民真实杠杆空间：杠杆率 vs 债务收入比」图（`buildMultiLine`：居民部门杠杆率 vs 居民债务收入比，取自 `derived_quarterly`）。体现真实加杠杆空间——杠杆率看似仅 ~60%，但债务收入比已 >120%。
2. **[修复] `scripts/02_compute_derived.py`**：修正 `hh_debt_to_income` 口径——居民杠杆率相对**年度** GDP，原实现误用单季累计 GDP 作债务基数、低估债务约 4 倍（算出 ~32%）；改以 Q1 累计×4 年化近似全年 GDP 作基数，修正后 ~124-129%。

### 验证

- 修正后 `derived_quarterly.hh_debt_to_income` 2025-2026 ≈ 124-129%（符合"债务收入比已很高"的判断）；API `/derived/quarterly` 返回一致；`vue-tsc` 0 + `vite build` 成功；图表经 `buildMultiLine` 渲染（与其余图一致）。

### New Feature (English)

1. **[feat] `frontend/src/pages/DebtCycle.vue`**: added "居民真实杠杆空间：杠杆率 vs 债务收入比" chart (`buildMultiLine`: household leverage vs household debt-to-income, from `derived_quarterly`). Shows true leverage headroom — leverage looks ~60% but debt/income already >120%.
2. **[fix] `scripts/02_compute_derived.py`**: corrected `hh_debt_to_income` — household leverage is relative to ANNUAL GDP; the old code used single-quarter cumulative GDP as the debt base, understating debt ~4x (~32%); now annualizes Q1×4 as the base, corrected to ~124-129%.

### Verification (English)

- Corrected `derived_quarterly.hh_debt_to_income` ≈ 124-129% for 2025-2026 (matches the "debt/income already high" expectation); API `/derived/quarterly` returns the same; `vue-tsc` 0 + `vite build` success; chart renders via `buildMultiLine` like the others.

---

### 债务收入比图与其他表日期对齐（derived_quarterly 保留季末月日期）

### 修复

1. **[修复] `scripts/02_compute_derived.py`**：derived_quarterly 原先把 leverage 季末月日期归一到季初（2026-03→2026-01），使「居民真实杠杆空间」图 x 轴末端比债务页其他图（leverage 原始表，季末月）早一个刻度、看似"数据截止更早"。实为同一期数据（2026-03=2026-Q1）的日期约定差异。现保留 leverage 原生季末月日期与同页其他图对齐；GDP 仍 `merge_asof(backward)` 填充，收入改 `merge_asof` 回填。

### 验证

- derived_quarterly max=2026-03-01 == leverage max；hh_debt_to_income 2026-03=129.4；cycle_merrill 年去重仍正常（新增 2026 行合理）；API 两表对齐 2026-03。

### Fix (English)

1. **[fix] `scripts/02_compute_derived.py`**: derived_quarterly previously normalized leverage quarter-end dates to quarter-start (2026-03→2026-01), making the debt-income chart's x-axis end one tick earlier than the page's other charts (leverage raw, quarter-end) — it looked like "data cut off earlier", but it was the same data point (2026-03 = 2026-Q1) under a different date convention. Now keeps leverage's native quarter-end dates (aligned with the other charts); GDP still `merge_asof(backward)`, income via `merge_asof`.

### Verification (English)

- derived_quarterly max=2026-03-01 == leverage max; hh_debt_to_income 2026-03=129.4; cycle_merrill year-dedup still sane (2026 row added sensibly); API both aligned to 2026-03.

---

### 新增《数据补充运行手册》（NIFD 杠杆率等手工/Agent 补充流程）

### 文档

1. **[文档] `docs/data-supplement-runbook.md`**：列清所有「靠手工/Agent 补充」的数据——NIFD 宏观杠杆率（季度，主要手工项，含已知报告期 URL 与 Agent 补充步骤+校验规则）、`household_income`（NBS，现已自动、监控）、GDP 季度（可选）、PPI 环比（推导、无需手工）。写明从哪取/怎么取/取什么。
   原因：NIFD 无公开 API、自动发现最新期+解析数字不可靠，硬塞自动刷新易污染数据，故用 Agent 半自动补充。

### Docs (English)

1. **[docs] `docs/data-supplement-runbook.md`**: runbook listing all manually/Agent-supplemented data — NIFD macro leverage (quarterly, main manual item, with known report URLs + Agent steps + validation rules), `household_income` (NBS, now auto, monitor), quarterly GDP (optional), PPI MoM (derived, no manual). Documents where/how/what to fetch.
   Rationale: NIFD has no public API; auto-discovery + parsing is unreliable and would risk polluting data if baked into auto-refresh, so use Agent semi-auto supplement.

---

### 补 NIFD 2026Q2 杠杆率 + 硬编码数据清单入册

### 数据

1. **[数据] `scripts/01_fetch_data.py` + `scripts/03_supplement_leverage.py`**：`_NIFD_DATA`/`NIFD_DATA` 追加 2026Q2（2026-06-01：居民 57.7 / 非金 179.5 / 政府 71.0 / 中央 30.5 / 地方 40.4 / 实体 308.2），经 Workflow 双源交叉验证（NIFD 报告 id 4976 + 同花顺/东财/新浪，57.7+179.5+71.0=308.2 校验通过）。杠杆率更新至 **2026-06**。
2. **[文档] `docs/data-supplement-runbook.md`**：新增「硬编码数据清单」——全仓唯一硬编码时序数据为 NIFD 宏观杠杆率；其余（CITIES/周期分类阈值）为配置非数据。当前到 2026-06；§1 已知报告期 URL 加 2026Q2=4976。

### 验证

- 走闸门 01+02：leverage max=2026-06；derived_quarterly 86 行；hh_debt_to_income 2026-06=126.6；API 对齐 2026-06。

### Data (English)

1. **[data] `scripts/01_fetch_data.py` + `scripts/03_supplement_leverage.py`**: appended NIFD 2026Q2 (2026-06-01: household 57.7 / non-fin 179.5 / gov 71.0 / central 30.5 / local 40.4 / real-economy 308.2), Workflow cross-validated (NIFD report id 4976 + 10jqka/Eastmoney/Sina; sum check 57.7+179.5+71.0=308.2 ✓). Leverage updated to **2026-06**.
2. **[docs] `docs/data-supplement-runbook.md`**: added "Hardcoded Data Inventory" — the only hardcoded time-series data is NIFD macro leverage; others (CITIES / classification thresholds) are config, not data. Now to 2026-06; §1 known report URLs add 2026Q2=4976.

### Verification (English)

- Gated 01+02: leverage max=2026-06; derived_quarterly 86 rows; hh_debt_to_income 2026-06=126.6; API aligned to 2026-06.

---

### GDP 补 2026-Q2 + 社融补 2026-05/06（case1/case2）

### 数据

1. **[数据] `scripts/01_fetch_data.py`**：`fetch_gdp` 正则扩展接受累计季度（"2026年第1-2季度"→2026-04-01），gdp 补到 **2026-Q2**。`fetch_social_finance` 新增 PBoC 调查统计司 XLSX 备用源（仅追加 >主源max 月份、dropna 未发布月），社融补到 **2026-06**（2026-05=20293亿 / 06=33645亿，与官方一致；保留主源历史）。
2. **[修复] `scripts/02_compute_derived.py`**：`hh_debt_to_income` 年化基数改用该年 Q4(10月)累计 GDP（ffill 上年、回退 Q1×4），适配 gdp 累计行。

### 验证

- gdp max=2026-04；social_finance max=2026-06；hh_debt_to_income 2026-06=132.7（合理）；API 对齐。

### Data (English)

1. **[data] `scripts/01_fetch_data.py`**: `fetch_gdp` regex accepts cumulative quarters ("2026年第1-2季度"→2026-04-01), GDP to **2026-Q2**; `fetch_social_finance` gains a PBoC XLSX backup (append only rows >primary-max, dropna unpublished), social-financing to **2026-06** (2026-05=20293亿 / 06=33645亿, matches official; primary history kept).
2. **[fix] `scripts/02_compute_derived.py`**: `hh_debt_to_income` annual base now uses that year's Q4(Oct) cumulative GDP (ffill prior year, fallback Q1×4), adapted to cumulative gdp rows.

### Verification (English)

- gdp max=2026-04; social_finance max=2026-06; hh_debt_to_income 2026-06=132.7 (sane); API aligned.

---

### 人口与城镇化改用 NBS 官方值（WB 长历史回退）

### 修复

1. **[修复] `scripts/01_fetch_data.py`**：`fetch_demographics` 人口/城镇化率改 **NBS 官方优先**（"人口>总人口" 取「年末总人口/城镇人口」行，城镇化率=城镇/总×100），World Bank 补长历史（`combine_first`，年份数不缩水、过校验闸门）；出生率/自然增长率仍用 WB（NBS 经 akshare 无可用 path，留在 2024）。修正此前 WB 值与统计局公报的差异（2025 总人口 140489万 / 城镇化率 67.89%）。

### 验证

- demographics 66 年、2025 总人口 140489万 / 城镇化率 67.89%（NBS 官方）；校验闸门通过（kept_previous 0）；API 对齐。

### Fix (English)

1. **[fix] `scripts/01_fetch_data.py`**: `fetch_demographics` population/urbanization now **NBS-official-first** ("人口>总人口" rows 年末总人口/城镇人口, urbanization=urban/total×100); World Bank supplies the long history via `combine_first` (year count not shrunk, so the gate passes); birth/natural-growth stay WB (NBS not obtainable via akshare, stays 2024). Corrects the prior WB-vs-NBS discrepancy (2025 total 140489万 / urbanization 67.89%).

### Verification (English)

- demographics 66 years; 2025 total 140489万 / urbanization 67.89% (NBS official); gate passed (kept_previous 0); API aligned.

---

### 人口出生率/自然增长率补 2025 公报官方值 + 财政/外需数据恢复

### 数据

1. **[数据] `scripts/01_fetch_data.py`**：`fetch_demographics` 新增 `_NBS_BIRTH_NATURAL` 补充 2025 出生率 **5.63‰** / 自然增长率 **-2.41‰**（《2025年国民经济和社会发展统计公报》2026-02-28 发布；NBS API 被 WAF 封、akshare 无 birth path）。人口四指标 2025 全部对齐官方。
2. **[数据] 财政/外需**：`fiscal`/`external_demand` 表此前因 NBS 瞬时不可达未建表导致页面 500；重跑 fetch 后建表（fiscal 127 行到 2026-04、external_demand 137 行），端点恢复 200。

### 验证

- demographics 2025 = 140489万 / 67.89% / 5.63‰ / -2.41‰；`/table/fiscal`、`/table/external_demand` 均 200。

### Data (English)

1. **[data] `scripts/01_fetch_data.py`**: `fetch_demographics` adds `_NBS_BIRTH_NATURAL` supplement for 2025 birth **5.63‰** / natural-growth **-2.41‰** (《2025 statistical communiqué》2026-02-28; NBS API WAF-blocked, akshare lacks a birth path). All four 2025 population indicators now match official.
2. **[data] fiscal/external**: `fiscal`/`external_demand` tables were missing (NBS transiently unreachable) causing page 500; re-running fetchers created them (fiscal 127 rows to 2026-04, external_demand 137 rows), endpoints back to 200.

### Verification (English)

- demographics 2025 = 140489万 / 67.89% / 5.63‰ / -2.41‰; `/table/fiscal` and `/table/external_demand` both 200.

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
