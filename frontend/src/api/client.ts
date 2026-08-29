// API client — typed wrappers over the FastAPI endpoints. Types mirror the
// Pydantic schemas (single source of truth via shared/openapi.json codegen; P0
// ships hand-written types, `npm run gen:api` regenerates from OpenAPI).
//
// Transport contract (see docs/AUDIT_FIXES.md FE-M2/M3/M6):
//   · every call accepts an optional caller `signal`; it is merged with the
//     timeout via AbortSignal.any so the deadline covers the BODY download too
//     (the old clearTimeout-after-headers left slow bodies unbounded);
//   · idempotent GETs retry with bounded exponential backoff on transport
//     errors / 408 / 429 / 5xx — POSTs never retry;
//   · every POST carries the local capability token (F4): mutating endpoints are
//     token-guarded so a localhost-CSRF page cannot fire them, and the token is
//     read same-origin from GET /session (a cross-origin page can send that GET
//     but cannot read its body, so it can never obtain the token);
//   · identical signal-less GETs are deduped in flight and cached for a short
//     TTL, invalidated by invalidateCache() on every successful data refresh;
//   · failures throw ApiError with a machine-readable `kind` so the UI can name
//     the category instead of dumping `500 {"detail":...}` at the user.
import type { DerivedFrame, CycleFrame, SignalSummary, SignalHistory, RefreshResult, RealEstateResponse, Commentary, SourcesHealth, CrclOverview, CrclMetric, CrclEvent, CrclAlertRule, CrclLogRow, CrclFundamentals, AiProfile, AiProfileList, AiTestResult, AiTemplatesOut, AiTemplatesSaved, CommentaryHistoryIndex } from './types'

export const BASE = '/api/v1'

const DEFAULT_TIMEOUT_MS = 30_000
const DEFAULT_TTL_MS = 15_000     // short enough that a re-navigation is "the same screen"
const MAX_RETRIES = 2             // → at most 3 attempts, GET only
const RETRY_BASE_MS = 300         // 300ms, 900ms (×3 exponential)
const RETRY_STATUS = new Set([408, 429, 500, 502, 503, 504])

/** Error category the UI can turn into a sentence (never a raw HTTP dump). */
export type ApiErrorKind =
  | 'unreachable'   // transport failed: backend down / DNS / offline
  | 'timeout'       // our own deadline fired
  | 'aborted'       // the caller aborted (route change, newer request)
  | 'server'        // 5xx or an unparseable body
  | 'client'        // 4xx (bad params, 404 …)

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly detail: string
  /** Safe to re-issue: transport hiccup or a transient server status. */
  readonly retriable: boolean

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, detail = '') {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
    this.retriable = kind === 'unreachable' || (status !== null && RETRY_STATUS.has(status))
  }
}

export interface ReqOpts {
  /** Caller lifetime — merged with the timeout; aborting frees the connection. */
  signal?: AbortSignal
  timeoutMs?: number
  /** 0 disables the response cache for this call (polling endpoints). */
  ttlMs?: number
  retries?: number
  /** JSON-serialisable request body (POST/PUT). */
  body?: unknown
}

// ── error mapping ───────────────────────────────────────────────────────────
const HTTP_LABEL: Record<number, string> = {
  401: '缺少本机令牌（401）',
  403: '本机令牌无效（403）',
  404: '接口不存在（404）',
  408: '后端处理超时（408）',
  422: '请求参数不合法（422）',
  429: '请求过于频繁（429）',
  500: '服务端内部错误（500）',
  502: '网关错误（502）',
  503: '服务暂不可用（503）',
  504: '网关超时（504）',
}

/** Pull FastAPI's `{"detail": ...}` out of the body so the UI can show it separately. */
function bodyDetail(body: string): string {
  const raw = body.slice(0, 400)
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown }
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      return typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail)
    }
  } catch { /* not JSON — fall through to the raw text */ }
  return raw
}

function httpError(status: number, body: string): ApiError {
  const kind: ApiErrorKind = status >= 500 ? 'server' : 'client'
  const label = HTTP_LABEL[status] ?? `请求失败（HTTP ${status}）`
  return new ApiError(kind, label, status, bodyDetail(body))
}

