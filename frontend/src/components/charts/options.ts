// ECharts option builders — one per chart family. Pure functions: records in,
// option out. Each applies the Terminal Fintech theme (≈ _apply_layout).

import { applyTheme, baseAxis, chartTheme } from '@/design/echarts.theme'
import { phaseColor, phaseLabel } from '@/design/phases'
import { hexA, mergePhaseSegments } from './utils'
import type { EChartsOption, LineSeriesOption, ScatterSeriesOption } from 'echarts'

type Rec = Record<string, string | number | null>

// applyTheme lives in echarts.theme.ts and is typed Record<string, any>, so a
// mistyped option key passed straight to it is invisible. Wrap it once with an
// EChartsOption-typed parameter: every builder now runs its option literal
// through this seam, so `markLine`→`marklLine` (and friends) is a compile error,
// and each builder can honestly return EChartsOption.
const themed = (option: EChartsOption): EChartsOption => applyTheme(option)

/** 列 key → 中文图例名（NBS / 央行 / NIFD 官方术语；CPI/PPI/M2/PMI/LPR/GDP 等
 *  特有名词保留英文缩语）。未收录的 key 原样回退。 */
const COL_ZH: Record<string, string> = {
  cpi_yoy: 'CPI同比', cpi_mom: 'CPI环比',
  ppi_yoy: 'PPI同比', ppi_mom: 'PPI环比',
  m2_yoy: 'M2同比', m1_yoy: 'M1同比', m0_yoy: 'M0同比',
  m2_m1_spread: 'M2-M1剪刀差',
  pmi_official: '官方PMI', pmi_caixin: '财新PMI',
  pmi_non_mfg: '非制造业PMI', pmi_caixin_svc: '财新服务业PMI',
  ip_yoy: '工业增加值同比', gdp_yoy: 'GDP同比',
  household: '居民部门', non_fin_corp: '非金融企业部门',
  gov_total: '政府部门', gov_central: '中央政府', gov_local: '地方政府',
  real_economy: '实体经济部门',
  lpr_1y: 'LPR 1年', lpr_5y: 'LPR 5年', real_rate: '实际利率', bond_10y: '10年期国债',
  total: '社融增量', sf_stock_yoy: '社融存量增速',
  new_rmb_loan: '新增人民币贷款', loan_yoy: '新增贷款同比',
  urbanization_rate: '城镇化率', population: '年末总人口',
  birth_rate: '出生率', natural_growth_rate: '自然增长率',
  credit_impulse: '信贷脉冲',
  revenue_cum: '财政收入(累计)', revenue_cum_yoy: '财政收入累计同比',
  expenditure_cum: '财政支出(累计)', expenditure_cum_yoy: '财政支出累计同比',
  exports_yoy: '出口同比(美元)', imports_yoy: '进口同比(美元)',
  trade_balance: '贸易差额', us_ism_pmi: '美国ISM制造业PMI',
}
const zh = (col: string): string => COL_ZH[col] ?? col

/** Credit cycle flagship: M2 同比 line (connectNulls) + M2 趋势 dashed +
 *  phase-background markArea + the 1991–1996 source-gap markArea + caption. */
export function buildCreditM2Chart(derived: Rec[], cycle: Rec[]): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const dates = derived.map((r) => r.date as string)
  const m2 = derived.map((r) => r.m2_yoy)
  const trendByDate = new Map(cycle.map((r) => [r.date as string, r.m2_trend as number | null]))
  const trend = dates.map((d) => trendByDate.get(d) ?? null)

  const segs = mergePhaseSegments(cycle).filter((s) => s.phase !== 'neutral')
  const phaseBg = segs.map((s): [{ xAxis: string; itemStyle: { color: string } }, { xAxis: string }] => [
    { xAxis: s.x0, itemStyle: { color: hexA(phaseColor(s.phase), 0.08) } },
    { xAxis: s.x1 },
  ])
  return themed({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '%', scale: true }) },
    series: [
      {
        name: 'M2同比',
        type: 'line', smooth: false, connectNulls: true, symbol: 'none',
        data: m2, itemStyle: { color: COLORS.accent }, lineStyle: { color: COLORS.accent, width: 2.5 },
        areaStyle: { opacity: 0.1 },
        markArea: { silent: true, data: [...phaseBg] },
      },
      {
        name: 'M2趋势',
        type: 'line', connectNulls: true, symbol: 'none',
        data: trend, itemStyle: { color: COLORS.warn }, lineStyle: { color: COLORS.warn, width: 2, type: 'dashed' },
      },
    ],
  })
}

