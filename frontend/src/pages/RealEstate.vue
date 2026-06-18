<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import { applyTheme, baseAxis, COLORS, PALETTE } from '@/design/echarts.theme'
import { buildRadar } from '@/components/charts/options'

const filters = useFiltersStore()
const loading = ref(true)
const hp = ref<Record<string, string | number | null>[]>([])
const assessment = ref<Record<string, any>>({})

const CITIES = ['北京', '上海', '广州', '深圳', '杭州', '成都', '南京', '武汉', '重庆', '天津']
let reqId = 0

async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const [h, a] = await Promise.all([
      api.getTable('house_price', filters.start ?? undefined, filters.end ?? undefined),
      api.getRealEstate(CITIES),
    ])
    if (mine !== reqId) return
    hp.value = h.records; assessment.value = a
  } finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })

// pivot house_price rows → series per city (new_yoy)
function priceOption(): Record<string, any> {
  const byDate = new Map<string, Record<string, number | null>>()
  for (const r of hp.value) {
    const d = r.date as string
    const c = r.city as string
    if (!byDate.has(d)) byDate.set(d, {})
    byDate.get(d)![c] = r.new_yoy as number | null
  }
  const dates = Array.from(byDate.keys())
  const series = CITIES.map((c, i) => ({
    name: c, type: 'line', connectNulls: true, symbol: 'none',
    lineStyle: { width: 1.5, color: PALETTE[i % PALETTE.length] },
    data: dates.map((d) => byDate.get(d)?.[c] ?? null),
  }))
  return applyTheme({
    xAxis: { type: 'category', data: dates, ...baseAxis({ boundaryGap: false }) },
    yAxis: { type: 'value', ...baseAxis({ name: '同比%' }) },
    series,
  })
}

// the assessment dict may be nested under response.assessment or at top-level
const scores = () => assessment.value.assessment ?? assessment.value
</script>

<template>
  <div class="p-6 space-y-5">
    <header><h1 class="text-xl font-bold text-text">房地产市场</h1>
      <p class="text-xs text-text-3 mt-1">多城市新房价格同比 + 三维评估（杠杆空间/利率环境/价格动能）</p>
    </header>
    <GraphCard title="新建商品住宅价格指数同比（多城市）" tip="70 城房价指数同比；城市可后续多选。" :loading="loading">
      <EChart :option="priceOption()" height="380px" />
    </GraphCard>
    <GraphCard title="房地产三维评估" tip="杠杆空间 / 利率环境 / 价格动能 三维评分（0–100，越高越支撑）。" :loading="loading">
      <EChart :option="buildRadar(scores())" height="360px" />
      <p v-if="scores()?.summary" class="text-xs text-text-2 mt-3">
        {{ scores().summary }}<span v-if="scores()?.composite_score">
          · 综合 {{ Number(scores().composite_score).toFixed(2) }}
        </span>
      </p>
    </GraphCard>
  </div>
</template>
