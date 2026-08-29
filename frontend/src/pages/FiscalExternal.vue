<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import SectionCommentary from '@/components/layout/SectionCommentary.vue'
import { buildMultiLine, buildSpreadChart } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const refresh = useRefreshStore()

// useAsyncData owns loading/error/abort; `load` is still the retry handler.
const { data, errorText: error, loading, retry: load } = useAsyncData(async (signal) => {
  const [f, x] = await Promise.all([
    api.getTable('fiscal', filters.start ?? undefined, filters.end ?? undefined, { signal }),
    api.getTable('external_demand', filters.start ?? undefined, filters.end ?? undefined, { signal }),
  ])
  return { fiscal: markRaw(f.records), ext: markRaw(x.records) }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

// 两张原始表直通 /table/{name}（不进 derived/signals），前端直读
const fiscal = computed<Rec[]>(() => data.value?.fiscal ?? [])
const ext = computed<Rec[]>(() => data.value?.ext ?? [])

// Options built in computeds (not the template) → one markRaw'd object per
// rebuild that ECharts merges into the live instance (preserves zoom/legend).
const revYoyOpt = computed(() => markRaw(buildMultiLine(fiscal.value, [{ col: 'revenue_cum_yoy', name: '财政收入累计同比' }, { col: 'expenditure_cum_yoy', name: '财政支出累计同比' }], '%')))
const revCumOpt = computed(() => markRaw(buildMultiLine(fiscal.value, [{ col: 'revenue_cum', name: '财政收入(累计)' }, { col: 'expenditure_cum', name: '财政支出(累计)' }], '亿元')))
const tradeYoyOpt = computed(() => markRaw(buildMultiLine(ext.value, [{ col: 'exports_yoy', name: '出口同比(美元)' }, { col: 'imports_yoy', name: '进口同比(美元)' }], '%', 0, '零线')))
const balanceOpt = computed(() => markRaw(buildSpreadChart(ext.value, 'trade_balance', '贸易差额', '亿美元', 0)))
const ismOpt = computed(() => markRaw(buildMultiLine(ext.value, [{ col: 'us_ism_pmi', name: '美国ISM制造业PMI' }], '', 50)))
</script>

<template>
  <div class="p-6 space-y-5">
    <header><h1 class="text-xl font-bold text-text">财政与外需</h1>
      <p class="text-xs text-text-3 mt-1">国家财政收支（NBS 月度，2015- 起）与货物进出口（美元计）+ 美国 ISM 制造业 PMI（外需景气代理）</p>
    </header>
    <GraphCard title="财政收支累计同比" tip="国家财政收入/支出累计增长（%）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="revYoyOpt" height="320px" />
    </GraphCard>
    <SectionCommentary section="fiscal_external" />
    <GraphCard title="财政收支累计值" tip="国家财政收入/支出累计值（亿元）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="revCumOpt" height="320px" />
    </GraphCard>
    <GraphCard title="进出口同比（美元计）" tip="出口/进口总值同比增长（%），零线参考。" :loading="loading" :error="error" @retry="load">
      <EChart :option="tradeYoyOpt" height="320px" />
    </GraphCard>
    <GraphCard title="贸易差额" tip="进出口差额当期值（亿美元）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="balanceOpt" height="300px" />
    </GraphCard>
    <GraphCard title="美国 ISM 制造业 PMI" tip="外需景气代理；荣枯线 50。日期由发布日归一到数据月。Jin10 源冻结于 2025-08 数据月，其后由 ISM 官方发布值按月人工/Agent 补充（见 docs/data-supplement-runbook.md）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="ismOpt" height="300px" />
    </GraphCard>
  </div>
</template>
