# M4a 设计文档 — AI 配置层：keychain + provider 适配器 + profiles CRUD + AI 设置页

> 分支：worktree-ai-commentary-m4 ｜ 日期：2026-08-16
> 范围纪律：M4a 只做配置层——①keychain 封装 ②provider 适配器（chat_completions + responses 双端点）
> ③profiles CRUD API ④AI 设置页第一部分（profile 管理 + 连接测试）。
> **不做**：snapshot v2、结构化生成、模板编辑器、生成历史、细分页切片、Overview 卡改造（M4b/M4c）。
> 约束：零新依赖（requirements.txt / package.json 不动）；`commentary.py` 本里程碑**零 diff**
> （生成逻辑不动，只在其旁长出配置层，M4b 接管 `call_model` 的 env 读取）。

## 0. 现状要点（读取结论，约束设计的既有事实）

- `backend/app/core/commentary.py`：模块级 `BASE_URL/API_KEY/MODEL = os.getenv("COMMENTARY_*")`，
  `call_model()` httpx POST `{base}/chat/completions`（timeout=60，temperature 硬编码 0.3），
  单飞锁 `_gen_lock` + `_busy` Event + stale 重生成。**接管点已天然存在**：M4b 只换
  `call_model` 里「env 三件套 + httpx 调用」这一段为 `ai_config.get_effective_active()` +
  `keychain.get()` + `ai_client.call_chat()`；M4a 不需要在 commentary.py 里预埋任何代码。
- `backend/app/core/db.py`：`PROJECT_ROOT = parents[3]`，`DB_PATH = PROJECT_ROOT/"data"/"macro_data.db"`
  → 配置文件落 `PROJECT_ROOT/"data"/"ai_config.json"`（与库同目录，纯运行时产物）。
- `.gitignore` **未整体 ignore `data/`**——只列了 `data/*.db`、`data/*.csv`、`data/last_run.json` 等具名条目
  （`git ls-files data/` 为空，无任何已跟踪文件）。→ 需新增一行 `data/ai_config.json`
  （紧跟 `data/last_run.json` 先例），否则机器本地配置会进 git。
- 分层惯例：逻辑在 `core/`、路由薄壳在 `api/v1/`（commentary 先例）；schema 在 `schemas/`，
  `schemas/__init__.py` 只导出顶层响应模型；`api/v1/__init__.py` 聚合 router。
- 前端：路由 `lazy('PageName')` 映射 `src/pages/{PageName}.vue`；Sidebar 手工 items 数组
  （几何字符图标 ◉◐◈▣◆▧◎◫）；`api/client.ts` 手写 getJSON/postJSON（**postJSON 目前不带 body**，
  需加可选 body 参数；无 PUT/DELETE helper）；types.ts 手写镜像 schema（`npm run gen:api`
  产出的 schema.d.ts 无消费者，沿用 M3 结论不生成）。
- HealthLight.vue 是 a11y/弹层基线：`role="dialog"` + `aria-label` + `tabindex="-1"`，
  打开 `nextTick` 后移焦入面板、关闭归还触发器，`@keydown.esc` 关闭，
  焦点环 `focus-visible:outline-accent`。
- httpx 0.28.1 已在 venv（FastAPI/akshare 传递依赖），`httpx.MockTransport` 可用于单测，零新依赖。
- macOS `security` CLI 已核实：`add-generic-password -s <svc> -a <acct> -w <pwd> -U`、
  `find-generic-password -s <svc> -a <acct> -w`（仅输出密码到 stdout，未命中 exit≠0）、
  `delete-generic-password -s <svc> -a <acct>`。man 页明示 `-w` 传参会短暂出现在进程列表——
  单用户桌面应用可接受，§2 注明取舍。

---

## 1. data/ai_config.json — schema 与 gitignore

### 1.1 文件 schema（非敏感明文；密钥永不入此文件）

```json
{
  "active_profile": "qwen-max",
  "profiles": [
    {
      "name": "qwen-max",
      "preset": "dashscope",
      "endpoint": "chat_completions",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model": "qwen-max",
      "temperature": 0.3
    }
  ]
}
```

- `name`：`[A-Za-z0-9_-]{1,40}`（与 keychain account 同一套白名单，**一条规则两处复用**）。
- `preset`：`dashscope | deepseek | openrouter | custom`（决定 base_url 默认值，见 §3）。
- `endpoint`：`chat_completions | responses`（两种 provider 方言，见 §3）。
- `temperature`：float，0–2，默认 0.3（与 commentary 现值一致）。
- `active_profile`：可为 null；解析时若指向不存在的 profile 则回退 env（§1.2）再回退 null。

