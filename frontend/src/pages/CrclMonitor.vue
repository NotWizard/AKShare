<script setup lang="ts">
// CRCL 监控 — 投资论点追踪页。五区：KPI / 指标图表 / 宏观事件时间线 / 告警面板 / 更新日志。
// 数据：自动采集入 data/crcl_monitor.db（启动 + 手动 SSE 刷新）；事件与季报拆解为手工维护 JSON。
//
// 刷新状态住在 stores/refresh（FE-H4）：本页曾自持 refreshing/progress + 裸 fetch
// SSE，导致顶栏 🔄 与日期预设在本页是死控件、离开页面时 reader 循环继续写已销毁
// 组件的 ref、返回本页还能再启动一次并发采集。现在统一走 refresh.stream(false,'crcl')，
// 顶栏按 route.meta.refreshKind 呈现，本页只读状态。
import { ref, markRaw, computed } from 'vue'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import MetricTile from '@/components/layout/MetricTile.vue'
import PageState from '@/components/layout/PageState.vue'
import ChartTip from '@/components/controls/ChartTip.vue'
import { applyTheme, baseAxis, chartTheme } from '@/design/echarts.theme'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { themedOption } from '@/composables/useThemedOption'
import { useRefreshStore } from '@/stores/refresh'
import type { CrclMetric, CrclPoint } from '@/api/types'

const refresh = useRefreshStore()
const logsOpen = ref(false)

const METRIC_KEYS = 'crcl_close,usdc_circ,stablecoin_total,treasury_3m,treasury_6m,treasury_1y'

// ---------- data loading ----------
const { state, data, error, errorText, loading, retry: load } = useAsyncData(async (signal) => {
  const [ov, mt, ev, al, lg, fu] = await Promise.all([
    api.getCrclOverview({ signal }),
    api.getCrclMetrics(METRIC_KEYS, { signal }),
    api.getCrclEvents({ signal }),
    api.getCrclAlerts({ signal }),
    api.getCrclLogs(60, { signal }),
    api.getCrclFundamentals({ signal }),
  ])
  return {
    overview: ov,
    metrics: markRaw(mt.metrics),
    events: ev.events,
    eventsUpdatedAt: ev.updated_at,
    rules: al.rules,
    logs: lg.logs,
    fundamentals: fu,
  }
}, { watch: [() => refresh.crclRefreshedAt] })   // 采集完成 → 自动重取

const overview = computed(() => data.value?.overview ?? null)
const metrics = computed<Record<string, CrclMetric>>(() => data.value?.metrics ?? {})
const events = computed(() => data.value?.events ?? [])
const eventsUpdatedAt = computed(() => data.value?.eventsUpdatedAt ?? null)
const rules = computed(() => data.value?.rules ?? [])
const logs = computed(() => data.value?.logs ?? [])
const fundamentals = computed(() => data.value?.fundamentals ?? null)

// 采集状态只读自 store：跨路由持久，回到本页不会再启一次并发采集
const collecting = computed(() => refresh.running && refresh.kind === 'crcl')
// 后端可达但库里还没有任何采集结果（≠ 后端不可达）
const isEmpty = computed(() =>
  !overview.value?.last_run && Object.values(metrics.value).every((m) => !m.points?.length))

// ---------- formatting ----------
const fmtNum = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)
const fmtTs = (ts: string | null | undefined) =>
  ts ? ts.replace('T', ' ').replace('Z', '') : '—'

// ---------- 同比 / 环比 delta ----------
interface TileDelta { text: string; dir?: 'up' | 'down' | 'flat' }

/** 序列最新值相对 ~daysBack 天前的变化 %；数据不足返回 null。 */
function seriesDelta(pts: CrclPoint[] | undefined, daysBack: number): number | null {
  if (!pts || pts.length < 2) return null
  const last = pts[pts.length - 1]
  const target = new Date(last.date).getTime() - daysBack * 86400000
  // Parse each point once and carry the running best's distance, instead of
  // re-parsing best.date every iteration (this loops the full ~3187-pt series).
  let best = pts[0]
  let bestDiff = Math.abs(new Date(best.date).getTime() - target)
  for (const pt of pts) {
    const diff = Math.abs(new Date(pt.date).getTime() - target)
    if (diff < bestDiff) {
      best = pt
      bestDiff = diff
    }
  }
  if (best.value <= 0) return null
  return (last.value / best.value - 1) * 100
}
const pctChip = (label: string, v: number | null): TileDelta =>
  v == null
    ? { text: `${label} —` }
    : { text: `${label} ${v >= 0 ? '+' : ''}${v.toFixed(1)}%`, dir: v > 0.05 ? 'up' : v < -0.05 ? 'down' : 'flat' }
