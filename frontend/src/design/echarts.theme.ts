// ECharts theme — Observatory Dark 图表默认。经 `applyTheme()` 合入每个 option。

export const PALETTE = ['#22d3ee', '#a78bfa', '#fbbf24', '#34d399', '#f87171', '#60a5fa', '#f97316', '#ec4899']

export const COLORS = {
  bg: '#070b12',
  card: '#101a2b',
  grid: 'rgba(148,163,184,0.06)',
  gridHi: 'rgba(148,163,184,0.10)',
  border: 'rgba(148,163,184,0.14)',
  text: '#e8eef7',
  text2: '#9baac0',
  text3: '#7c8da5',
  accent: '#22d3ee',
  up: '#34d399',
  down: '#f87171',
  warn: '#fbbf24',
  info: '#60a5fa',
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
  return [
    {
      type: 'slider', xAxisIndex: 0, bottom: 6, height: 14,
      borderColor: 'transparent', backgroundColor: 'rgba(148,163,184,0.05)',
      fillerColor: 'rgba(34,211,238,0.12)',
      handleStyle: { color: COLORS.accent, borderColor: 'transparent' },
      moveHandleStyle: { color: 'rgba(34,211,238,0.35)' },
      dataBackground: { lineStyle: { color: 'rgba(148,163,184,0.25)' }, areaStyle: { color: 'rgba(148,163,184,0.08)' } },
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

// Downsample long line series: real series carry ~3187 points into charts a few
// hundred px tall, where LTTB keeps the visual shape at a fraction of the draw
// cost. Centralised here so no builder has to remember it (an explicit
// `sampling` on a series still wins).
const applySampling = (merged: Record<string, any>) => {
  const series = merged.series
  if (!Array.isArray(series)) return
  for (const s of series) {
    // stacked series are skipped: LTTB may keep different x positions per series,
    // which would misalign the stack.
    if (s && s.type === 'line' && s.sampling === undefined && !s.stack) s.sampling = 'lttb'
  }
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
      backgroundColor: 'rgba(12,19,34,0.92)',
      borderColor: 'rgba(148,163,184,0.18)',
      borderWidth: 1,
      padding: [8, 12],
      extraCssText: 'border-radius:10px;backdrop-filter:blur(6px);box-shadow:0 8px 24px rgba(0,0,0,0.35);font-variant-numeric:tabular-nums;',
      textStyle: { color: COLORS.text, fontSize: 12 },
      axisPointer: {
        type: 'cross',
        lineStyle: { color: 'rgba(34,211,238,0.35)', type: 'dashed' },
        crossStyle: { color: 'rgba(34,211,238,0.35)', type: 'dashed' },
        label: { backgroundColor: '#0c1322', borderColor: 'rgba(148,163,184,0.18)', color: COLORS.text2 },
      },
    },
    legend: {
      textStyle: { color: COLORS.text2, fontSize: 11 },
      top: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      inactiveColor: '#4b5a70',
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
  applySampling(merged)
  return merged
}
