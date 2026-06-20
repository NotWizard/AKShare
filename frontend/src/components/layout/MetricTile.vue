<script setup lang="ts">
import { toRef } from 'vue'
import { useCountUp } from '@/composables/useCountUp'
import ChartTip from '@/components/controls/ChartTip.vue'

const props = defineProps<{
  label: string
  value: number | null
  suffix?: string
  accent?: boolean
  tip?: string
}>()

const display = useCountUp(toRef(() => props.value))
</script>

<template>
  <div class="bg-card border border-border rounded-xl p-4 transition-colors hover:border-border-hi">
    <div class="text-xs text-text-3">{{ label }}<ChartTip v-if="tip" :text="tip" /></div>
    <div class="text-2xl font-bold mt-1" :class="accent ? 'text-accent' : 'text-text'">
      {{ display }}<span v-if="suffix" class="text-sm text-text-3 ml-0.5">{{ suffix }}</span>
    </div>
  </div>
</template>
