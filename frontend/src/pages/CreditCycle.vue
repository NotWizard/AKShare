<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import { buildCreditM2Chart, buildCreditImpulseChart, buildBarLineCombo, buildDualAxisLine, buildSpreadChart } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
const refresh = useRefreshStore()

// Per-chart column groups, each with its own align_start so a late-starting
// column (社融存量 2016) doesn't truncate an early one (M2 1991).
type Rec = Record<string, string | number | null>

// useAsyncData owns loading/error/abort; `load` is still the retry handler.
const { data, errorText: error, loading, retry: load } = useAsyncData(async (signal) => {
  // M2 主图复用 m1m2 组（m2_yoy 覆盖相同、align_start 口径一致），不再单列请求
  const [m12, sp, sf, nc, cc] = await Promise.all([
    api.getDerivedMonthly(filters.start ?? '1996-12-01', filters.end ?? undefined, 'date,m1_yoy,m2_yoy', true, { signal }),
    api.getDerivedMonthly(filters.start ?? '1996-12-01', filters.end ?? undefined, 'date,m2_m1_spread', true, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,total,sf_stock_yoy', true, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,new_rmb_loan,loan_yoy', true, { signal }),
    api.getCycle('credit', filters.start ?? undefined, filters.end ?? undefined, { signal }),
  ])
  return {
    m1m2: markRaw(m12.records), spread: markRaw(sp.records),
    sf: markRaw(sf.records), nc: markRaw(nc.records), credit: markRaw(cc),
  }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

const m1m2Dm = computed<Rec[]>(() => data.value?.m1m2 ?? [])       // date,m1_yoy,m2_yoy → 1991-12
const spreadDm = computed<Rec[]>(() => data.value?.spread ?? [])   // date,m2_m1_spread  → 1991-12
const sfDm = computed<Rec[]>(() => data.value?.sf ?? [])           // date,total,sf_stock_yoy → 2016-01
const ncDm = computed<Rec[]>(() => data.value?.nc ?? [])           // date,new_rmb_loan,loan_yoy → 2009-01
const credit = computed<CycleFrame | null>(() => data.value?.credit ?? null)

// Options are built in computeds (not the template) so each rebuild yields one
// markRaw'd object that ECharts merges into the live instance (preserves zoom).
const m2Opt = computed(() => markRaw(buildCreditM2Chart(m1m2Dm.value, credit.value?.series ?? [])))
const m1m2Opt = computed(() => markRaw(buildDualAxisLine(m1m2Dm.value, 'm1_yoy', 'm2_yoy')))
const spreadOpt = computed(() => markRaw(buildSpreadChart(spreadDm.value, 'm2_m1_spread')))
const impulseOpt = computed(() => markRaw(buildCreditImpulseChart(credit.value?.series ?? [])))
const sfOpt = computed(() => markRaw(buildBarLineCombo(sfDm.value, 'total', 'sf_stock_yoy', '社融增量', '存量增速', '亿', '%')))
const ncOpt = computed(() => markRaw(buildBarLineCombo(ncDm.value, 'new_rmb_loan', 'loan_yoy', '新增贷款', '同比', '亿', '%')))
</script>

<template>
  <div class="p-6 space-y-5">
    <header>
      <div>
        <h1 class="text-xl font-bold text-text">信用周期</h1>
        <p class="text-xs text-text-3 mt-1">M2 同比 vs 12 月均线（信贷脉冲）｜社融信贷脉冲</p>
      </div>
    </header>

    <div v-if="credit?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(credit.latest_phase) }" />
      <span class="text-xs text-text-2">当前阶段：<b class="text-text">{{ phaseLabel(credit.latest_phase) }}</b></span>
      <span v-if="credit.latest_value != null" class="text-xs text-text-3">M2 同比 {{ credit.latest_value.toFixed(1) }}%</span>
    </div>

    <GraphCard title="M2 同比与趋势" tip="M2（广义货币）同比增速 vs 12 月均线趋势；背景色为信用周期宽松/紧缩阶段。1992–1996 仅年度结存。" :loading="loading" :error="error" @retry="load">
      <EChart :option="m2Opt" height="360px" />
    </GraphCard>

    <GraphCard title="M1 vs M2 同比" tip="M2-M1 剪刀差扩大常预示需求偏弱；M1 反映企业活期存款与资金活化。" :loading="loading" :error="error" @retry="load">
      <EChart :option="m1m2Opt" height="300px" />
    </GraphCard>

    <GraphCard title="M2−M1 剪刀差" tip="M2 同比减 M1 同比（百分点）。>0 资金活化偏弱（定期化）；0 线为增速持平。" :loading="loading" :error="error" @retry="load">
      <EChart :option="spreadOpt" height="260px" />
    </GraphCard>

    <GraphCard title="信贷脉冲（社融增量）" tip="社融增量代理信贷脉冲；柱高扩张=信用扩张。" :loading="loading" :error="error" @retry="load">
      <EChart :option="impulseOpt" height="260px" />
    </GraphCard>

    <GraphCard title="社会融资规模：增量与存量增速" tip="社融增量（柱，当月新增）+ 社融存量同比增速（线）；央行核心宽信用指标。" :loading="loading" :error="error" @retry="load">
      <EChart :option="sfOpt" height="300px" />
    </GraphCard>

    <GraphCard title="新增人民币贷款与同比" tip="新增人民币贷款（柱，当月值）+ 同比增速（线）；实体融资需求强度。" :loading="loading" :error="error" @retry="load">
      <EChart :option="ncOpt" height="300px" />
    </GraphCard>
  </div>
</template>
