<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildScatterQuadrant } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
const loading = ref(true)
const merrill = ref<CycleFrame | null>(null)
let reqId = 0
async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const r = await api.getCycle('merrill', filters.start ?? undefined, filters.end ?? undefined)
    if (mine !== reqId) return
    merrill.value = r
  }
  finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })
</script>

<template>
  <div class="p-6 space-y-5 ml-[200px]">
    <header><h1 class="text-xl font-bold text-text">美林时钟</h1>
      <p class="text-xs text-text-3 mt-1">GDP 同比 vs CPI 同比四象限（复苏/过热/滞胀/衰退）</p>
    </header>
    <div v-if="merrill?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(merrill.latest_phase) }" />
      <span class="text-xs text-text-2">当前：<b class="text-text">{{ phaseLabel(merrill.latest_phase) }}</b></span>
    </div>
    <GraphCard title="美林投资时钟" tip="横轴 GDP 同比、纵轴 CPI 同比；点的颜色为投资时钟阶段。" :loading="loading">
      <EChart :option="buildScatterQuadrant(merrill?.series ?? [], 'gdp_yoy', 'cpi_yoy', 'GDP同比(%)', 'CPI同比(%)', 2, 0)" height="420px" />
    </GraphCard>
  </div>
</template>
