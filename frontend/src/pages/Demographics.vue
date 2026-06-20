<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildMultiLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const loading = ref(true)
const dm = ref<Rec[]>([])
let reqId = 0

async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const d = await api.getTable('demographics', filters.start ?? undefined, filters.end ?? undefined)
    if (mine !== reqId) return
    dm.value = d.records
  } finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })

function latest(col: string): number | null {
  for (const r of dm.value) {
    const v = r[col]
    if (typeof v === 'number') return v
  }
  return null
}
</script>

<template>
  <div class="p-6 space-y-5">
    <header>
      <h1 class="text-xl font-bold text-text">人口与城镇化</h1>
      <p class="text-xs text-text-3 mt-1">城镇化率 · 总人口 · 出生率 · 自然增长率（NBS 年度数据）</p>
    </header>

    <!-- KPI -->
    <div class="grid grid-cols-4 gap-3" v-if="dm.length">
      <div class="bg-card border border-border rounded-xl p-4">
        <div class="text-xs text-text-3">城镇化率</div>
        <div class="text-2xl font-bold text-text mt-1">{{ latest('urbanization_rate')?.toFixed(1) ?? '—' }}<span class="text-sm text-text-3 ml-0.5">%</span></div>
      </div>
      <div class="bg-card border border-border rounded-xl p-4">
        <div class="text-xs text-text-3">年末总人口</div>
        <div class="text-2xl font-bold text-text mt-1">{{ latest('population')?.toFixed(0) ?? '—' }}<span class="text-sm text-text-3 ml-0.5">万</span></div>
      </div>
      <div class="bg-card border border-border rounded-xl p-4">
        <div class="text-xs text-text-3">出生率</div>
        <div class="text-2xl font-bold text-text mt-1">{{ latest('birth_rate')?.toFixed(2) ?? '—' }}<span class="text-sm text-text-3 ml-0.5">‰</span></div>
      </div>
      <div class="bg-card border border-border rounded-xl p-4">
        <div class="text-xs text-text-3">自然增长率</div>
        <div class="text-2xl font-bold text-text mt-1">{{ latest('natural_growth_rate')?.toFixed(2) ?? '—' }}<span class="text-sm text-text-3 ml-0.5">‰</span></div>
      </div>
    </div>

    <GraphCard title="常住人口城镇化率" tip="城镇常住人口占总人口比重，反映城镇化进程。NBS 年度数据。" :loading="loading">
      <EChart :option="buildMultiLine(dm, [{ col: 'urbanization_rate', name: '城镇化率' }], '%')" height="300px" />
    </GraphCard>

    <GraphCard title="年末总人口" tip="年末常住人口（万人），近年增速趋缓。NBS 年度数据。" :loading="loading">
      <EChart :option="buildMultiLine(dm, [{ col: 'population', name: '年末总人口' }], '万人')" height="300px" />
    </GraphCard>

    <GraphCard title="出生率与自然增长率" tip="出生率（‰）与自然增长率（‰，= 出生率 − 死亡率）。0 线为人口零增长。" :loading="loading">
      <EChart :option="buildMultiLine(dm, [{ col: 'birth_rate', name: '出生率' }, { col: 'natural_growth_rate', name: '自然增长率' }], '‰', 0)" height="300px" />
    </GraphCard>
  </div>
</template>
