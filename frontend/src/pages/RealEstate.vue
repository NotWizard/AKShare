<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { api } from '@/api/client'
import { useAsyncData } from '@/composables/useAsyncData'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import SectionCommentary from '@/components/layout/SectionCommentary.vue'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { applyTheme, baseAxis, COLORS, PALETTE } from '@/design/echarts.theme'
import { buildRadar, buildMultiLine } from '@/components/charts/options'

// Register RadarChart only on this page (lazy-loaded via router) — keeps
// Radar out of the shared vendor-echarts chunk.
import { use as echartsUse } from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { RadarComponent } from 'echarts/components'
echartsUse([RadarChart, RadarComponent])

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const refresh = useRefreshStore()

const CITIES = ['北京', '上海', '广州', '深圳', '杭州', '成都', '南京', '武汉', '重庆', '天津']

// useAsyncData owns loading/error/abort; `load` is still the retry handler.
const { data, errorText: error, loading, retry: load } = useAsyncData(async (signal) => {
  const [h, a, r] = await Promise.all([
    api.getTable('house_price', filters.start ?? undefined, filters.end ?? undefined, { signal }),
    api.getRealEstate(CITIES, { signal }),
    api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,lpr_5y,real_rate', true, { signal }),
  ])
  return { hp: markRaw(h.records), assessment: a as Record<string, any>, rate: markRaw(r.records) }
}, { watch: [() => filters.start, () => filters.end, () => refresh.lastRefreshedAt] })

const hp = computed<Rec[]>(() => data.value?.hp ?? [])
const rate = computed<Rec[]>(() => data.value?.rate ?? [])   // lpr_5y, real_rate → 房贷锚
const assessment = computed<Record<string, any>>(() => data.value?.assessment ?? {})

// pivot house_price rows → series per city (new_yoy)
const priceOpt = computed(() => {
  const byDate = new Map<string, Record<string, number | null>>()
  for (const r of hp.value) {
    const d = r.date as string
    const c = r.city as string
    if (!byDate.has(d)) byDate.set(d, {})
    byDate.get(d)![c] = r.new_yoy as number | null
  }
  const dates = Array.from(byDate.keys())
  const series = CITIES.map((c, i) => {
    const color = PALETTE[i % PALETTE.length]
    return {
      name: c, type: 'line', connectNulls: true, symbol: 'none',
      itemStyle: { color }, lineStyle: { width: 1.5, color },
      data: dates.map((d) => byDate.get(d)?.[c] ?? null),
    }
  })
  return markRaw(applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '同比%' }) },
    series,
  }))
})

// the assessment dict may be nested under response.assessment or at top-level
const scores = () => assessment.value.assessment ?? assessment.value

// Remaining options built in computeds (not the template) → one markRaw'd
// object per rebuild that ECharts merges into the live instance.
const rateOpt = computed(() => markRaw(buildMultiLine(rate.value, [{ col: 'lpr_5y', name: 'LPR 5年' }, { col: 'real_rate', name: '实际利率' }], '%')))
const radarOpt = computed(() => markRaw(buildRadar(scores())))
</script>

<template>
  <div class="p-6 space-y-5">
    <header><h1 class="text-xl font-bold text-text">房地产市场</h1>
      <p class="text-xs text-text-3 mt-1">多城市新房价格同比 + 三维评估（杠杆空间/利率环境/价格动能）</p>
    </header>
    <GraphCard title="新建商品住宅价格指数同比（多城市）" tip="70 城房价指数同比；城市可后续多选。" :loading="loading" :error="error" @retry="load">
      <EChart :option="priceOpt" height="380px" />
    </GraphCard>
    <SectionCommentary section="real_estate" />
    <GraphCard title="利率环境（房贷锚）" tip="5 年期 LPR（房贷定价基准）+ 实际利率（LPR 1Y − CPI 同比）；利率走低支撑购房需求。" :loading="loading" :error="error" @retry="load">
      <EChart :option="rateOpt" height="300px" />
    </GraphCard>
    <GraphCard title="房地产三维评估" tip="杠杆空间 / 利率环境 / 价格动能 三维评分（0–100，越高越支撑）。" :loading="loading" :error="error" @retry="load">
      <EChart :option="radarOpt" height="360px" />
      <p v-if="scores()?.summary" class="text-xs text-text-2 mt-3">
        {{ scores().summary }}<span v-if="scores()?.composite_score">
          · 综合 {{ Number(scores().composite_score).toFixed(2) }}
        </span>
      </p>
    </GraphCard>
  </div>
</template>
