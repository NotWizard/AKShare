<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import MetricTile from '@/components/layout/MetricTile.vue'
import CommentaryCard from '@/components/layout/CommentaryCard.vue'
import PageState from '@/components/layout/PageState.vue'
import ChartTip from '@/components/controls/ChartTip.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { SignalHistoryRow, SignalSummary } from '@/api/types'

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const refresh = useRefreshStore()

const KPI_COLS = 'date,m2_yoy,cpi_yoy,pmi_official,pmi_caixin,m2_m1_spread,m0_yoy'

// One fetcher, one state machine, one abort signal — PageState renders the
// error branch, so it can no longer be assigned and forgotten.
const { state, data, error, retry, loading } = useAsyncData(async (signal) => {
  const st = filters.start ?? undefined, en = filters.end ?? undefined
  const [kpi, s, h] = await Promise.all([
    api.getDerivedMonthly(st, en, KPI_COLS, undefined, { signal }),
    api.getSignals({ signal }),
    api.getSignalHistory(undefined, { signal }),
  ])
  return {
    kpi: kpi.records.slice().reverse() as Rec[],   // latest first for latest()
    signals: s as SignalSummary,
    history: h.items as SignalHistoryRow[],
  }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

const kpiDm = computed<Rec[]>(() => data.value?.kpi ?? [])
const signals = computed<SignalSummary | null>(() => data.value?.signals ?? null)
const history = computed<SignalHistoryRow[]>(() => data.value?.history ?? [])
// Backend answered, but there is genuinely nothing to show yet (fresh DB) —
// deliberately distinct from an unreachable backend.
const isEmpty = computed(() => !kpiDm.value.length && !signals.value)
const onlyFlips = ref(false)

function latest(col: string): number | null {
  for (const r of kpiDm.value) {           // kpiDm is latest-first
    const v = r[col]
    if (typeof v === 'number') return v
  }
  return null
}

const FRAMEWORKS = ['merrill', 'credit', 'inventory', 'debt'] as const
type Fw = typeof FRAMEWORKS[number]
const FW: Record<Fw, string> = { merrill: '美林', credit: '信用', inventory: '库存', debt: '债务' }
const historyRows = computed(() => onlyFlips.value ? history.value.filter(r => r.flips.length) : history.value)
const isFlipped = (r: SignalHistoryRow, f: Fw) => r.flips.some(fl => fl.framework === f)
const rowAria = (r: SignalHistoryRow) =>
  `${r.ts.slice(0, 10)} 综合信号 ${r.composite}` +
  (r.flips.length ? '；' + r.flips.map(fl =>
    `${FW[fl.framework as Fw]}相位 ${phaseLabel(fl.prev)} → ${phaseLabel(fl.curr)}`).join('；') : '')

const historyTip = `每次成功刷新记录一行：综合信号 [-4,+4] 与四框架最新相位；任一框架相位相对上一条变化即翻转，翻转行以 warn 细环高亮。

取数：/api/v1/signals/history → signal_history 表（01_fetch 成功提交后由 scripts/signal_history.py 追加，ts 与 manifest 同源）。`

const tiles = [
  { label: 'M2 同比', col: 'm2_yoy', suffix: '%', tip: `广义货币供应量 M2 同比增速，反映市场整体流动性，增速上行通常对应宽货币。

取数：AKShare macro_china_supply_of_money → money_supply.m2_yoy（原始同比，无衍生计算）→ 合并入 derived_monthly 表 → 取日期范围内最近一期有效值，单位 %。` },
  { label: 'CPI 同比', col: 'cpi_yoy', suffix: '%', tip: `居民消费价格指数同比，衡量通胀/通缩，2% 为常用目标线。

取数：AKShare macro_china_cpi_yearly → cpi.cpi_yoy（原始同比）→ left join 入 derived_monthly.cpi_yoy → 取最近一期有效值，单位 %。` },
  { label: 'PMI 官方', col: 'pmi_official', tip: `国家统计局制造业采购经理指数，50 为荣枯分界线，>50 表示扩张。

取数：AKShare macro_china_pmi_yearly → pmi.pmi_official（原始）→ 合并于 derived_monthly.pmi_official → 取最近一期有效值。` },
  { label: '财新 PMI', col: 'pmi_caixin', tip: `财新/S&P 制造业 PMI，样本偏中小及沿海企业，公认领先官方 PMI，同为 50 荣枯线。

取数：AKShare macro_china_cx_pmi_yearly → pmi.pmi_caixin（原始）→ 合并于 derived_monthly.pmi_caixin → 取最近一期有效值。` },
  { label: 'M2-M1 剪刀差', col: 'm2_m1_spread', suffix: 'pp', tip: `M2 同比减 M1 同比，衡量资金活化程度。剪刀差扩大（正值）常预示企业活期存款走弱、需求疲软。

取数：衍生计算 derived_monthly.m2_m1_spread = m2_yoy − m1_yoy（脚本 02_compute_derived.py）→ 取最近一期有效值，单位 pp（百分点）。` },
  { label: 'M0 同比', col: 'm0_yoy', suffix: '%', tip: `流通中现金 M0 同比，反映现金需求与居民消费活跃度。

取数：AKShare macro_china_supply_of_money → money_supply.m0_yoy（原始同比）→ 透传至 derived_monthly.m0_yoy → 取最近一期有效值，单位 %。` },
]

const signalTip = `聚合四大周期（美林/信用/库存/债务）最新阶段的复合得分，范围 [-4, +4]，正值偏多、负值偏空；下方文字为对应解读。

取数：/api/v1/signals → analysis/signals.compute_signals：取四周期最新一期 phase 各查表映射为 −1/0/+1 后求和。`

const lagNum = (k: string): number | null => {
  const v = (signals.value?.cross_lags as Record<string, unknown> | undefined)?.[k]
  return typeof v === 'number' ? v : null
}
const fmtLag = (k: string) => lagNum(k) ?? '—'
const fmtCorr = (k: string) => lagNum(k) !== null ? lagNum(k)!.toFixed(2) : '—'
</script>

<template>
  <div class="p-6 space-y-5">
    <header>
      <h1 class="text-xl font-bold text-text">综合概览</h1>
      <p class="text-xs text-text-3 mt-1">关键宏观指标 + 综合信号</p>
    </header>

    <!-- 取数状态由 PageState 统一渲染：后端不可达 ≠ 数据库暂无数据 -->
    <PageState
      :state="state"
      :error="error"
      :has-data="data != null"
      :empty="isEmpty"
      empty-title="数据库暂无宏观数据"
      empty-hint="后端已连接，但 derived_monthly / signals 还没有记录。点击顶部「🔄 刷新数据」执行一次采集。"
      min-height="320px"
      @retry="retry"
    >
      <div class="space-y-5">
        <div class="grid grid-cols-5 gap-3">
          <MetricTile v-for="t in tiles" :key="t.col" :label="t.label" :value="latest(t.col)" :suffix="t.suffix" :tip="t.tip" />
          <MetricTile label="综合信号" :value="signals?.composite_score ?? null" accent :digits="0" :tip="signalTip" />
        </div>
        <p v-if="signals" class="text-xs text-text-2">{{ signals.interpretation }}</p>

        <CommentaryCard />

        <div v-if="signals?.cross_lags" class="text-xs text-text-2 space-y-1 px-4 py-3 rounded-lg bg-card border border-border">
          <div class="text-text-3 uppercase tracking-wide">跨指标领先</div>
          <div>M1 → PPI 领先约 <b class="text-text">{{ fmtLag('m1_ppi_best_lag') }}</b> 个月（相关 r = {{ fmtCorr('m1_ppi_max_corr') }}）</div>
          <div>剪刀差 → CPI 领先约 <b class="text-text">{{ fmtLag('spread_cpi_best_lag') }}</b> 个月（相关 r = {{ fmtCorr('spread_cpi_max_corr') }}）</div>
        </div>

        <section class="bg-card border border-border rounded-2xl p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-text">信号与相位历史<ChartTip :text="historyTip" /></h3>
            <label class="flex items-center gap-1.5 text-xs text-text-2 cursor-pointer">
              <input v-model="onlyFlips" type="checkbox" class="accent-warn"> 仅看翻转
            </label>
          </div>
          <ol role="list" class="space-y-1">
            <li v-for="r in historyRows" :key="r.ts"
                class="grid grid-cols-[5.5rem_2.5rem_1fr] items-center gap-3 px-2 py-1.5 rounded-lg"
                :class="r.flips.length ? 'ring-1 ring-warn/40 bg-warn/5' : ''"
                :tabindex="r.flips.length ? 0 : undefined"
                :aria-label="rowAria(r)">
              <span class="text-xs text-text-3">{{ r.ts.slice(0, 10) }}</span>
              <span class="text-xs font-bold text-center"
                    :class="r.composite > 0 ? 'text-up' : r.composite < 0 ? 'text-down' : 'text-text-2'">
                {{ r.composite > 0 ? '+' : '' }}{{ r.composite }}
              </span>
              <span class="flex flex-wrap gap-1">
                <span v-for="f in FRAMEWORKS" :key="f"
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border bg-surface text-[11px] text-text-2"
                      :class="isFlipped(r, f) ? 'border-warn/60 text-text' : 'border-border'">
                  <span class="w-1.5 h-1.5 rounded-full" :style="{ background: phaseColor(r[f]) }" />
                  {{ FW[f] }}·{{ phaseLabel(r[f]) }}
                </span>
              </span>
            </li>
          </ol>
          <!-- reachable only when the fetch SUCCEEDED, so "暂无历史" is now true -->
          <p v-if="!loading && !historyRows.length" class="text-xs text-text-3">
            {{ history.length ? '暂无翻转行——取消「仅看翻转」可查看全部快照。' : '暂无历史快照——每次成功刷新后记录一条。' }}
          </p>
        </section>
      </div>
    </PageState>
  </div>
</template>
