<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildDualAxisLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import MetricTile from '@/components/layout/MetricTile.vue'
import type { SignalSummary } from '@/api/types'

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const loading = ref(true)
const dm = ref<Rec[]>([])
const signals = ref<SignalSummary | null>(null)

function latest(col: string): number | null {
  for (const r of dm.value) {
    const v = r[col]
    if (typeof v === 'number') return v
  }
  return null
}

async function load() {
  loading.value = true
  try {
    const [d, s] = await Promise.all([
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,m2_yoy,cpi_yoy,ppi_yoy,m1_yoy,pmi_official,m2_m1_spread'),
      api.getSignals(),
    ])
    dm.value = d.records.slice().reverse()  // latest first
    signals.value = s
  } finally { loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })

const tiles = [
  { label: 'M2 同比', col: 'm2_yoy', suffix: '%' },
  { label: 'CPI 同比', col: 'cpi_yoy', suffix: '%' },
  { label: 'PMI 官方', col: 'pmi_official' },
  { label: 'M2-M1 剪刀差', col: 'm2_m1_spread', suffix: 'pp' },
]
</script>

<template>
  <div class="p-6 space-y-5 ml-[200px]">
    <header>
      <h1 class="text-xl font-bold text-text">综合概览</h1>
      <p class="text-xs text-text-3 mt-1">关键宏观指标 + 综合信号</p>
    </header>

    <!-- KPI tiles with count-up micro-interaction -->
    <div class="grid grid-cols-5 gap-3">
      <MetricTile v-for="t in tiles" :key="t.col" :label="t.label" :value="latest(t.col)" :suffix="t.suffix" />
      <MetricTile label="综合信号" :value="signals?.composite_score ?? null" accent />
    </div>
    <p v-if="signals" class="text-xs text-text-2">{{ signals.interpretation }}</p>

    <GraphCard title="CPI vs PPI 同比" tip="居民消费价格 vs 工业生产者出厂价格同比。" :loading="loading">
      <EChart :option="buildDualAxisLine(dm.slice().reverse(), 'cpi_yoy', 'ppi_yoy')" height="300px" />
    </GraphCard>
    <GraphCard title="M1 vs M2 同比" tip="M2-M1 剪刀差扩大常预示需求偏弱。" :loading="loading">
      <EChart :option="buildDualAxisLine(dm.slice().reverse(), 'm1_yoy', 'm2_yoy')" height="300px" />
    </GraphCard>
  </div>
</template>
