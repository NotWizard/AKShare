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
  <div class="bg-card border border-border rounded-xl px-4 pt-3.5 pb-3 transition-colors duration-150 hover:border-border-hi hover:bg-card-hover">
    <div class="text-[11px] font-medium text-text-3 tracking-wide">{{ label }}<ChartTip v-if="tip" :text="tip" /></div>
    <div class="text-[26px] font-extrabold tnum leading-tight mt-1.5" :class="accent ? 'text-accent' : 'text-text'">
      {{ display }}<span v-if="suffix" class="text-[13px] font-medium text-text-3 ml-0.5">{{ suffix }}</span>
    </div>
    <div v-if="deltas?.length" class="flex flex-wrap gap-x-2.5 gap-y-0.5 mt-1.5 text-[10px] tnum leading-tight">
      <span
        v-for="(d, i) in deltas"
        :key="i"
        :class="d.dir === 'up' ? 'text-up' : d.dir === 'down' ? 'text-down' : 'text-text-4'"
      >{{ d.dir === 'up' ? '▲' : d.dir === 'down' ? '▼' : '·' }} {{ d.text }}</span>
    </div>
  </div>
</template>
