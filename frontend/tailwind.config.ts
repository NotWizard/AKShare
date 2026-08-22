import type { Config } from 'tailwindcss'

// Design tokens mirror dashboard/config.py's Terminal Fintech palette.
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        bg: '#0a0e17',
        surface: '#111827',
        card: '#1a2332',
        'card-hover': '#1f2937',
        border: 'rgba(255,255,255,0.06)',
        'border-hi': 'rgba(255,255,255,0.10)',
        accent: '#6366f1',
        up: '#10b981',
        down: '#ef4444',
        warn: '#f59e0b',
        info: '#3b82f6',
        text: '#f1f5f9',
        'text-2': '#94a3b8',
        'text-3': '#8294a8',
        // Dimmest text tier that still passes WCAG AA (≥4.5:1) at 10–11px:
        // measured in-app at 4.83:1 on #1a2332 (card) and 5.43:1 on #111827
        // (surface). Use this INSTEAD of opacity-dimmed text like
        // text-text-3/60 (2.73:1) or text-text-3/70 (3.21:1), which fail AA.
        'text-4': '#7f90a4',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Inter', 'SF Pro Display', 'Segoe UI', 'Noto Sans SC', 'PingFang SC', 'sans-serif'],
        mono: ['SF Mono', 'JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