### 1.2 env 回退 —— 隐式只读 profile「env」

三件 `COMMENTARY_*` env **全部非空**时（与 `commentary.call_model` 的配置齐全判定同口径），
列表追加一条**不落盘**的合成 profile：

```python
{"name": "env", "source": "env", "preset": "custom", "endpoint": "chat_completions",
 "base_url": COMMENTARY_BASE_URL, "model": COMMENTARY_MODEL, "temperature": 0.3}
```

- `source` 字段：`user`（文件里的）| `env`（合成的）；前端列表标注来源。
- env profile 不可编辑、不可删（PUT/DELETE name=="env" → 400）；可设默认、可测连接
  （其 key = `COMMENTARY_API_KEY`）。
- env 每次调用动态读（`os.getenv`，不做模块级常量）——与 commentary.py 的 import 期读取解耦，
  测试可自由 monkeypatch，也不产生两份缓存。
- 现状不破坏：没有任何 profile 时，active 解析落到 env —— 即今天 commentary 的行为。

### 1.3 gitignore

`.gitignore` `data/last_run.json` 行后新增一行：`data/ai_config.json`
（该文件是机器本地运行时配置；虽无密钥，但 profiles 因人而异，不进版本库）。

---

## 2. backend/app/core/keychain.py（新，~60 行）

macOS `security` CLI 薄封装。**任何失败返回 None/False 不抛**；key 永不进日志/异常文本；
`subprocess.run(argv 列表)`（绝不 shell=True），`capture_output=True, timeout=10`。

```python
"""macOS keychain wrapper for AI profile API keys (via `security` CLI).

Secrets never touch data/ai_config.json, logs, or exception text. Every
function returns None/False on ANY failure instead of raising — keychain
hiccups must not 500 the config API.

MACRO_AI_KEYCHAIN=off → in-process dict fallback (unit tests, headless/CI).
"""
import os, re, subprocess

SERVICE = "macro-ai-profiles"
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")   # 白名单：与 ai_config 共用，防 CLI 注入
_FALLBACK: dict[str, str] = {}                  # MACRO_AI_KEYCHAIN=off 时的进程内存储


def _off() -> bool:
    return os.getenv("MACRO_AI_KEYCHAIN", "").lower() == "off"


def _valid(name: str) -> bool:
    return bool(re.fullmatch(NAME_RE, name))


def set_key(name: str, key: str) -> bool:
    if not _valid(name) or not key:
        return False
    if _off():
        _FALLBACK[name] = key
        return True
    try:
        r = subprocess.run(
            ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", key],
            capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False
    # 注：key 经 argv 传递会短暂出现在本机进程列表（man security 亦提示 -w 不安全）。
    # 单用户桌面场景可接受；若将来上多用户/服务器，改 -T "" + 交互式授权或直接换
    # `security` 的 stdin 替代方案，不在 M4a 范围。


def get_key(name: str) -> str | None:
    if not _valid(name):
        return None
    if _off():
        return _FALLBACK.get(name)
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            capture_output=True, timeout=10)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", "replace").strip() or None
    except Exception:
        return None


def delete_key(name: str) -> bool:
    if not _valid(name):
        return False
    if _off():
        return _FALLBACK.pop(name, None) is not None
    try:
        r = subprocess.run(
            ["security", "delete-generic-password", "-s", SERVICE, "-a", name],
            capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False
    # 删除失败不阻断 profile 删除（孤儿 keychain 项无害，重试删除即可）——调用方忽略返回值。
```

---

## 3. backend/app/core/ai_client.py（新，~90 行）

provider 适配器：两种方言的 POST + 解析、错误归一化、连接测试。

### 3.1 PRESETS 与 AiError

```python
PRESETS = {
    "dashscope":  "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek":   "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "custom":     "",
}

class AiError(Exception):
    """归一化错误：stage ∈ {request(网络/超时), http(非 2xx), parse(响应解析)}。
    msg 永不含 key。"""
    def __init__(self, stage: str, status: int | None, msg: str):
        self.stage, self.status, self.msg = stage, status, msg
        super().__init__(f"{stage}: {msg}")   # 只带 stage+msg，key 无进入路径
```

