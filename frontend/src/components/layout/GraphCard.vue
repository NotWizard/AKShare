<script setup lang="ts">
import ChartTip from '@/components/controls/ChartTip.vue'

defineProps<{ title: string; tip?: string; loading?: boolean; height?: string; error?: string | null }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <section class="bg-card border border-border rounded-2xl p-5">
    <div v-if="title" class="mb-3">
      <!-- icon hugs the title's right side (was pushed to far right by justify-between) -->
      <h3 class="inline text-sm font-semibold text-text">{{ title }}</h3>
      <ChartTip v-if="tip" :text="tip" />
    </div>
    <!-- The chart slot stays mounted across every load: loading/error render as
         ABSOLUTE overlays so the ECharts instance is never disposed (preserving
         dataZoom + legend) and min-height keeps the layout from jumping. -->
    <div class="relative" :style="{ minHeight: height ?? '320px' }">
      <slot />
      <div v-if="loading"
           class="absolute inset-0 flex items-center justify-center rounded-xl bg-card/70 text-text-3 text-xs">
        加载中…
      </div>
      <div v-else-if="error" role="alert"
           class="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl bg-card/80 text-down text-xs">
        <span>{{ error }}</span>
        <button type="button"
                class="px-3 py-1 rounded-lg border border-border text-text-2 hover:border-accent transition-colors"
                @click="$emit('retry')">
          重试
        </button>
      </div>
    </div>
  </section>
</template>
