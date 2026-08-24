import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, effectScope, nextTick } from 'vue'
import { useCountUp } from '@/composables/useCountUp'

// FE-L6：0 是合法数值，必须显示 "0.0"（老代码用 truthy 判空，把 0 也当空显示 —）。
// 用 rAF 打桩把动画直接跑到终点，做单次 toFixed(digits) 断言。

beforeEach(() => {
  let now = 1_000_000
  vi.stubGlobal('performance', { now: () => now })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    now += 10_000                       // 一跳跨过 600ms 动画窗口 → t=1
    cb(now)
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', () => {})
})
afterEach(() => { vi.unstubAllGlobals() })

describe('useCountUp', () => {
  it('null → 显示 —', () => {
    const src = ref<number | null>(null)
    const scope = effectScope(); scope.run(() => {
      const d = useCountUp(src)
      expect(d.value).toBe('—')
    })
    scope.stop()
  })

  it('0 是合法数值，显示 "0.0"（FE-L6：不得把 0 视为空）', async () => {
    const src = ref<number | null | undefined>(0)
    const scope = effectScope()
    scope.run(() => {
      const d = useCountUp(src, 600, 1)
      // immediate:true → 首帧同步进入 animate，rAF 桩会直接推进到终点。
      expect(d.value).toBe('0.0')
    })
    scope.stop()
  })

  it('数值→null 回退到 —', async () => {
    const src = ref<number | null>(1.23)
    const scope = effectScope()
    await scope.run(async () => {
      const d = useCountUp(src, 600, 2)
      expect(d.value).toBe('1.23')
      src.value = null
      await nextTick()
      expect(d.value).toBe('—')
    })
    scope.stop()
  })

  it('digits 参数控制精度', async () => {
    const scope = effectScope()
    scope.run(() => {
      const a = useCountUp(ref<number>(3.14159), 600, 0); expect(a.value).toBe('3')
      const b = useCountUp(ref<number>(3.14159), 600, 2); expect(b.value).toBe('3.14')
    })
    scope.stop()
  })
})