### 3.2 call_chat —— 双方言

```python
def call_chat(profile: dict, key: str, messages: list[dict],
              temperature: float | None = None, *, transport=None) -> str:
    """POST 一次对话，返回纯文本。profile 为 ai_config 产出的 dict。

    - chat_completions 方言：POST {base}/chat/completions
        body {model, messages, temperature} → choices[0].message.content
    - responses 方言：POST {base}/responses
        body {model, input: [{role, content}], temperature} → output_text，
        缺失时回退拼接 output[].content[].text（OpenAI Responses 两种返回形态都兼容）
    transport 仅供单测注入 httpx.MockTransport。
    """
```

实现要点：
- `base = profile["base_url"].rstrip("/")`；url 按方言拼 `/chat/completions` 或 `/responses`。
- `temp = profile.get("temperature", 0.3) if temperature is None else temperature`。
- `headers = {"Authorization": f"Bearer {key}"}`；`httpx.Client(timeout=60.0, transport=transport)`
  （timeout 与 commentary 现值一致）。
- 异常归一化（三层，**except 块不复述 URL body/key**）：
  - `httpx.TimeoutException` / `httpx.HTTPError` → `AiError("request", None, "网络错误/超时")`
    （`type(e).__name__` 可入 msg，异常对象不含 key）。
  - `r.status_code != 2xx` → `AiError("http", r.status_code, r.text[:200])`
    （provider 错误正文截断 200 字符——其中不会出现我方 key，只有 provider 自己的报文）。
  - JSON/字段解析失败 → `AiError("parse", None, "响应解析失败")`。
- responses 方言解析：

```python
data = r.json()
text = data.get("output_text")
if not text:  # 回退：output[].content[].text
    parts = [p.get("text", "") for item in data.get("output", [])
             for p in (item.get("content") or []) if isinstance(p, dict)]
    text = "".join(parts)
return (text or "").strip() or (_ for _ in ()).throw(AiError("parse", None, "空回复"))
```

（空回复按 parse 错误处理——连接测试需要明确的成败信号。）

### 3.3 test_connection —— 极简 ping

```python
PING = [{"role": "user", "content": "Reply with the single word OK"}]

def test_connection(profile: dict, key: str, *, transport=None) -> dict:
    """返回 {ok, latency_ms, error?}；失败 error 形如 "http: 401 …"（不含 key）。"""
    t0 = time.perf_counter()
    try:
        call_chat(profile, key, PING, 0.0, transport=transport)
        return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000), "error": None}
    except AiError as e:
        return {"ok": False, "latency_ms": round((time.perf_counter() - t0) * 1000),
                "error": f"{e.stage}: {e.msg}" + (f" (HTTP {e.status})" if e.status else "")}
```

---

## 4. backend/app/core/ai_config.py（新，~90 行）+ API + schemas

### 4.1 ai_config.py —— JSON 存储 + env 回退 + active 解析

```python
"""AI profile config store — data/ai_config.json + COMMENTARY_* env fallback.

Plain JSON, no secrets (keys live in the keychain, core/keychain.py).
ponytail: whole-file read/write per op — profiles are few, edits rare.
"""
import json, os, re, threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "data" / "ai_config.json"   # 测试 monkeypatch 此常量
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
_lock = threading.Lock()   # ponytail: 全局单锁；profile 编辑是低频人工操作，无并发压力


def load() -> dict: ...        # 文件缺失/损坏 → {"active_profile": None, "profiles": []}
def _save(cfg: dict) -> None:  # mkdir parents + 写 .tmp 后 os.replace（原子，防半截文件丢配置）
def env_profile() -> dict | None: ...   # §1.2 合成 profile（三 env 全非空才出现），source="env"
def list_profiles() -> dict:   # {"active_profile": 有效值, "profiles": [user... + env?]}
def get(name) -> dict | None   # user profile 或 env（name=="env"）
def create(p: dict, api_key: str | None) -> dict      # 重名 → 抛 ValueError（路由转 409）
def update(name, patch: dict, api_key: str | None) -> dict   # name=="env"/不存在 → ValueError
def delete(name) -> None       # 连带 keychain.delete_key(name)；删的是 active → active 置 null
def set_active(name) -> dict   # 必须存在（user 或 env），否则 ValueError
def key_for(name) -> str | None  # name=="env" → COMMENTARY_API_KEY；否则 keychain.get_key(name)
def resolve_active() -> dict | None  # active_profile 有效 → 之；否则 env_profile()；否则 None
                                       # —— M4b 生成链路的唯一取配置入口（接管点）
```

