<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildCreditM2Chart, buildCreditImpulseChart, buildBarLineCombo, buildDualAxisLine, buildSpreadChart } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()

// Per-chart column groups, each with its own align_start so a late-starting
// column (社融存量 2016) doesn't truncate an early one (M2 1991).
type Rec = Record<string, string | number | null>
const m2Dm = ref<Rec[]>([])       // date,m2_yoy        → 1991-12
const m1m2Dm = ref<Rec[]>([])     // date,m1_yoy,m2_yoy → 1991-12
const spreadDm = ref<Rec[]>([])   // date,m2_m1_spread  → 1991-12
const sfDm = ref<Rec[]>([])       // date,total,sf_stock_yoy → 2016-01
const ncDm = ref<Rec[]>([])       // date,new_rmb_loan,loan_yoy → 2009-01
const credit = ref<CycleFrame | null>(null)
const loading = ref(true)
let reqId = 0

async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const [m2, m12, sp, sf, nc, cc] = await Promise.all([
      api.getDerivedMonthly(filters.start ?? '1996-12-01', filters.end ?? undefined, 'date,m2_yoy', true),
      api.getDerivedMonthly(filters.start ?? '1996-12-01', filters.end ?? undefined, 'date,m1_yoy,m2_yoy', true),
      api.getDerivedMonthly(filters.start ?? '1996-12-01', filters.end ?? undefined, 'date,m2_m1_spread', true),
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,total,sf_stock_yoy', true),
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,new_rmb_loan,loan_yoy', true),
      api.getCycle('credit', filters.start ?? undefined, filters.end ?? undefined),
    ])
    if (mine !== reqId) return
    m2Dm.value = m2.records; m1m2Dm.value = m12.records; spreadDm.value = sp.records; sfDm.value = sf.records; ncDm.value = nc.records; credit.value = cc
  } finally { if (mine === reqId) loading.value = false }
}

watchEffect(() => { void filters.start; void filters.end; load() })
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

    <GraphCard title="M2 同比与趋势" tip="M2（广义货币）同比增速 vs 12 月均线趋势；背景色为信用周期宽松/紧缩阶段。1992–1996 仅年度结存。" :loading="loading">
      <EChart :option="buildCreditM2Chart(m2Dm, credit?.series ?? [])" height="360px" />
    </GraphCard>

    <GraphCard title="M1 vs M2 同比" tip="M2-M1 剪刀差扩大常预示需求偏弱；M1 反映企业活期存款与资金活化。" :loading="loading">
      <EChart :option="buildDualAxisLine(m1m2Dm, 'm1_yoy', 'm2_yoy')" height="300px" />
    </GraphCard>

    <GraphCard title="M2−M1 剪刀差" tip="M2 同比减 M1 同比（百分点）。>0 资金活化偏弱（定期化）；0 线为增速持平。" :loading="loading">
      <EChart :option="buildSpreadChart(spreadDm, 'm2_m1_spread')" height="260px" />
    </GraphCard>

    <GraphCard title="信贷脉冲（社融增量）" tip="社融增量代理信贷脉冲；柱高扩张=信用扩张。" :loading="loading">
      <EChart :option="buildCreditImpulseChart(credit?.series ?? [])" height="260px" />
    </GraphCard>

    <GraphCard title="社会融资规模：增量与存量增速" tip="社融增量（柱，当月新增）+ 社融存量同比增速（线）；央行核心宽信用指标。" :loading="loading">
      <EChart :option="buildBarLineCombo(sfDm, 'total', 'sf_stock_yoy', '社融增量', '存量增速', '亿', '%')" height="300px" />
    </GraphCard>

    <GraphCard title="新增人民币贷款与同比" tip="新增人民币贷款（柱，当月值）+ 同比增速（线）；实体融资需求强度。" :loading="loading">
      <EChart :option="buildBarLineCombo(ncDm, 'new_rmb_loan', 'loan_yoy', '新增贷款', '同比', '亿', '%')" height="300px" />
    </GraphCard>
  </div>
</template>
