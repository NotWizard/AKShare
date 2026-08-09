# M1 设计文档 — 数据源健康探针 + 发布日历增量抓取 + 可选 launchd 调度

> 分支：worktree-macro-roadmap-m123 ｜ 日期：2026-08-09
> 范围纪律：M1 只做三件事——①数据源健康探针+看板健康灯 ②发布日历驱动增量抓取 ③可选 launchd 调度。
> **不做**：AI 评论激活策略、PE/估值指标、回测、信号历史表。
> 约束：零新依赖（requirements.txt / package.json 不动）；复用现有模式与令牌。

## 0. 数据流总览

```
01_fetch_data.py（--full 或 增量）
  ├─ should_fetch(table, today)          ← scripts/release_calendar.py（纯函数）
  ├─ 每个 fetcher：计时 + ok/error       → _MANIFEST["sources"]（新）
  │    consecutive_failures = 读上次 last_run.json 递增/清零
  └─ write_manifest() → data/last_run.json（tables 行为不变，新增 sources 键）
        │
backend GET /api/v1/sources/health（只读 manifest，纯函数推导）
        │
frontend RefreshBar → HealthLight.vue（健康灯 + popover + 全量刷新次按钮）
```

关键原则：**健康状态不落任何新存储**——last_run.json 是唯一事实源，后端在请求时
用纯函数推导红黄绿。无 manifest 时返回 green + updated_at=null，前端画灰点。

---

## 1. manifest.sources schema

`_MANIFEST`（scripts/01_fetch_data.py）新增顶层键 `sources`，为 **14 个 fetcher 的有序列表**
（顺序 = main() 里 fetchers 列表顺序），每项：

```jsonc
{
  "table": "cpi",                  // 表名（= fetcher 名去 fetch_ 前缀）
  "channel": "eastmoney",          // 数据通道短名，来自 release_calendar.TABLE_CALENDAR
  "ok": true,                      // fetcher 未抛异常（main 循环 try/except 口径）
  "elapsed_s": 1.23,               // fetcher 耗时，round(…, 2)
  "error": null,                   // 异常时 "ExceptionType: msg"，截断 200 字符防膨胀
  "consecutive_failures": 0,       // 见下
  "last_success": "2026-08-09T18:07:20"  // 最近一次 ok=true 运行的 ts；从未成功为 null
}
```

### consecutive_failures 递增/清零规则

运行开始时读上一次 `data/last_run.json`（任何读取失败视为空，模式同
`core/refresh.read_manifest_summary`）：

- 本次该表**被抓取**且 `ok=true` → `consecutive_failures = 0`，`last_success = 本次 ts`。
- 本次该表**被抓取**且 `ok=false` → `consecutive_failures = 上次值 + 1`（上次缺省 0），`last_success` 沿用上次。
- 本次该表**未被抓取**（增量窗口外）→ 整条沿用上次（不增不减，last_success 保持真实）。
- 旧格式 manifest（无 sources 键）→ 计数器从 0 起步，无需迁移。

### ok 的口径（重要决策）

`ok` **仅表示 fetcher 是否抛异常**，不表示数据是否入库。验证闸门拒收
（kept_previous）走第 2 节的 divergence 通道。原因：cpi/ppi/social_finance/lpr/
new_credit/household_income/demographics 等 fetcher 内部吞异常返回空 df，
这类"静默陈旧"应显示为黄色 divergence（popover 可见 reason），而不是与
"源彻底挂了"的红色混为一谈。持续静默陈旧的根治是 M2 双源的事。

`tables` 键行为**完全不变**：只记录本次实际抓取的表（updated / kept_previous）。

---

## 2. 健康规则（后端纯函数）

对每源先挂 `warning`：本次 `tables[table].status == "kept_previous"` →
`warning = "kept previous — " + reason`（验证闸门拒收 = 新数据与旧好数据分歧）。

```
red    ：任一源 consecutive_failures ≥ 2
yellow ：（非 red 时）任一源 consecutive_failures == 1，或任一源 warning 非空
green  ：其余
```

