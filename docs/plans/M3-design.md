# M3 设计文档 — signal_history 快照表 + Overview 相位翻转高亮

> 分支：worktree-macro-roadmap-m123 ｜ 日期：2026-08-09
> 范围纪律：M3 只做一件事的两半——⑧signal_history 表（每次成功刷新落一条 composite+四相位快照）+ 前端翻转高亮。
> **不做**：回测、AI 周报、事件注记、PE/估值、健康灯/日历/vintage/双源逻辑再改动。
> 约束：零新依赖（requirements.txt / package.json 不动）；复用现有模式（commentary 表先例 / phaseLabel / tokens / 卡片模式）。

## 0. 现状要点（读取结论，约束设计的既有事实）

- `analysis/signals.py compute_signals(db_path)`（lru_cache by db_path）返回
  `composite_score: int [-4,+4]` + 四框架 dict，各自含 `phase`（debt 为 `overall_phase` 取值）。
  脚本进程内首次调用必读新库，无陈旧缓存问题。
- `scripts/01_fetch_data.py main()` 顺序：backup → open_staging → fetchers（闸门 save_to_db）
  → run_derived → `commit_staging()`（原子提升）→ `write_manifest(_MANIFEST)`。
  **增量空计划提前返回**在 `if not selected: return 0`（未开 staging、未提交）。
- `backend/app/core/refresh.py` 以子进程跑 01_fetch，stdout 两处正则：
  `计划抓取 (\d+)/` 与 `"✅" in line` 计进度——**M3 新增日志行不得含 ✅**。
  子进程成功后 `clear_all_caches()`（已含 `_load_full` 与 `compute_signals`）。
- commentary 先例（`backend/app/core/commentary.py`）：业务表直接落在 live `macro_data.db`，
  `CREATE TABLE IF NOT EXISTS` + append；`data_as_of` = `derived_monthly` MAX(date) 取 `YYYY-MM`。
- `MANIFEST_PATH` 在 `_pipeline.py` 与 `refresh.py` 各自定义（跨进程常量复制先例）→
  `signal_history` 表名/DDL 在 scripts 与 backend 各持一份，不做跨包共享模块。
- 前端已有 `design/phases.ts`（`phaseLabel`/`phaseColor`）、tokens（`warn/up/down/card/border`）、
  MetricTile/CommentaryCard 卡片类。PHASE_LABELS 缺 4 个 debt 相位（leveraging_boom/
  stable_growth/leveraging_bust/stable_contraction），现状 DebtCycle 直出英文原值。

---

## 1. signal_history 表 + 写入点

### 1.1 表结构（live `macro_data.db` 内，append-only）

```sql
CREATE TABLE IF NOT EXISTS signal_history (
    ts         TEXT NOT NULL,   -- ISO 秒级，复用本次运行 manifest 的 ts（行↔manifest 一一对应）
    data_as_of TEXT,            -- YYYY-MM，derived_monthly MAX(date)（与 commentary 同口径）；可空
    composite  INTEGER NOT NULL,-- [-4,+4]
    merrill    TEXT,            -- 阶段字符串，可空
    credit     TEXT,
    inventory  TEXT,
    debt       TEXT
)
```

- 无主键/无 UNIQUE：append-only，重复成功提交各落一行（测试口径「跑两次落两行」即此语义）。
- **不进 `TABLE_SPECS`**（不经 staging 闸门、不被 validate 管）：它是提交**后**的派生快照，
  不存在"坏数据覆盖好数据"路径；写入失败只告警。
- 加入 `/table` 白名单（§2.4）供可选浏览。

### 1.2 scripts/signal_history.py（新，~30 行）

