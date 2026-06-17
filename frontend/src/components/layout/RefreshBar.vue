<script setup lang="ts">
import { onMounted } from 'vue'
import { useRefreshStore } from '@/stores/refresh'
const refresh = useRefreshStore()
onMounted(() => refresh.loadStatus())
</script>

<template>
  <div class="sticky top-0 z-50 flex items-center gap-3 px-6 py-2 bg-surface/80 backdrop-blur border-b border-border">
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
    <div v-if="refresh.running" class="flex-1 h-1 bg-[rgba(255,255,255,0.06)] rounded overflow-hidden">
      <div class="h-full bg-accent transition-all" :style="{ width: (refresh.progress * 100).toFixed(0) + '%' }" />
    </div>
    <div v-else-if="refresh.lastResult" class="text-[11px] text-text-3 truncate">
      {{ refresh.lastResult.msg }}{{ refresh.lastResult.ts ? ' · ' + refresh.lastResult.ts : '' }}
    </div>
  </div>
</template>
