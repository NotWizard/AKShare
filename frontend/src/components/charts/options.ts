// ECharts option builders — one per chart family. Pure functions: records in,
// option out. Each applies the Terminal Fintech theme (≈ _apply_layout).

import { applyTheme, baseAxis, COLORS, PALETTE } from '@/design/echarts.theme'
import { phaseColor, phaseLabel } from '@/design/phases'
import { hexA, mergePhaseSegments } from './utils'

type Rec = Record<string, string | number | null>

/** Credit cycle flagship: M2 同比 line (connectNulls) + M2 趋势 dashed +
 *  phase-background markArea + the 1991–1996 source-gap markArea + caption. */
export function buildCreditM2Chart(derived: Rec[], cycle: Rec[]): Record<string, any> {
  const dates = derived.map((r) => r.date as string)
  const m2 = derived.map((r) => r.m2_yoy)
  const trendByDate = new Map(cycle.map((r) => [r.date as string, r.m2_trend as number | null]))
  const trend = dates.map((d) => trendByDate.get(d) ?? null)

  const segs = mergePhaseSegments(cycle).filter((s) => s.phase !== 'neutral')
  const phaseBg = segs.map((s) => [
    { xAxis: s.x0, itemStyle: { color: hexA(phaseColor(s.phase), 0.08) } },
    { xAxis: s.x1 },
  ])
  // Source-data gap disclosure (M2 monthly only from ~1997)
  const gapBg = [
    [
      { xAxis: '1991-01-01', itemStyle: { color: hexA(COLORS.warn, 0.07) } },
      { xAxis: '1996-12-01' },
    ],
  ]

  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '%', scale: true }) },
    series: [
      {
        name: 'M2同比',
        type: 'line', smooth: false, connectNulls: true, symbol: 'none',
        data: m2, lineStyle: { color: COLORS.accent, width: 2.5 },
        areaStyle: { opacity: 0.1 },
        markArea: { silent: true, data: [...phaseBg, ...gapBg] },
      },
      {
        name: 'M2趋势',
        type: 'line', connectNulls: true, symbol: 'none',
        data: trend, lineStyle: { color: COLORS.warn, width: 2, type: 'dashed' },
      },
    ],
    graphic: [{
      type: 'text', left: 'center', top: 30, z: 2,
      style: {
        text: '此段 M2 仅年度结存，月度源数据缺失',
        fill: COLORS.text3, fontSize: 10,
      },
    }],
  })
}

/** Credit impulse — bars (社融信贷脉冲). */
export function buildCreditImpulseChart(cycle: Rec[]): Record<string, any> {
  const dates = cycle.map((r) => r.date as string)
  const impulse = cycle.map((r) => r.credit_impulse as number | null)
  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis() },
    yAxis: { type: 'value', ...baseAxis({ name: '亿' }) },
    series: [
      {
        name: '信贷脉冲', type: 'bar',
        data: impulse,
        itemStyle: { color: hexA(COLORS.accent, 0.65) },
      },
    ],
  })
}

/** Dual-axis line — two series on TWO independent y-axes (different units).
 *  CPI vs PPI share the % axis; PMI (~50) vs IP-yoy (~5%) need separate axes. */
export function buildDualAxisLine(
  derived: Rec[], a: string, b: string,
  aColor = COLORS.accent, bColor = COLORS.up,
  aName?: string, bName?: string,
): Record<string, any> {
  const dates = derived.map((r) => r.date as string)
  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: [
      { type: 'value', name: aName ?? a, scale: true, ...baseAxis() },
      { type: 'value', name: bName ?? b, scale: true, ...baseAxis({ splitLine: { show: false } }) },
    ],
    series: [
      { name: a, type: 'line', yAxisIndex: 0, connectNulls: true, symbol: 'none',
        data: derived.map((r) => r[a]),
        lineStyle: { color: aColor, width: 2.5 }, areaStyle: { opacity: 0.08 } },
      { name: b, type: 'line', yAxisIndex: 1, connectNulls: true, symbol: 'none',
        data: derived.map((r) => r[b]),
        lineStyle: { color: bColor, width: 2 } },
    ],
  })
}

/** Stacked area — multiple series stacked (e.g. leverage by sector). */
export function buildStackedArea(
  derived: Rec[], cols: string[],
): Record<string, any> {
  const dates = derived.map((r) => r.date as string)
  const palette = ['#6366f1', '#10b981', '#f59e0b', '#3b82f6', '#a78bfa', '#06b6d4']
  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '%' }) },
    series: cols.map((c, i) => ({
      name: c, type: 'line', stack: 'total', connectNulls: true, symbol: 'none',
      areaStyle: { opacity: 0.12 },
      lineStyle: { width: 1.5, color: palette[i % palette.length] },
      data: derived.map((r) => r[c]),
    })),
  })
}

