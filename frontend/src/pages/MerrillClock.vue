<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import SectionCommentary from '@/components/layout/SectionCommentary.vue'
import { buildScatterQuadrant, buildDualAxisLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { phaseColor, phaseLabel } from '@/design/phases'
import type { CycleFrame } from '@/api/types'

const filters = useFiltersStore()
const refresh = useRefreshStore()
// 通胀原料曲线（美林纵轴 CPI 的主轴 + 短周期先行）
type Rec = Record<string, string | number | null>

// useAsyncData owns loading/error/abort; `load` is still the retry handler.
const { data, errorText: error, loading, retry: load } = useAsyncData(async (signal) => {
  const [r, cp, cm] = await Promise.all([
    api.getCycle('merrill', filters.start ?? undefined, filters.end ?? undefined, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,cpi_yoy,ppi_yoy', true, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,cpi_mom,ppi_mom', true, { signal }),
  ])
  return { merrill: markRaw(r), cpiPpi: markRaw(cp.records), cpiMom: markRaw(cm.records) }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

const merrill = computed<CycleFrame | null>(() => data.value?.merrill ?? null)
const cpiPpi = computed<Rec[]>(() => data.value?.cpiPpi ?? [])   // cpi_yoy,ppi_yoy
const cpiMom = computed<Rec[]>(() => data.value?.cpiMom ?? [])   // cpi_mom,ppi_mom (环比呼应图)

// Options built in computeds (not the template) → one markRaw'd object per
// rebuild that ECharts merges into the live instance (preserves zoom/legend).
// 分类边界是「GDP vs 趋势（5 期中位数潜在增长 ±0.5pp 死区）」而非 GDP=0：
// 横轴换成 (gdp_yoy − gdp_trend)，零线即边界中心——点的相位颜色与视觉象限一致。
const quadrant = computed(() =>
  (merrill.value?.series ?? []).map((r) => ({
    ...r,
    gdp_gap:
      typeof r.gdp_yoy === 'number' && typeof r.gdp_trend === 'number'
        ? r.gdp_yoy - r.gdp_trend
        : null,
  })),
)
const clockOpt = computed(() => markRaw(buildScatterQuadrant(quadrant.value, 'gdp_gap', 'cpi_yoy', 'GDP同比−潜在增长(pp)', 'CPI同比(%)', 2, 0)))
const cpiPpiOpt = computed(() => markRaw(buildDualAxisLine(cpiPpi.value, 'cpi_yoy', 'ppi_yoy')))
const cpiMomOpt = computed(() => markRaw(buildDualAxisLine(cpiMom.value, 'cpi_mom', 'ppi_mom')))
</script>

<template>
  <div class="p-6 space-y-5">
    <header><h1 class="text-xl font-bold text-text">美林时钟</h1>
      <p class="text-xs text-text-3 mt-1">增长缺口（GDP 同比 − 潜在增长）vs CPI 同比四象限（复苏/过热/滞胀/衰退）</p>
    </header>
    <div v-if="merrill?.latest_phase" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border">
      <span class="w-2 h-2 rounded-full" :style="{ background: phaseColor(merrill.latest_phase) }" />
      <span class="text-xs text-text-2">当前：<b class="text-text">{{ phaseLabel(merrill.latest_phase) }}</b></span>
    </div>
    <GraphCard title="美林投资时钟" tip="横轴 = GDP 同比 − 潜在增长（5 期中位数趋势，分类带 ±0.5pp 死区，零线即边界中心）、纵轴 CPI 同比；点的颜色为投资时钟阶段（复苏/过热/滞胀/衰退）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="clockOpt" :not-merge="true" height="420px" />
    </GraphCard>
    <SectionCommentary section="merrill" />
    <GraphCard title="CPI vs PPI 同比" tip="居民消费价格 vs 工业生产者出厂价格同比——美林时钟纵轴 CPI 的主轴曲线。" :loading="loading" :error="error" @retry="load">
      <EChart :option="cpiPpiOpt" height="300px" />
    </GraphCard>
    <GraphCard title="CPI vs PPI 环比" tip="居民消费价格 vs 工业生产者出厂价格环比（月度高频先行、0 上下波动），与同比图呼应。PPI 环比为同比推导值（东财无免费直接源）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="cpiMomOpt" height="260px" />
    </GraphCard>
  </div>
</template>