/** Classify a thrown fetch/JSON failure. `external` decides abort vs timeout. */
function transportError(e: unknown, external: AbortSignal | undefined, timeoutMs: number): ApiError {
  if (e instanceof ApiError) return e
  const err = e as { name?: string; message?: string }
  if (err?.name === 'AbortError' || err?.name === 'TimeoutError') {
    if (external?.aborted) return new ApiError('aborted', '请求已取消')
    return new ApiError('timeout', `请求超时（${Math.round(timeoutMs / 1000)}s）`, null, err.message ?? '')
  }
  if (err?.name === 'SyntaxError') {
    return new ApiError('server', '响应解析失败（非 JSON）', null, err.message ?? '')
  }
  return new ApiError('unreachable', '后端未连接', null, err?.message ?? String(e))
}

// ── local capability token (F4) ──────────────────────────────────────────────
// The mutating endpoints (all POSTs) require the token the backend minted at
// startup. We read it same-origin from GET /session and cache it for the page's
// lifetime; a localhost-CSRF page can send that GET too but cannot read the
// response body, so it can never reach this value.
const TOKEN_HEADER = 'X-API-Token'
let tokenPromise: Promise<string> | null = null

function fetchToken(): Promise<string> {
  const p = (async () => {
    const resp = await fetch(`${BASE}/session`, { signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) })
    if (!resp.ok) throw httpError(resp.status, await resp.text().catch(() => ''))
    const body = (await resp.json()) as { token?: string }
    if (!body.token) throw new ApiError('server', '本机令牌为空（/session 未返回 token）')
    return body.token
  })().catch((e) => {
    if (tokenPromise === p) tokenPromise = null   // never cache a failure
    throw e
  })
  tokenPromise = p
  return p
}

/** Cached local capability token; fetched once per page load. */
function apiToken(): Promise<string> {
  return tokenPromise ?? fetchToken()
}

/** Drop the cached token — the backend rotates it on every restart. */
function forgetToken(): void {
  tokenPromise = null
}

// ── single attempt ──────────────────────────────────────────────────────────
async function attempt<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'DELETE', opts: ReqOpts): Promise<T> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const external = opts.signal
  // One merged signal for headers AND body: the deadline no longer stops at the
  // response headers, and a caller abort tears the connection down immediately.
  const signal = external
    ? AbortSignal.any([AbortSignal.timeout(timeoutMs), external])
    : AbortSignal.timeout(timeoutMs)
  try {
    // GETs stay header-free: they are read-only, so they need no capability.
    // Every mutation (POST/PUT/DELETE) carries the token; a JSON body is attached
    // when the caller supplies one.
    const headers: Record<string, string> = {}
    if (method !== 'GET') headers[TOKEN_HEADER] = await apiToken()
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
    const resp = await fetch(`${BASE}${path}`, {
      method, signal,
      headers: Object.keys(headers).length ? headers : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
    if (!resp.ok) throw httpError(resp.status, await resp.text().catch(() => ''))
    return (await resp.json()) as T
  } catch (e) {
    throw transportError(e, external, timeoutMs)
  }
}

/** Backoff wait that ends early when the caller aborts (no dangling timer). */
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve) => {
    const done = () => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', done)
      resolve()
    }
    const timer = setTimeout(done, ms)
    signal?.addEventListener('abort', done, { once: true })
  })
}

/** GET with bounded exponential-backoff retry. Only ever used for GET. */
async function getWithRetry<T>(path: string, opts: ReqOpts): Promise<T> {
  const attempts = (opts.retries ?? MAX_RETRIES) + 1
  for (let i = 0; ; i++) {
    try {
      return await attempt<T>(path, 'GET', opts)
    } catch (e) {
      const err = e as ApiError
      const last = i >= attempts - 1
      if (last || !err.retriable || opts.signal?.aborted) throw err
      await sleep(RETRY_BASE_MS * 3 ** i, opts.signal)
      if (opts.signal?.aborted) throw new ApiError('aborted', '请求已取消')
    }
  }
}

// ── dedupe + TTL cache (GET only) ───────────────────────────────────────────
const cache = new Map<string, { at: number; data: unknown }>()
const inflight = new Map<string, Promise<unknown>>()

/**
 * Drop every cached response. Called whenever the dataset changes
 * (stores/refresh.ts bumps lastRefreshedAt / crclRefreshedAt), so the TTL never
 * hides fresh data.
 */
export function invalidateCache(): void {
  cache.clear()
}