- env 三件套每次经 `os.getenv` 动态读（§1.2 理由）。
- create/update 返回的 dict 带 `source="user"`；`has_key` 不落盘、由路由层现算
  （`key_for(name) is not None`）——key 状态只反映 keychain 实况，不存第二份事实。

### 4.2 backend/app/schemas/ai.py（新）

```python
from typing import Literal
from pydantic import BaseModel, Field

Preset = Literal["dashscope", "deepseek", "openrouter", "custom"]
Endpoint = Literal["chat_completions", "responses"]


class ProfileBase(BaseModel):
    preset: Preset = "custom"
    endpoint: Endpoint = "chat_completions"
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(0.3, ge=0.0, le=2.0)


class ProfileCreate(ProfileBase):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    api_key: str | None = None          # 可选；提供则写 keychain


class ProfileUpdate(BaseModel):         # 全可选，exclude_unset 后按字段打补丁
    preset: Preset | None = None
    endpoint: Endpoint | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    api_key: str | None = None          # 非空 → 覆盖 keychain；空/缺省 → 保留原 key


class ProfileOut(ProfileBase):          # GET/POST/PUT 响应 —— 无任何 key 物料
    name: str
    source: Literal["user", "env"] = "user"
    has_key: bool = False


class ProfileList(BaseModel):
    active_profile: str | None = None
    profiles: list[ProfileOut] = []


class ActiveIn(BaseModel):
    name: str


class TestResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None
```

`schemas/__init__.py` `__all__` 追加 `ProfileList`、`TestResult`（沿用只导出顶层响应模型的惯例）。
**不支持改名**：name 是 keychain account + 唯一键，改名 = 新建 + 删旧（YAGNI）。

### 4.3 backend/app/api/v1/ai.py（新 router，prefix="/ai"，tags=["ai"]）

```
GET    /api/v1/ai/profiles               → ProfileList（has_key 现算，无 key 物料）
POST   /api/v1/ai/profiles               → ProfileCreate → ProfileOut；重名 409；
                                           api_key 给了但 keychain.set_key 失败 → 500
                                           （profile 已存、key 未存，文案提示重新保存密钥）
PUT    /api/v1/ai/profiles/{name}        → ProfileUpdate → ProfileOut；env/不存在 400
DELETE /api/v1/ai/profiles/{name}        → 删 profile + keychain 项；env 400；返回 {"status":"ok"}
POST   /api/v1/ai/profiles/{name}/test   → key_for(name) 为空 → 400「未配置密钥」；
                                           否则 ai_client.test_connection → TestResult
POST   /api/v1/ai/active                 → ActiveIn → ProfileList（设默认后直接回最新列表，省一次 GET）
```

- `ValueError` → `HTTPException(400/409/404)` 的映射在路由内显式写（一个小 try/except 每端点，
  不做全局 exception handler——现有代码无此先例，不造抽象）。
- `api/v1/__init__.py` 追加 `from ... import ai` + `router.include_router(ai.router)`（按现有行序）。

### 4.4 openapi 重新导出（同 M3 §2.5 命令）

```bash
cd <repo-root>
.venv312/bin/python -c "import json; from backend.app.main import app; open('shared/openapi.json','w').write(json.dumps(app.openapi(), ensure_ascii=False, indent=2))"
```

前端 TS 类型沿用手写镜像（types.ts），schema.d.ts 不生成（无消费者，M3 先例）。

---

## 5. 前端：AISettings.vue + 路由 + sidebar

### 5.1 types / client（`frontend/src/api/`）

`types.ts` 追加：

```ts
export interface AiProfile {
  name: string
  preset: 'dashscope' | 'deepseek' | 'openrouter' | 'custom'
  endpoint: 'chat_completions' | 'responses'
  base_url: string
  model: string
  temperature: number
  source: 'user' | 'env'
  has_key: boolean
}
export interface AiProfileList { active_profile: string | null; profiles: AiProfile[] }
export interface AiTestResult { ok: boolean; latency_ms: number | null; error: string | null }
```

`client.ts`：`postJSON(path, body?)` 加可选 body（`JSON.stringify` + `Content-Type: application/json`，
body 为 undefined 时行为与现状完全一致）；同风格新增 `putJSON(path, body)`、`delJSON(path)`；
`api` 对象追加：

