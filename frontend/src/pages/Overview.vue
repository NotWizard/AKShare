<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { api } from '@/api/client'
import { useFiltersStore } from '@/stores/filters'
import { useRefreshStore } from '@/stores/refresh'
import MetricTile from '@/components/layout/MetricTile.vue'
import CommentaryCard from '@/components/layout/CommentaryCard.vue'
import type { SignalSummary } from '@/api/types'

type Rec = Record<string, string | number | null>
const filters = useFiltersStore()
const refresh = useRefreshStore()
const loading = ref(true)
const error = ref<string | null>(null)

const kpiDm = ref<Rec[]>([])        // latest-first for KPI latest(); no align
const signals = ref<SignalSummary | null>(null)
let reqId = 0

function latest(col: string): number | null {
  for (const r of kpiDm.value) {           // kpiDm is latest-first
    const v = r[col]
    if (typeof v === 'number') return v
  }
  return null
}

const A = (s?: string, e?: string) => [s, e] as const
async function load() {
  const mine = ++reqId
  loading.value = true
  error.value = null
  const st = filters.start ?? undefined, en = filters.end ?? undefined
  try {
    const [kpi, s] = await Promise.all([
      api.getDerivedMonthly(st, en, 'date,m2_yoy,cpi_yoy,pmi_official,pmi_caixin,m2_m1_spread,m0_yoy'),
      api.getSignals(),
    ])
    if (mine !== reqId) return
    kpiDm.value = kpi.records.slice().reverse()  // latest first
    signals.value = s
  } catch (e) { if (mine === reqId) error.value = (e as Error).message } finally { if (mine === reqId) loading.value = false }
}
watchEffect(() => { void filters.start; void filters.end; void refresh.lastRefreshedAt; load() })
void A

const tiles = [
  { label: 'M2 同比', col: 'm2_yoy', suffix: '%', tip: `广义货币供应量 M2 同比增速，反映市场整体流动性，增速上行通常对应宽货币。

取数：AKShare macro_china_supply_of_money → money_supply.m2_yoy（原始同比，无衍生计算）→ 合并入 derived_monthly 表 → 取日期范围内最近一期有效值，单位 %。` },
  { label: 'CPI 同比', col: 'cpi_yoy', suffix: '%', tip: `居民消费价格指数同比，衡量通胀/通缩，2% 为常用目标线。

取数：AKShare macro_china_cpi_yearly → cpi.cpi_yoy（原始同比）→ left join 入 derived_monthly.cpi_yoy → 取最近一期有效值，单位 %。` },
  { label: 'PMI 官方', col: 'pmi_official', tip: `国家统计局制造业采购经理指数，50 为荣枯分界线，>50 表示扩张。

取数：AKShare macro_china_pmi_yearly → pmi.pmi_official（原始）→ 合并于 derived_monthly.pmi_official → 取最近一期有效值。` },
  { label: '财新 PMI', col: 'pmi_caixin', tip: `财新/S&P 制造业 PMI，样本偏中小及沿海企业，公认领先官方 PMI，同为 50 荣枯线。

取数：AKShare macro_china_cx_pmi_yearly → pmi.pmi_caixin（原始）→ 合并于 derived_monthly.pmi_caixin → 取最近一期有效值。` },
  { label: 'M2-M1 剪刀差', col: 'm2_m1_spread', suffix: 'pp', tip: `M2 同比减 M1 同比，衡量资金活化程度。剪刀差扩大（正值）常预示企业活期存款走弱、需求疲软。

取数：衍生计算 derived_monthly.m2_m1_spread = m2_yoy − m1_yoy（脚本 02_compute_derived.py）→ 取最近一期有效值，单位 pp（百分点）。` },
  { label: 'M0 同比', col: 'm0_yoy', suffix: '%', tip: `流通中现金 M0 同比，反映现金需求与居民消费活跃度。

取数：AKShare macro_china_supply_of_money → money_supply.m0_yoy（原始同比）→ 透传至 derived_monthly.m0_yoy → 取最近一期有效值，单位 %。` },
]

const signalTip = `聚合四大周期（美林/信用/库存/债务）最新阶段的复合得分，范围 [-4, +4]，正值偏多、负值偏空；下方文字为对应解读。

取数：/api/v1/signals → analysis/signals.compute_signals：取四周期最新一期 phase 各查表映射为 −1/0/+1 后求和。`

const lagNum = (k: string): number | null => {
  const v = (signals.value?.cross_lags as Record<string, unknown> | undefined)?.[k]
  return typeof v === 'number' ? v : null
}
const fmtLag = (k: string) => lagNum(k) ?? '—'
const fmtCorr = (k: string) => lagNum(k) !== null ? lagNum(k)!.toFixed(2) : '—'
</script>

<template>
  <div class="p-6 space-y-5">
    <header>
      <h1 class="text-xl font-bold text-text">综合概览</h1>
      <p class="text-xs text-text-3 mt-1">关键宏观指标 + 综合信号</p>
    </header>

    <div class="grid grid-cols-5 gap-3">
      <MetricTile v-for="t in tiles" :key="t.col" :label="t.label" :value="latest(t.col)" :suffix="t.suffix" :tip="t.tip" />
      <MetricTile label="综合信号" :value="signals?.composite_score ?? null" accent :tip="signalTip" />
    </div>
    <p v-if="signals" class="text-xs text-text-2">{{ signals.interpretation }}</p>

    <CommentaryCard />

    <div v-if="signals?.cross_lags" class="text-xs text-text-2 space-y-1 px-4 py-3 rounded-lg bg-card border border-border">
      <div class="text-text-3 uppercase tracking-wide">跨指标领先</div>
      <div>M1 → PPI 领先约 <b class="text-text">{{ fmtLag('m1_ppi_best_lag') }}</b> 个月（相关 r = {{ fmtCorr('m1_ppi_max_corr') }}）</div>
      <div>剪刀差 → CPI 领先约 <b class="text-text">{{ fmtLag('spread_cpi_best_lag') }}</b> 个月（相关 r = {{ fmtCorr('spread_cpi_max_corr') }}）</div>
    </div>
  </div>
</template>
