<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useRefreshStore } from '@/stores/refresh'
import { useFiltersStore, type Preset } from '@/stores/filters'
import HealthLight from './HealthLight.vue'

const refresh = useRefreshStore()
const filters = useFiltersStore()
const route = useRoute()
onMounted(() => refresh.loadStatus())

const presets: Preset[] = ['5Y', '10Y', '20Y', 'ALL']

// Per-route capabilities (router meta) — controls that don't apply are hidden
// rather than rendered dead (FE-H4: on CRCL the presets and 🔄 did nothing).
const showDateFilter = computed(() => route.meta.dateFilter !== false)
// `null` means "no refresh action here" and must survive; only a MISSING key defaults.
const refreshKind = computed(() => route.meta.refreshKind === undefined ? 'macro' : route.meta.refreshKind)
const canRefresh = computed(() => refreshKind.value !== null)
const refreshLabel = computed(() => (refreshKind.value === 'crcl' ? '🔄 采集 CRCL' : '🔄 刷新数据'))
// A run started elsewhere still owns the button — never allow two collections.
const busyElsewhere = computed(() => refresh.running && refresh.kind !== refreshKind.value)
const runningHere = computed(() => refresh.running && refresh.kind === refreshKind.value)

function trigger() {
  const k = refreshKind.value
  if (k === null) return
  refresh.stream(false, k)
}
</script>

<template>
  <div class="sticky top-0 z-[110] flex items-center gap-3 px-6 py-2 bg-surface/85 backdrop-blur border-b border-border">
    <!-- GLOBAL date-range presets: one change links every chart on every page -->
    <div v-if="showDateFilter" class="flex gap-1.5">
      <button
        v-for="p in presets" :key="p"
        class="px-2.5 py-1 text-[11px] rounded border transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        :class="filters.preset === p
          ? 'border-accent text-text bg-[rgba(99,102,241,0.15)]'
          : 'border-border text-text-3 hover:border-border-hi'"
        @click="filters.applyPreset(p)"
      >{{ p }}</button>
    </div>
    <div v-else class="text-[11px] text-text-4">本页数据不受全局日期范围影响</div>

    <div class="w-px h-4 bg-border" />

    <HealthLight />

    <button
      v-if="canRefresh"
      class="px-3 py-1 text-xs font-semibold rounded-lg border transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:cursor-not-allowed"
      :class="refresh.running
        ? 'border-border text-text-3 cursor-wait'
        : 'border-border-hi text-text hover:border-accent'"
      :disabled="refresh.running"
      :title="busyElsewhere ? '另一项采集正在进行，请稍候' : undefined"
      @click="trigger"
    >
      {{ runningHere ? '🔄 采集中…' : busyElsewhere ? '🔄 其他采集中…' : refreshLabel }}
    </button>
    <button
      v-if="refresh.running"
      class="px-3 py-1 text-xs font-semibold rounded-lg border border-border-hi text-text-2 hover:border-accent transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
      @click="refresh.cancel()"
    >取消</button>

    <div v-if="refresh.running" class="flex-1 max-w-[200px] h-1 bg-[rgba(255,255,255,0.06)] rounded overflow-hidden" role="progressbar" :aria-valuenow="Math.round(refresh.progress*100)" aria-valuemin="0" aria-valuemax="100">
      <div class="h-full bg-accent transition-all duration-200" :style="{ width: (refresh.progress * 100).toFixed(0) + '%' }" />
    </div>
    <div v-else-if="refresh.lastResult" role="status" aria-live="polite" class="text-[11px] text-text-3 truncate">
      {{ refresh.lastResult.msg }}{{ refresh.lastResult.ts ? ' · ' + refresh.lastResult.ts : '' }}
    </div>
  </div>
</template>
