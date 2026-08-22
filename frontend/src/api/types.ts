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
  // F12：原 detail 会外泄子进程 traceback 与绝对路径，已改为只回 8 位 error_id，
  // 完整详情留在服务端日志里按 id 检索。
  error_id?: string | null
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

// ---------- CRCL 监控 ----------
export interface CrclPoint { date: string; value: number }

export interface CrclMetric {
  label: string
  unit: string
  source: string
  freq: string
  points: CrclPoint[]
}

export interface CrclOverview {
  snapshots: Record<string, Record<string, number | string | null>>
  alert_summary: {
    triggered: Array<{ rule: string; level: string; status: string; message: string }>
    levels: Record<string, string>
    rule_count: number
  }
  last_run: { run_id: string; source: string; status: string; message: string; duration_ms: number; ts: string } | null
  metric_labels: Record<string, [string, string, string, string]>
}

export interface CrclEvent {
  date: string
  category: string
  title: string
  detail: string
  source: string
  status: string
}

export interface CrclAlertRule {
  rule: string
  level: string
  description: string
  status: string
  message: string
  ts: string | null
}

export interface CrclLogRow {
  run_id: string
  source: string
  status: string
  message: string
  duration_ms: number
  ts: string
}

export interface CrclFundamentals {
  updated_at?: string
  flags?: Record<string, boolean>
  quarters?: Array<Record<string, number | string | null>>
  annual?: Array<Record<string, number | string | null>>
  presale?: Record<string, number>
  error?: string
}