const ppChip = (label: string, v: number | null): TileDelta =>
  v == null
    ? { text: `${label} —` }
    : { text: `${label} ${v >= 0 ? '+' : ''}${v.toFixed(1)}pp`, dir: v > 0.05 ? 'up' : v < -0.05 ? 'down' : 'flat' }

const priceSeries = computed(() => metrics.value.crcl_close?.points ?? [])
const priceDod = computed(() => {
  const s = priceSeries.value
  if (s.length < 2) return null
  return (s[s.length - 1].value / s[s.length - 2].value - 1) * 100
})
const priceDeltas = computed<TileDelta[]>(() => [
  pctChip('日环比', priceDod.value),
  pctChip('同比', seriesDelta(priceSeries.value, 365)),
])
const usdcDeltas = computed<TileDelta[]>(() => [
  pctChip('同比', seriesDelta(metrics.value.usdc_circ?.points, 365)),
  pctChip('季环比', seriesDelta(metrics.value.usdc_circ?.points, 90)),
])
const totalDeltas = computed<TileDelta[]>(() => [
  pctChip('同比', seriesDelta(metrics.value.stablecoin_total?.points, 365)),
  pctChip('季环比', seriesDelta(metrics.value.stablecoin_total?.points, 90)),
])
const peDeltas = computed<TileDelta[]>(() => [
  { text: `构成：TTM ${fmtNum(valuation.value.trailing_pe, 1)} / 前瞻 ${fmtNum(valuation.value.forward_pe, 1)}` },
])
const alertDeltas = computed<TileDelta[]>(() =>
  triggeredRules.value.length
    ? triggeredRules.value.map((r) => ({ text: r.rule }))
    : [{ text: '当前无触发' }],
)

const prevQ = computed(() => {
  const qs = fundamentals.value?.quarters ?? []
  return qs.length >= 2 ? qs[qs.length - 2] : null
})
const num = (q: Record<string, number | string | null> | null, k: string): number | null => {
  const v = q?.[k]
  return typeof v === 'number' ? v : null
}
// 注意：num() 返回 number|null，必须显式 `!= null` —— 直接当布尔用会把合法的 0
// 当成缺失（0 是有意义的基数/份额值）。
const revenueDeltas = computed<TileDelta[]>(() => [
  pctChip('同比', num(latestQ.value, 'total_revenue_yoy_pct')),
  pctChip('环比', num(latestQ.value, 'total_revenue_qoq_pct') ??
    (num(latestQ.value, 'total_revenue_m') != null && num(prevQ.value, 'total_revenue_m') != null
      ? (num(latestQ.value, 'total_revenue_m')! / num(prevQ.value, 'total_revenue_m')! - 1) * 100
      : null)),
])
const reserveShareDeltas = computed<TileDelta[]>(() => [
  pctChip('储备收入同比', num(latestQ.value, 'reserve_revenue_yoy_pct')),
])
const shareOf = (q: Record<string, number | string | null> | null) => num(q, 'nonreserve_share_pct')
const nonreserveDeltas = computed<TileDelta[]>(() => [
  ppChip('环比', num(latestQ.value, 'nonreserve_share_pp_qoq') ??
    (shareOf(latestQ.value) != null && shareOf(prevQ.value) != null
      ? shareOf(latestQ.value)! - shareOf(prevQ.value)!
      : null)),
])
const cpnInstDeltas = computed<TileDelta[]>(() => {
  const v = num(latestQ.value, 'cpn_institutions_qoq') ??
    (num(latestQ.value, 'cpn_institutions') != null && num(prevQ.value, 'cpn_institutions') != null
      ? num(latestQ.value, 'cpn_institutions')! - num(prevQ.value, 'cpn_institutions')!
      : null)
  return [v == null ? { text: '环比 —' } : { text: `环比 ${v >= 0 ? '+' : ''}${v.toFixed(0)} 家`, dir: v > 0 ? 'up' : v < 0 ? 'down' : 'flat' }]
})
const eurcDeltas = computed<TileDelta[]>(() => [
  pctChip('环比', num(latestQ.value, 'eurc_circ_qoq_pct') ??
    (num(latestQ.value, 'eurc_circ_m') != null && num(prevQ.value, 'eurc_circ_m') != null
      ? (num(latestQ.value, 'eurc_circ_m')! / num(prevQ.value, 'eurc_circ_m')! - 1) * 100
      : null)),
])

