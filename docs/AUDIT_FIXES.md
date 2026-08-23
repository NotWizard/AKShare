# 审计修复账本 · AUDIT_FIXES ledger

> 2026-08 五模块并行审计的修复追踪。断点续跑的唯一真相源。
> 状态: ⬜ pending · 🟨 in-progress · 🟦 reviewing · ✅ done · ⏸️ blocked
> 每组 = 一个功能点 = 一个 commit。fixer 子 Agent 实现 → 不同的 reviewer 子 Agent 独立复核 → 编排者提交。
> 目标: 全部修完 → bump v1.1.0 → 推 main → gh 发布 Release（推送/发布前须用户确认）。
> 基线: `cd backend && ../.venv312/bin/python -m pytest -q` = 63 passed；`cd frontend && npm run typecheck` = 0 errors。

## 约定
- 量化类修复必须新增「改前失败、改后通过」的测试。
- 不删/跳/弱化既有测试来变绿。不提交 .env / data/*.db / 密钥。不 force-push。不跳 hook。
- 每次提交同步更新 `changeLog.md` 的 `[Unreleased]`，双语结构化（AGENTS.md）。

## 第二波在飞（2026-08-22，resume 后必读）
第二批 5 个 fixer 子 Agent 已后台启动，**其产出可能以未提交改动的形式留在工作树里**。
resume 后第一件事：`git status --short` —— 若有改动，先辨认属于下列哪一组，跑该组测试并按组提交，**不要重复派发 fixer**。

| 组 | 覆盖 finding | 文件集（判断归属用） |
|---|---|---|
| W2 · G23+G03b | A-H1/A-H2/A-H3/A-M5 + cycle_*/real_estate 缓存版本键 + F15 | `analysis/*.py`, `backend/tests/test_signal_robustness.py` |
| W3 · G11+G12+G20+G21 | P-H1/P-H3/P-M1-M4/P-M6 + A-M2/A-M3 | `scripts/{01,02,_pipeline,03}*.py`, `backend/tests/test_pipeline_guards.py`/`test_derived_calc.py` |
| W4 · G13+G14+G15+G25 | FE-H2/FE-H3/FE-H4/FE-M1-M11 + F10(_busy 竞态) | `frontend/src/**`, `frontend/tailwind.config.ts`, `backend/app/core/commentary.py` |
| W5 · G09+G10+G24rest | F6/F7/F11/F12 + A-M1(WAL) + F16 | `backend/app/api/v1/{crcl,refresh}.py`, `core/{refresh,crcl_collect,crcl_db,db,locking}.py`, `main.py`, `schemas/refresh.py` |
| W6 · G17+G27 | O-H2/O-M2/O-M3/O-M6/O-L3 | `requirements.txt`, `requirements.lock`, `backend/pyproject.toml`, `run_app.sh`, `README.md`, `.env.example` |

后续仍未开工（按此顺序）：**G08**（变更端点鉴权，需 W5 落地后再动 main.py/api）→ **G16+G18**（CI + fixture DB + 契约/前端测试，必须在工作树干净时一起做：CI 没有 fixture DB 必红，而 conftest.py 会被 pytest 收集从而干扰在飞 Agent 的验证）→ `shared/openapi.json` 重导（依赖 W5 定稿）→ **G26/G28/G29/G30** → 发布。
发布前遗留动作：`changeLog.md` → `CHANGELOG.md` 改名（故意推迟，因在飞提交都指向现文件名）；未跟踪的 `backtest_hshylv/`、`.playwright-mcp/`、根目录 PNG 保持原样（已 gitignore，属用户本地文件，不删）。

### 第二波已全部落地（2026-08-22）
5 组均已按组提交，工作树已清空。全套 `pytest -q` = **217 passed / 0 failed**；`vue-tsc --noEmit` 退出码 0；`scripts/_pipeline_test.py` 全过。

| 组 | 提交 | 覆盖 |
|---|---|---|
| W6 · G17+G27 | `bfeb45d` + `ba45b91` | akshare 精确锁 / requirements.lock / 解释器解析 / data/logs / .env.example / README 纠错 |
| W2 · G23+G03b | `6d3c248` | as-of 对齐、缺失≠看空、债务净部门、信贷迟滞、cycles+real-estate 版本键、F15 |
| W3 · G11+G12+G20+G21 | `df0c565` | 可执行超时、house_price 多粒度闸门、派生口径/look-ahead、SQLite 约束去重 |
| W4 · G13+G14+G15+G25 | `6f2a99c` | useAsyncData/PageState、client 重试去重、轮询生命周期、F10、CRCL store、a11y |
| W5 · G09+G10+G24rest | `592ac03` | 异步 SSE、有界执行器、CRCL 单飞、WAL 连接工厂、F11、F12 |

