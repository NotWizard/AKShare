// ECharts theme — 双主题图表默认（暗 Obsidian Blue / 亮 Paper），经 `applyTheme()` 合入每个 option。
// COLORS/PALETTE 等颜色随主题切换：全部经 chartTheme() 按当前主题即时取值（调用方为纯函数，
// 页面 option computed 依赖 themeVersion 触发重建）。

import { isLight } from '@/stores/theme'

const DARK = {
  colors: {
    bg: '#070b12',
    card: '#101a2b',
    grid: 'rgba(148,163,184,0.06)',
    gridHi: 'rgba(148,163,184,0.10)',
    border: 'rgba(148,163,184,0.14)',
    text: '#e8eef7',
    text2: '#9baac0',
    text3: '#7c8da5',
    text4: '#7f90a4',
    accent: '#5b8cff',
    accentHi: '#7fa6ff',
    accentInk: '#06122b',
    accentSoft: 'rgba(91,140,255,0.14)',
    up: '#34d399',
    down: '#f87171',
    warn: '#fbbf24',
    info: '#60a5fa',
    tooltipBg: 'rgba(12,19,34,0.92)',
    zoomTrack: 'rgba(148,163,184,0.05)',
    zoomFill: 'rgba(91,140,255,0.14)',
    zoomHandle: '#5b8cff',
    zoomMove: 'rgba(91,140,255,0.35)',
    zoomDataLine: 'rgba(148,163,184,0.25)',
    zoomDataArea: 'rgba(148,163,184,0.08)',
    pointer: 'rgba(91,140,255,0.35)',
  },
  palette: ['#5b8cff', '#a78bfa', '#fbbf24', '#34d399', '#f87171', '#60a5fa', '#fb923c', '#f472b6'],
}

const LIGHT = {
  colors: {
    bg: '#f6f7f9',
    card: '#ffffff',
    grid: 'rgba(100,116,139,0.12)',
    gridHi: 'rgba(100,116,139,0.18)',
    border: '#e3e8ef',
    text: '#0f172a',
    text2: '#334155',
    text3: '#475569',
    text4: '#64748b',
    accent: '#2f5bff',
    accentHi: '#1e40af',
    accentInk: '#ffffff',
    accentSoft: 'rgba(47,91,255,0.10)',
    up: '#059669',
    down: '#dc2626',
    warn: '#b45309',
    info: '#2563eb',
    tooltipBg: 'rgba(255,255,255,0.96)',
    zoomTrack: 'rgba(100,116,139,0.08)',
    zoomFill: 'rgba(47,91,255,0.10)',
    zoomHandle: '#2f5bff',
    zoomMove: 'rgba(47,91,255,0.30)',
    zoomDataLine: 'rgba(100,116,139,0.35)',
    zoomDataArea: 'rgba(100,116,139,0.10)',
    pointer: 'rgba(47,91,255,0.35)',
  },
  palette: ['#2f5bff', '#7c3aed', '#b45309', '#047857', '#dc2626', '#2563eb', '#c2410c', '#db2777'],
}

export type ChartTheme = { colors: typeof DARK.colors; palette: string[] }

/** 当前主题的图表色板（暗/亮）。 */
export function chartTheme(): ChartTheme {
  return isLight() ? LIGHT : DARK
}

