import { describe, it, expect } from 'vitest'
import {
  buildCreditM2Chart, buildCreditImpulseChart, buildDualAxisLine,
  buildStackedArea, buildScatterQuadrant, buildRadar, buildBarLineCombo,
  buildMultiLine, buildSpreadChart,
} from '@/components/charts/options'
import type { LineSeriesOption } from 'echarts'

// options.ts 的行为断言（FE-L7 + 图例/参考线正确性）。这些是纯函数：records in →
// EChartsOption out；重点是每个 builder 的**语义**——series 数量、连接空值、以及
// FE-L7 里 markLine 必须挂到**每个 series**（挂 [0] 会在图例关掉第 0 条时把参考
// 线一起藏起来）。

const derivedMonthly = [
  { date: '2025-01-01', m2_yoy: 8.5, cpi_yoy: 0.5, ppi_yoy: -2, ip_yoy: 5, m2_m1_spread: 3, revenue_cum: 100, revenue_cum_yoy: 1 },
  { date: '2025-02-01', m2_yoy: null, cpi_yoy: 0.4, ppi_yoy: -1.8, ip_yoy: 4, m2_m1_spread: 2.9, revenue_cum: 200, revenue_cum_yoy: 2 },
  { date: '2025-03-01', m2_yoy: 8.7, cpi_yoy: 0.6, ppi_yoy: -1.5, ip_yoy: 6, m2_m1_spread: 3.1, revenue_cum: 300, revenue_cum_yoy: 3 },
]
const cycleCredit = [
  { date: '2025-01-01', phase: 'easing', m2_trend: 8.0, credit_impulse: 1.2 },
  { date: '2025-02-01', phase: 'easing', m2_trend: 8.1, credit_impulse: 0.9 },
  { date: '2025-03-01', phase: 'tightening', m2_trend: 8.2, credit_impulse: -0.3 },
]

describe('options: 结构与配色', () => {
  it('buildCreditM2Chart：2 条 series + phaseBg（filter 掉 neutral）', () => {
    const opt = buildCreditM2Chart(derivedMonthly, cycleCredit)
    const series = opt.series as Array<{ name: string; markArea?: { data: unknown[] } }>
    expect(series).toHaveLength(2)
    expect(series[0].name).toBe('M2同比')
    expect(series[1].name).toBe('M2趋势')
    // easing / tightening 至少 1 段 phase 背景
    expect((series[0].markArea!.data as unknown[]).length).toBeGreaterThan(0)
  })

  it('buildStackedArea：series 数 = cols 数，全部 stack:"total"', () => {
    const cols = ['household', 'non_fin_corp', 'gov_total']
    const opt = buildStackedArea(derivedMonthly, cols) as { series: LineSeriesOption[] }
    expect(opt.series).toHaveLength(cols.length)
    for (const s of opt.series) {
      expect(s.stack).toBe('total')
      expect(s.type).toBe('line')
    }
  })

  it('buildMultiLine 无 markLineAt：series 不带 markLine', () => {
    const opt = buildMultiLine(derivedMonthly, [
      { col: 'cpi_yoy', name: 'CPI' }, { col: 'ppi_yoy', name: 'PPI' },
    ]) as { series: LineSeriesOption[] }
    for (const s of opt.series) expect(s.markLine).toBeUndefined()
  })

  it('FE-L7：markLineAt 存在时，参考线挂到每个 series（不是仅 [0]）', () => {
    const opt = buildMultiLine(derivedMonthly, [
      { col: 'ip_yoy', name: 'IP' }, { col: 'cpi_yoy', name: 'CPI' },
    ], '%', 50, '荣枯线') as { series: LineSeriesOption[] }
    expect(opt.series.length).toBe(2)
    for (const s of opt.series) {
      expect(s.markLine).toBeDefined()
      const data = (s.markLine as { data: Array<{ yAxis: number }> }).data
      expect(data[0].yAxis).toBe(50)
    }
  })

  it('buildScatterQuadrant：按 phase 分组 + hline/vline 各一条 markLine', () => {
    const cycle = [
      { date: '2025-01-01', phase: 'recovery', gdp_yoy: 5, cpi_yoy: 1 },
      { date: '2025-02-01', phase: 'recovery', gdp_yoy: 6, cpi_yoy: 1.5 },
      { date: '2025-03-01', phase: 'overheating', gdp_yoy: 7, cpi_yoy: 3 },
      { date: '2025-04-01', phase: 'recovery', gdp_yoy: null, cpi_yoy: 2 }, // 应被丢
    ]
    const opt = buildScatterQuadrant(cycle, 'gdp_yoy', 'cpi_yoy', 'GDP', 'CPI', 2, 5) as { series: Array<{ type: string; markLine?: { data: unknown[] } }> }
    const scatters = opt.series.filter((s) => s.type === 'scatter' && !s.markLine)
    expect(scatters.length).toBe(2)   // 2 个 phase
    const helper = opt.series.find((s) => s.markLine)!
    expect(helper.markLine!.data).toHaveLength(2)   // hline + vline
  })

  it('buildRadar：assessment 缺字段回退 0，不抛', () => {
    const opt = buildRadar({ leverage_space_score: 60 }) as { series: Array<{ data: Array<{ value: number[] }> }> }
    expect(opt.series[0].data[0].value).toEqual([60, 0, 0])
  })

  it('buildDualAxisLine / buildBarLineCombo：两个 yAxis 两个 series', () => {
    const dual = buildDualAxisLine(derivedMonthly, 'cpi_yoy', 'ppi_yoy') as { yAxis: unknown[]; series: unknown[] }
    expect(dual.yAxis).toHaveLength(2); expect(dual.series).toHaveLength(2)
    const bl = buildBarLineCombo(derivedMonthly, 'revenue_cum', 'revenue_cum_yoy', '收入', '同比') as { yAxis: unknown[]; series: Array<{ type: string }> }
    expect(bl.yAxis).toHaveLength(2)
    expect(bl.series.map((s) => s.type)).toEqual(['bar', 'line'])
  })

  it('buildCreditImpulseChart / buildSpreadChart：单 series + 类型正确', () => {
    const imp = buildCreditImpulseChart(cycleCredit) as { series: Array<{ type: string }> }
    expect(imp.series).toHaveLength(1); expect(imp.series[0].type).toBe('bar')
    const sp = buildSpreadChart(derivedMonthly, 'm2_m1_spread') as { series: Array<{ type: string; markLine: { data: Array<{ yAxis: number }> } }> }
    expect(sp.series[0].type).toBe('line')
    expect(sp.series[0].markLine.data[0].yAxis).toBe(0)   // 默认零线
  })
})