### ⚠️ 遗留处理进展（来自 fixer 自查，按危害排序）
1. ✅ **已修 `e4823d2`** — WAL 与整库交换相互作用（数据丢失风险）：`_pipeline.py` 新增 `_checkpoint_wal()`（`PRAGMA wal_checkpoint(TRUNCATE)`）+ `_drop_wal_sidecars()`；复制前 checkpoint 活库、交换前 checkpoint staging、交换后清旧 inode 边车。fail→pass 实测：仅 stash `_pipeline.py` → 2 failed，恢复 → 2 passed（`test_pipeline_wal_swap.py`）。
2. ✅ **已修 `b55b391`** — `core/commentary.py` 三个早退分支（生成中/已在生成/生成失败）补 schema 必需的 `text=""`。此前缺该字段 → FastAPI 响应校验抛错 → 端点 500，把"模型未配置"伪装成服务器崩溃。fail→pass：3 failed → 3 passed。
3. ✅ **已修 `b55b391`** — `frontend/src/design/phases.ts` 补 `insufficient_data`→「数据不足」（该相位现会真实出现在 `/cycles` 与 `signal_history`）。
4. ✅ **已修 `b55b391`** — `frontend/src/api/types.ts` 的 `RefreshResult.detail` 改为 `error_id`（后端 F12 已移除 detail）。
5. ✅ **已修 `f4baa1f`** — F13-rest：`core/commentary.py` 的 `get_current` 裸 `except Exception` 收窄为只吞 `sqlite3.OperationalError` 且含 "no such table"，其余冒泡为可见 500（照抄 `signal_history.read_history` 同款）；顺带修掉错误路径 fd 泄漏。fail→pass：`test_commentary_errors.py` 改前 2 failed（编程错误/非良性 sqlite 错误未冒泡）→ 改后 passed。
6. ✅ **已修 `f4baa1f`** — `core/commentary.py`、`core/signal_history.py` 裸 `sqlite3.connect` 改走 `db.connect()` 工厂，补 `busy_timeout`（连接属性、默认 0）。fail→pass：`test_db_factory_callers.py` 改前 2 failed（模块无 `connect` 属性）→ 改后 passed（PRAGMA busy_timeout == BUSY_TIMEOUT_MS>0）。
7. ✅ **已修 `f4baa1f`** — `SignalSummary` 补 `as_of`/`included`/`excluded`/`stale`/`composite_raw` 五个可选字段。fail→pass：`test_signals_schema_fields.py` 改前 2 failed（response_model 过滤掉 as_of）→ 改后 passed；实测 `/signals` as_of=2026-06、stale=[inventory]、composite_raw=2.29。
8. ✅ **已修 `f4baa1f`（launcher 部分）** — `启动面板.command` `:5173`→`:8000`（vite preview 已下线）。余项 `max_points` 静默抽稀、`scipy`/`statsmodels` 零 import 归入 G26/G28-30 低危批次处理，不在本条。
9. 说明：`data/macro_data.db` 现为 `journal_mode=wal`（跑测试经新工厂读真实库的持久副作用）；`integrity_check ok`、无 `-wal/-shm` 残留、该文件已 gitignore。

### 当前实测门禁（2026-08-23，G08 提交后 29 次提交）
`pytest backend/tests -q` = **279 passed / 0 failed**（含 G26/G28-30 在飞未提交的新测试）；`vue-tsc --noEmit` 退出码 **0**；`scripts/_pipeline_test.py` = ALL CHECKS PASSED。已提交至 `9e8d4f8`。工作树**非干净**：仍有 G26 + G28-30 两组在飞改动（下方 resume 协议）。

