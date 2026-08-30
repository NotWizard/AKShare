<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()
const groups = [
  {
    label: '宏观分析',
    items: [
      { to: '/overview', label: '综合概览', icon: '◉' },
      { to: '/merrill-clock', label: '美林时钟', icon: '◐' },
      { to: '/credit-cycle', label: '信用周期', icon: '◈' },
      { to: '/inventory-cycle', label: '库存周期', icon: '▣' },
      { to: '/debt-cycle', label: '债务周期', icon: '◆' },
      { to: '/real-estate', label: '房地产市场', icon: '▧' },
      { to: '/demographics', label: '人口与城镇化', icon: '◎' },
      { to: '/fiscal-external', label: '财政与外需', icon: '◫' },
    ],
  },
  {
    label: '追踪与配置',
    items: [
      { to: '/crcl-monitor', label: 'CRCL 监控', icon: '◒' },
      { to: '/ai-settings', label: 'AI 设置', icon: '⚙' },
    ],
  },
]
// Plain function, not a computed factory: the template re-evaluates on every
// route change anyway, so wrapping each call in computed() only created 9 new
// (never-disposed) refs per render. String compare is trivially cheap.
const isActive = (to: string): boolean =>
  to === '/overview' ? route.path === to : route.path.startsWith(to)
</script>

<template>
  <aside class="w-[216px] shrink-0 min-h-screen bg-surface border-r border-border fixed top-0 left-0 overflow-y-auto z-[100] flex flex-col">
    <div class="px-5 pt-6 pb-5">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_var(--accent)]" aria-hidden="true" />
        <span class="text-lg font-extrabold tracking-[0.18em] text-text">MACRO</span>
      </div>
      <div class="text-[11px] text-text-3 mt-1.5">中国经济分析平台</div>
    </div>
    <nav class="flex-1 px-3 pb-4">
      <div v-for="g in groups" :key="g.label" class="mt-4 first:mt-0">
        <div class="px-2.5 mb-1.5 text-[10px] font-semibold tracking-[0.14em] text-text-4 select-none">{{ g.label }}</div>
        <RouterLink
          v-for="it in g.items"
          :key="it.to"
          :to="it.to"
          class="relative flex items-center gap-2.5 px-2.5 py-[7px] mb-0.5 rounded-lg text-[13px] font-medium transition-colors duration-150"
          :class="isActive(it.to)
            ? 'bg-accent-soft text-text'
            : 'text-text-3 hover:bg-white/[0.04] hover:text-text-2'"
        >
          <span
            class="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-full bg-accent transition-opacity duration-150"
            :class="isActive(it.to) ? 'opacity-100' : 'opacity-0'"
            aria-hidden="true"
          />
          <span class="text-sm w-5 text-center transition-opacity" :class="isActive(it.to) ? 'opacity-100 text-accent' : 'opacity-50'" aria-hidden="true">{{ it.icon }}</span>
          <span>{{ it.label }}</span>
        </RouterLink>
      </div>
    </nav>
    <div class="px-5 py-4 border-t border-border text-[10px] text-text-4 leading-relaxed">
      <div>数据来源 · AKShare / NBS / PBoC</div>
      <div class="mt-0.5">FastAPI · Vue 3 · ECharts</div>
    </div>
  </aside>
</template>
