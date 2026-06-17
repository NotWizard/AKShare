<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildCreditM2Chart, buildCreditImpulseChart } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()

const loading = ref(true)
const derived = ref<Record<string, string | number | null>[]>([])
const credit = ref<CycleFrame | null>(null)

async function load() {
  loading.value = true
  try {
    const [dm, cc] = await Promise.all([
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,m2_yoy'),
      api.getCycle('credit', filters.start ?? undefined, filters.end ?? undefined),
    ])
    derived.value = dm.records
    credit.value = cc
  } finally {
    loading.value = false
  }
}

watchEffect(() => {
  // re-run when the global filter changes (P3 cross-chart linking)
  void filters.start; void filters.end
  load()
})

const presets = ['5Y', '10Y', '20Y', 'ALL'] as const
</script>

<template>
  <div class="p-6 space-y-5 ml-[200px]">
    <header>
      <div>
        <h1 class="text-xl font-bold text-text">信用周期</h1>
        <p class="text-xs text-text-3 mt-1">M2 同比 vs 12 月均线（信贷脉冲）｜社融信贷脉冲</p>
      </div>
    </header>

    <!-- Latest phase badge -->
    <div v-if="credit?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(credit.latest_phase) }" />
      <span class="text-xs text-text-2">当前阶段：<b class="text-text">{{ phaseLabel(credit.latest_phase) }}</b></span>
      <span v-if="credit.latest_value != null" class="text-xs text-text-3">M2 同比 {{ credit.latest_value.toFixed(1) }}%</span>
    </div>

    <GraphCard
      title="M2 同比与趋势"
      tip="M2（广义货币）同比增速 vs 12 月均线趋势；背景色为信用周期宽松/紧缩阶段。1992–1996 仅年度结存。"
      :loading="loading"
    >
      <EChart :option="buildCreditM2Chart(derived, credit?.series ?? [])" height="360px" />
    </GraphCard>

    <GraphCard
      title="信贷脉冲（社融增量）"
      tip="社融增量代理信贷脉冲；柱高扩张=信用扩张。"
      :loading="loading"
    >
      <EChart :option="buildCreditImpulseChart(credit?.series ?? [])" height="260px" />
    </GraphCard>
  </div>
</template>