async function getJSON<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const ttl = opts.ttlMs ?? DEFAULT_TTL_MS
  if (ttl > 0) {
    const hit = cache.get(path)
    if (hit && Date.now() - hit.at < ttl) return hit.data as T
  }
  // Dedupe is restricted to signal-less callers: a shared promise would let one
  // consumer's abort reject an unrelated consumer. Signal-carrying callers
  // (pages, via useAsyncData) own their request and cancel only their own.
  if (opts.signal) {
    const data = await getWithRetry<T>(path, opts)
    if (ttl > 0) cache.set(path, { at: Date.now(), data })
    return data
  }
  const running = inflight.get(path)
  if (running) return running as Promise<T>
  const p = getWithRetry<T>(path, opts)
    .then((data) => {
      if (ttl > 0) cache.set(path, { at: Date.now(), data })
      return data
    })
    .finally(() => {
      if (inflight.get(path) === p) inflight.delete(path)
    })
  inflight.set(path, p)
  return p as Promise<T>
}

// Mutations are never retried, never cached, never deduped (not idempotent). The ONE
// exception is a REJECTED TOKEN: the backend mints a new token on every restart,
// so a long-open tab holds a stale one. A 401/403 is raised by the dependency
// BEFORE the endpoint body runs, so re-reading /session and replaying the call
// once cannot double-fire a refresh or a paid LLM call.
async function mutateJSON<T>(path: string, method: 'POST' | 'PUT' | 'DELETE', opts: ReqOpts): Promise<T> {
  try {
    return await attempt<T>(path, method, opts)
  } catch (e) {
    const err = e as ApiError
    if (err.status !== 401 && err.status !== 403) throw err
    forgetToken()
    return attempt<T>(path, method, opts)
  }
}

async function postJSON<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  return mutateJSON(path, 'POST', opts)
}

async function putJSON<T>(path: string, body: unknown, opts: ReqOpts = {}): Promise<T> {
  return mutateJSON(path, 'PUT', { ...opts, body })
}

async function delJSON<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  return mutateJSON(path, 'DELETE', opts)
}

// build "?a=..&b=.." from defined pairs (URLSearchParams drops undefined
// values when set with undefined, but filtering explicitly is safer).
function qs(pairs: Array<[string, string | undefined]>): string {
  const q = new URLSearchParams()
  for (const [k, v] of pairs) if (v) q.set(k, v)
  return q.toString() ? '?' + q.toString() : ''
}

// Polling / status endpoints must never read a cached body.
const NO_CACHE: ReqOpts = { ttlMs: 0 }

/**
 * What the two refresh POSTs return now (F4): they only START the background job
 * and hand back its `job_id`, which `GET …/refresh/stream?job_id=…` subscribes
 * to. `job_id === null` means nothing was started (pool saturated / busy) and
 * `msg` says why. The final result still arrives on the stream's `done` event.
 */
export interface JobStarted {
  status: string
  msg?: string
  ts?: string | null
  job_id: string | null
}

