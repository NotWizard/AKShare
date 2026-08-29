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
  <div class="sticky top-0 z-[110] flex items-center gap-4 px-6 py-2.5 bg-surface/80 backdrop-blur border-b border-border">
    <!-- GLOBAL date-range presets: one change links every chart on every page -->
    <div v-if="showDateFilter" class="flex items-center rounded-lg border border-border p-0.5 gap-0.5" role="group" aria-label="日期范围">
      <button
        v-for="p in presets" :key="p"
        class="px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors duration-150"
        :class="filters.preset === p
          ? 'bg-accent-soft text-accent'
          : 'text-text-3 hover:text-text-2'"
        :aria-pressed="filters.preset === p"
        @click="filters.applyPreset(p)"
      >{{ p === 'ALL' ? '全部' : p }}</button>
    </div>
    <div v-else class="text-[11px] text-text-4">本页数据不受全局日期范围影响</div>

    <div class="w-px h-4 bg-border" />

    <HealthLight />

    <button
      v-if="canRefresh"
      class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-150 disabled:cursor-not-allowed active:scale-[0.98]"
      :class="refresh.running
        ? 'border border-border text-text-3 cursor-wait'
        : 'bg-accent text-accent-ink hover:bg-accent-hi'"
      :disabled="refresh.running"
      :title="busyElsewhere ? '另一项采集正在进行，请稍候' : undefined"
      @click="trigger"
    >
      <span v-if="runningHere" class="inline-block w-3 h-3 rounded-full border-2 border-accent-ink/30 border-t-accent-ink animate-spin" aria-hidden="true" />
      {{ runningHere ? '采集中…' : busyElsewhere ? '其他采集中…' : (refreshKind === 'crcl' ? '采集 CRCL' : '刷新数据') }}
    </button>
    <button
      v-if="refresh.running"
      class="px-3 py-1 text-xs font-semibold rounded-lg border border-border-hi text-text-2 hover:border-accent transition-colors duration-150"
      @click="refresh.cancel()"
    >取消</button>

    <div v-if="refresh.running" class="flex-1 max-w-[200px] h-1 bg-white/[0.06] rounded-full overflow-hidden" role="progressbar" :aria-valuenow="Math.round(refresh.progress*100)" aria-valuemin="0" aria-valuemax="100">
      <div class="h-full bg-accent rounded-full transition-all duration-200" :style="{ width: (refresh.progress * 100).toFixed(0) + '%' }" />
    </div>
    <div v-else-if="refresh.lastResult" role="status" aria-live="polite" class="text-[11px] text-text-4 truncate">
      {{ refresh.lastResult.msg }}{{ refresh.lastResult.ts ? ' · ' + refresh.lastResult.ts : '' }}
    </div>
  </div>
</template>