```ts
getAiProfiles:    () => getJSON<AiProfileList>('/ai/profiles'),
createAiProfile:  (p: unknown) => postJSON<AiProfile>('/ai/profiles', p),
updateAiProfile:  (name: string, p: unknown) => putJSON<AiProfile>(`/ai/profiles/${name}`, p),
deleteAiProfile:  (name: string) => delJSON<{ status: string }>(`/ai/profiles/${name}`),
testAiProfile:    (name: string) => postJSON<AiTestResult>(`/ai/profiles/${name}/test`),
setAiActive:      (name: string) => postJSON<AiProfileList>('/ai/active', { name }),
```

### 5.2 路由 + sidebar

- `router/index.ts`：catch-all 前插一条
  `{ path: '/ai-settings', component: lazy('AISettings'), meta: { title: 'AI 设置', icon: '⚙' } }`。
- `Sidebar.vue`：items 末尾追加 `{ to: '/ai-settings', label: 'AI 设置', icon: '⚙' }`
  （设置项置底；⚙ 为单色文本字形，语义直达「设置」，与现有几何图标同为非 emoji 单字符）。

### 5.3 frontend/src/pages/AISettings.vue（新，~260 行）

页面骨架同现有页：`<div class="p-6 space-y-5">` + `<header><h1 class="text-xl font-bold text-text">AI 设置</h1>`
+ 卡片 `bg-card border border-border rounded-xl p-4`。**纯页面内局部 ref，不建 pinia store**
（设置页无跨组件共享态，YAGNI）。onMounted 拉 `getAiProfiles()`。

**① profile 列表卡**（行式布局，同 HealthLight 面板的紧凑行风格）：
- 每行：`★`（active，`text-warn`）+ name + 来源徽标（`env` → `text-text-3 border` 小 chip「环境变量」；
  user 不标）+ 摘要行（preset · endpoint · model）+ 密钥状态点（has_key → `text-up ✓ 密钥已存` /
  `text-down ✗ 无密钥`）。
- 行内按钮：`测试`（env/user 都可）、`编辑`、`删除`、`设为默认`（active 行隐藏后两者中的「设为默认」；
  env 行无编辑/删除）。按钮样式复用 CommentaryCard 的
  `text-xs px-2.5 py-1 rounded-lg border border-border hover:border-border-hi … focus-visible:outline-accent`。
- 测试结果原位显示：`testing` 态按钮禁用显「测试中…」；完成后行内
  `✓ 1234ms`（`text-up`）或 `✗ http: …`（`text-down`，`title` 挂全文）。
  结果容器 `role="status"`（ polite 播报）。
- 删除确认：行内翻转（`confirmName` ref）——该行按钮区换成「确认删除？ 确认/取消」，
  不再造第二个 dialog。
- 「设为默认」点击 → `setAiActive` → 用返回的 ProfileList 直接覆盖本地状态。

**② 新增/编辑 dialog**（HealthLight 弹层模式）：
- `role="dialog" aria-modal="true" :aria-label="编辑态 ? '编辑 AI 配置' : '新增 AI 配置'"`，
  `tabindex="-1"`，遮罩层 `fixed inset-0 z-[120] bg-black/60` 点击关闭；`@keydown.esc` 关闭；
  打开 `nextTick` 移焦第一个输入（name / preset），关闭归还触发按钮（triggerRef 同 HealthLight）。
- 表单字段（全部 `<label :for>` + id 成对）：
  - name（新增态可编辑，编辑态只读灰显——不支持改名）；
  - preset `<select>`（dashscope 通义 DashScope / deepseek / openrouter / custom 自定义）——
    选中非 custom 时**自动回填 base_url 且输入框只读**；custom 时 base_url 自由输入；
  - endpoint radio 两项：`chat_completions`（OpenAI 兼容 /chat/completions）、
    `responses`（OpenAI Responses /responses）；
  - model 自由文本输入；
  - temperature `<input type="number" min="0" max="2" step="0.1">`；
  - api_key `<input type="password" autocomplete="off">`：新增态 label「API Key（可选）」；
    编辑态 placeholder `留空保持原密钥`；提交后响应无 key 物料、前端任何状态不回显。
