// Animated count-up for numeric KPI tiles (micro-interaction, no heavy dep).
import { ref, watch, type Ref } from 'vue'

export function useCountUp(source: Ref<number | null | undefined>, duration = 600) {
  const display = ref<string>('—')
  let raf = 0

  function animate(target: number) {
    cancelAnimationFrame(raf)
    const from = 0
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)   // easeOutCubic
      const val = from + (target - from) * eased
      display.value = val.toFixed(1)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }

  watch(source, (v) => {
    if (typeof v === 'number') animate(v)
    else display.value = '—'
  }, { immediate: true })

  return display
}
