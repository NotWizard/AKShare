// ECharts theme — the Terminal Fintech chart defaults (mirror config.py
// CHART_LAYOUT + CHART_DEFAULTS). Merged into each chart's option via
// `baseGrid()` / `applyTheme()`.

export const PALETTE = ['#6366f1', '#10b981', '#ef4444', '#f59e0b', '#a78bfa', '#06b6d4', '#f97316', '#ec4899']

export const COLORS = {
  bg: '#0a0e17',
  card: '#1a2332',
  grid: 'rgba(148,163,184,0.05)',
  gridHi: 'rgba(148,163,184,0.08)',
  border: 'rgba(255,255,255,0.06)',
  text: '#f1f5f9',
  text2: '#94a3b8',
  text3: '#64748b',
  accent: '#6366f1',
  up: '#10b981',
  down: '#ef4444',
  warn: '#f59e0b',
  info: '#3b82f6',
}

// Common axis style — equivalent to CHART_DEFAULTS.xaxis (spike crosshair etc.)
export const baseAxis = (extra: Record<string, unknown> = {}) => ({
  axisLine: { lineStyle: { color: COLORS.border } },
  axisTick: { show: false },
  axisLabel: { color: COLORS.text3, fontSize: 11 },
  splitLine: { show: true, lineStyle: { color: COLORS.grid } },
  ...extra,
})

// Chart "layout" defaults merged into every chart option (≈ _apply_layout).
export function applyTheme(option: Record<string, any>): Record<string, any> {
  return {
    backgroundColor: 'transparent',
    color: PALETTE,
    textStyle: { color: COLORS.text2, fontFamily: 'inherit', fontSize: 12 },
    grid: { left: 52, right: 20, top: 32, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1e293b',
      borderColor: 'rgba(255,255,255,0.10)',
      textStyle: { color: COLORS.text, fontSize: 12 },
      axisPointer: {
        type: 'cross',
        lineStyle: { color: 'rgba(148,163,184,0.35)', type: 'dashed' },
        crossStyle: { color: 'rgba(148,163,184,0.35)', type: 'dashed' },
      },
    },
    legend: {
      textStyle: { color: COLORS.text2, fontSize: 11 },
      top: 0,
      itemWidth: 12,
      itemHeight: 12,
    },
    ...option,
  }
}

// Line series default — connectNulls:true bridges gaps natively (the Dash
// connectgaps fix, but cleaner: one flag per series).
export const baseLine = (extra: Record<string, unknown> = {}) => ({
  type: 'line',
  smooth: false,
  connectNulls: true,
  symbol: 'none',
  lineStyle: { width: 2 },
  ...extra,
})