- 提交：新增 → `createAiProfile`，编辑 → `updateAiProfile`（key 空串则不带 api_key 字段）；
  409/400/500 错误文本显示在 dialog 内 `text-down` 错误行；成功后关 dialog + 刷新列表。

**③ 空态**：无任何 profile 且无 env → 卡片内一句
`暂无配置——新增 profile 或设置 COMMENTARY_BASE_URL / COMMENTARY_API_KEY / COMMENTARY_MODEL 环境变量`。

**a11y 基线**（同 HealthLight.vue）：dialog 焦点进出管理 + Esc；所有输入 label 关联；
列表行按钮 focus-visible 环；测试结果 `role="status"`；env 行徽标带 `aria-label="来源：环境变量，只读"`。

---

## 6. 测试计划

### 6.1 backend/tests/test_ai_client.py（新）—— httpx.MockTransport

`transport=` 参数注入，不起真网络：

1. chat_completions happy：handler 校验 URL 以 `/chat/completions` 结尾、
   body 含 model/messages/temperature、`Authorization: Bearer k`；返回
   `{"choices":[{"message":{"content":" hi "}}]}` → 得 `"hi"`（strip 生效）。
2. responses happy（output_text 直返）→ 得文本；requests body 形如 `{model, input, temperature}`。
3. responses 回退解析：无 output_text、返回
   `{"output":[{"content":[{"type":"output_text","text":"a"},{"text":"b"}]}]}` → `"ab"`。
4. 401 → `AiError(stage="http", status=401)`；`"k" not in str(err)`（key 不入异常文本）。
5. 超时：handler 内 `raise httpx.TimeoutException("t")`（或 ConnectTimeout）→ `stage=="request"`。
6. 坏 JSON：200 + 非 JSON body → `stage=="parse"`；200 + `{}`（choices/output 皆缺）→ `stage=="parse"`。
7. test_connection：mock 200 → `{ok:True, latency_ms>=0, error:None}`；mock 401 →
   `{ok:False, error 含 "http"}`；两分支 key 均不出现在返回值里。

### 6.2 backend/tests/test_ai_profiles_api.py（新）—— TestClient + KEYCHAIN=off

fixture 基座（模块级）：`monkeypatch.setenv("MACRO_AI_KEYCHAIN", "off")` +
`monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path/"ai_config.json")` +
`monkeypatch.delenv/setenv("COMMENTARY_*")`；`TestClient(app)` 沿用现有测试的 sys.path 手法。

1. **CRUD shape**：POST 建 2 个 profile（一带 key）→ 200；GET → `profiles` 含两者、
   `has_key` 分别 True/False、**响应原文不含 key 字符串**（`assert KEY not in resp.text`）；
   POST 重名 → 409；POST 非法 name（含空格/超长）→ 422；PUT 改 model/temperature → 回读生效；
   PUT 不带 api_key → keychain 内原 key 仍在（has_key 不变 True）；PUT 带新 api_key → 覆盖。
2. **删除**：DELETE → GET 不再含之，keychain（_FALLBACK）对应项已删；删 active profile →
   `active_profile` 落回 env/null；DELETE 不存在 → 400。
3. **active**：POST /active 指向存在 profile → 返回 ProfileList 且 active_profile 生效；
   指向不存在 → 404。
4. **test 端点 shape**：monkeypatch `backend.app.api.v1.ai.test_connection`（路由 import 绑定名）
   返回桩值 → 200 且字段恰为 `{ok, latency_ms, error}`；对无 key profile → 400。
5. **env 回退只读**：setenv 三件 COMMENTARY_* → GET 列表末尾出现
   `{name:"env", source:"env"}`；PUT/DELETE `env` → 400；无 user profile 时
   `active_profile=="env"`；delenv 后 env 行消失。
6. **keychain 失败路径**：monkeypatch `keychain.set_key` → False，POST 带 api_key → 500
   且 profile 已存在、has_key False。

### 6.3 前端

`cd frontend && npm run typecheck`（vue-tsc --noEmit）0 error。

---

## 7. 验收标准 + 精确文件清单 + changeLog 草稿

### 验收标准

1. **keychain**：`security` 三连（add -U / find -w / delete）经封装函数读写真实钥匙串成功；
   非法 name（空格、50 字符、`$(…)`）全部返回 None/False 且不触 CLI；`MACRO_AI_KEYCHAIN=off`
   走进程内 dict；任何失败不抛、无日志、异常文本与返回值中不含 key。