```python
"""Append-only signal history — one row per successful pipeline commit."""
import sqlite3

from analysis.signals import compute_signals   # analysis 自带 sys.path 注入，scripts 内可直导

TABLE = "signal_history"
_CREATE = """CREATE TABLE IF NOT EXISTS signal_history (
    ts TEXT NOT NULL, data_as_of TEXT, composite INTEGER NOT NULL,
    merrill TEXT, credit TEXT, inventory TEXT, debt TEXT)"""


def append_signal_history(db_path, ts):
    """成功提交后追加一行 composite+四相位快照。抛异常由调用方告警兜底。"""
    sig = compute_signals(str(db_path))          # 提交后的新库
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE)
        try:  # data_as_of 口径同 commentary._latest_data_date
            row = conn.execute("SELECT MAX(date) FROM derived_monthly").fetchone()
            data_as_of = str(row[0])[:7] if row and row[0] else None
        except sqlite3.Error:
            data_as_of = None
        conn.execute(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?)",
            (ts, data_as_of, sig["composite_score"], sig["merrill"]["phase"],
             sig["credit"]["phase"], sig["inventory"]["phase"], sig["debt"]["phase"]))
        conn.commit()
    finally:
        conn.close()
```

### 1.3 01_fetch_data.py main() 接线（`write_manifest(_MANIFEST)` 之后）

```python
    # ⑥ 信号历史快照：commit 后追加，失败仅告警不影响已提交数据
    try:
        append_signal_history(DB_PATH, ts)
        log("📈 signal_history: +1 行（composite+四相位）")
    except Exception as e:
        log(f"  ⚠️ signal_history 写入失败（不影响数据）: {e}")
```

- 顶部 `from signal_history import append_signal_history`（scripts 目录已在 sys.path）。
- 复用 `ts = iso_ts()`（与 `_MANIFEST["ts"]` 同值）→ 历史行与 last_run.json 可互查。
- 日志用 📈 不含 ✅（进度计数依赖 ✅ 行数，见 §0）；不影响 `计划抓取` 正则。
- 空计划提前返回（`if not selected: return 0`）自然不写——写入点在其后。

---

## 2. 后端：GET /api/v1/signals/history

### 2.1 backend/app/core/signal_history.py（新，~40 行）

翻转检测放服务端的理由：前端无测试框架且零新依赖，而测试计划要求「翻转检测函数单测」；
后端标注后前端只渲染，更薄。

```python
"""Signal history read + flip annotation (written by scripts/signal_history.py)."""
import sqlite3
from backend.app.core.db import DB_PATH

TABLE = "signal_history"
FRAMEWORKS = ("merrill", "credit", "inventory", "debt")


def annotate_flips(rows):
    """rows 新→旧有序；为每行附 flips=[{framework,prev,curr}]（相对相邻更早一行）。
    prev != curr 即翻转（None 视为合法值参与比较）；窗口内最旧一行 flips=[]。"""
    out = []
    for i, r in enumerate(rows):
        flips = []
        if i + 1 < len(rows):
            prev = rows[i + 1]
            flips = [{"framework": f, "prev": prev[f], "curr": r[f]}
                     for f in FRAMEWORKS if r[f] != prev[f]]
        out.append({**r, "flips": flips})
    return out


def read_history(limit=60, db_path=DB_PATH):
    """倒序（rowid DESC，append-only 表 rowid 单调）取 limit+1 行——多取一行
    保证窗口内最旧一行的翻转也能对到前值；表缺失 → []（fresh install 不 500）。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            f"SELECT ts, data_as_of, composite, merrill, credit, inventory, debt "
            f"FROM {TABLE} ORDER BY rowid DESC LIMIT ?", (limit + 1,))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return annotate_flips(rows)[:limit]
```

### 2.2 路由（backend/app/api/v1/signals.py 追加）

```python
from fastapi import APIRouter, Query
from backend.app.core.signal_history import read_history
from backend.app.schemas.signals import SignalHistory, SignalSummary

@router.get("/history", response_model=SignalHistory)
def history(limit: int = Query(60, ge=1, le=500)):
    """信号快照历史（倒序；每次成功刷新一行，附相位翻转标注 flips）。"""
    return {"items": read_history(limit)}
```

### 2.3 Pydantic schema（backend/app/schemas/signals.py 追加）

```python
class PhaseFlip(BaseModel):
    framework: str            # merrill | credit | inventory | debt
    prev: str | None = None
    curr: str | None = None

class SignalHistoryRow(BaseModel):
    ts: str
    data_as_of: str | None = None
    composite: int
    merrill: str | None = None
    credit: str | None = None
    inventory: str | None = None
    debt: str | None = None
    flips: list[PhaseFlip] = []

class SignalHistory(BaseModel):
    items: list[SignalHistoryRow]
```