// ---------- KPI ----------
const valuation = computed(() => (overview.value?.snapshots?.valuation ?? {}) as Record<string, number | null>)
const stableSnap = computed(() => (overview.value?.snapshots?.stablecoins ?? {}) as Record<string, number | string | null>)
const peSpread = computed(() => {
  const t = valuation.value.trailing_pe, f = valuation.value.forward_pe
  return t != null && f != null ? f - t : null
})
const triggeredRules = computed(() => overview.value?.alert_summary.triggered ?? [])

// ---------- chart options ----------
function lineOption(m: CrclMetric | undefined, opts: { area?: boolean; unit?: string; divisor?: number; markLineY?: number } = {}) {
  if (!m) return null
  const dates = m.points.map((p) => p.date)
  const div = opts.divisor ?? 1
  const vals = m.points.map((p) => +(p.value / div).toFixed(4))
  return markRaw(applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: {
      type: 'value', ...baseAxis({ name: opts.unit ?? m.unit, scale: true }),
    },
    tooltip: { valueFormatter: (v: number) => `${v}${opts.unit ? ' ' + opts.unit : ''}` },
    series: [{
      name: m.label, type: 'line', symbol: 'none', smooth: false,
      data: vals,
      itemStyle: { color: themeColors().accent },
      lineStyle: { color: themeColors().accent, width: 2 },
      ...(opts.area ? { areaStyle: { opacity: 0.1 } } : {}),
      ...(opts.markLineY != null ? {
        markLine: {
          silent: true, symbol: 'none',
          data: [{ yAxis: opts.markLineY }],
          lineStyle: { color: themeColors().warn, type: 'dashed', width: 1.5 },
          label: { formatter: String(opts.markLineY), color: themeColors().warn, fontSize: 10 },
        },
      } : {}),
    }],
  }))
}

const priceOpt = themedOption(() => lineOption(metrics.value.crcl_close, { unit: 'USD' }))
const usdcOpt = themedOption(() => lineOption(metrics.value.usdc_circ, { area: true, unit: '十亿美元', divisor: 1e9 }))
const totalOpt = themedOption(() => lineOption(metrics.value.stablecoin_total, { area: true, unit: '十亿美元', divisor: 1e9 }))
// 6M / 1Y 曲线配色（3M 用 accent）——treasuryOpt 内引用，声明须在其之前（否则一旦
// 该 computed 变为 eager 求值就会命中 TDZ ReferenceError）。
// 主题化：1 号色 = accent，2 号色 = warn（暗亮两套自动跟换）
const themeColors = () => chartTheme().colors
const treasuryOpt = themedOption(() => {
  const m3 = metrics.value.treasury_3m, m6 = metrics.value.treasury_6m, m12 = metrics.value.treasury_1y
  if (!m3 || !m6 || !m12) return null
  const dates = m3.points.map((p) => p.date)
  const byDate = (m: CrclMetric) => new Map(m.points.map((p) => [p.date, p.value]))
  const v6 = byDate(m6), v12 = byDate(m12)
  const mk = (name: string, data: Array<number | null>, color: string) => ({
    name, type: 'line', symbol: 'none', data,
    itemStyle: { color }, lineStyle: { color, width: 1.8 },
  })
  return markRaw(applyTheme({
    legend: { show: true },
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '%', scale: true }) },
    series: [
      mk('3M', m3.points.map((p) => p.value), themeColors().accent),
      mk('6M', dates.map((d) => v6.get(d) ?? null), themeColors().warn),
      mk('1Y', dates.map((d) => v12.get(d) ?? null), themeColors().up),
    ],
  }))
})

