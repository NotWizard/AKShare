import type { Config } from 'tailwindcss'

// 双主题：色板全部引用 CSS 变量（tokens.css 定义暗/亮双套值），
// 工具类（bg-card / text-text-2 / border-border …）零改动自动换肤。
// 注意：var() 色值不支持 bg-x/10 透明度语法——软底色走 up-soft/down-soft/warn-soft 专用 token。
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        card: 'var(--card)',
        'card-hover': 'var(--card-hover)',
        border: 'var(--border)',
        'border-hi': 'var(--border-hi)',
        accent: 'var(--accent)',
        'accent-hi': 'var(--accent-hi)',
        'accent-ink': 'var(--accent-ink)',
        'accent-soft': 'var(--accent-soft)',
        up: 'var(--up)',
        down: 'var(--down)',
        warn: 'var(--warn)',
        info: 'var(--info)',
        'up-soft': 'var(--up-soft)',
        'down-soft': 'var(--down-soft)',
        'warn-soft': 'var(--warn-soft)',
        text: 'var(--text)',
        'text-2': 'var(--text-2)',
        'text-3': 'var(--text-3)',
        // Dimmest text tier that still passes WCAG AA (≥4.5:1) at 10–11px in BOTH themes.
        'text-4': 'var(--text-4)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Inter', 'SF Pro Display', 'Segoe UI', 'Noto Sans SC', 'PingFang SC', 'sans-serif'],
        mono: ['SF Mono', 'JetBrains Mono', 'Fira Code', 'monospace'],
        // 大数字/KPI 用：等宽数字特性经 .tnum utility 开启
        num: ['-apple-system', 'BlinkMacSystemFont', 'Inter', 'SF Pro Display', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