`schemas/__init__.py` `__all__` 增 `SignalHistory`（沿用只导出顶层响应模型的习惯）。

### 2.4 /table 白名单（backend/app/api/v1/data.py）

`_ALLOWED_TABLES` 增 `"signal_history"`（可选浏览；无 date 列，`db.load` 直返全表，
start/end 忽略——既有 loader 行为，零改动）。

### 2.5 openapi 重新导出

```bash
cd <repo-root>
.venv312/bin/python -c "import json; from backend.app.main import app; open('shared/openapi.json','w').write(json.dumps(app.openapi(), ensure_ascii=False, indent=2))"
```

前端 TS 类型沿用 P0 惯例**手写镜像** `src/api/types.ts`（client.ts 头注明示）；
`schema.d.ts` 当前无消费者，不生成。

---

## 3. 前端：Overview 新卡片「信号与相位历史」

### 3.1 types / client（各 +1 段）

`types.ts`：`PhaseFlip` / `SignalHistoryRow` / `SignalHistory` 三接口镜像 §2.3。
`client.ts`：`getSignalHistory: (limit?: number) => getJSON<SignalHistory>(\`/signals/history${qs([['limit', limit?.toString()]])}\`)`。

### 3.2 Overview.vue 新卡片（唯一组件改动，不新建组件/页面/路由）

- 数据：现有 `load()` 的 `Promise.all` 增第三路 `api.getSignalHistory()`；
  随 `refresh.lastRefreshedAt` watchEffect 自动重载（刷新后新行即现）。
- `const onlyFlips = ref(false)`；`rows = computed(() => onlyFlips.value ? history.filter(r => r.flips.length) : history)`。
- 复用 `phaseLabel`/`phaseColor`；`FW = { merrill:'美林', credit:'信用', inventory:'库存', debt:'债务' }`。
- 结构（紧凑表格式时间条，每行日期 + composite + 四相位 chip）：

```html
<section class="bg-card border border-border rounded-2xl p-5">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-sm font-semibold text-text">信号与相位历史<ChartTip :text="historyTip" /></h3>
    <label class="flex items-center gap-1.5 text-xs text-text-2 cursor-pointer">
      <input v-model="onlyFlips" type="checkbox" class="accent-warn"> 仅看翻转
    </label>
  </div>
  <ol role="list" class="space-y-1">
    <li v-for="r in rows" :key="r.ts"
        class="grid grid-cols-[5.5rem_2.5rem_1fr] items-center gap-3 px-2 py-1.5 rounded-lg"
        :class="r.flips.length ? 'ring-1 ring-warn/40 bg-warn/5' : ''"
        :tabindex="r.flips.length ? 0 : undefined"
        :aria-label="rowAria(r)">
      <span class="text-xs text-text-3">{{ r.ts.slice(0, 10) }}</span>
      <span class="text-xs font-bold text-center"
            :class="r.composite > 0 ? 'text-up' : r.composite < 0 ? 'text-down' : 'text-text-2'">
        {{ r.composite > 0 ? '+' : '' }}{{ r.composite }}
      </span>
      <span class="flex flex-wrap gap-1">
        <span v-for="f in FRAMEWORKS" :key="f"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border bg-surface text-[11px] text-text-2"
              :class="isFlipped(r, f) ? 'border-warn/60 text-text' : 'border-border'">
          <span class="w-1.5 h-1.5 rounded-full" :style="{ background: phaseColor(r[f]) }" />
          {{ FW[f] }}·{{ phaseLabel(r[f]) }}
        </span>
      </span>
    </li>
  </ol>
  <p v-if="!rows.length" class="text-xs text-text-3">暂无历史——每次成功刷新后记录一条快照。</p>
</section>
```

