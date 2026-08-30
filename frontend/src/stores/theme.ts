// 主题 store — 亮/暗切换（模块级单例，不进 pinia：design/ 层也要读，避免 pinia 激活时序依赖）。
// 初始：localStorage 记忆 > 系统 prefers-color-scheme；写 <html data-theme> 驱动 tokens.css 双套变量。
// version 每次切换 +1：图表 option 是纯计算产物，各页 computed 依赖它即整图换肤。
import { ref } from 'vue'

export type ThemeMode = 'dark' | 'light'

const KEY = 'macro-theme'
const hasDOM = typeof window !== 'undefined' && typeof document !== 'undefined'

function initialMode(): ThemeMode {
  if (!hasDOM) return 'dark'   // 测试/SSR 环境默认暗色
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* 隐私模式读不到就当没有 */ }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export const themeMode = ref<ThemeMode>(initialMode())
export const themeVersion = ref(0)

export function applyThemeMode(m: ThemeMode) {
  themeMode.value = m
  themeVersion.value++
  if (hasDOM) document.documentElement.dataset.theme = m
  try { localStorage.setItem(KEY, m) } catch { /* 忽略写入失败 */ }
}

export function toggleTheme() {
  applyThemeMode(themeMode.value === 'dark' ? 'light' : 'dark')
}

export const isLight = () => themeMode.value === 'light'

// 模块加载即同步一次 <html>（初始模式来自记忆/系统）
if (hasDOM) document.documentElement.dataset.theme = themeMode.value