// ---------- alerts ----------
const LEVEL_STYLE: Record<string, { ring: string; badge: string; label: string }> = {
  yellow: { ring: 'border-warn', badge: 'bg-amber-500/15 text-warn', label: '黄色警报' },
  red: { ring: 'border-down', badge: 'bg-red-500/15 text-down', label: '红色警报' },
  confirm: { ring: 'border-up', badge: 'bg-up-soft text-up', label: '确认信号' },
}
const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  triggered: { text: '已触发', cls: 'bg-red-500/20 text-red-300' },
  ok: { text: '正常', cls: 'bg-up-soft text-up' },
  insufficient_data: { text: '数据不足', cls: 'bg-slate-500/20 text-slate-400' },
  not_evaluated: { text: '未评估', cls: 'bg-slate-500/20 text-slate-400' },
}
const CATEGORY_CLS: Record<string, string> = {
  '财报': 'bg-indigo-500/15 text-indigo-300',
  '监管': 'bg-amber-500/15 text-warn',
  '宏观': 'bg-cyan-500/15 text-cyan-300',
  '里程碑': 'bg-up-soft text-up',
  '合作': 'bg-purple-500/15 text-purple-300',
  '检查点': 'bg-red-500/15 text-red-300',
}
const EVENT_STATUS_CLS: Record<string, string> = {
  '已发生': 'text-text-4', '进行中': 'text-info', '待观察': 'text-warn',
  '待验证': 'text-emerald-400', '计划': 'text-text-3',
}

const latestQ = computed(() => {
  const qs = fundamentals.value?.quarters ?? []
  return qs.length ? qs[qs.length - 1] : null
})
</script>

