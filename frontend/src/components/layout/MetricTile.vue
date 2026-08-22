<script setup lang="ts">
import { toRef } from 'vue'
import { useCountUp } from '@/composables/useCountUp'
import ChartTip from '@/components/controls/ChartTip.vue'

export interface TileDelta {
  text: string
  dir?: 'up' | 'down' | 'flat'
}

const props = withDefaults(defineProps<{
  label: string
  value: number | null
  suffix?: string
  accent?: boolean
  tip?: string
  deltas?: TileDelta[]
  /** Decimals in the animated value: 0 for counts, 2 for per-share numbers. */
  digits?: number
}>(), { digits: 1 })

const display = useCountUp(toRef(() => props.value), 600, props.digits)
</script>

<template>
  <div class="bg-card border border-border rounded-xl p-4 transition-colors hover:border-border-hi">
    <div class="text-xs text-text-3">{{ label }}<ChartTip v-if="tip" :text="tip" /></div>
    <div class="text-2xl font-bold mt-1" :class="accent ? 'text-accent' : 'text-text'">
      {{ display }}<span v-if="suffix" class="text-sm text-text-3 ml-0.5">{{ suffix }}</span>
    </div>
    <div v-if="deltas?.length" class="flex flex-wrap gap-x-2.5 gap-y-0.5 mt-1.5 text-[10px] tabular-nums leading-tight">
      <span
        v-for="(d, i) in deltas"
        :key="i"
        :class="d.dir === 'up' ? 'text-emerald-400' : d.dir === 'down' ? 'text-red-400' : 'text-text-3'"
      >{{ d.dir === 'up' ? '▲' : d.dir === 'down' ? '▼' : '·' }} {{ d.text }}</span>
    </div>
  </div>
</template>
