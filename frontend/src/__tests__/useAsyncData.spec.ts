import { describe, it, expect, vi } from 'vitest'
import { ref, effectScope, nextTick } from 'vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { ApiError } from '@/api/client'

// FE-H2：4 态机 idle/loading/ok/error 必须完备；自身发出的 abort 不得被当作错误
// 呈现（否则 Overview 会闪一下红条）；superseded 请求也不允许改状态。

describe('useAsyncData', () => {
  it('immediate=true → loading → ok', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const q = useAsyncData(async () => ({ v: 1 }))
      expect(q.state.value).toBe('loading')
      await nextTick(); await nextTick()
      expect(q.state.value).toBe('ok')
      expect(q.data.value).toEqual({ v: 1 })
      expect(q.error.value).toBeNull()
    })
    scope.stop()
  })

  it('ApiError → error 态；errorText 是 message', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const q = useAsyncData(async () => { throw new ApiError('server', '爆了', 500) })
      await nextTick(); await nextTick()
      expect(q.state.value).toBe('error')
      expect(q.errorText.value).toBe('爆了')
    })
    scope.stop()
  })

  it("kind='aborted' 不被视为错误（自身 abort 不能变红）", async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const q = useAsyncData(async () => { throw new ApiError('aborted', '取消') })
      await nextTick(); await nextTick()
      expect(q.state.value).not.toBe('error')
      expect(q.error.value).toBeNull()
    })
    scope.stop()
  })

  it('retry 会 abort 上一发；被 supersede 的响应不改状态', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      let aborted = 0
      const q = useAsyncData<{ n: number }>(async (signal) => {
        signal.addEventListener('abort', () => { aborted++ })
        await new Promise((r) => setTimeout(r, 50))
        if (signal.aborted) throw new ApiError('aborted', 'ab')
        return { n: 1 }
      }, { immediate: false })

      const p1 = q.retry()
      const p2 = q.retry()   // 立即再发一次 → 第一发应被 abort
      await Promise.all([p1, p2])
      expect(aborted).toBeGreaterThanOrEqual(1)
      expect(q.state.value).toBe('ok')   // 只有最新一发落地
    })
    scope.stop()
  })

  it('watch 数组变化触发重新加载', async () => {
    const dep = ref(0)
    let calls = 0
    const scope = effectScope()
    await scope.run(async () => {
      useAsyncData(async () => { calls++; return dep.value }, { watch: [dep] })
      await nextTick(); await nextTick()
      expect(calls).toBe(1)
      dep.value = 1
      await nextTick(); await nextTick()
      expect(calls).toBe(2)
    })
    scope.stop()
  })

  it('作用域销毁后 → 未完的 fetcher 结果不再改状态', async () => {
    let release!: () => void
    const scope = effectScope()
    const q = scope.run(() =>
      useAsyncData<{ v: number }>(() =>
        new Promise<{ v: number }>((r) => { release = () => r({ v: 42 }) })))!
    scope.stop()          // 作用域销毁
    release()             // 迟到的成功回来
    await nextTick(); await nextTick()
    expect(q.state.value).toBe('loading')   // 销毁瞬间的态被冻结
    expect(q.data.value).toBeNull()
  })
})
