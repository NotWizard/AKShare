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

---

## Critical 层

### G01 · 美林时钟误判重构（旗舰）· ✅
- findings: A-C1 (`cycle_merrill.py:78,81-91`) + GDP 口径 (`02_compute_derived.py:203,206-207`)
- 症状: +5% 增长被判 "recession"，拖累 composite=-2。根因: gdp 存的是 Q1 单季累计同比 → 4 年滚动趋势被 2021 低基数污染 + 相对阈值 `gdp_yoy>gdp_trend` + 零迟滞。
- 根治: `gdp_trend` 滚动均值改滚动中位数（对基数异常稳健的潜在增速代理）+ 迟滞（0.5pp 死区 + 连续 2 期持续）；`02_compute_derived.py` 保持不动（全年 YoY 不可从库重建，分类器侧稳健化）。
- files: analysis/cycle_merrill.py, backend/tests/test_merrill_phase.py（02_compute_derived.py 经评估不改）
- reviewer: PASS（独立 reviewer 子 Agent：中位数=稳健潜在增速代理、无 look-ahead、window{3-9}均判 recovery、迟滞不粘滞、边界正确；2026 gdp5.0/cpi0.98 recession→recovery、composite −2→0；确认 02 不可重建全年 YoY。残留：growth 轴偏扩张、极少报衰退，非阻断）· commit: 本批次提交 · evidence: test_merrill_phase.py（8 例 passed，改前 6 failed）；全套 85 passed

### G02 · 刷新锁 flock 化（原子锁+真超时+去除只读删锁）· ⬜
- findings: F1 (`refresh.py:143-148`,`_pipeline.py:39`) + F2 (`refresh.py:166-187`) + F8 (`refresh.py:39-47`)
- 症状: TOCTOU 竞态 + 超时不可执行 + 只读端点 unlink 运行中的锁 → 生产库损坏。
- 根治: `fcntl.flock(LOCK_EX|LOCK_NB)`（内核退出自动释放，删除陈旧启发式）；`proc.wait(timeout=)` 与输出解耦；CLI(`01_fetch_data.py` main)共享同一锁。新增测试。
- files: backend/app/core/refresh.py, scripts/01_fetch_data.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G03 · 版本化缓存失效 · ⬜
- findings: F3 (`cache.py:28`,`db.py:19`) + F14 (`db.py:22`)
- 症状: 缓存失效绑定"调用路径"；CLI/cron 换库或提交后异常 → API 永久返回旧数据。
- 根治: 缓存键纳入 `_db_version()=(mtime_ns,size)`，任何来源换库自动失效；`analysis/*` 的 db_path 键同并。新增测试。
- files: backend/app/core/cache.py, db.py, analysis/signals.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G04 · NaN/Inf JSON 安全（SafeJSONResponse）· ✅
- findings: F5 (`crcl.py` 全端点,`real_estate.py:29`,`serial.py:20-25`)
- 症状: NaN/Inf → HTTP 500（实测），坏值持久化进 DB，overview 页持续 500。
- 根治: `default_response_class=SafeJSONResponse`(allow_nan=False + 非有限→null)；`serial` 用 isfinite；落库前清洗。新增测试。
- files: backend/app/main.py, backend/app/core/serial.py, crcl_db.py, backend/tests/test_json_safety.py
- reviewer: PASS（独立 reviewer 子 Agent：SafeJSONResponse 递归 null 化 + 注册 default_response_class；nan 路由 500→200；df/snapshot ±inf/nan→None；真实 crcl_monitor.db checksum 不变；全套 85 passed。残留 upsert_points/SSE 经传输层兜底，判定可延后）· commit: 本批次提交 · evidence: test_json_safety.py 3 passed（改前 3 failed：500 + inf 泄漏 + NaN 持久化）

### G05 · FastAPI 托管 dist + run_app.sh 加固 · ⬜
- findings: O-C2 (`run_app.sh:42-47,55,59-65`) + O-H1 (`run_app.sh:22`) + O-M1 (`run_app.sh:24`) + F(static mount)
- 症状: cleanup 链在 set -e 下断裂、kill 不杀孙进程、vite preview 端口静默漂移、就绪失败仍报成功、dist 只在缺失时重建 → 用户看到旧构建。
- 根治: `StaticFiles` 挂 dist（单进程单端口，移除 vite preview）；cleanup 用进程组；vite `strictPort`；就绪超时 exit 1；`npm ci`；dist 按指纹重建。
- files: backend/app/main.py, run_app.sh, frontend/vite.config.ts
- reviewer: — · commit: — · evidence: —

