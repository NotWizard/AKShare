import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useFiltersStore } from '@/stores/filters'

// filters.ts 的时区断言（FE-L1）：applyPreset 必须用**本地日历部件**构造 YYYY-MM-01，
// 而不是 toISOString()——后者会把 Asia/Shanghai 的本地零点向前推 8 小时，5Y 预设
// 在 2026-07 会得到 2021-06-30。这里显式改系统时钟到当年 7 月来锁住这个 bug。

beforeEach(() => {
  setActivePinia(createPinia())
  // 2026-07-15 12:00 UTC —— 无论跑测的机器在什么时区，getMonth()+1 都是 7。
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-07-15T12:00:00Z'))
})
afterEach(() => { vi.useRealTimers() })

describe('filters.applyPreset', () => {
  it('5Y 从年份减 5、月份用当前月，日恒为 01', () => {
    const s = useFiltersStore()
    s.applyPreset('5Y')
    expect(s.preset).toBe('5Y')
    expect(s.start).toBe('2021-07-01')
    expect(s.end).toBeNull()
  })

  it('10Y / 20Y 减 10 / 20 年', () => {
    const s = useFiltersStore()
    s.applyPreset('10Y'); expect(s.start).toBe('2016-07-01')
    s.applyPreset('20Y'); expect(s.start).toBe('2006-07-01')
  })

  it('ALL 清空 start/end', () => {
    const s = useFiltersStore()
    s.applyPreset('5Y')
    s.applyPreset('ALL')
    expect(s.start).toBeNull()
    expect(s.end).toBeNull()
  })

  it('日期部件走本地日历，永远是月初 01（不会被时区推成前一天）', () => {
    const s = useFiltersStore()
    for (const p of ['5Y', '10Y', '20Y'] as const) {
      s.applyPreset(p)
      expect(s.start!.endsWith('-01')).toBe(true)
    }
  })

  it('params 只暴露非空的 start/end', () => {
    const s = useFiltersStore()
    s.applyPreset('ALL')
    expect(s.params).toEqual({ start: undefined, end: undefined })
    s.applyPreset('5Y')
    expect(s.params).toEqual({ start: '2021-07-01', end: undefined })
  })
})
