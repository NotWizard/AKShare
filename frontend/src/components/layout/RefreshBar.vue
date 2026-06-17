<script setup lang="ts">
import { onMounted } from 'vue'
import { useRefreshStore } from '@/stores/refresh'
import { useFiltersStore, type Preset } from '@/stores/filters'

const refresh = useRefreshStore()
const filters = useFiltersStore()
onMounted(() => refresh.loadStatus())

const presets: Preset[] = ['5Y', '10Y', '20Y', 'ALL']
</script>

<template>
  <div class="sticky top-0 z-50 flex items-center gap-3 px-6 py-2 bg-surface/85 backdrop-blur border-b border-border">
    <!-- GLOBAL date-range presets: one change links every chart on every page -->
    <div class="flex gap-1.5">
      <button
        v-for="p in presets" :key="p"
        class="px-2.5 py-1 text-[11px] rounded border transition-all"
        :class="filters.preset === p
          ? 'border-accent text-text bg-[rgba(99,102,241,0.15)]'
          : 'border-border text-text-3 hover:border-border-hi'"
        @click="filters.applyPreset(p)"
      >{{ p }}</button>
    </div>

    <div class="w-px h-4 bg-border" />

    <button
      class="px-3 py-1 text-xs font-semibold rounded-lg border transition-all"
      :class="refresh.running
        ? 'border-border text-text-3 cursor-wait'
        : 'border-border-hi text-text hover:border-accent'"
      :disabled="refresh.running"
      @click="refresh.stream()"
    >
      {{ refresh.running ? '🔄 采集中…' : '🔄 刷新数据' }}
    </button>

    <div v-if="refresh.running" class="flex-1 max-w-[200px] h-1 bg-[rgba(255,255,255,0.06)] rounded overflow-hidden">
      <div class="h-full bg-accent transition-all duration-200" :style="{ width: (refresh.progress * 100).toFixed(0) + '%' }" />
    </div>
    <div v-else-if="refresh.lastResult" class="text-[11px] text-text-3 truncate">
      {{ refresh.lastResult.msg }}{{ refresh.lastResult.ts ? ' · ' + refresh.lastResult.ts : '' }}
    </div>
  </div>
</template>
