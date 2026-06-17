<script setup lang="ts">
defineProps<{ pageTitle?: string }>()
</script>

<template>
  <div class="p-6 ml-[200px]">
    <h1 class="text-xl font-bold text-text">{{ pageTitle }}</h1>
    <div class="mt-6 p-10 rounded-2xl border border-dashed border-border text-center text-text-3">
      <div class="text-sm">P2 待迁移</div>
      <div class="text-xs mt-1 opacity-70">此页将在 Phase 2 从 Dash 迁移为 Vue + ECharts。</div>
    </div>
  </div>
</template>
