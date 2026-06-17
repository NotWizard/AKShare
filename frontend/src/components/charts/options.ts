// ECharts option builders — one per chart family. Pure functions: records in,
// option out. Each applies the Terminal Fintech theme (≈ _apply_layout).

import { applyTheme, baseAxis, COLORS } from '@/design/echarts.theme'
import { phaseColor } from '@/design/phases'
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