无 manifest / sources 为空 → `status="green", updated_at=null, sources=[]`
（前端对 updated_at=null 画灰点，语义为"尚无运行记录"）。

---

## 3. 后端契约 GET /api/v1/sources/health

**路由**：新建 `backend/app/api/v1/sources.py`（`prefix="/sources", tags=["sources"]`，
风格同 refresh/cycles 等既有路由），注册进 `api/v1/__init__.py`。
**实现**：纯函数 `sources_health(manifest: dict) -> dict` + 读文件的
`read_sources_health()`（永不抛异常），放在 `backend/app/core/refresh.py`
（该文件已持有 MANIFEST_PATH 与 manifest 解析，避免新 core 文件）。
**无缓存**：文件很小，每次请求直读。

```jsonc
// 200 响应示例
{
  "status": "yellow",
  "updated_at": "2026-08-09T18:07:20",     // manifest.ts
  "sources": [
    {
      "table": "cpi", "channel": "eastmoney", "ok": true,
      "elapsed_s": 1.2, "error": null,
      "consecutive_failures": 0,
      "last_success": "2026-08-09T18:07:20",
      "warning": "kept previous — empty result"
    }
    // …共 14 条
  ]
}
```

**Pydantic**（新建 `backend/app/schemas/sources.py`）：

```python
class SourceHealth(BaseModel):
    table: str
    channel: str
    ok: bool
    elapsed_s: float | None = None
    error: str | None = None
    consecutive_failures: int = 0
    last_success: str | None = None
    warning: str | None = None

class SourcesHealth(BaseModel):
    status: Literal["green", "yellow", "red"]
    updated_at: str | None = None
    sources: list[SourceHealth] = []
```

**测试**：新建 `backend/tests/test_sources_health.py`（pytest 已配置，
风格同 test_golden.py）：纯函数红/黄/绿/沿用/无 manifest 用例 + 一个
TestClient 形状测试。

---

## 4. 前端健康灯

### 位置

RefreshBar（sticky 顶栏）内：日期预设分隔线之后、`🔄 刷新数据` 按钮之前，
一个小圆点按钮。新组件 `frontend/src/components/layout/HealthLight.vue`
（RefreshBar 已 50 行，popover 逻辑不塞进去）。

### 视觉（只用现有令牌）

| 状态 | 颜色 |
|---|---|
| green | `bg-up`（--up #10b981）|
| yellow | `bg-warn`（--warn #f59e0b）|
| red | `bg-down`（--down #ef4444）+ 细环 |
| unknown（updated_at=null）| 灰（text-3 系）|

圆点 ~8px 圆形；触发按钮复用 RefreshBar 既有 focus-visible outline 类。

### Popover 内容

- 头部：`数据源健康` + updated_at。
- 每源一行：表名（mono）｜通道短名｜最后成功时间（或"从未成功"）｜
  状态符号：✓（up）/ warning reason（warn）/ error（down，截断显示，title 挂全文）。
- 尾部：**「全量刷新」次按钮**（描边样式，同现有"取消"按钮）→ `refresh.stream(true)`；
  一行小字提示"增量刷新按发布日历自动跳过窗口外的表"。

### a11y

- 圆点 span：`role="status"` + `aria-label="数据源健康：绿/黄/红（N 个源异常）"`
  （role=status 隐含 aria-live=polite，状态变化自动播报）。
- 触发器为 `<button>`：键盘天然可达（Tab 聚焦、Enter/Space 开合），
  `aria-haspopup="dialog"` + `:aria-expanded`。
- Popover：`role="dialog" aria-label="数据源健康详情"`；打开时焦点移入，
  Esc 关闭并把焦点还给触发器；点击外部关闭——用已安装的
  `@vueuse/core` 的 `onClickOutside`（零新依赖）。

### 数据接入

