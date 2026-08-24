import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// client.ts 的公开契约测试（FE-M2/M3/M6 + F4 令牌）。只 mock 全局 fetch，其余全真：
// 重试/退避、TTL 缓存、in-flight 去重、POST 令牌与 401 重放、错误分类。
//
// client.ts 的 cache / inflight / tokenPromise 是**模块级单例**，会跨测试污染，
// 故每个测试用 vi.resetModules() + 动态 import 拿一份全新模块状态。

type Body = unknown

function res(status: number, body: Body): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response
}

async function freshClient() {
  vi.resetModules()
  return import('@/api/client')
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('GET：请求形状与缓存', () => {
  it('命中端点、method=GET、不带令牌头', async () => {
    const { api } = await freshClient()
    fetchMock.mockResolvedValueOnce(res(200, { composite_score: 1 }))
    const out = await api.getSignals()
    expect(out).toEqual({ composite_score: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/signals')
    expect(init.method).toBe('GET')
    expect(init.headers).toBeUndefined()   // 只读，无 capability
  })

  it('qs 丢弃 undefined 参数', async () => {
    const { api } = await freshClient()
    fetchMock.mockResolvedValueOnce(res(200, {}))
    await api.getDerivedMonthly('2020-01-01', undefined)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/derived/monthly?start=2020-01-01')
  })

  it('TTL 内相同 GET 命中缓存，只打一次网络', async () => {
    const { api } = await freshClient()
    fetchMock.mockResolvedValue(res(200, { v: 1 }))
    await api.getSignals()
    await api.getSignals()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('invalidateCache 后重新请求', async () => {
    const { api, invalidateCache } = await freshClient()
    fetchMock.mockResolvedValue(res(200, { v: 1 }))
    await api.getSignals()
    invalidateCache()
    await api.getSignals()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('NO_CACHE 端点（getRefreshStatus, ttl=0）每次都打网络', async () => {
    const { api } = await freshClient()
    fetchMock.mockResolvedValue(res(200, { msg: '', ts: null }))
    await api.getRefreshStatus()
    await api.getRefreshStatus()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('并发相同 GET 在飞去重，只打一次网络', async () => {
    const { api } = await freshClient()
    let release!: (r: Response) => void
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => { release = r }))
    const p1 = api.getSignals()
    const p2 = api.getSignals()
    release(res(200, { v: 9 }))
    const [a, b] = await Promise.all([p1, p2])
    expect(a).toEqual({ v: 9 })
    expect(b).toEqual({ v: 9 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('GET：重试与错误分类', () => {
  it('5xx 退避重试后成功', async () => {
    const { api } = await freshClient()
    fetchMock
      .mockResolvedValueOnce(res(503, {}))
      .mockResolvedValueOnce(res(200, { ok: 1 }))
    await expect(api.getSignals()).resolves.toEqual({ ok: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('传输失败重试到上限后抛 unreachable（默认 3 次）', async () => {
    const { api } = await freshClient()
    fetchMock.mockRejectedValue(new TypeError('failed to fetch'))
    await expect(api.getSignals()).rejects.toMatchObject({ kind: 'unreachable' })
    expect(fetchMock).toHaveBeenCalledTimes(3)   // 1 + MAX_RETRIES(2)
  })

  it('4xx 不重试，映射为 client + detail 取自 body', async () => {
    const { api } = await freshClient()
    fetchMock.mockResolvedValueOnce(res(422, { detail: '参数不合法' }))
    await expect(api.getSignals()).rejects.toMatchObject({
      kind: 'client', status: 422, detail: '参数不合法',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries=0 关闭重试', async () => {
    const { api } = await freshClient()
    fetchMock.mockResolvedValueOnce(res(503, {}))
    await expect(api.getSignals({ retries: 0 })).rejects.toMatchObject({
      kind: 'server', status: 503,
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('POST：令牌与 401 重放（F4）', () => {
  it('POST 先取 /session 令牌并带 X-API-Token 头', async () => {
    const { api } = await freshClient()
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(String(url).endsWith('/session')
        ? res(200, { token: 'T1' })
        : res(200, { status: 'running', job_id: 'j1' })))
    const out = await api.triggerRefresh()
    expect(out).toMatchObject({ job_id: 'j1' })
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'POST')!
    expect((post[1] as RequestInit).headers).toMatchObject({ 'X-API-Token': 'T1' })
  })

  it('POST 遇 401 → 重取令牌并重放一次，第二次带新令牌', async () => {
    const { api } = await freshClient()
    let session = 0
    let post = 0
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith('/session')) {
        session += 1
        return Promise.resolve(res(200, { token: session === 1 ? 'T1' : 'T2' }))
      }
      post += 1
      return Promise.resolve(post === 1 ? res(401, { detail: 'stale' }) : res(200, { job_id: 'j2' }))
    })
    const out = await api.triggerRefresh()
    expect(out).toMatchObject({ job_id: 'j2' })
    expect(session).toBe(2)   // 令牌被重取
    expect(post).toBe(2)      // POST 恰好重放一次
    const posts = fetchMock.mock.calls.filter((c) => (c[1] as RequestInit)?.method === 'POST')
    expect((posts[1][1] as RequestInit).headers).toMatchObject({ 'X-API-Token': 'T2' })
  })

  it('POST 遇 500（非 401/403）不重放', async () => {
    const { api } = await freshClient()
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(String(url).endsWith('/session')
        ? res(200, { token: 'T' })
        : res(500, { detail: 'boom' })))
    await expect(api.triggerRefresh()).rejects.toMatchObject({ kind: 'server', status: 500 })
    const posts = fetchMock.mock.calls.filter((c) => (c[1] as RequestInit)?.method === 'POST')
    expect(posts.length).toBe(1)   // 未重放
  })
})
