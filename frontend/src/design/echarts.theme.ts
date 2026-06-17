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

// Default dataZoom — slider (bottom) + inside (drag on chart). Applied only to
// category (time) axes so scatter/radar are unaffected.
const dataZoomForCategory = (option: Record<string, any>) => {
  const xa = option.xAxis
  const isCategory = Array.isArray(xa) ? xa.some((x) => x?.type === 'category') : xa?.type === 'category'
  if (!isCategory) return undefined
  return [
    {
      type: 'slider', xAxisIndex: 0, bottom: 6, height: 16,
      borderColor: 'transparent', backgroundColor: 'transparent',
      fillerColor: 'rgba(99,102,241,0.15)',
      handleStyle: { color: COLORS.accent, borderColor: COLORS.accent },
      moveHandleStyle: { color: 'rgba(99,102,241,0.4)' },
      textStyle: { color: COLORS.text3, fontSize: 9 },
      labelFormatter: (v: string) => (v ? String(v).slice(0, 7) : ''),
    },
    { type: 'inside', xAxisIndex: 0 },
  ]
}

// Chart "layout" defaults merged into every chart option (≈ _apply_layout).
// tooltip / legend are deep-merged so a builder that sets its own tooltip
// (e.g. scatter trigger:'item') keeps the theme's colors/confine.
export function applyTheme(option: Record<string, any>): Record<string, any> {
  const base = {
    backgroundColor: 'transparent',
    color: PALETTE,
    textStyle: { color: COLORS.text2, fontFamily: 'inherit', fontSize: 12 },
    grid: { left: 52, right: 24, top: 32, bottom: 60 },   // +bottom room for the dataZoom slider
    tooltip: {
      trigger: 'axis',
      confine: true,        // keep tooltip inside the chart container (fix: clipped tooltips)
      appendToBody: true,    // render to <body> so ancestor overflow can't clip it
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
  }
  const merged: Record<string, any> = { ...base, ...option }
  merged.tooltip = { ...base.tooltip, ...(option.tooltip || {}) }
  merged.legend = { ...base.legend, ...(option.legend || {}) }
  merged.dataZoom = option.dataZoom ?? dataZoomForCategory(option)
  return merged
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
