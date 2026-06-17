// ECharts option builders — one per chart family. Pure functions: records in,
// option out. Each applies the Terminal Fintech theme (≈ _apply_layout).

import { applyTheme, baseAxis, COLORS } from '@/design/echarts.theme'
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

/** Dual-axis line — two series on one category axis (e.g. CPI vs PPI, M1 vs M2). */
export function buildDualAxisLine(
  derived: Rec[], a: string, b: string,
  aColor = COLORS.accent, bColor = COLORS.up,
): Record<string, any> {
  const dates = derived.map((r) => r.date as string)
  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '%', scale: true }) },
    series: [
      { name: a, type: 'line', connectNulls: true, symbol: 'none', data: derived.map((r) => r[a]),
        lineStyle: { color: aColor, width: 2.5 }, areaStyle: { opacity: 0.08 } },
      { name: b, type: 'line', connectNulls: true, symbol: 'none', data: derived.map((r) => r[b]),
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

/** Scatter quadrant — x vs y coloured by phase (Merrill clock / inventory). */
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
  return applyTheme({
    xAxis: { type: 'value', name: xLabel, ...baseAxis({ name: xLabel }) },
    yAxis: { type: 'value', name: yLabel, ...baseAxis({ name: yLabel }) },
    tooltip: { trigger: 'item' },
    series: Array.from(byPhase.entries()).map(([p, data]) => ({
      name: phaseLabel(p), type: 'scatter', data, symbolSize: 8,
      itemStyle: { color: phaseColor(p), opacity: 0.85 },
    })),
    markLine: {
      silent: true, symbol: 'none', lineStyle: { type: 'dashed', color: COLORS.text3 },
      data: [hline ? [{ yAxis: hline }, { yAxis: hline }] : [], vline ? [{ xAxis: vline }, { xAxis: vline }] : []].flat(),
    } as any,
  })
}