2. **适配器**：MockTransport 下两方言 happy path 解析正确（含 responses output[].content[].text
   回退）；401/超时/坏 JSON 分别归一 `http/request/parse`；timeout=60；AiError 文本无 key。
3. **配置存储**：`data/ai_config.json` 原子写（.tmp+replace）、缺文件自愈为默认结构；
   `.gitignore` 含 `data/ai_config.json`；env 三件齐全时列表出现只读 env profile
   （不可 PUT/DELETE，可测连接/设默认），三件不全则消失。
4. **API**：六端点 shape 如 §4.3；GET/POST/PUT 响应零 key 物料（has_key bool 是唯一密钥信号）；
   重名 409、非法 name 422、env 守卫 400、无 key 测连接 400；openapi.json 含 `/api/v1/ai` 全部端点。
5. **前端**：`/ai-settings` 路由 + sidebar「AI 设置」项可达；列表星标/来源/密钥态/测试结果
   （✓ms / ✗错误）渲染正确；dialog preset 联动 base_url、编辑态 key 留空保持、提交后不回显；
   删除行内确认；Esc/焦点管理/label 齐全；`vue-tsc --noEmit` 0 error。
6. **卫生**：`backend/app/core/commentary.py` **零 diff**（生成逻辑原样，M4b 接管 call_model）；
   requirements.txt / package.json / tokens.css 零变化；analysis/、HealthLight.vue、
   CommentaryCard.vue、Overview.vue 零触碰；`backend/tests` 全绿（54 + 新增）。

### 改动文件清单

**新增（9）**
- `docs/plans/M4a-design.md`（本文档）
- `backend/app/core/keychain.py`（security CLI 封装 + off 回退）
- `backend/app/core/ai_client.py`（双方言适配器 + AiError + PRESETS + test_connection）
- `backend/app/core/ai_config.py`（JSON 存储 + env 回退 + active 解析）
- `backend/app/schemas/ai.py`（ProfileCreate/Update/Out/List、ActiveIn、TestResult）
- `backend/app/api/v1/ai.py`（六端点）
- `backend/tests/test_ai_client.py`
- `backend/tests/test_ai_profiles_api.py`
- `frontend/src/pages/AISettings.vue`

**修改（10）**
- `backend/app/api/v1/__init__.py`（include ai.router）
- `backend/app/schemas/__init__.py`（__all__ + ProfileList/TestResult）
- `.gitignore`（+ `data/ai_config.json`）
- `frontend/src/router/index.ts`（+ /ai-settings 路由）
- `frontend/src/components/layout/Sidebar.vue`（+ AI 设置 nav 项）
- `frontend/src/api/types.ts`（+3 接口）
- `frontend/src/api/client.ts`（postJSON +body；putJSON/delJSON；6 个 api 方法）
- `shared/openapi.json`（重导）
- `changeLog.md`（[Unreleased] M4a 段）
- `README.md`（端点表 +6 行 `/api/v1/ai/*`）

**明确不动**：`backend/app/core/commentary.py`（接管点 = M4b 换 call_model 内 env 读取，
本里程碑零 diff）、`api/v1/commentary.py`、`analysis/`、`HealthLight.vue`、`CommentaryCard.vue`、
`Overview.vue`、`requirements.txt`、`package.json`、`tokens.css`。

### changeLog 条目草稿（[Unreleased] 下新增 M4a 段）

