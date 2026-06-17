// API client — typed wrappers over the FastAPI endpoints. Types mirror the
// Pydantic schemas (single source of truth via shared/openapi.json codegen; P0
// ships hand-written types, `npm run gen:api` regenerates from OpenAPI).
import type { DerivedFrame, CycleFrame, SignalSummary, RefreshResult } from './types'

const BASE = '/api/v1'

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`)
  return resp.json()
}

async function postJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { method: 'POST' })
  if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`)
  return resp.json()
}

export const api = {
  getDerivedMonthly: (start?: string, end?: string, cols?: string) => {
    const q = new URLSearchParams()
    if (start) q.set('start', start)
    if (end) q.set('end', end)
    if (cols) q.set('cols', cols)
    return getJSON<DerivedFrame>(`/derived/monthly${q.size ? '?' + q : ''}`)
  },
  getDerivedQuarterly: (start?: string, end?: string) => {
    const q = new URLSearchParams()
    if (start) q.set('start', start)
    if (end) q.set('end', end)
    return getJSON<DerivedFrame>(`/derived/quarterly${q.size ? '?' + q : ''}`)
  },
  getTable: (name: string, start?: string, end?: string) => {
    const q = new URLSearchParams()
    if (start) q.set('start', start)
    if (end) q.set('end', end)
    return getJSON<DerivedFrame>(`/table/${name}${q.size ? '?' + q : ''}`)
  },
  getCycle: (name: string, start?: string, end?: string) => {
    const q = new URLSearchParams()
    if (start) q.set('start', start)
    if (end) q.set('end', end)
    return getJSON<CycleFrame>(`/cycles/${name}${q.size ? '?' + q : ''}`)
  },
  getSignals: () => getJSON<SignalSummary>('/signals'),
  getRealEstate: (cities?: string[]) =>
    getJSON<Record<string, any>>(`/real-estate${cities ? '?cities=' + encodeURIComponent(cities.join(',')) : ''}`),
  getRefreshStatus: () => getJSON<RefreshResult>('/refresh/status'),
  triggerRefresh: () => postJSON<RefreshResult>('/refresh'),
}