/** Credit impulse — bars (社融信贷脉冲). */
export function buildCreditImpulseChart(cycle: Rec[]): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const dates = cycle.map((r) => r.date as string)
  const impulse = cycle.map((r) => r.credit_impulse as number | null)
  return themed({
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
  aColor?: string, bColor?: string,
  aName?: string, bName?: string,
): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const aCol = aColor ?? COLORS.accent
  const bCol = bColor ?? COLORS.up
  const dates = derived.map((r) => r.date as string)
  return themed({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: [
      { type: 'value', name: aName ?? zh(a), scale: true, ...baseAxis() },
      { type: 'value', name: bName ?? zh(b), scale: true, ...baseAxis({ splitLine: { show: false } }),
        // 右轴名默认向右越界被裁（「工业增加值同…」）；右对齐让文本向左收进图区
        nameTextStyle: { align: 'right' } },
    ],
    series: [
      { name: aName ?? zh(a), type: 'line', yAxisIndex: 0, connectNulls: true, symbol: 'none',
        data: derived.map((r) => r[a]),
        itemStyle: { color: aCol }, lineStyle: { color: aCol, width: 2.5 }, areaStyle: { opacity: 0.08 } },
      { name: bName ?? zh(b), type: 'line', yAxisIndex: 1, connectNulls: true, symbol: 'none',
        data: derived.map((r) => r[b]),
        itemStyle: { color: bCol }, lineStyle: { color: bCol, width: 2 } },
    ],
  })
}

/** Stacked area — multiple series stacked (e.g. leverage by sector). */
export function buildStackedArea(
  derived: Rec[], cols: string[],
): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const dates = derived.map((r) => r.date as string)
  return themed({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '%' }) },
    series: cols.map((c, i): LineSeriesOption => {
      const color = PALETTE[i % PALETTE.length]
      return {
        name: zh(c), type: 'line', stack: 'total', connectNulls: true, symbol: 'none',
        itemStyle: { color },          // legend marker + area fill use the same color as the line
        areaStyle: { opacity: 0.12 }, // no explicit color → inherits itemStyle.color
        lineStyle: { width: 1.5, color },
        data: derived.map((r) => r[c]),
      }
    }),
  })
}

/** Scatter quadrant — x vs y coloured by phase (Merrill clock / inventory).
 *  Reference lines (PMI 50 / CPI 2% / …) live as markLine on an empty helper
 *  series — ECharts only renders markLine that is a child of a series.
 *  hline/vline 用 null 表示「不画」（0 是合法值：美林的零线就是 vline=0）。
 *  quadrantLabels: 四象限角落标注 {tl,tr,bl,br}（含相位色微染色底），不传则不画。 */
export function buildScatterQuadrant(
  cycle: Rec[], xKey: string, yKey: string,
  xLabel: string, yLabel: string, hline: number | null = null, vline: number | null = null,
  quadrantLabels?: { tl?: string; tr?: string; bl?: string; br?: string },
): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const byPhase = new Map<string, [number, number][]>()
  for (const r of cycle) {
    const x = r[xKey] as number | null
    const y = r[yKey] as number | null
    if (x == null || y == null) continue
    const p = (r.phase as string) ?? 'unknown'
    if (!byPhase.has(p)) byPhase.set(p, [])
    byPhase.get(p)!.push([x, y])
  }
  const refLines: Array<{ yAxis: number } | { xAxis: number }> = []
  if (hline != null) refLines.push({ yAxis: hline })
  if (vline != null) refLines.push({ xAxis: vline })

  // 四象限染色 + 角落标注：基于数据范围 pad 出四个矩形，标签放在各自内侧角落
  const helper: Record<string, unknown> = {
    type: 'scatter', data: [], silent: true,
    markLine: {
      silent: true, symbol: 'none',
      lineStyle: { type: 'dashed', color: COLORS.text3, width: 1 },
      label: { show: false },   // 端点数值标签是噪声（零线/荣枯线无需标值）
      data: refLines,
    },
  }
  if (quadrantLabels && refLines.length === 2) {
    const xs = cycle.map((r) => r[xKey] as number).filter((v) => typeof v === 'number')
    const ys = cycle.map((r) => r[yKey] as number).filter((v) => typeof v === 'number')
    if (xs.length && ys.length) {
      const padX = (Math.max(...xs) - Math.min(...xs)) * 0.05 || 1
      const padY = (Math.max(...ys) - Math.min(...ys)) * 0.08 || 1
      const [x0, x1] = [Math.min(...xs) - padX, Math.max(...xs) + padX]
      const [y0, y1] = [Math.min(...ys) - padY, Math.max(...ys) + padY]
      const vx = vline as number, hy = hline as number
      const areas = [
        { key: 'tr', from: [vx, hy], to: [x1, y1], pos: 'insideTopRight', phase: quadrantLabels.tr },
        { key: 'tl', from: [x0, hy], to: [vx, y1], pos: 'insideTopLeft', phase: quadrantLabels.tl },
        { key: 'br', from: [vx, y0], to: [x1, hy], pos: 'insideBottomRight', phase: quadrantLabels.br },
        { key: 'bl', from: [x0, y0], to: [vx, hy], pos: 'insideBottomLeft', phase: quadrantLabels.bl },
      ].filter((a) => a.phase)
      helper.markArea = {
        silent: true,
        data: areas.map((a) => [
          {
            coord: a.from,
            name: phaseLabel(a.phase!),
            itemStyle: { color: hexA(phaseColor(a.phase!), 0.05) },
            label: {
              show: true, position: a.pos, fontSize: 11, fontWeight: 600,
              color: hexA(phaseColor(a.phase!), 0.75), padding: [6, 10],
            },
          },
          { coord: a.to },
        ]),
      }
    }
  }

  return themed({
    // x 轴名居中（旧默认在端点，长名被裁成「GI…」）；y 轴名保持默认端点位（顶部横排），
    // 左对齐收进图区——value 轴 middle+旋转在中文字符下会裁边
    xAxis: { type: 'value', name: xLabel, nameLocation: 'middle', nameGap: 28, ...baseAxis() },
    yAxis: { type: 'value', name: yLabel, nameTextStyle: { align: 'left', padding: [0, 0, 0, 8] }, ...baseAxis() },
    tooltip: { trigger: 'item' },
    series: [
      ...Array.from(byPhase.entries()).map(([p, data]): ScatterSeriesOption => ({
        name: phaseLabel(p), type: 'scatter', data, symbolSize: 8,
        itemStyle: { color: phaseColor(p), opacity: 0.85 },
      })),
      helper,
    ],
  })
}

