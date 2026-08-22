// Animated count-up for numeric KPI tiles (micro-interaction, no heavy dep).
import { ref, watch, onScopeDispose, type Ref } from 'vue'

/**
 * @param digits decimals to render. Must match the tile's real precision:
 *   toFixed(1) turned EPS 0.18 into "0.2" (next to a raw 0.26 consensus) and
 *   integer counts into "2.0". Pass 0 for counts, 2 for per-share numbers.
 */
export function useCountUp(source: Ref<number | null | undefined>, duration = 600, digits = 1) {
  const display = ref<string>('—')
  let raf = 0

  function animate(target: number) {
    cancelAnimationFrame(raf)
    let from = parseFloat(display.value)
    if (Number.isNaN(from)) from = 0   // 首次 display='—' → 从 0 起；后续从上次显示值平滑过渡
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)   // easeOutCubic
      const val = from + (target - from) * eased
      display.value = val.toFixed(digits)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }

  watch(source, (v) => {
    if (typeof v === 'number') animate(v)
    else display.value = '—'
  }, { immediate: true })

  // cancel any pending frame when the owner scope is disposed
  onScopeDispose(() => cancelAnimationFrame(raf))

  return display
}
