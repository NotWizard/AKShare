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
        'text-3': '#64748b',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Inter', 'SF Pro Display', 'Segoe UI', 'Noto Sans SC', 'PingFang SC', 'sans-serif'],
        mono: ['SF Mono', 'JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
