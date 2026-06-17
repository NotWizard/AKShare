<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const items = [
  { to: '/overview', label: '综合概览', icon: '◉' },
  { to: '/merrill-clock', label: '美林时钟', icon: '◐' },
  { to: '/credit-cycle', label: '信用周期', icon: '◈' },
  { to: '/inventory-cycle', label: '库存周期', icon: '▣' },
  { to: '/debt-cycle', label: '债务周期', icon: '◆' },
  { to: '/real-estate', label: '房地产市场', icon: '▧' },
]
const isActive = (to: string) => computed(() =>
  to === '/overview' ? route.path === to : route.path.startsWith(to),
)
</script>

<template>
  <aside class="w-[200px] shrink-0 min-h-screen bg-surface border-r border-border fixed top-0 left-0 overflow-y-auto z-[100]">
    <div class="px-3.5 pt-5 pb-4 border-b border-border">
      <div class="text-lg font-extrabold tracking-widest text-text">MACRO</div>
      <div class="text-[11px] text-text-3 mt-1">中国经济分析平台</div>
    </div>
    <nav class="py-2">
      <RouterLink
        v-for="it in items"
        :key="it.to"
        :to="it.to"
        class="flex items-center gap-2.5 px-3.5 py-2 mx-0 mb-0.5 rounded-lg text-[13px] font-medium transition-all"
        :class="isActive(it.to).value
          ? 'bg-[rgba(99,102,241,0.15)] text-text border-l-2 border-accent pl-3'
          : 'text-text-3 hover:bg-[rgba(255,255,255,0.04)] hover:text-text-2'"
      >
        <span class="text-sm opacity-60 w-4 text-center">{{ it.icon }}</span>
        <span>{{ it.label }}</span>
      </RouterLink>
    </nav>
    <div class="absolute bottom-4 left-3 right-3 pt-3 border-t border-border text-[10px] text-text-3 leading-relaxed">
      <div>数据来源</div>
      <div class="mt-0.5 opacity-70">FastAPI · analysis · AKShare</div>
    </div>
  </aside>
</template>