`stores/refresh.ts` 增加 `health: ref<SourcesHealth|null>` 与 `loadHealth()`
（失败静默 → health=null → 灰点）。调用时机：HealthLight onMounted；
SSE done 后（manifest 已变）；`loadStatus()` 内顺带。
`api/client.ts` 增加 `getSourcesHealth()`；`types.ts` 增加
`SourceHealth` / `SourcesHealth` 接口（手写镜像 Pydantic，同现有注释约定）。

---

## 5. release_calendar 设计（新建 scripts/release_calendar.py）

单一数据字典 `TABLE_CALENDAR`（每表：kind / months / days 窗口 / channel / 依据注释），
加纯函数 `should_fetch`。**零依赖**（datetime 标准库）。

```python
def should_fetch(table: str, today: datetime.date, force: bool = False) -> bool:
    meta = TABLE_CALENDAR.get(table)
    if force or meta is None or meta["kind"] == "market":
        return True                    # 未知表 fail-open：新表永不被日历静默饿死
    if today.month not in meta["months"]:
        return False
    return any(lo <= today.day <= hi for lo, hi in meta["days"])
```

### 逐表判定（14 表，覆盖 main() fetchers 全集）

| 表 | kind | 月份 | 日窗口 | channel | 依据 |
|---|---|---|---|---|---|
| money_supply | release | 全月 | 9–17 | pbc-akshare | 央行上月金融统计数据约每月 10–15 日发布；春节月偏移，窗口放宽自 9 日 |
| gdp | release | 1,4,7,10 | 10–22 | nbs-akshare | NBS 季度 GDP 初值于季后月 15–18 日左右发布 |
| cpi | release | 全月 | 8–12 | eastmoney | NBS 每月 9 日左右发布 CPI；东财数据中心镜像同步 |
| ppi | release | 全月 | 8–12 | eastmoney | 与 CPI 同日发布 |
| pmi | release | 全月 | 1–5 及 25–31 | nbs-akshare | 官方 PMI 当月最后一天、财新次月首个工作日，跨月 → 双窗口 |
| leverage | release | 1,4,7,10 | 10–31 | cnbs-akshare | NIFD 季报约季后月 20–30 日；CNBS 经 AKShare 滞后 1–2 年且不定期 → 宽窗口兜底 |
| social_finance | release | 全月 | 9–17 | pbc-akshare | 央行社融初值与金融统计同批（每月 10–15 日） |
| lpr | release | 全月 | 19–22 | pbc-akshare | LPR 每月 20 日公布，遇节假日顺延 |
| industrial | release | 全月 | 12–20 | nbs-akshare | NBS 规上工业增加值每月 15–16 日；**1–2 月合并值 3 月中旬发布**，窗口天然覆盖 |
| house_price | release | 全月 | 12–20 | nbs-akshare | NBS 70 城房价每月 15–18 日；1、2 月照常单独发布 |
| household_income | release | 1–3 | 1–31 | nbs-akshare | NBS 年度数据/公报一季度发布；源现被 NBS WAF 封锁（data-sources-guide §十一），窗口按真实节奏保留，失败经探针可见 |
| new_credit | release | 全月 | 9–17 | pbc-akshare | 新增人民币贷款与社融同批金融统计数据 |
| bond_yield | **market** | — | — | chinabond | 中债信息网收益率曲线为**日频市场数据，永远抓** |
| demographics | release | 9,10 | 1–31 | worldbank | World Bank WDI 年度指标约每年 9–10 月更新一次 |

**1–2 月合并发布注记**：NBS 对规上工业增加值等指标因春节扰动合并发布 1–2 月值
（3 月中旬公布）；CPI/PPI/70 城房价 1、2 月照常按月发布；央行金融统计春节月
（1–2 月）发布时间可能偏移，故窗口起点放到 9 日。窗口宁宽勿窄：误报成本是一次
廉价抓取（验证闸门兜底），漏报成本是数据陈旧。

### 离线自检

新建 `scripts/release_calendar_test.py`（风格同 `scripts/_pipeline_test.py`：
check() + 非零退出码，`.venv312/bin/python scripts/release_calendar_test.py` 运行）：
lpr 20 日 True / 23 日 False；pmi 1 月 2 日 True、1 月 15 日 False；
bond_yield 恒 True；force 恒 True；gdp 2 月 False；industrial 3 月 15 日 True；
未知表 True；TABLE_CALENDAR 键集 ⊇ 14 表名校验。