/** Scatter quadrant — x vs y coloured by phase (Merrill clock / inventory).
 *  Reference lines (PMI 50 / CPI 2% / …) live as markLine on an empty helper
 *  series — ECharts only renders markLine that is a child of a series. */
export function buildScatterQuadrant(
  cycle: Rec[], xKey: string, yKey: string,
  xLabel: string, yLabel: string, hline = 0, vline = 0,
): Record<string, any> {
  const byPhase = new Map<string, [number, number][]>()
  for (const r of cycle) {
    const x = r[xKey] as number | null
    const y = r[yKey] as number | null
    if (x == null || y == null) continue
    const p = (r.phase as string) ?? 'unknown'
    if (!byPhase.has(p)) byPhase.set(p, [])
    byPhase.get(p)!.push([x, y])
  }
  const refLines: any[] = []
  if (hline) refLines.push({ yAxis: hline })
  if (vline) refLines.push({ xAxis: vline })

  return applyTheme({
    xAxis: { type: 'value', name: xLabel, ...baseAxis({ name: xLabel }) },
    yAxis: { type: 'value', name: yLabel, ...baseAxis({ name: yLabel }) },
    tooltip: { trigger: 'item' },
    series: [
      ...Array.from(byPhase.entries()).map(([p, data]) => ({
        name: phaseLabel(p), type: 'scatter', data, symbolSize: 8,
        itemStyle: { color: phaseColor(p), opacity: 0.85 },
      })),
      // invisible helper series carrying the threshold cross-hairs
      {
        type: 'scatter', data: [], silent: true,
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: COLORS.text3, width: 1 },
          data: refLines,
        },
      },
    ],
  })
}

/** Radar — real-estate 3D assessment (leverage space / price momentum / rate env). */
export function buildRadar(assessment: {
  leverage_space_score?: number
  price_momentum_score?: number
  rate_env_score?: number
}): Record<string, any> {
  return applyTheme({
    tooltip: { trigger: 'item' },
    legend: { show: false },
    radar: {
      indicator: [
        { name: '杠杆空间', max: 100 },
        { name: '价格动能', max: 100 },
        { name: '利率环境', max: 100 },
      ],
      radius: '62%',
      axisName: { color: COLORS.text2, fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(148,163,184,0.03)', 'rgba(148,163,184,0.06)'] } },
      splitLine: { lineStyle: { color: COLORS.grid } },
      axisLine: { lineStyle: { color: COLORS.grid } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          assessment.leverage_space_score ?? 0,
          assessment.price_momentum_score ?? 0,
          assessment.rate_env_score ?? 0,
        ],
        name: '当前评分',
        areaStyle: { color: hexA(COLORS.accent, 0.25) },
        lineStyle: { color: COLORS.accent, width: 2 },
        itemStyle: { color: COLORS.accent },
      }],
    }],
  })
}

/** Bar + line combo — bar on the primary axis, line on a secondary axis
 *  (e.g. 社融增量 bar vs 社融存量增速 line, 新增贷款 bar vs 贷款同比 line). */
export function buildBarLineCombo(
  derived: Rec[], barCol: string, lineCol: string,
  barName: string, lineName: string,
  barUnit = '', lineUnit = '',
): Record<string, any> {
  const dates = derived.map((r) => r.date as string)
  return applyTheme({
    legend: { top: 0 },
    xAxis: { type: 'category', data: dates, ...baseAxis() },
    yAxis: [
      { type: 'value', name: barUnit, ...baseAxis() },
      { type: 'value', name: lineUnit, ...baseAxis(), splitLine: { show: false } },
    ],
    series: [
      { name: barName, type: 'bar', yAxisIndex: 0,
        data: derived.map((r) => r[barCol]), itemStyle: { color: hexA(COLORS.accent, 0.55) } },
      { name: lineName, type: 'line', yAxisIndex: 1, connectNulls: true, symbol: 'none',
        data: derived.map((r) => r[lineCol]), lineStyle: { color: COLORS.warn, width: 2 } },
    ],
  })
}

/** Multi-line — N series on one value axis (e.g. PMI 官方+财新+非制造业, LPR 1Y+5Y).
 *  Single-column input also renders a one-series line. */
export function buildMultiLine(
  derived: Rec[], cols: { col: string; name: string }[], yUnit = '',
): Record<string, any> {
  const dates = derived.map((r) => r.date as string)
  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', name: yUnit, ...baseAxis({ name: yUnit }) },
    series: cols.map((c, i) => ({
      name: c.name, type: 'line', connectNulls: true, symbol: 'none',
      lineStyle: { width: 2, color: PALETTE[i % PALETTE.length] },
      data: derived.map((r) => r[c.col]),
    })),
  })
}