### 仍未开工（按此顺序）
已完成并提交：Critical/High/Medium 主体 + 遗留 5-8（`f4baa1f`）+ **G08 变更端点鉴权（`9e8d4f8`，Critical）**。
剩余：
1. **G26 源已提交 `b9167ec`（P-M7/P-M8/P-M9）**。⚠️ 但**仍有一个在飞 agent 未报**正在改 `scripts/03_supplement_leverage.py`（给 `backup_db` 加 `backup_dir` 注入参数，疑似 G30 P-L「双备份拷贝」）并已落 `backend/tests/test_pm9_declarative_fetch.py`（9 passed）。当前工作树**红**：`test_pipeline_supplement` 4 例失败，因为该 03 改动改了签名而其已提交测试仍期望旧签名——**HEAD (`b9167ec`) 本身是绿的**（旧 03 + 匹配测试），红只在未提交改动里。resume：等该 agent 报完，把 `03` 新版 + `test_pm9_declarative_fetch.py` +（可能的 `test_pipeline_supplement` 更新）作为一组 review→绿门禁→提交；勿把当前半成品红态提交。
2. **提交 G28-G30（低危，`analysis/`+前端）**：在飞文件 = `analysis/cross_indicator.py`、`backend/app/core/serial.py`、`frontend/src/components/charts/{EChart.vue,options.ts}`、`frontend/src/components/layout/Sidebar.vue`、`frontend/src/pages/CrclMonitor.vue`、`backend/tests/test_{cross_lag_semantics,serial_precision}.py`。同上流程。
3. **G16+G18**（CI + fixture DB + 契约/前端测试 + openapi 漂移门禁）：**必须工作树干净后**再做（`conftest.py` 会被每次 pytest 收集，在飞期会污染 agent 验证）。
4. `shared/openapi.json` 重导（现缺全部 8 条 `/crcl/*` + G08 的 `/session`、POST/GET 拆分）：**放在版本 bump 之后**（`info.version` 取自 app，先 bump 免得重导两次）。
5. 发布：bump `1.0.0`→`1.1.0`（`backend/pyproject.toml` + `frontend/package.json` 双文件）→ `changeLog.md`→`CHANGELOG.md` 改名 → **停下等用户确认** → `git push` → `gh release create`（双语，中文在前，遵 `Release_Notes_Guidelines.md`）。

resume 协议：`git status --short` → 按上表把每个在飞文件归到 G26（`scripts/**`）或 G28-30（`analysis/`+前端）→ 取该组 fixer 回报或自行重建 fail→pass → **只 stage 该组文件**单独提交，切勿混入另一组或用 `git checkout --`/`stash` 碰 agent 未提交改动。
发布前遗留动作：未跟踪的 `backtest_hshylv/`、`.playwright-mcp/`、根目录 PNG 保持原样（已 gitignore，属用户本地文件，不删）。

---

## Critical 层

### G01 · 美林时钟误判重构（旗舰）· ✅
- findings: A-C1 (`cycle_merrill.py:78,81-91`) + GDP 口径 (`02_compute_derived.py:203,206-207`)
- 症状: +5% 增长被判 "recession"，拖累 composite=-2。根因: gdp 存的是 Q1 单季累计同比 → 4 年滚动趋势被 2021 低基数污染 + 相对阈值 `gdp_yoy>gdp_trend` + 零迟滞。
- 根治: `gdp_trend` 滚动均值改滚动中位数（对基数异常稳健的潜在增速代理）+ 迟滞（0.5pp 死区 + 连续 2 期持续）；`02_compute_derived.py` 保持不动（全年 YoY 不可从库重建，分类器侧稳健化）。
- files: analysis/cycle_merrill.py, backend/tests/test_merrill_phase.py（02_compute_derived.py 经评估不改）
- reviewer: PASS（独立 reviewer 子 Agent：中位数=稳健潜在增速代理、无 look-ahead、window{3-9}均判 recovery、迟滞不粘滞、边界正确；2026 gdp5.0/cpi0.98 recession→recovery、composite −2→0；确认 02 不可重建全年 YoY。残留：growth 轴偏扩张、极少报衰退，非阻断）· commit: 本批次提交 · evidence: test_merrill_phase.py（8 例 passed，改前 6 failed）；全套 85 passed

### G02 · 刷新锁 flock 化（原子锁+真超时+去除只读删锁）· ✅
- findings: F1 (`refresh.py:143-148`,`_pipeline.py:39`) + F2 (`refresh.py:166-187`) + F8 (`refresh.py:39-47`)
- 症状: TOCTOU 竞态 + 超时不可执行 + 只读端点 unlink 运行中的锁 → 生产库损坏。
- 根治: `fcntl.flock(LOCK_EX|LOCK_NB)`（内核退出自动释放，删除陈旧启发式）；`proc.wait(timeout=)` 与输出解耦；CLI(`01_fetch_data.py` main)共享同一锁。新增测试。
- files: backend/app/core/refresh.py, backend/app/core/locking.py(新), scripts/01_fetch_data.py, backend/tests/test_refresh_lock.py
- reviewer: PASS（独立 reviewer 子 Agent：跨进程 flock 互斥 BlockingIOError；静默 sleep 子进程 REFRESH_TIMEOUT_S=2 时 2.00s 被 SIGKILL 回收（旧代码 8s）；is_running 无副作用不 unlink；SSE 进度分数单调；CLI 共享锁 + REFRESH_LOCK_HELD 委托无自锁）· commit: 本批次提交 · evidence: test_refresh_lock.py（5 例 passed）；全套 85 passed

