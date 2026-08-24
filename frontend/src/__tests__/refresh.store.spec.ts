import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useRefreshStore } from '@/stores/refresh'

// stores/refresh.ts 的 SSE 解析（FE-H4 + FE-L2）：分帧、progress 递增、done 触发
// markRefreshed（同时清缓存并 bump *_refreshedAt）、job_id=null 不订阅、单个畸形
// 事件不杀流、以及网关早关（无 done）时不谎报成功。

function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(c) {
      const enc = new TextEncoder()
      for (const chunk of chunks) c.enqueue(enc.encode(chunk))
      c.close()
    },
  })
}

function sseRes(chunks: string[]): Response {
  return {
    ok: true, status: 200, body: sseStream(chunks),
  } as unknown as Response
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.unstubAllGlobals() })

describe('refresh.stream', () => {
  it('macro 路径：POST 拿 job_id → GET stream → progress+done → markRefreshed', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/session')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ token: 'T' }), text: async () => '' } as Response)
      if ((init?.method === 'POST') && String(url).includes('/refresh')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'running', job_id: 'JOB1' }), text: async () => '' } as Response)
      }
      if (String(url).includes('/refresh/stream')) {
        // 两个 SSE 事件塞在一个 chunk（测分帧），第三块跨帧
        return Promise.resolve(sseRes([
          'data: {"progress":0.5}\n\ndata: {"progress":0.9}\n\n',
          'data: {"done":true,"result":{"msg":"ok","ts":"2026-08-24T00:00:00"}}\n\n',
        ]))
      }
      if (String(url).endsWith('/sources/health')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ sources: {}, level: 'unknown' }), text: async () => '' } as Response)
      throw new Error('unexpected url ' + url)
    })

    const s = useRefreshStore()
    const before = s.lastRefreshedAt
    await s.stream()
    expect(s.progress).toBe(0.9)
    expect(s.lastResult).toEqual({ msg: 'ok', ts: '2026-08-24T00:00:00' })
    expect(s.lastRefreshedAt).toBeGreaterThan(before)
    expect(s.running).toBe(false)
    // subscribe GET 必须带 job_id
    const streamCall = fetchMock.mock.calls.find(([u]) => String(u).includes('/refresh/stream'))!
    expect(String(streamCall[0])).toContain('job_id=JOB1')
  })

  it('crcl 路径独立 bump crclRefreshedAt（FE-H4）', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/session')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ token: 'T' }), text: async () => '' } as Response)
      if ((init?.method === 'POST') && String(url).includes('/crcl/refresh')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'running', job_id: 'C1' }), text: async () => '' } as Response)
      }
      if (String(url).includes('/crcl/refresh/stream')) {
        return Promise.resolve(sseRes(['data: {"done":true,"result":{"msg":"crcl done","ts":null}}\n\n']))
      }
      if (String(url).endsWith('/sources/health')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ sources: {}, level: 'unknown' }), text: async () => '' } as Response)
      throw new Error('unexpected ' + url)
    })

    const s = useRefreshStore()
    const macroBefore = s.lastRefreshedAt
    const crclBefore = s.crclRefreshedAt
    await s.stream(false, 'crcl')
    expect(s.crclRefreshedAt).toBeGreaterThan(crclBefore)
    expect(s.lastRefreshedAt).toBe(macroBefore)   // macro 不受影响
  })

  it('job_id=null（池饱和）→ 只记 msg，不去订阅 stream', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/session')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ token: 'T' }), text: async () => '' } as Response)
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'busy', msg: '池已满', job_id: null }), text: async () => '' } as Response)
      }
      throw new Error('不应订阅 stream，但去调了 ' + url)
    })
    const s = useRefreshStore()
    await s.stream()
    expect(s.lastResult?.msg).toBe('池已满')
    expect(s.running).toBe(false)
    // 没有任何 stream 调用
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/refresh/stream'))).toBe(false)
  })

  it('单个畸形 SSE 事件不杀流：后续 done 仍生效', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/session')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ token: 'T' }), text: async () => '' } as Response)
      if (init?.method === 'POST') return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'running', job_id: 'J' }), text: async () => '' } as Response)
      if (String(url).includes('/refresh/stream')) {
        return Promise.resolve(sseRes([
          'data: {not json\n\n',
          'data: {"progress":0.3}\n\n',
          'data: {"done":true,"result":{"msg":"done despite garbage","ts":null}}\n\n',
        ]))
      }
      if (String(url).endsWith('/sources/health')) return Promise.resolve({ ok: true, status: 200, json: async () => ({}), text: async () => '' } as Response)
      throw new Error('unexpected ' + url)
    })
    const s = useRefreshStore()
    await s.stream()
    expect(s.progress).toBe(0.3)
    expect(s.lastResult?.msg).toBe('done despite garbage')
  })

  it('流被对端提前关闭（无 done）→ 不谎报成功', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/session')) return Promise.resolve({ ok: true, status: 200, json: async () => ({ token: 'T' }), text: async () => '' } as Response)
      if (init?.method === 'POST') return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'running', job_id: 'J' }), text: async () => '' } as Response)
      if (String(url).includes('/refresh/stream')) {
        return Promise.resolve(sseRes(['data: {"progress":0.5}\n\n']))   // 无 done 就关
      }
      throw new Error('unexpected ' + url)
    })
    const s = useRefreshStore()
    await s.stream()
    expect(s.lastResult?.msg).toContain('意外结束')
    expect(s.progress).toBe(0.5)   // 已收的 progress 保留
  })
})
