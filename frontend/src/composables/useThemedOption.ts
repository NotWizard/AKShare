// 主题化图表 option：包一层 computed——读 themeVersion 建立响应式依赖，
// 亮/暗切换时所有图表 option 自动重建（builder 内部经 chartTheme() 取当前主题色）。
import { computed, markRaw, type ComputedRef } from 'vue'
import { themeVersion } from '@/stores/theme'

export function themedOption<T>(fn: () => T): ComputedRef<T> {
  return computed(() => {
    void themeVersion.value   // 主题切换 → 重建 option（整图换肤）
    const v = fn()
    return (v !== null && typeof v === 'object' ? markRaw(v) : v) as T
  })
}
