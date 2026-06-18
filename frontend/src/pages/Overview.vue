<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { buildDualAxisLine, buildMultiLine } from '@/components/charts/options'
import EChart from '@/components/charts/EChart.vue'
import GraphCard from '@/components/layout/GraphCard.vue'
import MetricTile from '@/components/layout/MetricTile.vue'
import type { SignalSummary } from '@/api/types'

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const loading = ref(true)
const dm = ref<Rec[]>([])
const signals = ref<SignalSummary | null>(null)
let reqId = 0   // request token: rapid preset changes can race; only the latest result applies

function latest(col: string): number | null {
  for (const r of dm.value) {
    const v = r[col]
    if (typeof v === 'number') return v
  }
  return null
}

async function load() {
  const mine = ++reqId
  loading.value = true
  try {
    const [d, s] = await Promise.all([
      api.getDerivedMonthly(filters.start ?? undefined, filters.end ?? undefined, 'date,m2_yoy,cpi_yoy,ppi_yoy,m1_yoy,pmi_official,pmi_caixin,pmi_non_mfg,pmi_caixin_svc,m2_m1_spread,m0_yoy,lpr_1y,lpr_5y,real_rate,cpi_mom'),
      api.getSignals(),
    ])
    if (mine !== reqId) return  // superseded by a newer request
    dm.value = d.records.slice().reverse()  // latest first
    signals.value = s
  } finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; load() })

const tiles = [
  { label: 'M2 同比', col: 'm2_yoy', suffix: '%' },
  { label: 'CPI 同比', col: 'cpi_yoy', suffix: '%' },
  { label: 'PMI 官方', col: 'pmi_official' },
  { label: '财新 PMI', col: 'pmi_caixin' },
  { label: 'M2-M1 剪刀差', col: 'm2_m1_spread', suffix: 'pp' },
  { label: 'M0 同比', col: 'm0_yoy', suffix: '%' },
]

// Cross-indicator leading/lag (surfaced from analysis signals.cross_lags).
const lagNum = (k: string): number | null => {
  const v = (signals.value?.cross_lags as Record<string, unknown> | undefined)?.[k]
  return typeof v === 'number' ? v : null
}
const fmtLag = (k: string) => lagNum(k) ?? '—'
const fmtCorr = (k: string) => lagNum(k) !== null ? lagNum(k)!.toFixed(2) : '—'
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
    <GraphCard title="CPI 同比 vs 环比" tip="同比（年度通胀）vs 环比（月度变动，0 上下波动）。" :loading="loading">
      <EChart :option="buildDualAxisLine(dm.slice().reverse(), 'cpi_yoy', 'cpi_mom')" height="260px" />
    </GraphCard>
    <GraphCard title="利率环境" tip="LPR 1 年/5 年利率 + 实际利率（LPR 1Y − CPI 同比）。" :loading="loading">
      <EChart :option="buildMultiLine(dm.slice().reverse(), [{ col: 'lpr_1y', name: 'LPR 1年' }, { col: 'lpr_5y', name: 'LPR 5年' }, { col: 'real_rate', name: '实际利率' }], '%')" height="300px" />
    </GraphCard>
    <GraphCard title="PMI 多维（官方 / 财新 / 非制造业 / 服务）" tip="官方制造业 PMI + 财新制造业 PMI（公认领先）+ 非制造业 PMI + 财新服务业 PMI；50 为荣枯线。" :loading="loading">
      <EChart :option="buildMultiLine(dm.slice().reverse(), [{ col: 'pmi_official', name: '官方' }, { col: 'pmi_caixin', name: '财新' }, { col: 'pmi_non_mfg', name: '非制造业' }, { col: 'pmi_caixin_svc', name: '服务' }])" height="300px" />
    </GraphCard>

    <!-- 跨指标领先/滞后（消费 analysis 的 signals.cross_lags，零额外计算）-->
    <div v-if="signals?.cross_lags" class="text-xs text-text-2 space-y-1 px-4 py-3 rounded-lg bg-card border border-border">
      <div class="text-text-3 uppercase tracking-wide">跨指标领先</div>
      <div>M1 → PPI 领先约 <b class="text-text">{{ fmtLag('m1_ppi_best_lag') }}</b> 个月（相关 r = {{ fmtCorr('m1_ppi_max_corr') }}）</div>
      <div>剪刀差 → CPI 领先约 <b class="text-text">{{ fmtLag('spread_cpi_best_lag') }}</b> 个月（相关 r = {{ fmtCorr('spread_cpi_max_corr') }}）</div>
    </div>
  </div>
</template>