- 翻转高亮：**warn 令牌细环 + 浅底**（`ring-warn/40 bg-warn/5`）整行标示；发生变化的 chip 另加 `border-warn/60`。
- a11y：容器 `role="list"`、行 `role="listitem"`（li 语义）；翻转行 `tabindex="0"` 键盘可达，
  `rowAria(r)` 播报 `「<日期> 综合信号 <n>；美林相位 recovery → overheating；…」`（from→to 用 phaseLabel 中文）；
  「仅看翻转」为原生 checkbox（Tab 可达、读屏可辨）。非翻转行不设 tabindex（不可交互元素不做假焦点）。

### 3.3 phases.ts 补 4 个 debt 相位中文标签

chip 是这四个值的直接消费者（否则直出英文原值）：
`leveraging_boom: '加杠杆繁荣'`、`stable_growth: '稳定增长'`、
`leveraging_bust: '加杠杆衰退'`、`stable_contraction: '稳定收缩'`。

---

## 4. 测试计划 — backend/tests/test_signal_history.py（新）+ vue-tsc

全部进 pytest（与现有 29 例同跑），scripts 侧不新增 *_test.py（写入函数经 importlib 加载，
手法同 `_pipeline.run_derived` / test_derived_golden）。

1. **翻转检测单测（构造相位序列，纯函数）**：
   - 无翻转序列 → 各行 `flips == []`；
   - 单框架翻转 → 恰 1 条 `{framework, prev, curr}`，方向正确（新行 curr vs 旧行 prev）；
   - 同帧多框架翻转 → 多条；`None → 'easing'` 与 `'easing' → None` 均判翻转；
   - 窗口最旧一行（无前值）`flips == []`。
2. **两次写入落两行**：live DB 缺失 → `pytest.skip`；复制 live 至临时文件，
   importlib 加载 `scripts/signal_history.py`，`append_signal_history(tmp, "t1")` /
   `("t2")` 两次 → sqlite 读回恰 2 行（append-only 不去重），ts 有序，
   composite/四相位与该库 `compute_signals` 当前值一致，`data_as_of` 为 `YYYY-MM`。
3. **端点 shape**：`TestClient GET /api/v1/signals/history` → 200；`items` 为列表；
   ts 严格不增（倒序）；`?limit=1` → ≤1 行；每行含 7 个存储字段 + flips；
   有翻转的相邻行 flips 与相邻差分一致。另对临时空库直调 `read_history` → `[]`（表缺失不 500）。
4. **前端**：`cd frontend && npm run typecheck`（vue-tsc --noEmit）0 error。

---

## 5. 验收标准 + 精确文件清单 + changeLog 草稿

### 验收标准

1. **写入点**：`01_fetch_data.py` 任一成功提交（含经后端 refresh 触发）后 signal_history
   恰增 1 行，`ts` == 本次 manifest.ts，composite/四相位与当时 `GET /api/v1/signals` 一致；
   增量空计划提前返回不写；人为令 compute_signals 抛错 → 仅 ⚠️ 告警，数据与 manifest 不受影响。
2. **append-only**：临时库上连写两次（单测）/ worktree 内 `--full` 实跑两次 → 表内 2 行，不去重。
3. **端点**：`GET /api/v1/signals/history` 200 倒序、默认 ≤60 行、`limit` 生效、flips 标注正确；
   表缺失返回 `{"items": []}` 不 500；`GET /api/v1/table/signal_history` 200 可浏览；
   `TABLE_SPECS`/`validate()` 零改动（闸门不管此表）。
4. **前端**：Overview 卡片按日期倒序渲染 行=日期+composite（符号着色）+四相位 chip；
   翻转行 warn 细环高亮、变化 chip 边框加深；「仅看翻转」过滤正确；
   role=list/listitem、翻转行 aria-label 播报 from→to、checkbox Tab 可达；
   `vue-tsc --noEmit` 0 error；requirements.txt / package.json / tokens.css 零变化。
5. **卫生**：shared/openapi.json 含 `/api/v1/signals/history` 与三新 schema；
   changeLog.md [Unreleased] 同步；analysis/、commentary、HealthLight.vue、
   release_calendar、vintage/双源逻辑零触碰；新增日志行不含 ✅（进度计数不破）。

### 改动文件清单

**新增（4）**
- `docs/plans/M3-design.md`（本文档）
- `scripts/signal_history.py`（append 写入函数）
- `backend/app/core/signal_history.py`（read_history + annotate_flips）
- `backend/tests/test_signal_history.py`

