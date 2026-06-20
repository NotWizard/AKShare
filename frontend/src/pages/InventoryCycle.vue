<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildDualAxisLine, buildScatterQuadrant, buildMultiLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
type Rec = Record<string, string | number | null>
// Per-chart groups so 财新 PMI (2012) doesn't truncate 官方 PMI + IP (2008).
const ipDm = ref<Rec[]>([])      // date,pmi_official,ip_yoy → 2008-02
const caixinDm = ref<Rec[]>([])  // date,pmi_official,pmi_caixin → 2012-01
const cycle = ref<CycleFrame | null>(null)
const loading = ref(true)
let reqId = 0
async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const [ip, cx, c] = await Promise.all([
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,pmi_official,ip_yoy', true),
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,pmi_official,pmi_caixin', true),
      api.getCycle('inventory', filters.start ?? undefined, filters.end ?? undefined),
    ])
    if (mine !== reqId) return
    ipDm.value = ip.records; caixinDm.value = cx.records; cycle.value = c
  } finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })
</script>

<template>
  <div class="p-6 space-y-5">
    <header><h1 class="text-xl font-bold text-text">库存周期</h1>
      <p class="text-xs text-text-3 mt-1">PMI + 工业增加值 → 主动/被动 补库·去库</p>
    </header>
    <div v-if="cycle?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(cycle.latest_phase) }" />
      <span class="text-xs text-text-2">当前：<b class="text-text">{{ phaseLabel(cycle.latest_phase) }}</b></span>
    </div>
    <GraphCard title="PMI vs 工业增加值同比" tip="PMI 50 荣枯线；工业增加值同比趋势。" :loading="loading">
      <EChart :option="buildDualAxisLine(ipDm, 'pmi_official', 'ip_yoy', '#6366f1', '#f59e0b')" height="320px" />
    </GraphCard>
    <GraphCard title="库存周期四象限" tip="PMI vs 工业增加值同比的阶段分布。" :loading="loading">
      <EChart :option="buildScatterQuadrant(cycle?.series ?? [], 'pmi_official', 'ip_yoy', 'PMI', '工业增加值同比(%)', 50, 0)" height="360px" />
    </GraphCard>
    <GraphCard title="PMI 官方 vs 财新" tip="财新制造业 PMI 常被视为领先指标；50 为荣枯线。" :loading="loading">
      <EChart :option="buildMultiLine(caixinDm, [{ col: 'pmi_official', name: '官方' }, { col: 'pmi_caixin', name: '财新' }], '', 50)" height="300px" />
    </GraphCard>
  </div>
</template>