---

## 6. --full 接线

### scripts/01_fetch_data.py

- `main()` 加 argparse `--full`。
- 计划：`selected = [(name, f) for f in fetchers if should_fetch(name, date.today(), args.full)]`。
- 打印计划行（供后端进度解析）：`📋 计划抓取 {K}/{N} 表（全量|增量）`。
- **K == 0**：打印"窗口内无表，跳过"，直接 return 0——不 backup、不开 staging、
  不写 manifest（什么都没变）。
- 循环内对每个 fetcher 计时 + 记 sources（第 1 节规则）；`write_manifest` 时带上 sources。
- 导入：`from release_calendar import should_fetch`（沿用文件顶部已有的 sys.path insert）。

### backend

- `core/refresh.py` `run_refresh(progress_cb, stop_event, full=False)`：
  `full=True` 时子进程命令追加 `--full`。
  进度：初始 `expected = EXPECTED_FETCH_STEPS`；stdout 出现
  `计划抓取 (\d+)/` 时更新 `expected = K + 2`（derived_monthly / derived_quarterly
  两条 ✅；顺带修正存量计数 15 已过时的问题），保留 `min(done, expected)` 钳制。
- `api/v1/refresh.py`：`POST ""` 与 `GET /stream` 各加查询参数 `full: bool = False`
  （GET 无 body；POST 也用查询参数，两处一致），透传 `run_refresh`。
  RefreshResult schema 不变。

### frontend

- `stores/refresh.ts` `stream(full = false)`：URL 追加 `?full=1`；done 后 `loadHealth()`。
- `client.ts` `triggerRefresh(full?)` 同步加 `?full=1`（保持 client 完整；实际页面走 stream）。
- HealthLight popover「全量刷新」次按钮 → `refresh.stream(true)`。

---

## 7. 可选调度（launchd，默认不安装）

新建 `scripts/schedule/` 三件套：

### com.macro.refresh.plist（模板，占位符 `__PROJECT_ROOT__` / `__PYTHON__`）

```xml
<key>Label</key><string>com.macro.refresh</string>
<key>ProgramArguments</key>
<array>
  <string>__PYTHON__</string>
  <string>__PROJECT_ROOT__/scripts/01_fetch_data.py</string>
</array>
<key>WorkingDirectory</key><string>__PROJECT_ROOT__</string>
<key>StartCalendarInterval</key>
<dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>7</integer></dict>
<key>EnvironmentVariables</key>
<dict><key>DYLD_LIBRARY_PATH</key><string>/opt/homebrew/opt/expat/lib</string></dict>
<key>StandardOutPath</key><string>__PROJECT_ROOT__/data/refresh_schedule.log</string>
<key>StandardErrorPath</key><string>__PROJECT_ROOT__/data/refresh_schedule.log</string>
```

- 每日 **10:07**：晚于 NBS 09:30 晨间发布；窗口外日期因日历过滤近乎空转
  （读 manifest 即提前返回），成本可忽略。
- `DYLD_LIBRARY_PATH` 与 run_app.sh / core/refresh._subprocess_env 保持一致（expat）。

### schedule_install.sh / schedule_uninstall.sh（set -e，chmod +x）

- install：`sed` 替换占位符（PROJECT_ROOT=脚本所在 ../..，PYTHON=.venv312/bin/python）
  → 写入 `~/Library/LaunchAgents/com.macro.refresh.plist`（已存在先 bootout 保证幂等）
  → `launchctl bootstrap gui/$(id -u) <plist>`。
- uninstall：`launchctl bootout gui/$(id -u)/com.macro.refresh` + 删除 plist。
- **默认不安装**：README 说明由用户显式执行。

### README.md 一小节

在「数据流水线」章节后追加「定时刷新（可选，launchd）」：安装/卸载一行命令、
每日 10:07 触发、日历过滤说明、日志路径。