**修改（11）**
- `scripts/01_fetch_data.py`（import + main() write_manifest 后 ⑥ 接线）
- `backend/app/api/v1/signals.py`（+ `/history` 端点）
- `backend/app/api/v1/data.py`（_ALLOWED_TABLES += signal_history）
- `backend/app/schemas/signals.py`（PhaseFlip / SignalHistoryRow / SignalHistory）
- `backend/app/schemas/__init__.py`（导出 SignalHistory）
- `frontend/src/api/types.ts`（三接口镜像）
- `frontend/src/api/client.ts`（getSignalHistory）
- `frontend/src/pages/Overview.vue`(新卡片 + load 第三路)
- `frontend/src/design/phases.ts`（PHASE_LABELS +4 debt 相位）
- `changeLog.md`（[Unreleased] M3 段）
- `README.md`（macro_data.db 结构行 + 端点表各一行）

**明确不动**：`scripts/_pipeline.py`（TABLE_SPECS/validate/闸门）、`02_compute_derived.py`、
`analysis/`、`backend/app/core/commentary.py`、`cache.py` / `refresh.py`（clear_all_caches 已覆盖）、
`router/index.ts` / `Sidebar.vue`（卡片非页面）、`requirements.txt`、`package.json`、`tokens.css`。

### changeLog 条目草稿（[Unreleased] 下新增 M3 段）

```markdown
### M3：信号历史表 + Overview 相位翻转高亮

### 新功能
1. **[新功能] `scripts/signal_history.py`**：signal_history 表（ts/data_as_of/composite/
   merrill/credit/inventory/debt，append-only）；01_fetch main() 成功提交后追加一行
   composite+四相位快照（ts 复用 manifest、data_as_of=derived_monthly 最大月），
   空计划提前返回不写、写入失败仅告警；不进 TABLE_SPECS 闸门，/table 白名单可浏览
2. **[新功能] `GET /api/v1/signals/history`**：倒序 limit（默认 60），行附 flips 翻转标注
   （任一框架相位相对上一条变化，framework/prev/curr）；表缺失空列表不 500；
   Pydantic 三新 schema，shared/openapi.json 重导
3. **[新功能] Overview「信号与相位历史」卡片**：每行日期+composite（符号着色）+四相位 chip
   （复用 phaseLabel/phaseColor）；翻转行 warn 细环高亮、「仅看翻转」过滤；
   role=list、翻转行 aria-label 播报 from→to、键盘可达；零新依赖
4. **[新功能] `backend/tests/test_signal_history.py`**：翻转检测构造序列单测、
   临时库两次写入落两行、端点 shape 与 limit

### 验证
- ✅ backend pytest（含 test_signal_history）全绿；两次成功提交 → 表内恰 2 行
- ✅ 端点倒序/limit/flips 标注正确；表缺失 {"items": []}
- ✅ vue-tsc --noEmit 0 error；requirements.txt/package.json/tokens.css 零变化；
  analysis/、commentary、健康灯、日历/vintage 零触碰

### M3: Signal History Table + Phase-Flip Highlights (English)
1. **[feat] `scripts/signal_history.py`**: append-only signal_history table; one
   composite + four-phase snapshot row after each successful pipeline commit
   (reuses manifest ts; skipped on empty incremental plan; failure only warns);
   outside TABLE_SPECS gating, browsable via /table whitelist
2. **[feat] `GET /api/v1/signals/history`**: newest-first rows with limit (default 60),
   each annotated with flips (framework/prev/curr vs the previous row); missing
   table → empty list; three new Pydantic schemas, openapi.json re-exported
3. **[feat] Overview "信号与相位历史" card**: date + composite + four phase chips per
   row (reuses phaseLabel/phaseColor); flip rows highlighted with warn ring,
   "flips only" toggle; role=list, from→to aria-labels, keyboard reachable; zero new deps
4. **[feat] `test_signal_history.py`**: constructed-sequence flip detection unit tests,
   two-writes-two-rows on a temp DB copy, endpoint shape/limit
```
