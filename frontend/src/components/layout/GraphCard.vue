<script setup lang="ts">
import ChartTip from '@/components/controls/ChartTip.vue'

defineProps<{ title: string; tip?: string; loading?: boolean; height?: string }>()
</script>

<template>
  <section class="bg-card border border-border rounded-2xl p-5">
    <div v-if="title" class="mb-3">
      <!-- icon hugs the title's right side (was pushed to far right by justify-between) -->
      <h3 class="inline text-sm font-semibold text-text">{{ title }}</h3>
      <ChartTip v-if="tip" :text="tip" />
    </div>
    <div v-if="loading" class="flex items-center justify-center min-h-[320px] text-text-3 text-xs">
      加载中…
    </div>
    <slot v-else />
  </section>
</template>