### G06 · 健康端点说真话 + 采集非零退出 + 日志 · ⬜
- findings: O-C1/B1 (`refresh.py:97`,`sources.py`) + P-H2 (`01_fetch_data.py:1119`)
- 症状: `sources==[]`→green、无新鲜度判据、`01_fetch` 从不非零退出、零日志零告警 → 数据陈旧一个月仍绿灯。
- 根治: 采集脚本汇总退出码（任一表失败/kept_previous→非零）；`sources_health` 加 staleness 判据、`sources==[]`→unknown(灰)；引入 logging + 可插拔 notifier。新增测试。
- files: scripts/01_fetch_data.py, backend/app/api/v1/sources.py, backend/app/core/refresh.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G07 · 前端图表渲染重构（去响应式代理+停止卸载）· ⬜
- findings: FE-C1 (各页 buildXxx 模板表达式 + `ref<Rec[]>`) + FE-H1 (`GraphCard.vue:14-20`)
- 症状: option 在模板构建 + 数据深层响应式 → 全量重建、deep-watch 遍历、notMerge 重建；刷新时 6 图白屏、缩放/图例全丢。
- 根治: `shallowRef`+`markRaw` 数据与 option；builder 移入 `computed`；`GraphCard` 改覆盖层（图表常驻）；`EChart` notMerge:false。
- files: frontend/src/pages/*.vue, components/charts/EChart.vue, components/layout/GraphCard.vue
- reviewer: — · commit: — · evidence: —

---

## High 层

### G08 · 变更端点鉴权 + GET 收回 POST · ⬜
- findings: F4 (`refresh.py:26/36`,`crcl.py:107/113`,`commentary.py:21`,`main.py:52-62`)
- 根治: 变更语义收回 POST；进程启动生成随机 token 写 `data/.api_token`，中间件校验；前端同源取用。
- files: backend/app/main.py, api/v1/{refresh,crcl,commentary}.py, frontend/src/api/client.ts
- reviewer: — · commit: — · evidence: —

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

### G22 · 手工 JSON schema 校验 · ⬜
- findings: A-M4 (`crcl.py:63-80`,`crcl_alerts.py`)
- 根治: 加载时 pydantic/jsonschema 校验字段类型/日期格式/枚举，失败定位到字段；告警取值前数值化 + 相邻季校验。新增测试。
- files: backend/app/api/v1/crcl.py, core/crcl_alerts.py, backend/tests/
- reviewer: — · commit: — · evidence: —

### G23 · 信号鲁棒性（缺失≠中性 + 跨期对齐 + 迟滞）· ⬜
- findings: A-H1 (`signals.py:112`,`cycle_inventory.py:45`) + A-H2 (`signals.py:112`,`real_estate.py:137`) + A-H3 (`cycle_debt.py:97,111-127`) + A-M5 (`cycle_credit.py:48-54`)
- 根治: composite 聚合前 as-of 对齐、缺失项剔除按可用归一、空表→insufficient_data；债务改净部门方向 + 相对 gdp 阈值；信贷加平滑/死区；房价缺失→中性。新增测试。
- files: analysis/signals.py, cycle_inventory.py, cycle_debt.py, cycle_credit.py, real_estate.py, backend/tests/
- reviewer: — · commit: — · evidence: —
- 注: High 级 finding，因与 G01 同属 analysis 深改、需在 G01 后做以免冲突，故排此处。

### G24 · 后端查询/错误/健壮性中危项 · ⬜
- findings: F11 (`crcl.py:46-60,101-104` keys 校验+LIMIT) + F12 (`refresh.py:186` 错误泄露路径) + F13 (`signal_history.py:39`,`commentary.py:244`,`crcl.py:68` 吞异常)
- 根治: keys 白名单过滤 + `Query(ge,le)`；错误落日志回 error_id + 子进程 env 白名单；只吞 "no such table" 其余上抛。
- files: backend/app/api/v1/crcl.py, core/{refresh,signal_history,commentary}.py
- reviewer: — · commit: — · evidence: —

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

### G29 · 前端低危项 · ⬜
- findings: FE-L1(时区 off-by-one filters.ts:17) L2(refresh.ts done 缺失) L3(Sidebar computed/render) L4(Overview 死代码) L5(PALETTE TDZ) L6(num truthy 0 bug) L7(any 消除) L8(Date 解析缓存) L9(li tabindex) L10(focus-visible)
- files: frontend/src/**

### G30 · 分析/管线低危项 · ⬜
- findings: A-L2(cross_indicator in-sample/abs) A-L3(SELECT*) A-L4(lru_cache mutable) + P-L(TLS verify=False / dfs[1] 位置式 / 双备份拷贝 / 未用 import / plist expat 路径)
- files: analysis/cross_indicator.py, backend/app/core/db.py, scripts/01_fetch_data.py, _pipeline.py, schedule/*

---

## 发布（全部 ✅ 后）
- [ ] 全量 pytest 绿（无回归 + 新量化/契约测试）
- [ ] `npm run typecheck` 0 error；app 启动，/health、/signals、/crcl/overview、/derived/monthly 返回合法 JSON（无 NaN/500）
- [ ] 账本 100% done；changeLog 更新
- [ ] bump v1.1.0（backend/pyproject.toml + frontend/package.json）
- [ ] ⏸️ 用户确认 → `git push` main
- [ ] ⏸️ 用户确认 → `gh release create v1.1.0`（双语 notes 依 Release_Notes_Guidelines.md）