export const api = {
  getDerivedMonthly: (start?: string, end?: string, cols?: string, alignStart?: boolean, opts?: ReqOpts) =>
    getJSON<DerivedFrame>(`/derived/monthly${qs([['start', start], ['end', end], ['cols', cols], ['align_start', alignStart ? 'true' : undefined]])}`, opts),
  getDerivedQuarterly: (start?: string, end?: string, opts?: ReqOpts) =>
    getJSON<DerivedFrame>(`/derived/quarterly${qs([['start', start], ['end', end]])}`, opts),
  getTable: (name: string, start?: string, end?: string, opts?: ReqOpts) =>
    getJSON<DerivedFrame>(`/table/${name}${qs([['start', start], ['end', end]])}`, opts),
  getCycle: (name: string, start?: string, end?: string, opts?: ReqOpts) =>
    getJSON<CycleFrame>(`/cycles/${name}${qs([['start', start], ['end', end]])}`, opts),
  getSignals: (opts?: ReqOpts) => getJSON<SignalSummary>('/signals', opts),
  getSignalHistory: (limit?: number, opts?: ReqOpts) =>
    getJSON<SignalHistory>(`/signals/history${qs([['limit', limit?.toString()]])}`, opts),
  // cities as repeated query params (?cities=北京&cities=上海) — robust vs proxies.
  // frames=false → 仅 assessment（三维帧 ~199KB 白传；雷达/摘要只需 assessment）
  getRealEstate: (cities?: string[], opts?: ReqOpts, frames = false) => {
    const q = new URLSearchParams()
    for (const c of cities ?? []) q.append('cities', c)
    if (frames) q.set('frames', 'true')
    const s = q.toString()
    return getJSON<RealEstateResponse>(`/real-estate${s ? '?' + s : ''}`, opts)
  },
  getRefreshStatus: (opts?: ReqOpts) => getJSON<RefreshResult>('/refresh/status', { ...NO_CACHE, ...opts }),
  // Starts the job and returns its id; progress comes from /refresh/stream?job_id=…
  triggerRefresh: (full?: boolean, opts?: ReqOpts) =>
    postJSON<JobStarted>(`/refresh${qs([['full', full ? '1' : undefined]])}`, opts),
  triggerCrclRefresh: (opts?: ReqOpts) => postJSON<JobStarted>('/crcl/refresh', opts),
  getSourcesHealth: (opts?: ReqOpts) => getJSON<SourcesHealth>('/sources/health', opts),
  getCommentary: (opts?: ReqOpts) => getJSON<Commentary>('/commentary', { ...NO_CACHE, ...opts }),
  // 同步重新生成：最坏 9 次串行模型调用，前端 30s abort 后后端仍在跑——调用方需按
  // 超时→轮询处理（CommentaryCard 已内置该逻辑）
  regenerateCommentary: (opts?: ReqOpts) => postJSON<Commentary>('/commentary/regenerate', opts),
  // 评论批次历史（M4c）：索引 / 单批详情
  getCommentaryHistory: (opts?: ReqOpts) => getJSON<CommentaryHistoryIndex>('/commentary/history', opts),
  getCommentaryBatch: (ts: string, opts?: ReqOpts) =>
    getJSON<Commentary>(`/commentary/history${qs([['ts', ts]])}`, opts),
  // AI 配置（M4a）：profiles CRUD / 连接测试 / 默认项；M4c：模板覆盖
  getAiProfiles: (opts?: ReqOpts) => getJSON<AiProfileList>('/ai/profiles', opts),
  createAiProfile: (p: unknown, opts?: ReqOpts) => postJSON<AiProfile>('/ai/profiles', { ...opts, body: p }),
  updateAiProfile: (name: string, p: unknown, opts?: ReqOpts) =>
    putJSON<AiProfile>(`/ai/profiles/${encodeURIComponent(name)}`, p, opts),
  deleteAiProfile: (name: string, opts?: ReqOpts) =>
    delJSON<{ status: string }>(`/ai/profiles/${encodeURIComponent(name)}`, opts),
  testAiProfile: (name: string, opts?: ReqOpts) =>
    postJSON<AiTestResult>(`/ai/profiles/${encodeURIComponent(name)}/test`, opts),
  setAiActive: (name: string, opts?: ReqOpts) => postJSON<AiProfileList>('/ai/active', { ...opts, body: { name } }),
  getAiTemplates: (opts?: ReqOpts) => getJSON<AiTemplatesOut>('/ai/templates', opts),
  saveAiTemplates: (templates: Record<string, string>, opts?: ReqOpts) =>
    putJSON<AiTemplatesSaved>('/ai/templates', { templates }, opts),
  // CRCL 监控
  getCrclOverview: (opts?: ReqOpts) => getJSON<CrclOverview>('/crcl/overview', opts),
  getCrclMetrics: (keys?: string, opts?: ReqOpts) =>
    getJSON<{ metrics: Record<string, CrclMetric> }>(`/crcl/metrics${qs([['keys', keys]])}`, opts),
  getCrclEvents: (opts?: ReqOpts) => getJSON<{ updated_at: string | null; events: CrclEvent[] }>('/crcl/events', opts),
  getCrclAlerts: (opts?: ReqOpts) => getJSON<{ rules: CrclAlertRule[]; history: CrclLogRow[] }>('/crcl/alerts', opts),
  getCrclLogs: (limit = 60, opts?: ReqOpts) => getJSON<{ logs: CrclLogRow[] }>(`/crcl/logs?limit=${limit}`, opts),
  getCrclFundamentals: (opts?: ReqOpts) => getJSON<CrclFundamentals>('/crcl/fundamentals', opts),
}