### G03 · 版本化缓存失效 · ✅
- findings: F3 (`cache.py:28`,`db.py:19`) + F14 (`db.py:22`)
- 症状: 缓存失效绑定"调用路径"；CLI/cron 换库或提交后异常 → API 永久返回旧数据。
- 根治: 缓存键纳入 `_db_version()=(mtime_ns,size)`，任何来源换库自动失效；`compute_signals` 同并 + 下游 `classify_*` 缓存按版本变更清理（cycle_*.py 不可改）。新增测试。
- files: backend/app/core/db.py, cache.py, analysis/signals.py, backend/tests/test_cache_version.py
- reviewer: 自测（编排者 live 跑 test_cache_version.py（3 例 passed）；turn-13 checkpoint 已独立观察改前失败 → 构成 fail→pass；提交经 test-gate 二次确认）；独立 reviewer 子 Agent 已派发、判定待回执（并发延迟），若发现 gap 将补修 · commit: 本批次提交 · evidence: fixer 报告全套 98 passed；改前"换库返回旧 [1.0] vs 新 [2.0,3.0]"失败

### G04 · NaN/Inf JSON 安全（SafeJSONResponse）· ✅
- findings: F5 (`crcl.py` 全端点,`real_estate.py:29`,`serial.py:20-25`)
- 症状: NaN/Inf → HTTP 500（实测），坏值持久化进 DB，overview 页持续 500。
- 根治: `default_response_class=SafeJSONResponse`(allow_nan=False + 非有限→null)；`serial` 用 isfinite；落库前清洗。新增测试。
- files: backend/app/main.py, backend/app/core/serial.py, crcl_db.py, backend/tests/test_json_safety.py
- reviewer: PASS（独立 reviewer 子 Agent：SafeJSONResponse 递归 null 化 + 注册 default_response_class；nan 路由 500→200；df/snapshot ±inf/nan→None；真实 crcl_monitor.db checksum 不变；全套 85 passed。残留 upsert_points/SSE 经传输层兜底，判定可延后）· commit: 本批次提交 · evidence: test_json_safety.py 3 passed（改前 3 failed：500 + inf 泄漏 + NaN 持久化）

### G05 · FastAPI 托管 dist + run_app.sh 加固 · ✅
- findings: O-C2 (`run_app.sh:42-47,55,59-65`) + O-H1 (`run_app.sh:22`) + O-M1 (`run_app.sh:24`) + F(static mount)
- 症状: cleanup 链在 set -e 下断裂、kill 不杀孙进程、vite preview 端口静默漂移、就绪失败仍报成功、dist 只在缺失时重建 → 用户看到旧构建。
- 根治: SPA 由 FastAPI 提供（`/assets` 挂载 + 404 兜底回退，优于字面 `StaticFiles(/)`——不 shadow 任何路由）；`run_app.sh` 单进程 uvicorn、指纹重建 dist、`npm ci`、就绪失败 exit1、cleanup set +e；vite `strictPort`。
- files: backend/app/main.py, run_app.sh, frontend/vite.config.ts, backend/tests/test_static_serving.py
- reviewer: PASS（独立 reviewer 子 Agent：live TestClient `/api/未命中`→JSON 404 非 HTML 壳、deep-link→index、`/assets` 命中/缺失正确、路径穿越守护成立；run_app.sh 确单进程无 vite preview、指纹重建、就绪失败 exit1 无假报、cleanup set +e；10 例 passed，另 2 failed 属 G03）· commit: 本批次提交 · evidence: test_static_serving.py（10 例 passed）· 3 项非阻断 follow-up：①fingerprint 未含 build-config(vite/tsconfig/tailwind)②test docstring 仍述旧设计③main.py 注释措辞