// Common axis style — equivalent to CHART_DEFAULTS.xaxis (spike crosshair etc.)
export const baseAxis = (extra: Record<string, unknown> = {}) => ({
  axisLine: { lineStyle: { color: chartTheme().colors.border } },
  axisTick: { show: false },
  axisLabel: { color: chartTheme().colors.text3, fontSize: 11 },
  splitLine: { show: true, lineStyle: { color: chartTheme().colors.grid } },
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

// 轴刻度日期按时间跨度抽稀：>8 年标年份，且标在「每年第一个出现的类目」上——
// 不能写死 1 月：NBS 月度财政等序列 1 月不发布（无 2019-01 类目），写死会整年丢标签。
// interval 必须为 0（让 formatter 看到每个类目；auto 抽样会漏掉首月）。空串标签零宽度。
// 2.5–8 年标到月（月月唯一）；更短保留全日。tooltip 表头始终全日。
function axisDateFormatter(data: unknown[]): (v: unknown) => string {
  const ts = data.map((d) => Date.parse(String(d))).filter((t) => !Number.isNaN(t))
  const spanYears = ts.length > 1 ? (Math.max(...ts) - Math.min(...ts)) / (365.25 * 864e5) : 0
  const idxOf = new Map(data.map((d, i) => [fmtDate(d), i]))
  return (v: unknown) => {
    const s = fmtDate(v)
    if (!/^\d{4}-\d{2}-\d{2}/.test(s)) return s
    if (spanYears > 8) {
      const i = idxOf.get(s) ?? 0
      const prev = i > 0 ? String(fmtDate(data[i - 1])) : ''
      return prev.slice(0, 4) === s.slice(0, 4) ? '' : s.slice(0, 4)
    }
    if (spanYears > 2.5) return s.slice(0, 7)
    return s
  }
}

/** >8 年跨度走 interval:0 + formatter 门控（见 axisDateFormatter 注释）。 */
function isLongSpan(data: unknown[]): boolean {
  const ts = data.map((d) => Date.parse(String(d))).filter((t) => !Number.isNaN(t))
  return ts.length > 1 && (Math.max(...ts) - Math.min(...ts)) / (365.25 * 864e5) > 8
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
  const C = chartTheme().colors
  return [
    {
      type: 'slider', xAxisIndex: 0, bottom: 6, height: 14,
      borderColor: 'transparent', backgroundColor: C.zoomTrack,
      fillerColor: C.zoomFill,
      handleStyle: { color: C.zoomHandle, borderColor: 'transparent' },
      moveHandleStyle: { color: C.zoomMove },
      dataBackground: { lineStyle: { color: C.zoomDataLine }, areaStyle: { color: C.zoomDataArea } },
      textStyle: { color: C.text3, fontSize: 9 },
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

// Force category axes whose data looks date-like to render with span-aware labels.
const applyDateFormat = (merged: Record<string, any>) => {
  const xa = merged.xAxis
  const fmt = (ax: any) => {
    if (!ax || ax.type !== 'category' || !Array.isArray(ax.data) || !ax.data.length) return
    if (!/^\d{4}-\d{2}-\d{2}/.test(String(ax.data[0]))) return
    ax.axisLabel = {
      ...(ax.axisLabel || {}),
      formatter: axisDateFormatter(ax.data),
      // interval:0 让 formatter 看到每个类目（auto 抽样会跳过首月导致整年丢标签）；
      // hideOverlap 再把过密的年份标签抽稀（空串零宽度不参与重叠计算）。
      ...(isLongSpan(ax.data) ? { interval: 0 } : {}),
      hideOverlap: true,
    }
  }
  if (Array.isArray(xa)) xa.forEach(fmt)
  else fmt(xa)
}

// Chart "layout" defaults merged into every chart option (≈ _apply_layout).
// tooltip / legend are deep-merged so a builder that sets its own tooltip
// (e.g. scatter trigger:'item') keeps the theme's colors/confine.
export function applyTheme(option: Record<string, any>): Record<string, any> {
  const C = chartTheme().colors
  const base = {
    backgroundColor: 'transparent',
    color: chartTheme().palette,
    textStyle: { color: C.text2, fontFamily: 'inherit', fontSize: 12 },
    grid: { left: 52, right: 24, top: 32, bottom: 60 },   // +bottom room for the dataZoom slider
    tooltip: {
      trigger: 'axis',
      confine: true,        // keep tooltip inside the chart container (fix: clipped tooltips)
      appendToBody: true,    // render to <body> so ancestor overflow can't clip it
      backgroundColor: C.tooltipBg,
      borderColor: C.border,
      borderWidth: 1,
      padding: [8, 12],
      extraCssText: 'border-radius:10px;backdrop-filter:blur(6px);box-shadow:0 8px 24px rgba(0,0,0,0.25);font-variant-numeric:tabular-nums;',
      textStyle: { color: C.text, fontSize: 12 },
      axisPointer: {
        type: 'cross',
        lineStyle: { color: C.pointer, type: 'dashed' },
        crossStyle: { color: C.pointer, type: 'dashed' },
        label: { backgroundColor: C.tooltipBg, borderColor: C.border, color: C.text2 },
      },
    },
    legend: {
      textStyle: { color: C.text2, fontSize: 11 },
      top: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      inactiveColor: C.text4,
    },
    aria: {
      enabled: true,
      label: { description: '时间序列图表，详见 tooltip 与图例' },
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