---

## 8. 验收标准 + 精确改动文件清单

### 验收标准

1. **sources schema**：运行 `01_fetch_data.py` 后 `last_run.json` 含 sources 列表
   （14 条、字段齐全）；某 fetcher 连续 2 次异常 → 该源 consecutive_failures=2；
   恢复一次 → 归零且 last_success 更新；增量跳过的表整条沿用；旧格式 manifest 无报错。
2. **健康规则**：`test_sources_health.py` 全绿——2 连败 → red；1 败或任一
   kept_previous warning → yellow；其余 → green；无 manifest → green + updated_at=null。
3. **健康端点**：`GET /api/v1/sources/health` 恒 200，形状 = SourcesHealth；
   OpenAPI 中可见；无新依赖。
4. **健康灯**：RefreshBar 显示圆点；颜色仅取 up/warn/down 令牌；popover 列出 14 源
   （表名/通道/最后成功时间/错误）；Tab 可达、Enter/Space 开、Esc 关、焦点归还；
   role=status 的 aria-label 随状态变化播报。
5. **发布日历**：`release_calendar_test.py` 全过；`should_fetch` 对 14 表判定与第 5 节
   表一致（示例：2026-08-09 增量 = money_supply、cpi、ppi、social_finance、
   new_credit、bond_yield 六表——9–17 窗口含 9 日）；`--full` 恒 14 表。
6. **接线**：`POST /api/v1/refresh?full=1` 与 `GET /refresh/stream?full=1` 子进程
   命令含 `--full`（stdout 计划行可证）；增量模式进度条到 100%（expected 自适应）；
   窗口内零表时脚本提前退出且不触碰 DB/manifest；popover 全量刷新按钮走 full 流。
7. **调度**：install 后 `launchctl print gui/$(id -u)/com.macro.refresh` 可见且
   10:07 触发一次真实运行（日志落 data/refresh_schedule.log）；uninstall 后无残留；
   默认状态无任何 LaunchAgent 被安装；README 小节存在。
8. **卫生**：changeLog.md 的 [Unreleased] 同步更新；shared/openapi.json 重新导出；
   requirements.txt / package.json 零变化；无范围外改动
   （commentary/analysis/signals 代码零触碰）。

### 改动文件清单

**新增（10）**
- `docs/plans/M1-design.md`（本文档）
- `scripts/release_calendar.py`
- `scripts/release_calendar_test.py`
- `backend/app/schemas/sources.py`
- `backend/app/api/v1/sources.py`
- `backend/tests/test_sources_health.py`
- `frontend/src/components/layout/HealthLight.vue`
- `scripts/schedule/com.macro.refresh.plist`
- `scripts/schedule/schedule_install.sh`
- `scripts/schedule/schedule_uninstall.sh`

**修改（11）**
- `scripts/01_fetch_data.py`（--full、sources 记录、计划行、空计划提前返回）
- `backend/app/core/refresh.py`（sources_health 纯函数、run_refresh(full)、进度解析）
- `backend/app/api/v1/refresh.py`（POST/stream 加 full 查询参数）
- `backend/app/api/v1/__init__.py`（注册 sources 路由）
- `frontend/src/api/types.ts`（SourceHealth/SourcesHealth）
- `frontend/src/api/client.ts`（getSourcesHealth、triggerRefresh(full)）
- `frontend/src/stores/refresh.ts`（health/loadHealth、stream(full)）
- `frontend/src/components/layout/RefreshBar.vue`(挂载 HealthLight)
- `README.md`（定时刷新小节）
- `changeLog.md`（[Unreleased] 条目）
- `shared/openapi.json`（后端改动后重新导出：
  `.venv312/bin/python -c "import json; from backend.app.main import app; open('shared/openapi.json','w').write(json.dumps(app.openapi(), ensure_ascii=False, indent=2))"`）

**明确不动**：`backend/app/core/commentary.py`、`analysis/`、signals/cycles 相关、
`requirements.txt`、`frontend/package.json`、`tailwind.config.ts`、`tokens.css`。
