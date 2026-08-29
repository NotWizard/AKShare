<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import SectionCommentary from '@/components/layout/SectionCommentary.vue'
import { buildStackedArea, buildMultiLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
const refresh = useRefreshStore()
type Rec = Record<string, string | number | null>

// useAsyncData owns loading/error/abort; `load` is still the retry handler.
const { data, errorText: error, loading, retry: load } = useAsyncData(async (signal) => {
  const [q, rt, c, dqy] = await Promise.all([
    api.getTable('leverage', filters.start ?? undefined, filters.end ?? undefined, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,lpr_1y,lpr_5y,real_rate,bond_10y', true, { signal }),
    api.getCycle('debt', filters.start ?? undefined, filters.end ?? undefined, { signal }),
    api.getDerivedQuarterly(filters.start ?? undefined, filters.end ?? undefined, { signal }),
  ])
  return { dq: markRaw(q.records), rate: markRaw(rt.records), cycle: markRaw(c), dqi: markRaw(dqy.records) }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

// Read the leverage table DIRECTLY (quarterly, non-null). derived_quarterly's
// leverage columns are now populated (02_compute_derived anchors on leverage
// quarterly freq + GDP merge_asof ffill); the debt page reads leverage raw for
// directness and to avoid the ffill step-shape in GDP-derived series.
const dq = computed<Rec[]>(() => data.value?.dq ?? [])
const rateDm = computed<Rec[]>(() => data.value?.rate ?? [])  // lpr_1y,lpr_5y,real_rate,bond_10y
const dqi = computed<Rec[]>(() => data.value?.dqi ?? [])      // derived_quarterly: household,hh_debt_to_income
const cycle = computed<CycleFrame | null>(() => data.value?.cycle ?? null)

// Options built in computeds (not the template) → one markRaw'd object per
// rebuild that ECharts merges into the live instance (preserves zoom/legend).
const stackedOpt = computed(() => markRaw(buildStackedArea(dq.value, ['household', 'non_fin_corp', 'gov_total'])))
const govOpt = computed(() => markRaw(buildStackedArea(dq.value, ['gov_central', 'gov_local'])))
const rateOpt = computed(() => markRaw(buildMultiLine(rateDm.value, [{ col: 'lpr_1y', name: 'LPR 1年' }, { col: 'lpr_5y', name: 'LPR 5年' }, { col: 'real_rate', name: '实际利率' }, { col: 'bond_10y', name: '10年期国债' }], '%')))
const hhOpt = computed(() => markRaw(buildMultiLine(dqi.value, [{ col: 'household', name: '居民部门杠杆率' }, { col: 'hh_debt_to_income', name: '居民债务收入比' }], '%')))
</script>

<template>
  <div class="p-6 space-y-5">
    <header><h1 class="text-xl font-bold text-text">债务周期</h1>
      <p class="text-xs text-text-3 mt-1">各部门杠杆率（达利欧去杠杆框架）</p>
    </header>
    <div v-if="cycle?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(cycle.latest_phase) }" />
      <span class="text-xs text-text-2">总体阶段：<b class="text-text">{{ phaseLabel(cycle.latest_phase) }}</b></span>
    </div>
    <GraphCard title="分部门宏观杠杆率（堆叠）" tip="居民 / 非金融企业 / 政府杠杆率堆叠（占 GDP %）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="stackedOpt" height="380px" />
    </GraphCard>
    <SectionCommentary section="debt" />
    <GraphCard title="政府杠杆：中央 vs 地方" tip="政府部门杠杆率拆分为中央政府与地方政府（占 GDP %）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="govOpt" height="320px" />
    </GraphCard>
    <GraphCard title="利率环境" tip="LPR 1 年/5 年利率 + 实际利率（LPR 1Y − CPI 同比）+ 10 年期国债收益率（无风险利率锚）。债务周期标准框架里 社融↔债券利率↔期限利差 为判定链路。" :loading="loading" :error="error" @retry="load">
      <EChart :option="rateOpt" height="300px" />
    </GraphCard>
    <GraphCard title="居民真实杠杆空间：杠杆率 vs 债务收入比" tip="居民部门杠杆率（占GDP%）vs 居民债务/可支配收入（%）。杠杆率看似仅~60%，但债务收入比已>120%，更真实反映居民加杠杆空间。债务=居民杠杆率×年化GDP（Q1×4近似）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="hhOpt" height="300px" />
    </GraphCard>
  </div>
</template>
