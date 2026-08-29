import type { Config } from 'tailwindcss'

// Design tokens mirror dashboard/config.py's Terminal Fintech palette.
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        bg: '#070b12',
        surface: '#0c1322',
        card: '#101a2b',
        'card-hover': '#152236',
        border: 'rgba(148,163,184,0.10)',
        'border-hi': 'rgba(148,163,184,0.18)',
        accent: '#22d3ee',
        'accent-hi': '#67e8f9',
        'accent-ink': '#052531',
        'accent-soft': 'rgba(34,211,238,0.12)',
        up: '#34d399',
        down: '#f87171',
        warn: '#fbbf24',
        info: '#60a5fa',
        text: '#e8eef7',
        'text-2': '#9baac0',
        'text-3': '#7c8da5',
        // Dimmest text tier that still passes WCAG AA (≥4.5:1) at 10–11px:
        // measured in-app at 4.83:1 on #1a2332 (card) and 5.43:1 on #111827
        // (surface). Use this INSTEAD of opacity-dimmed text like
        // text-text-3/60 (2.73:1) or text-text-3/70 (3.21:1), which fail AA.
        'text-4': '#7f90a4',
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