### G06 · 健康端点说真话 + 采集非零退出 + 日志 · ✅
- findings: O-C1/B1 (`refresh.py:97`,`sources.py`) + P-H2 (`01_fetch_data.py:1119`)
- 症状: `sources==[]`→green、无新鲜度判据、`01_fetch` 从不非零退出、零日志零告警 → 数据陈旧一个月仍绿灯。
- 根治: `01_fetch_data.py` `compute_exit_code` 汇总退出码（任一表因失败落 kept_previous → exit 2，区别于窗口外跳过）+ `sys.exit(main())`；`sources_health` 空→unknown、加 staleness(40/80d，HEALTH_STALE_DAYS 可配)；stderr + RotatingFile 日志。
- files: backend/app/core/refresh.py, backend/app/schemas/sources.py（+unknown Literal）, scripts/01_fetch_data.py, backend/tests/test_sources_health.py, backend/tests/test_health_truthfulness.py
- reviewer: 编排者复核（读 test_sources_health diff 确认为口径修正非弱化：空→unknown、端点 shape 增 unknown、green 用例改动态新鲜 ts；test-gate 提交前 test_health_truthfulness + test_sources_health 全过）；fixer 报告全套 107 passed。因预算未派独立 reviewer 子 Agent · commit: 本批次提交 · evidence: test_health_truthfulness.py 9 例（改前 empty→green/无 staleness/无 compute_exit_code 失败）· 注意 run_refresh 现对任一失败表报 error（预期"响亮失败"）
- 遗留 follow-up（来自 G03 reviewer）：G03b — `/cycles/{name}`(classify_*) 与 `/real-estate`(_analyze_real_estate_cached) 缓存未纳入版本键，CLI/cron 换库后对这两端点仍可能陈旧，需在 cycle_*.py/real_estate.py 补版本键以完全闭合 F3。