/** Radar — real-estate 3D assessment (leverage space / price momentum / rate env). */
export function buildRadar(assessment: {
  leverage_space_score?: number
  price_momentum_score?: number
  rate_env_score?: number
}): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  return themed({
    tooltip: { trigger: 'item', valueFormatter: (v: unknown) => Number(v).toFixed(2) },
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
): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const dates = derived.map((r) => r.date as string)
  return themed({
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
        data: derived.map((r) => r[lineCol]), itemStyle: { color: COLORS.warn }, lineStyle: { color: COLORS.warn, width: 2 } },
    ],
  })
}

/** Multi-line — N series on one value axis (e.g. PMI 官方+财新+非制造业, LPR 1Y+5Y).
 *  Single-column input also renders a one-series line.
 *  markLineAt: draw a subdued reference line (e.g. PMI 荣枯线 50);
 *  markLineName overrides the label (e.g. 零线 for the demographics zero line). */
export function buildMultiLine(
  derived: Rec[], cols: { col: string; name: string }[], yUnit = '', markLineAt?: number, markLineName = '荣枯线',
): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const dates = derived.map((r) => r.date as string)
  const series: LineSeriesOption[] = cols.map((c, i): LineSeriesOption => {
    const color = PALETTE[i % PALETTE.length]
    return {
      name: c.name, type: 'line', connectNulls: true, symbol: 'none',
      itemStyle: { color },            // legend marker = line color
      lineStyle: { width: 2, color },
      data: derived.map((r) => r[c.col]),
    }
  })
  if (markLineAt !== undefined && series.length) {
    // Attach the reference line to EVERY series, not just [0], so toggling any
    // one off in the legend still leaves the line on the others. It only
    // disappears when all series are hidden — which is correct.
    // The LABEL, however, is drawn only on the first series: N identical labels
    // at the same spot over-print (alpha stacks) and look bolder than designed.
    // Subdued reference styling (same vocabulary as quadrant cross-hairs &
    // spread zero line): thin dashed slate at reduced alpha — a background
    // dimension, not a data-bright line (the old amber solid clashed with the
    // amber 服务 series and out-shouted the data).
    series.forEach((s, i) => {
      s.markLine = {
        silent: true, symbol: ['none', 'none'],
        lineStyle: { color: hexA(COLORS.text3, 0.8), type: 'dashed', width: 1 },
        label: i === 0
          ? { formatter: `${markLineName} {c}`, color: hexA(COLORS.text3, 0.9), fontSize: 10, position: 'insideEndTop' }
          : { show: false },
        data: [{ yAxis: markLineAt }],
      }
    })
  }
  return themed({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    // scale:true → the y-axis adapts to the data range (not forced from 0),
    // so narrow-amplitude series (PMI 49~52) aren't flattened into a near-line.
    yAxis: { type: 'value', name: yUnit, scale: true, ...baseAxis({ name: yUnit }) },
    series,
  })
}

/** Spread chart — a single value (e.g. M2−M1 剪刀差) as an area line, with an
 *  emphasized zero line (the semantic axis: growth equal / diverging). The y-axis
 *  is scaled to the data range so the small pp swings are visible.
 *  `markLineValue` defaults to 0. */
export function buildSpreadChart(
  derived: Rec[], col: string, name = '剪刀差', unit = 'pp', markLineValue = 0,
): EChartsOption {
  const { colors: COLORS, palette: PALETTE } = chartTheme()
  const dates = derived.map((r) => r.date as string)
  return themed({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', name: unit, scale: true, ...baseAxis({ name: unit }) },
    series: [
      {
        name, type: 'line', connectNulls: true, symbol: 'none',
        data: derived.map((r) => r[col]),
        itemStyle: { color: COLORS.accent }, lineStyle: { color: COLORS.accent, width: 2 },
        areaStyle: { color: hexA(COLORS.accent, 0.15) },
        markLine: {
          silent: true, symbol: ['none', 'none'],
          lineStyle: { color: COLORS.text3, type: 'solid', width: 1 },
          label: { formatter: '持平', color: COLORS.text3, fontSize: 10, position: 'insideEndTop' },
          data: [{ yAxis: markLineValue }],
        },
      },
    ],
  })
}
