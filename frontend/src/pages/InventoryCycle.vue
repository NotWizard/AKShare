<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import SectionCommentary from '@/components/layout/SectionCommentary.vue'
import { buildDualAxisLine, buildScatterQuadrant, buildMultiLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
const refresh = useRefreshStore()
type Rec = Record<string, string | number | null>

// useAsyncData owns loading/error/abort; `load` is still the retry handler.
const { data, errorText: error, loading, retry: load } = useAsyncData(async (signal) => {
  const [ip, cx, c] = await Promise.all([
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,pmi_official,ip_yoy', true, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,pmi_official,pmi_caixin,pmi_non_mfg,pmi_caixin_svc', true, { signal }),
    api.getCycle('inventory', filters.start ?? undefined, filters.end ?? undefined, { signal }),
  ])
  return { ip: markRaw(ip.records), pmi: markRaw(cx.records), cycle: markRaw(c) }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

// Per-chart groups so 财新 PMI (2012) doesn't truncate 官方 PMI + IP (2008).
const ipDm = computed<Rec[]>(() => data.value?.ip ?? [])      // date,pmi_official,ip_yoy → 2008-02
const pmiDm = computed<Rec[]>(() => data.value?.pmi ?? [])    // date,pmi_official,pmi_caixin,pmi_non_mfg,pmi_caixin_svc → 2012-04
const cycle = computed<CycleFrame | null>(() => data.value?.cycle ?? null)

// Options built in computeds (not the template) → one markRaw'd object per
// rebuild that ECharts merges into the live instance (preserves zoom/legend).
const ipOpt = computed(() => markRaw(buildDualAxisLine(ipDm.value, 'pmi_official', 'ip_yoy', '#6366f1', '#f59e0b')))
const quadOpt = computed(() => markRaw(buildScatterQuadrant(cycle.value?.series ?? [], 'pmi_official', 'ip_yoy', 'PMI', '工业增加值同比(%)', null, 50)))
const pmiOpt = computed(() => markRaw(buildMultiLine(pmiDm.value, [{ col: 'pmi_official', name: '官方' }, { col: 'pmi_caixin', name: '财新' }, { col: 'pmi_non_mfg', name: '非制造业' }, { col: 'pmi_caixin_svc', name: '服务' }], '', 50)))
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
    <GraphCard title="PMI vs 工业增加值同比" tip="PMI 50 荣枯线；工业增加值同比趋势。" :loading="loading" :error="error" @retry="load">
      <EChart :option="ipOpt" height="320px" />
    </GraphCard>
    <SectionCommentary section="inventory" />
    <GraphCard title="库存周期四象限" tip="PMI vs 工业增加值同比的阶段分布。" :loading="loading" :error="error" @retry="load">
      <EChart :option="quadOpt" :not-merge="true" height="360px" />
    </GraphCard>
    <GraphCard title="PMI 多维（官方 / 财新 / 非制造业 / 服务）" tip="官方制造业 PMI + 财新制造业 PMI（公认领先）+ 非制造业 PMI + 财新服务业 PMI；50 为荣枯线。" :loading="loading" :error="error" @retry="load">
      <EChart :option="pmiOpt" height="300px" />
    </GraphCard>
  </div>
</template>