### G07 · 前端图表渲染重构（去响应式代理+停止卸载）· ✅
- findings: FE-C1 (各页 buildXxx 模板表达式 + `ref<Rec[]>`) + FE-H1 (`GraphCard.vue:14-20`)
- 症状: option 在模板构建 + 数据深层响应式 → 全量重建、deep-watch 遍历、notMerge 重建；刷新时 6 图白屏、缩放/图例全丢。
- 根治: `shallowRef`+`markRaw` 数据与 option；builder 移入 `computed`；`GraphCard` 改覆盖层（图表常驻）；`EChart` notMerge:false + lazyUpdate。
- files: frontend/src/pages/*.vue（8）, components/charts/EChart.vue, components/layout/GraphCard.vue
- reviewer: PASS-WITH-FOLLOWUP（独立 reviewer 子 Agent：typecheck 0、10 文件 pattern 一致、notMerge 覆盖经 vue-echarts 源码确认、缩放/图例保留；**发现回归**：象限/散点图 notMerge:false 在相位集收窄时残留 ghost 系列）→ 编排者按处方补 `EChart` `notMerge` prop 并对 quadOpt/clockOpt 置 true，`vue-tsc --noEmit` EXIT=0 复核（运行期视觉未经浏览器确认，逻辑经审）· commit: 本批次提交 · evidence: typecheck EXIT=0；notMerge 覆盖 spread 顺序确认

---

## High 层

### G08 · 变更端点鉴权 + GET 收回 POST · ✅
- findings: F4 (`refresh.py:26/36`,`crcl.py:107/113`,`commentary.py:21`,`main.py:52-62`)
- 根治: 变更语义收回 POST（`create_job`→有界池，返回不可猜 `job_id`）；SSE GET 仅 `get_job` 查表、缺 `job_id`→422；lifespan 生成 `token_urlsafe(32)` 写 `data/.api_token`(0600)，`require_token`(`compare_digest`) 校验，同源 SPA 经 `/api/v1/session` 取用带 `X-API-Token`。
- files: backend/app/core/{auth(new),locking}.py, api/v1/{refresh,crcl,commentary}.py, schemas/refresh.py, main.py, frontend/src/{api/client.ts,stores/refresh.ts}
- reviewer: orchestrator 独立复核（逐读 auth.py + 三路由鉴权装配 + job 注册表同锁收发 + test 差分非弱化）· commit: 见 [Unreleased] item 20 · evidence: `test_mutation_auth.py` 改前 21 failed→24 passed；`test_mutation_auth+test_endpoint_hardening` 48 passed；全套 273 passed；前端 typecheck 退出 0。

### G09 · CRCL 采集单飞+超时 + SQLite WAL · ⬜
- findings: F6 (`crcl.py:107-110`,`crcl_collect.py`) + A-M1 (`db.py:22`,`crcl_db.py:24`)
- 根治: CRCL 复用 flock；第三方阻塞调用隔离进带超时 future；连接工厂统一 `PRAGMA journal_mode=WAL; busy_timeout; synchronous=NORMAL`。
- files: backend/app/api/v1/crcl.py, core/crcl_collect.py, crcl_db.py, db.py
- reviewer: — · commit: — · evidence: —

### G10 · 异步 SSE + 有界线程池 · ⬜
- findings: F7 (`refresh.py:57-73`,`crcl.py:125-141`)
- 根治: SSE 改 `async def`+`asyncio.Queue`（不占 AnyIO 令牌）；实际工作提交到有界 `ThreadPoolExecutor(max_workers=2)`；CRCL worker 加 stop_event。
- files: backend/app/api/v1/{refresh,crcl}.py, core/refresh.py
- reviewer: — · commit: — · evidence: —

### G11 · 管线墙钟超时 + 单表软超时 + 限速 · ⬜
- findings: P-H1 (`01_fetch_data.py:1040`, plist)
- 根治: 外层 `timeout` + 每 fetcher `future.result(timeout=)` + 表间 sleep 限速。
- files: scripts/01_fetch_data.py, scripts/schedule/*
- reviewer: — · commit: — · evidence: —

### G12 · house_price 多粒度完整性闸门 · ⬜
- findings: P-H3 (`01_fetch_data.py:563-595`,`_pipeline.py:141-148`)
- 根治: shrink guard 从 distinct-date 改 distinct-(date,category)；spec 增价格列 required。新增测试。
- files: scripts/01_fetch_data.py, scripts/_pipeline.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G13 · 前端统一异步态（useAsyncData+PageState）· ⬜
- findings: FE-H2 (`Overview.vue:16/48/100-153`) + FE-M6 (`GraphCard.vue:17`,`client.ts` 无重试)
- 根治: 抽 `useAsyncData` + `<PageState>`，从类型上杜绝漏渲染 error；幂等 GET 分类重试；错误文案分类。
- files: frontend/src/composables/useAsyncData.ts(新), components/layout/PageState.vue(新), pages/Overview.vue, api/client.ts
- reviewer: — · commit: — · evidence: —

### G14 · Commentary 轮询生命周期 · ⬜
- findings: FE-H3 (`CommentaryCard.vue:12-40`) + F10 (`commentary.py:169-185`)
- 根治: 前端 setTimeout 链 + 总超时 + 区分瞬时/终态错误 + reqId；后端 busy 由 `_gen_lock.locked()` 派生。
- files: frontend/src/components/layout/CommentaryCard.vue, backend/app/core/commentary.py
- reviewer: — · commit: — · evidence: —

### G15 · CRCL 页接入全局 store + SSE 取消 · ⬜
- findings: FE-H4 (`CrclMonitor.vue:247-278,285`)
- 根治: CRCL 采集状态提升 store 复用 AbortController；路由 meta 声明能力使工具栏自适应；`load()` 随 refreshedAt 重载。
- files: frontend/src/pages/CrclMonitor.vue, stores/refresh.ts, router/index.ts, components/layout/RefreshBar.vue
- reviewer: — · commit: — · evidence: —

### G16 · CI + 夹具库 + 测试收编 + openapi 漂移门禁 · ⬜
- findings: O-H3 + O-H5 + O-H9 + O-H6/FE-M5 + O-H7
- 根治: 一个 GH Actions（ruff+pytest+vue-tsc+`npm ci`+openapi diff）；提交几 KB fixture DB + `conftest.py` 注入 DB_PATH；`scripts/*_test.py` 收编 backend/tests；`gen:api` 从 live app 生成并纳入 build。
- files: .github/workflows/ci.yml(新), backend/tests/conftest.py(新), backend/tests/fixtures/*, frontend/package.json, scripts/*_test.py
- reviewer: — · commit: — · evidence: —

### G17 · Python 依赖锁定 + 单一 venv · ⬜
- findings: O-H2 (`requirements.txt`,`pyproject.toml`)
- 根治: 精确钉 akshare；引入带哈希 lockfile；删除多余 venv 引用（不物理删 .venv，收敛脚本路径）。
- files: requirements.txt, requirements.lock(新), backend/pyproject.toml, run_app.sh
- reviewer: — · commit: — · evidence: —

### G18 · 量化/契约/前端测试补齐 · ⬜
- findings: O-H4 + O-H7 + O-H8
- 根治: analysis/ 各分类器相位表驱动测试；API 契约测试（遍历 OpenAPI GET 做 schema 校验，写操作 mock 子进程）；前端 vitest 测 client.ts + options.ts。
- files: backend/tests/test_analysis_phases.py(新), test_api_contract.py(新), frontend/vitest 配置 + *.spec.ts
- reviewer: — · commit: — · evidence: —

### G19 · 日期参数类型化 → 422 · ✅
- findings: F9 (`db.py:40-47`,`cycles.py:44-48`)
- 根治: schema 层声明 `date | None`，FastAPI 进入处理器前返回 422；删 db.load 的 try/except。
- files: backend/app/api/v1/{data,cycles}.py, core/db.py, backend/tests/test_date_params.py
- reviewer: PASS（独立 reviewer 子 Agent：4 端点 `date|None`（data.py:28/80/94, cycles.py:28）、`db.load` 裸 except 已删、TestClient 非法→422/合法→200 切片(582→12)、全套 77 passed、前端 filters.ts 发 ISO 兼容）· commit: 本批次提交 · evidence: test_date_params.py 6 passed（改前 3 failed：silent 200 全表 + cycles 500）

---

## Medium 层

### G20 · 派生计算口径修正 · ⬜
- findings: P-M1 (`02:130/144/147` asfreq) + P-M2 (`02:129` min_periods) + P-M3 (`01:610`,`02:212-231` look-ahead) + P-M4 (`02:203` 窗口) + P-M6 (`01:1084-1096` 派生失败仍提交)
- 根治: 月频 `asfreq('MS')` 再位移；`min_periods=12`；年度序列时间戳落可得日；确认平滑窗口；派生失败 `discard_staging`。新增测试。
- files: scripts/02_compute_derived.py, 01_fetch_data.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G21 · SQLite 约束+索引+去重 · ⬜
- findings: A-M2 (`01:82`,`02:169/237` to_sql replace) + A-M3 (pmi/lpr 重复日期,`_pipeline.py:117`,`data.py:11`)
- 根治: 建表带 PK/UNIQUE(date[,city])+索引，`INSERT OR REPLACE`；写前去重；`validate()` 增重复日期拒收。新增测试。
- files: scripts/01_fetch_data.py, 02_compute_derived.py, _pipeline.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G22 · 手工 JSON schema 校验 · ✅
- findings: A-M4 (`crcl.py:63-80`,`crcl_alerts.py`)
- 根治: 加载时 pydantic 校验字段类型/日期格式/枚举，失败明确报错并记日志（不再静默透传/伪装"评估异常"）；告警取值前数值化 + `_eval_y_nonreserve_stagnant` 相邻季校验。新增测试。
- files: backend/app/api/v1/crcl.py, backend/app/core/crcl_alerts.py, backend/tests/test_crcl_json_schema.py
- reviewer: 编排者 test-gate（提交前 test_crcl_json_schema.py + test_crcl_alerts.py 全过；G22 仅新增测试、未改既有测试）；因预算未派独立 reviewer 子 Agent（可后补一次读 diff 复核）· commit: 本批次提交 · evidence: test_crcl_json_schema.py 通过；既有 test_crcl_alerts.py 未回归

### G23 · 信号鲁棒性（缺失≠中性 + 跨期对齐 + 迟滞）· ⬜
- findings: A-H1 (`signals.py:112`,`cycle_inventory.py:45`) + A-H2 (`signals.py:112`,`real_estate.py:137`) + A-H3 (`cycle_debt.py:97,111-127`) + A-M5 (`cycle_credit.py:48-54`)
- 根治: composite 聚合前 as-of 对齐、缺失项剔除按可用归一、空表→insufficient_data；债务改净部门方向 + 相对 gdp 阈值；信贷加平滑/死区；房价缺失→中性。新增测试。
- files: analysis/signals.py, cycle_inventory.py, cycle_debt.py, cycle_credit.py, real_estate.py, backend/tests/
- reviewer: — · commit: — · evidence: —
- 注: High 级 finding，因与 G01 同属 analysis 深改、需在 G01 后做以免冲突，故排此处。

### G24 · 后端查询/错误/健壮性中危项 · 🟨（部分：F13-signal_history 已修）
- findings: F11 (`crcl.py:46-60,101-104` keys 校验+LIMIT) + F12 (`refresh.py:186` 错误泄露路径) + F13 (`signal_history.py:39`,`commentary.py:244`,`crcl.py:68` 吞异常)
- 根治: keys 白名单过滤 + `Query(ge,le)`；错误落日志回 error_id + 子进程 env 白名单；只吞 "no such table" 其余上抛。
- 进度: [G24a] `signal_history.read_history` 已改为仅在"表不存在"返回 []、其余（schema 漂移/损坏）冒泡（本批次提交）；**待续**：F11(crcl keys 白名单+LIMIT ge/le)、F12(错误改 error_id + 子进程 env 白名单)、F13 剩余(commentary.py:244 / crcl.py:68 的宽 except)。
- files: backend/app/core/signal_history.py, backend/tests/test_signal_history_errors.py（已）; 待续 backend/app/api/v1/crcl.py, core/{refresh,commentary}.py
- reviewer: 编排者 test-gate（test_signal_history_errors + test_signal_history 13 passed）· commit: 本批次提交（G24a 部分）· evidence: schema 漂移改前静默返回 []、改后冒泡 OperationalError

### G25 · 前端交互/性能中危项 · ⬜
- findings: FE-M1(sampling) M2(去重缓存) M3(signal 取消) M4(countUp 小数) M7(响应式断点) M8(对比度) M9(ChartTip a11y) M10(chunk 兜底) M11(manualChunks)
- 根治: applyTheme 注入 `sampling:'lttb'`；client.ts in-flight 去重+TTL 缓存+外部 signal；useCountUp digits 参数；MetricGrid 断点；text-4 色阶≥4.5:1；ChartTip role=tooltip+aria；router.onError 重载守卫；修 radar chunk。
- files: frontend/src/**（多文件，可拆多 commit）
- reviewer: — · commit: — · evidence: —

### G26 · 管线结构/性能中危项 · ⬜
- findings: P-M7(validate 新鲜度+dtype) P-M8(NIFD 双副本+03 直写 live) P-M9(01 数据驱动重构) P-M10(并发抓取)
- 根治: spec 增 max_date_lag+required；NIFD 抽单一模块，03 走 staging；01 声明式 spec+通用循环（~30% 减行）；fetcher 并发。新增测试。
- files: scripts/01_fetch_data.py, 03_supplement_leverage.py, _pipeline.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G27 · 运维中危项 · ⬜
- findings: O-M2(日志轮转) O-M3(.venv312 硬编码) O-M4(.gitignore 补漏) O-M5(backtest_hshylv 移出) O-M6(README 漂移) O-M7(changeLog→CHANGELOG 改名) O-M8(依赖漏洞扫描)
- 根治: RotatingFileHandler+data/logs；路径收敛 env；.gitignore 补 4 项；移走孤儿目录；README 纠错；`git mv changeLog.md CHANGELOG.md`（两步过大小写）；CI 加 audit。
- files: 多处
- reviewer: — · commit: — · evidence: —

---

## Low 层

### G28 · 后端低危项 · ⬜
- findings: F15(real_estate 缓存键归一) F16(crcl_db 连接关闭+docstring) F17(db.load copy / SELECT* 防御 / crcl.py:31 KeyError / serial 精度 / commentary 常量)
- files: analysis/real_estate.py, backend/app/core/{crcl_db,db,serial,commentary}.py, api/v1/crcl.py

### G29 · 前端低危项 · 🟨 部分
- findings: FE-L1(时区 off-by-one filters.ts:17) L2(refresh.ts done 缺失) L3(Sidebar computed/render) L4(Overview 死代码) L5(PALETTE TDZ) L6(num truthy 0 bug) L7(any 消除) L8(Date 解析缓存) L9(li tabindex) L10(focus-visible)
- files: frontend/src/**
- 已确认修复：FE-L3/L5/L7/L8（`740899f`，G28-30 批次）；FE-L1 时区 off-by-one 与 router.onError 已在 G25(`6f2a99c`) 提及。
- **需复核（resume 时逐项确认是否已在 G25/M3 覆盖，未覆盖则补修）**：FE-L2(refresh.ts done)、FE-L4(Overview 死代码)、FE-L6(num truthy 0)、FE-L9(li tabindex)、FE-L10(focus-visible)。

### G30 · 分析/管线低危项 · 🟨 部分
- findings: A-L2(cross_indicator in-sample/abs) A-L3(SELECT*) A-L4(lru_cache mutable) + P-L(TLS verify=False / dfs[1] 位置式 / 双备份拷贝 / 未用 import / plist expat 路径)
- files: analysis/cross_indicator.py, backend/app/core/db.py, scripts/01_fetch_data.py, _pipeline.py, schedule/*
- 已确认修复：A-L2（`740899f`）。
- **需复核（resume）**：A-L3(SELECT*)、A-L4(lru_cache mutable) 是否随 G03b/G23 缓存版本键一并处理；P-L 各项（TLS verify=False、dfs[1] 位置式、双备份拷贝、未用 import、plist expat 路径）多在 `scripts/`，应在 **G26 提交时**核对是否覆盖，未覆盖则补一条低危提交。

---

## 发布（全部 ✅ 后）
- [ ] 全量 pytest 绿（无回归 + 新量化/契约测试）
- [ ] `npm run typecheck` 0 error；app 启动，/health、/signals、/crcl/overview、/derived/monthly 返回合法 JSON（无 NaN/500）
- [ ] 账本 100% done；changeLog 更新
- [ ] bump v1.1.0（backend/pyproject.toml + frontend/package.json）
- [ ] ⏸️ 用户确认 → `git push` main
- [ ] ⏸️ 用户确认 → `gh release create v1.1.0`（双语 notes 依 Release_Notes_Guidelines.md）
