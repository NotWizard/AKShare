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

export interface SourceHealth {
  table: string
  channel: string
  ok: boolean
  elapsed_s: number | null
  error: string | null
  consecutive_failures: number
  last_success: string | null
  warning: string | null
}

export interface SourcesHealth {
  status: 'green' | 'yellow' | 'red'
  updated_at: string | null
  sources: SourceHealth[]
}

export interface RealEstateAssessment {
  leverage_space_score?: number
  price_momentum_score?: number
  rate_env_score?: number
  composite_score?: number
  summary?: string
}

export interface RealEstateResponse {
  assessment?: RealEstateAssessment
  [k: string]: unknown
}

export interface Commentary {
  ts: string | null
  data_as_of: string | null
  composite_score: number | null
  text: string
  model: string | null
  stale: boolean
  status: 'ok' | 'generating' | 'empty' | 'error'
  msg: string | null
}

export interface PhaseFlip {
  framework: string            // merrill | credit | inventory | debt
  prev: string | null
  curr: string | null
}

export interface SignalHistoryRow {
  ts: string
  data_as_of: string | null
  composite: number
  merrill: string | null
  credit: string | null
  inventory: string | null
  debt: string | null
  flips: PhaseFlip[]
}

export interface SignalHistory {
  items: SignalHistoryRow[]
}
