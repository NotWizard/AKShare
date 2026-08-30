<script setup lang="ts">
// PageState — the page-level counterpart of GraphCard's overlays: it OWNS the
// loading / error / empty branches so a page can't render content while an
// error is being swallowed (FE-H2: Overview showed `—` KPIs when fetch threw).
//
// Contract: `state` is required and the page's content lives in the default
// slot, so wiring the failure branch is not an optional extra step — dropping
// this wrapper deletes the content too. `hasData` keeps a *re*load
// non-destructive: known-good content stays on screen with a banner/pill instead
// of flashing to a placeholder on every preset click.
import { computed } from 'vue'
import type { ApiError } from '@/api/client'
import type { AsyncState } from '@/composables/useAsyncData'

const props = withDefaults(defineProps<{
  state: AsyncState
  error?: ApiError | null
  /** Content already on screen (page passes `data != null`). */
  hasData?: boolean
  /** Loaded fine, but the dataset itself is empty — NOT the same as a failure. */
  empty?: boolean
  emptyTitle?: string
  emptyHint?: string
  loadingText?: string
  minHeight?: string
}>(), {
  error: null,
  hasData: false,
  empty: false,
  emptyTitle: '暂无数据',
  emptyHint: '后端已连接，但该范围内没有记录。点击顶部「🔄 刷新数据」采集，或放宽日期范围。',
  loadingText: '加载中…',
  minHeight: '240px',
})
defineEmits<{ retry: [] }>()

// Backend-unreachable vs no-data-yet vs server error — named, never a raw dump.
const HINT: Record<string, { title: string; hint: string }> = {
  unreachable: {
    title: '后端未连接',
    hint: '无法连接后端服务（开发环境默认 http://127.0.0.1:8000）。请确认服务已启动，然后重试。数据可能已存在，只是取不到。',
  },
  timeout: {
    title: '请求超时',
    hint: '后端在 30 秒内没有返回。可能正在抓取数据，请稍后重试。',
  },
  server: {
    title: '服务端错误',
    hint: '后端处理请求时出错。可展开详情排查，或稍后重试。',
  },
  client: {
    title: '请求未被接受',
    hint: '通常是参数或接口不匹配（如日期范围非法）。调整筛选条件后重试。',
  },
  aborted: { title: '请求已取消', hint: '请求被中断，可重试。' },
}
const box = computed(() => HINT[props.error?.kind ?? 'server'] ?? HINT.server)
const title = computed(() => (props.error?.kind === 'server' || props.error?.kind === 'client'
  ? props.error.message          // already carries the HTTP status label
  : box.value.title))

const showError = computed(() => props.state === 'error' && !!props.error)
const showContent = computed(() => props.hasData || props.state === 'ok')
const showEmpty = computed(() => props.state === 'ok' && props.empty)
const reloading = computed(() => props.state === 'loading')
</script>

<template>
  <div>
    <!-- reload failed but we still hold good data: banner, don't nuke the page -->
    <div v-if="showError && hasData" role="alert"
         class="mb-4 flex items-start gap-3 px-4 py-3 rounded-xl border border-down bg-down-soft">
      <div class="min-w-0 flex-1 text-xs">
        <div class="font-semibold text-red-300">{{ title }} — 页面显示的是上一次成功获取的数据</div>
        <div class="text-red-300/80 mt-0.5">{{ box.hint }}</div>
      </div>
      <button type="button"
              class="shrink-0 px-3 py-1 rounded-lg border border-border text-text-2 text-xs hover:border-accent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
              @click="$emit('retry')">重试</button>
    </div>

    <!-- first load failed: the ONLY thing on screen (no misleading skeleton) -->
    <div v-else-if="showError" role="alert"
         class="flex flex-col items-center justify-center gap-2 text-center px-6 py-10 rounded-2xl border border-down bg-down-soft"
         :style="{ minHeight }">
      <div class="text-sm font-semibold text-red-300">{{ title }}</div>
      <p class="text-xs text-red-300/80 max-w-[520px] leading-relaxed">{{ box.hint }}</p>
      <details v-if="error?.detail" class="text-[11px] text-text-2 max-w-[520px]">
        <summary class="cursor-pointer text-text-3 hover:text-text-2">技术详情</summary>
        <pre class="mt-1 whitespace-pre-wrap break-words text-left font-mono">{{ error.detail }}</pre>
      </details>
      <button type="button"
              class="mt-1 px-3 py-1 rounded-lg border border-border text-text-2 text-xs hover:border-accent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
              @click="$emit('retry')">重试</button>
    </div>

    <!-- first load in flight -->
    <div v-else-if="!showContent" role="status" aria-live="polite"
         class="flex items-center justify-center rounded-2xl border border-border bg-card text-text-3 text-xs"
         :style="{ minHeight }">
      {{ loadingText }}
    </div>

    <template v-else>
      <div v-if="reloading" role="status" aria-live="polite" class="mb-3 text-[11px] text-text-4">更新中…</div>
      <!-- backend fine, dataset empty — deliberately NOT the error styling -->
      <div v-if="showEmpty"
           class="flex flex-col items-center justify-center gap-2 text-center px-6 py-10 rounded-2xl border border-border bg-card"
           :style="{ minHeight }">
        <div class="text-sm font-semibold text-text-2">{{ emptyTitle }}</div>
        <p class="text-xs text-text-4 max-w-[520px] leading-relaxed">{{ emptyHint }}</p>
      </div>
      <slot v-else />
    </template>
  </div>
</template>
