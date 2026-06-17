<script setup lang="ts">
defineProps<{ title: string; tip?: string; loading?: boolean; height?: string }>()
</script>

<template>
  <section class="bg-card border border-border rounded-2xl p-5">
    <div v-if="title" class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-text">{{ title }}</h3>
      <span v-if="tip" class="chart-tip text-text-3 text-xs cursor-help" :data-tip="tip">ⓘ</span>
    </div>
    <div v-if="loading" class="flex items-center justify-center min-h-[320px] text-text-3 text-xs">
      加载中…
    </div>
    <slot v-else />
  </section>
</template>
