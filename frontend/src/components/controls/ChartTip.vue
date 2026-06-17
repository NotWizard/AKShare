<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<template>
  <span class="chart-tip text-text-3 text-xs cursor-help" :data-tip="text">ⓘ</span>
</template>
