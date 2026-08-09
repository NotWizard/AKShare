<script setup lang="ts">
// 健康灯 — GET /sources/health 纯函数推导（无新存储）。
// 绿 = 各源正常；黄 = 1 连败或 kept_previous warning；红 = 任一源 2 连败；
// 灰点 = 尚无运行记录 / 后端不可达。
import { computed, nextTick, onMounted, ref } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useRefreshStore } from '@/stores/refresh'

const refresh = useRefreshStore()
onMounted(() => refresh.loadHealth())

const open = ref(false)
const triggerRef = ref<HTMLButtonElement | null>(null)
const panelRef = ref<HTMLDivElement | null>(null)
onClickOutside(panelRef, () => close(), { ignore: [triggerRef] })

// updated_at 缺失 → 尚无运行记录 → 灰点
const unknown = computed(() => !refresh.health || refresh.health.updated_at === null)
const status = computed<'green' | 'yellow' | 'red' | 'unknown'>(() =>
  unknown.value ? 'unknown' : refresh.health!.status)
const badCount = computed(() =>
  (refresh.health?.sources ?? []).filter((s) => !s.ok || s.consecutive_failures > 0 || s.warning).length)
const ariaLabel = computed(() => {
  const name = { green: '绿', yellow: '黄', red: '红', unknown: '未知' }[status.value]
  return `数据源健康：${name}` + (badCount.value ? `（${badCount.value} 个源异常）` : '')
})
const dotClass: Record<string, string> = {
  green: 'bg-up',
  yellow: 'bg-warn',
  red: 'bg-down ring-1 ring-down/50',
  unknown: 'bg-text-3',
}

function toggle() { open.value ? close() : openPanel() }
async function openPanel() {
  open.value = true
  await nextTick()
  panelRef.value?.focus()  // 焦点移入 dialog
}
function close() {
  if (!open.value) return
  open.value = false
  triggerRef.value?.focus()  // 焦点归还触发器
}
function fullRefresh() {
  close()
  refresh.stream(true)
}
</script>

<template>
  <div class="relative">
    <button
      ref="triggerRef"
      class="p-1.5 rounded transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
      :aria-expanded="open"
      aria-haspopup="dialog"
      @click="toggle"
    >
      <span role="status" class="block w-2 h-2 rounded-full" :class="dotClass[status]" :aria-label="ariaLabel" />
    </button>

    <div
      v-if="open"
      ref="panelRef"
      role="dialog"
      aria-label="数据源健康详情"
      tabindex="-1"
      class="absolute top-full left-0 mt-2 w-[460px] max-w-[calc(100vw-3rem)] max-h-[70vh] overflow-y-auto rounded-lg border border-border-hi bg-card shadow-xl p-3 z-[120] outline-none"
      @keydown.esc="close"
    >
      <div class="flex items-baseline justify-between mb-2">
        <span class="text-xs font-semibold text-text">数据源健康</span>
        <span class="text-[10px] text-text-3 font-mono">{{ refresh.health?.updated_at ?? '暂无运行记录' }}</span>
      </div>

      <div
        v-for="s in refresh.health?.sources ?? []" :key="s.table"
        class="flex items-center gap-2 py-1 border-b border-border last:border-0 text-[11px]"
      >
        <span class="font-mono text-text w-28 shrink-0">{{ s.table }}</span>
        <span class="text-text-3 w-24 shrink-0">{{ s.channel }}</span>
        <span class="text-text-3 flex-1 min-w-0 truncate">{{ s.last_success ?? '从未成功' }}</span>
        <span v-if="s.error" class="text-down shrink-0 max-w-[150px] truncate" :title="s.error">✗ {{ s.error }}</span>
        <span v-else-if="s.warning" class="text-warn shrink-0 max-w-[150px] truncate" :title="s.warning">⚠ {{ s.warning }}</span>
        <span v-else class="text-up shrink-0">✓</span>
      </div>
      <div v-if="!(refresh.health?.sources ?? []).length" class="text-[11px] text-text-3 py-2">暂无数据源信息</div>

      <div class="mt-2 pt-2 border-t border-border flex items-center justify-between gap-3">
        <span class="text-[10px] text-text-3">增量刷新按发布日历自动跳过窗口外的表</span>
        <button
          class="px-3 py-1 text-xs font-semibold rounded-lg border border-border-hi text-text-2 hover:border-accent transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          :disabled="refresh.running"
          @click="fullRefresh"
        >全量刷新</button>
      </div>
    </div>
  </div>
</template>