<template>
  <div class="p-6">
    <!-- header -->
    <div class="flex items-start justify-between gap-4 mb-5">
      <div>
        <h1 class="text-xl font-bold text-text">CRCL 监控体系</h1>
        <p class="text-xs text-text-3 mt-1 leading-relaxed">
          Circle 投资论点追踪：量化指标自动采集（DefiLlama / Treasury.gov / AKShare / Yahoo Finance），宏观事件与季报拆解手工维护。
          规范见 <code class="text-text-2">docs/CRCL监控体系.md</code>，启动时自动采集，可手动刷新。
        </p>
      </div>
      <!-- 采集入口只有一个：顶栏「🔄 采集 CRCL」（route.meta.refreshKind='crcl'）。
           这里只做只读状态显示，不再是第二个语义不同的刷新按钮。 -->
      <div class="shrink-0 text-right" role="status" aria-live="polite">
        <div class="text-xs text-text-2">
          {{ collecting ? `采集中 ${(refresh.progress * 100).toFixed(0)}%` : '手动采集：顶栏「🔄 采集 CRCL」' }}
        </div>
        <div class="text-[10px] text-text-4 mt-1.5">
          最近采集：{{ overview?.last_run ? fmtTs(overview.last_run.ts) : '—' }}
        </div>
        <div v-if="collecting" class="w-28 h-1 bg-border rounded mt-1.5 overflow-hidden ml-auto">
          <div class="h-full bg-accent transition-all" :style="{ width: `${refresh.progress * 100}%` }" />
        </div>
      </div>
    </div>

    <PageState
      :state="state"
      :error="error"
      :has-data="data != null"
      :empty="isEmpty"
      empty-title="CRCL 库暂无采集记录"
      empty-hint="后端已连接，但 crcl_monitor.db 里还没有指标。点击顶栏「🔄 采集 CRCL」执行一次采集。"
      min-height="320px"
      @retry="load"
    >
      <!-- ① 指标卡片：自动采集 -->
      <div class="text-[10px] text-text-4 uppercase tracking-wide mb-2">实时采集</div>
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-4">
        <MetricTile label="CRCL 股价" :deltas="priceDeltas" :value="valuation.price ?? null" suffix="USD" :digits="2"
          :tip="`Yahoo Finance 实时快照。\n\n取数：yfinance Ticker('CRCL').info → currentPrice。`" />
        <MetricTile label="市值" :deltas="priceDeltas" :value="valuation.market_cap != null ? +(valuation.market_cap / 1e9).toFixed(1) : null" suffix="B"
          :tip="`Yahoo Finance 口径市值（十亿美元）。日环比/同比由股价序列推导（股本短期不变）。\n\n取数：yfinance info.marketCap。`" />
        <MetricTile label="前瞻 − TTM P/E 价差" :deltas="peDeltas" :value="peSpread != null ? +peSpread.toFixed(1) : null" suffix="x" :accent="(peSpread ?? 0) > 0"
          :tip="`前瞻 P/E 高于 TTM = 市场预期未来利润下滑（降息压缩储备收入）。这是论点跟踪的关键估值信号。\n\n取数：yfinance forwardPE − trailingPE。注意 Yahoo 口径 trailingPE 含一次性项目，绝对值与其他数据商有差异，看方向不看绝对。`" />
        <MetricTile label="USDC 流通量" :deltas="usdcDeltas" :value="stableSnap.usdc_circ != null ? +(Number(stableSnap.usdc_circ) / 1e9).toFixed(1) : null" suffix="B"
          :tip="`USDC 链上流通量（十亿美元），DefiLlama 聚合口径（已去跨链桥重复）。\n\n取数：stablecoins.llama.fi/stablecoincharts/all?stablecoin=2。`" />
        <MetricTile label="稳定币总盘" :deltas="totalDeltas" :value="stableSnap.stablecoin_total != null ? +(Number(stableSnap.stablecoin_total) / 1e9).toFixed(0) : null" suffix="B" :digits="0"
          :tip="`全部稳定币市值总盘（十亿美元）——行业水位。\n\n取数：stablecoins.llama.fi/stablecoincharts/all。`" />
        <MetricTile label="EURC 流通" :value="stableSnap.eurc_circ != null ? +(Number(stableSnap.eurc_circ) / 1e6).toFixed(0) : null" suffix="M€" :digits="0"
          :deltas="eurcDeltas"
          :tip="`欧元稳定币流通量（百万欧元），全球最大数字欧元，自动采集。\n\n取数：DefiLlama stablecoincharts/all?stablecoin=50，日频。`" />
        <MetricTile label="已触发警报" :deltas="alertDeltas" :value="triggeredRules.length" :digits="0" :accent="triggeredRules.length > 0"
          :tip="`当前处于触发状态的告警规则数（黄/红/确认）。规则定义见下方告警面板与 docs/CRCL监控体系.md。`" />
      </div>

      <!-- ① 指标卡片：手工维护（季报） -->
      <div class="text-[10px] text-text-4 uppercase tracking-wide mb-2">
        手工维护 · {{ latestQ?.period ?? '—' }} 财报
        <span class="normal-case tracking-normal ml-1">（编辑 data/crcl_fundamentals.json 更新）</span>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 mb-5">
        <MetricTile label="总收入" :deltas="revenueDeltas" :value="latestQ?.total_revenue_m != null ? Number(latestQ.total_revenue_m) : null" suffix="M"
          :tip="`Circle 季度总收入（百万美元）。\n\n来源：${latestQ?.source ?? '—'}`" />
        <MetricTile label="储备收入占比" :deltas="reserveShareDeltas" :value="latestQ?.reserve_revenue_m != null && latestQ?.total_revenue_m != null ? +(100 * Number(latestQ.reserve_revenue_m) / Number(latestQ.total_revenue_m)).toFixed(1) : null" suffix="%"
          :tip="`储备（利息）收入占总收入比——越高越像“货币基金”。\n\n来源：季报拆解。`" />
        <MetricTile label="非储备收入占比 ⭐" :deltas="nonreserveDeltas" :value="latestQ?.nonreserve_share_pct != null ? Number(latestQ.nonreserve_share_pct) : null" suffix="%" accent
          :tip="`论点核心指标：CPN/Arc 等平台收入占比。>15% 且流通增速 ≥20% 为确认信号组合之一；2027 年中 <10% 为证伪组合之一。\n\n来源：季报拆解（手工维护）。`" />
        <MetricTile label="EPS 实际" :value="latestQ?.eps_actual != null ? Number(latestQ.eps_actual) : null" :digits="2" :suffix="`/ 预期 ${latestQ?.eps_consensus ?? '—'}`"
          :tip="`每股收益实际值 vs 一致预期。Q2 为 miss（0.18 vs 0.26）。\n\n来源：季报。`" />
        <MetricTile label="CPN 交易量同比" :value="latestQ?.cpn_usdc_volume_yoy_pct != null ? Number(latestQ.cpn_usdc_volume_yoy_pct) : null" suffix="%"
          :tip="`Circle Payment Network 上 USDC 交易量同比增速——支付网络起量的领先指标。\n\n来源：季报/财报会。`" />
        <MetricTile label="CPN 接入机构" :deltas="cpnInstDeltas" :value="latestQ?.cpn_institutions != null ? Number(latestQ.cpn_institutions) : null" suffix="+" :digits="0"
          :tip="`接入 CPN 的金融机构数量。\n\n来源：财报会/AMA。`" />
      </div>

      <!-- ② 图表 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
        <GraphCard title="CRCL 收盘价" height="280px" :loading="loading" :error="errorText" @retry="load"
          :tip="`IPO 以来日线收盘价。\n\n取数：AKShare stock_us_daily('CRCL')（主源）→ yfinance history（备用源），日频。`">
          <EChart v-if="priceOpt" :option="priceOpt" height="280px" />
        </GraphCard>
        <GraphCard title="USDC 流通量" height="280px" :loading="loading" :error="errorText" @retry="load"
          :tip="`2018 年至今完整历史。同比增速是黄色警报规则 y_usdc_growth 的输入（阈值 15%）。\n\n取数：DefiLlama，日频。`">
          <EChart v-if="usdcOpt" :option="usdcOpt" height="280px" />
        </GraphCard>
        <GraphCard title="稳定币总市值（行业水位）" height="280px" :loading="loading" :error="errorText" @retry="load"
          :tip="`全部稳定币合计市值——决定 Circle 增长的行业水位。\n\n取数：DefiLlama stablecoincharts/all，日频。`">
          <EChart v-if="totalOpt" :option="totalOpt" height="280px" />
        </GraphCard>
        <GraphCard title="短端美债收益率（储备收入之锚）" height="280px" :loading="loading" :error="errorText" @retry="load"
          :tip="`Circle 储备收益锚定短端美债。每 25bp 降息 ≈ 蒸发约 $1.8 亿年化收入（按 $73B 流通量估算）。\n\n取数：Treasury.gov 年度 CSV（daily_treasury_yield_curve），日频，回填 2 年。`">
          <EChart v-if="treasuryOpt" :option="treasuryOpt" height="280px" />
        </GraphCard>
      </div>

      <!-- ③ 告警规则状态 -->
      <div class="mb-5">
        <GraphCard title="告警规则状态" :loading="loading" :error="errorText" @retry="load"
          :tip="`规则来自 docs/CRCL监控体系.md 决策规则。每次采集后自动评估，状态变化写入告警历史。数据驱动规则用采集数据；判定规则用 data/crcl_fundamentals.json 的标志位与季报数据（手工维护）。`">
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
            <div v-for="r in rules" :key="r.rule"
              class="px-3.5 py-3 rounded-xl border bg-surface/60 flex flex-col gap-1.5"
              :class="[LEVEL_STYLE[r.level]?.ring ?? 'border-border', r.status === 'triggered' ? 'ring-1 ring-inset ring-red-500/40' : '']">
              <div class="flex items-center justify-between gap-2">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-medium" :class="LEVEL_STYLE[r.level]?.badge ?? 'bg-slate-500/15 text-slate-400'">
                  {{ LEVEL_STYLE[r.level]?.label ?? r.level }}
                </span>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-medium" :class="STATUS_LABEL[r.status]?.cls ?? 'bg-slate-500/20 text-slate-400'">
                  {{ STATUS_LABEL[r.status]?.text ?? r.status }}
                </span>
              </div>
              <div class="text-xs font-medium text-text leading-snug">{{ r.description }}</div>
              <div class="text-[11px] text-text-3 leading-snug">{{ r.message || '—' }}</div>
              <div class="text-[10px] text-text-4 mt-auto pt-1">{{ fmtTs(r.ts) }} · {{ r.rule }}</div>
            </div>
          </div>
        </GraphCard>
      </div>

      <!-- ④ 宏观事件与里程碑 -->
      <div class="mb-5">
        <GraphCard title="宏观事件与里程碑" :loading="loading" :error="errorText" @retry="load"
          :tip="`手工维护：编辑 data/crcl_events.json 后刷新页面即可。FOMC 具体日期以 Fed 官方日历为准（标注待核实的条目请核实）。`">
          <div class="text-[10px] text-text-4 mb-3">文件更新于 {{ eventsUpdatedAt ?? '—' }} · 共 {{ events.length }} 条</div>
          <div class="space-y-2.5">
            <div v-for="(ev, i) in events" :key="i"
              class="flex gap-3 px-3.5 py-3 rounded-xl border border-border bg-surface/60">
              <div class="shrink-0 w-[86px] pt-0.5">
                <div class="text-xs font-semibold text-text tabular-nums">{{ ev.date }}</div>
                <span class="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px]" :class="CATEGORY_CLS[ev.category] ?? 'bg-slate-500/15 text-slate-400'">{{ ev.category }}</span>
              </div>
              <div class="min-w-0">
                <div class="text-[13px] font-medium text-text">
                  {{ ev.title }}
                  <span class="ml-2 text-[10px]" :class="EVENT_STATUS_CLS[ev.status] ?? 'text-text-3'">● {{ ev.status }}</span>
                </div>
                <div class="text-xs text-text-3 mt-1 leading-relaxed">{{ ev.detail }}</div>
                <div class="text-[10px] text-text-4 mt-1">来源：{{ ev.source }}</div>
              </div>
            </div>
          </div>
        </GraphCard>
      </div>

      <!-- ⑤ 采集与告警日志（默认折叠） -->
      <section class="bg-card border border-border rounded-2xl p-5">
        <button class="w-full flex items-center justify-between gap-2 text-left" @click="logsOpen = !logsOpen"
          :aria-expanded="logsOpen">
          <h3 class="text-sm font-semibold text-text">
            采集与告警日志
            <span class="text-text-3 text-xs font-normal ml-2">
              {{ logs.length }} 条 · 最近 {{ logs.length ? fmtTs(logs[0].ts) : '—' }}
            </span>
          </h3>
          <span class="text-text-3 text-xs shrink-0">{{ logsOpen ? '收起 ▲' : '展开 ▼' }}</span>
        </button>
        <div v-if="logsOpen" class="mt-3 overflow-x-auto">
          <table class="w-full text-xs tabular-nums">
            <thead>
              <tr class="text-left text-text-3 border-b border-border">
                <th class="py-1.5 pr-3 font-medium">时间 (UTC)</th>
                <th class="py-1.5 pr-3 font-medium">来源</th>
                <th class="py-1.5 pr-3 font-medium">状态</th>
                <th class="py-1.5 pr-3 font-medium">信息</th>
                <th class="py-1.5 font-medium text-right">耗时</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(l, i) in logs" :key="i" class="border-b border-border/40 last:border-0">
                <td class="py-1.5 pr-3 text-text-3 whitespace-nowrap">{{ fmtTs(l.ts) }}</td>
                <td class="py-1.5 pr-3 text-text-2 font-mono text-[11px]">{{ l.source }}</td>
                <td class="py-1.5 pr-3">
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    :class="l.status === 'ok' ? 'bg-up-soft text-up'
                      : l.status === 'error' ? 'bg-red-500/15 text-red-300'
                      : l.status === 'alert' ? 'bg-amber-500/15 text-warn'
                      : 'bg-slate-500/15 text-slate-400'">{{ l.status }}</span>
                </td>
                <td class="py-1.5 pr-3 text-text-2 max-w-[420px] truncate" :title="l.message">{{ l.message }}</td>
                <td class="py-1.5 text-right text-text-3">{{ l.duration_ms >= 0 ? l.duration_ms + 'ms' : '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="text-[10px] text-text-4 mt-4 leading-relaxed">
        数据源：DefiLlama（稳定币）· Treasury.gov（美债收益率）· AKShare/Yahoo Finance（CRCL 行情与估值）· 手工 JSON（事件/季报/标志位）。
        Yahoo 口径估值与其他数据商存在差异（一次性项目影响），页面展示已标注。本页不构成投资建议。
      </div>
    </PageState>
  </div>
</template>
