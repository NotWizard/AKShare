// API client — typed wrappers over the FastAPI endpoints. Types mirror the
// Pydantic schemas (single source of truth via shared/openapi.json codegen; P0
// ships hand-written types, `npm run gen:api` regenerates from OpenAPI).
import type { DerivedFrame, CycleFrame, SignalSummary, RefreshResult, RealEstateResponse } from './types'

const BASE = '/api/v1'

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) {
    const body = (await resp.text()).slice(0, 200)
    throw new Error(`${resp.status} ${body}`)
  }
  return resp.json()
}

async function postJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { method: 'POST' })
  if (!resp.ok) {
    const body = (await resp.text()).slice(0, 200)
    throw new Error(`${resp.status} ${body}`)
  }
  return resp.json()
}

// build "?a=..&b=.." from defined pairs (URLSearchParams drops undefined
// values when set with undefined, but filtering explicitly is safer).
function qs(pairs: Array<[string, string | undefined]>): string {
  const q = new URLSearchParams()
  for (const [k, v] of pairs) if (v) q.set(k, v)
  return q.toString() ? '?' + q.toString() : ''
}

export const api = {
  getDerivedMonthly: (start?: string, end?: string, cols?: string) =>
    getJSON<DerivedFrame>(`/derived/monthly${qs([['start', start], ['end', end], ['cols', cols]])}`),
  getDerivedQuarterly: (start?: string, end?: string) =>
    getJSON<DerivedFrame>(`/derived/quarterly${qs([['start', start], ['end', end]])}`),
  getTable: (name: string, start?: string, end?: string) =>
    getJSON<DerivedFrame>(`/table/${name}${qs([['start', start], ['end', end]])}`),
  getCycle: (name: string, start?: string, end?: string) =>
    getJSON<CycleFrame>(`/cycles/${name}${qs([['start', start], ['end', end]])}`),
  getSignals: () => getJSON<SignalSummary>('/signals'),
  // cities as repeated query params (?cities=北京&cities=上海) — robust vs proxies.
  getRealEstate: (cities?: string[]) => {
    if (!cities?.length) return getJSON<RealEstateResponse>('/real-estate')
    const q = new URLSearchParams()
    for (const c of cities) q.append('cities', c)
    return getJSON<RealEstateResponse>(`/real-estate?${q.toString()}`)
  },
  getRefreshStatus: () => getJSON<RefreshResult>('/refresh/status'),
  triggerRefresh: () => postJSON<RefreshResult>('/refresh'),
}
