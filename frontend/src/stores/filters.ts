// Global date-range filter — the cross-chart linking lever (P3 wires charts to it).
// One change here → every subscribed chart refetches. (Dash couldn't do this cleanly.)
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type Preset = '5Y' | '10Y' | '20Y' | 'ALL'

export const useFiltersStore = defineStore('filters', () => {
  const start = ref<string | null>(null)
  const end = ref<string | null>(null)
  const preset = ref<Preset>('ALL')

  function applyPreset(p: Preset) {
    preset.value = p
    if (p === 'ALL') { start.value = null; end.value = null; return }
    const now = new Date()
    const years = p === '5Y' ? 5 : p === '10Y' ? 10 : 20
    // Build from LOCAL parts: toISOString() shifts local midnight into UTC, so in
    // Asia/Shanghai (+08) a 5Y preset used to yield 2021-06-30 for 2026-07.
    const y = now.getFullYear() - years
    const m = String(now.getMonth() + 1).padStart(2, '0')
    start.value = `${y}-${m}-01`
    end.value = null
  }

  function reset() {
    preset.value = 'ALL'
    start.value = null
    end.value = null
  }

  const params = computed(() => ({
    start: start.value ?? undefined,
    end: end.value ?? undefined,
  }))

  return { start, end, preset, applyPreset, reset, params }
})
