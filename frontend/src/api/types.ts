// API types — mirror backend Pydantic schemas (regenerable via `npm run gen:api`).

export interface DerivedFrame {
  table: string
  columns: string[]
  records: Array<Record<string, string | number | null>>
}

export interface CycleFrame {
  series: Array<Record<string, string | number | null>>
  latest_phase: string | null
  latest_value: number | null
  value_col: string | null
}

export interface SignalSummary {
  merrill: Record<string, unknown>
  credit: Record<string, unknown>
  inventory: Record<string, unknown>
  debt: Record<string, unknown>
  cross_lags: Record<string, unknown>
  composite_score: number
  interpretation: string
}

export interface RefreshResult {
  status: 'ok' | 'busy' | 'error' | 'unknown'
  msg: string
  ts: string | null
  updated: string[]
  kept_previous: string[]
  busy?: boolean
  detail?: string | null
}
