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

// Format a date-ish axis value to YYYY-MM-DD (drop any time component).
// Tolerates Date objects, ISO strings, and plain date strings; passes through
// anything that isn't date-like (so value axes / scatter are unaffected).
export function fmtDate(v: unknown): string {
  if (v == null) return ''
  const s = v instanceof Date ? v.toISOString() : String(v)
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : s
}

// Axis tooltip formatter — forces the date header to YYYY-MM-DD (no H:M:S,
// which ECharts can otherwise inject when the category looks date-like) and
// renders each series with a clean number. Only used for trigger:'axis'.
function fmtNum(v: unknown): string {
  if (v == null || v === '' || (typeof v === 'number' && Number.isNaN(v))) return '—'
  return typeof v === 'number' ? v.toFixed(2) : String(v)
}
const axisTooltipFormatter = (params: any): string => {
  const arr = Array.isArray(params) ? params : [params]
  if (!arr.length) return ''
  const p0 = arr[0]
  const header = fmtDate(p0.axisValue ?? p0.name)
  let html = `<div style="font-weight:600;margin-bottom:4px">${header}</div>`
  for (const p of arr) {
    const v = (Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value)
    html += `<div>${p.marker ?? ''} ${p.seriesName ?? ''}: <b>${fmtNum(v)}</b></div>`
  }
  return html
}

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
      labelFormatter: (v: unknown) => fmtDate(v),
    },
    // inside: drag-to-pan/zoom stays, but the mouse wheel is disabled so it
    // can't be triggered by accident while scrolling the page. Zoom via the
    // slider (below) or a click-drag on the chart instead.
    {
      type: 'inside', xAxisIndex: 0,
      zoomOnMouseWheel: false, moveOnMouseWheel: false,
    },
  ]
}

// Force category axes whose data looks date-like to render as YYYY-MM-DD.
const applyDateFormat = (merged: Record<string, any>) => {
  const xa = merged.xAxis
  const fmt = (ax: any) => {
    if (!ax || ax.type !== 'category' || !Array.isArray(ax.data) || !ax.data.length) return
    if (!/^\d{4}-\d{2}-\d{2}/.test(String(ax.data[0]))) return
    ax.axisLabel = { ...(ax.axisLabel || {}), formatter: fmtDate }
  }
  if (Array.isArray(xa)) xa.forEach(fmt)
  else fmt(xa)
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
  // force the date header (no H:M:S) in axis tooltips + the crosshair axis label
  if (merged.tooltip?.trigger === 'axis' && !option.tooltip?.formatter) {
    merged.tooltip.formatter = axisTooltipFormatter
  }
  if (merged.tooltip?.axisPointer) {
    merged.tooltip.axisPointer.label = {
      ...(merged.tooltip.axisPointer.label || {}),
      formatter: (p: any) => fmtDate(p.value),
    }
  }
  applyDateFormat(merged)
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