```markdown
### M4a：AI 配置层 — keychain + provider 适配器 + profiles CRUD + AI 设置页

### 新功能

1. **[新功能] `backend/app/core/keychain.py`**：macOS security CLI 封装
   （service=macro-ai-profiles；add -U / find -w / delete），name 白名单 [A-Za-z0-9_-]{1,40}
   防注入，任何失败返回 None/False 不抛，key 永不进日志/异常文本；MACRO_AI_KEYCHAIN=off
   进程内 dict 回退（单测/无 GUI）
2. **[新功能] `backend/app/core/ai_client.py`**：provider 适配器，双方言
   （chat_completions：{base}/chat/completions → choices[0].message.content；
   responses：{base}/responses → output_text，回退 output[].content[].text 拼接），
   httpx timeout=60，AiError(stage,status,msg) 归一化（request/http/parse），key 不进日志；
   PRESETS：dashscope/deepseek/openrouter/custom；test_connection 极简 ping 返回
   {ok, latency_ms, error?}
3. **[新功能] profiles CRUD API `/api/v1/ai`**：`backend/app/core/ai_config.py`
   （data/ai_config.json 原子写 + COMMENTARY_* env 回退为只读 profile「env」，
   现状不破坏）+ schemas/ai.py + api/v1/ai.py 六端点（GET/POST /profiles、
   PUT/DELETE /profiles/{name}（连带删 keychain 项）、POST /profiles/{name}/test、
   POST /active）；GET 只出 has_key bool，零 key 物料；shared/openapi.json 重导；
   .gitignore +data/ai_config.json
4. **[新功能] `frontend/src/pages/AISettings.vue` + /ai-settings 路由 + sidebar 项**：
   profile 列表（默认星标/来源标注/密钥态/连接测试 ✓ms·✗错误）、新增/编辑 dialog
   （preset 联动 base_url、endpoint radio、temperature、key 密码输入——编辑态留空保持原 key、
   提交后不回显）、行内删除确认、设为默认；dialog 焦点管理/Esc/label 同 HealthLight 基线；
   client.ts postJSON 支持 body + putJSON/delJSON；零新依赖

### 验证

- ✅ backend pytest 全绿：test_ai_client（两方言 happy/401/超时/坏 JSON/test_connection）
  + test_ai_profiles_api（KEYCHAIN=off：CRUD shape、GET 不泄漏 key、test 端点 shape、
  env 回退只读、keychain 失败 500）
- ✅ 真实钥匙串手工验证 add/find/delete；MACRO_AI_KEYCHAIN=off 回退路径覆盖单测
- ✅ vue-tsc --noEmit 0 error；commentary.py 零 diff；requirements.txt/package.json/tokens.css
  零变化；analysis/、HealthLight、CommentaryCard、Overview 零触碰

### M4a: AI Config Layer — Keychain + Provider Adapter + Profiles CRUD + AI Settings Page (English)

### New Features

1. **[feat] `backend/app/core/keychain.py`**: macOS security CLI wrapper
   (service=macro-ai-profiles; add -U / find -w / delete), name whitelist
   [A-Za-z0-9_-]{1,40} against injection, every failure returns None/False without
   raising, keys never reach logs or exception text; MACRO_AI_KEYCHAIN=off falls back
   to an in-process dict (unit tests, headless)
2. **[feat] `backend/app/core/ai_client.py`**: provider adapter with two dialects
   (chat_completions: {base}/chat/completions → choices[0].message.content;
   responses: {base}/responses → output_text, falling back to output[].content[].text),
   httpx timeout=60, normalized AiError(stage,status,msg) (request/http/parse), keys
   never logged; PRESETS dashscope/deepseek/openrouter/custom; test_connection minimal
   ping returning {ok, latency_ms, error?}
3. **[feat] profiles CRUD API `/api/v1/ai`**: `backend/app/core/ai_config.py`
   (atomic data/ai_config.json writes + COMMENTARY_* env fallback surfaced as a
   read-only profile "env" — current behavior unbroken) + schemas/ai.py + api/v1/ai.py
   with six endpoints (GET/POST /profiles, PUT/DELETE /profiles/{name} (also deletes
   the keychain item), POST /profiles/{name}/test, POST /active); GET exposes only a
   has_key bool, zero key material; shared/openapi.json re-exported; .gitignore
   +data/ai_config.json
4. **[feat] `frontend/src/pages/AISettings.vue` + /ai-settings route + sidebar item**:
   profile list (default star / source badge / key state / connection test ✓ms · ✗error),
   create/edit dialog (preset auto-fills base_url, endpoint radio, temperature, password
   key input — empty on edit keeps the stored key, never echoed back), inline delete
   confirmation, set-default; dialog focus management/Esc/labels on the HealthLight
   baseline; client.ts postJSON gains body + putJSON/delJSON; zero new deps

### Verification

- ✅ backend pytest green: test_ai_client (both dialects happy/401/timeout/bad JSON/
  test_connection) + test_ai_profiles_api (KEYCHAIN=off: CRUD shape, GET leaks no key,
  test endpoint shape, env fallback read-only, keychain-failure 500)
- ✅ real-keychain manual add/find/delete; MACRO_AI_KEYCHAIN=off fallback covered by tests
- ✅ vue-tsc --noEmit 0 errors; commentary.py zero diff; requirements.txt/package.json/
  tokens.css unchanged; analysis/, HealthLight, CommentaryCard, Overview untouched
```
