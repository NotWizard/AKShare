<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildStackedArea } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
const loading = ref(true)
// Read the leverage table DIRECTLY (quarterly, non-null). derived_quarterly's
// leverage columns are null because gdp is annual (YYYY-01-01) and leverage is
// quarterly (YYYY-03/06/09/12) — an exact-date merge hits 0 rows.
const dq = ref<Record<string, string | number | null>[]>([])
const cycle = ref<CycleFrame | null>(null)
let reqId = 0
async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const [q, c] = await Promise.all([
      api.getTable('leverage', filters.start ?? undefined, filters.end ?? undefined),
      api.getCycle('debt', filters.start ?? undefined, filters.end ?? undefined),
    ])
    if (mine !== reqId) return
    dq.value = q.records; cycle.value = c
  } finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })
</script>

<template>
  <div class="p-6 space-y-5 ml-[200px]">
    <header><h1 class="text-xl font-bold text-text">债务周期</h1>
      <p class="text-xs text-text-3 mt-1">各部门杠杆率（达利欧去杠杆框架）</p>
    </header>
    <div v-if="cycle?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(cycle.latest_phase) }" />
      <span class="text-xs text-text-2">总体阶段：<b class="text-text">{{ phaseLabel(cycle.latest_phase) }}</b></span>
    </div>
    <GraphCard title="分部门宏观杠杆率（堆叠）" tip="居民 / 非金融企业 / 政府杠杆率堆叠（占 GDP %）。" :loading="loading">
      <EChart :option="buildStackedArea(dq, ['household', 'non_fin_corp', 'gov_total'])" height="380px" />
    </GraphCard>
    <GraphCard title="政府杠杆：中央 vs 地方" tip="政府部门杠杆率拆分为中央政府与地方政府（占 GDP %）。" :loading="loading">
      <EChart :option="buildStackedArea(dq, ['gov_central', 'gov_local'])" height="320px" />
    </GraphCard>
  </div>
</template>
