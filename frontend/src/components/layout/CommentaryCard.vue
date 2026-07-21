<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/api/client'
import type { Commentary } from '@/api/types'

const data = ref<Commentary>({ ts: null, data_as_of: null, composite_score: null, text: '', model: null, stale: false, status: 'empty', msg: null })
const loading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

async function fetch() {
  try {
    data.value = await api.getCommentary()
  } catch (e) {
    data.value = { ...data.value, status: 'error', msg: (e as Error).message }
  }
}

async function regenerate() {
  loading.value = true
  try {
    const r = await api.regenerateCommentary()
    data.value = r
    // If backend kicked off async generation, poll until done.
    if (r.status === 'generating') startPolling()
  } catch (e) {
    data.value = { ...data.value, status: 'error', msg: (e as Error).message }
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await fetch()
    if (data.value.status !== 'generating') stopPolling()
  }, 2000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

onMounted(async () => {
  await fetch()
  if (data.value.status === 'generating') startPolling()
})
onUnmounted(stopPolling)
</script>

<template>
  <div class="bg-card border border-border rounded-xl p-4 transition-colors hover:border-border-hi">
    <div class="flex items-center justify-between mb-2">
      <div class="text-xs text-text-3 uppercase tracking-wide">AI 宏观分析评论</div>
      <button
        class="text-xs px-2.5 py-1 rounded-lg border border-border hover:border-border-hi text-text-2 transition-colors disabled:opacity-50"
        :disabled="loading || data.status === 'generating'"
        @click="regenerate"
      >
        {{ data.status === 'generating' ? '生成中…' : '重新分析' }}
      </button>
    </div>

    <!-- generating / empty / error states -->
    <div v-if="data.status === 'generating'" class="text-sm text-text-2 py-3 animate-pulse">
      {{ data.msg || '评论生成中…' }}
    </div>
    <div v-else-if="data.status === 'empty'" class="text-sm text-text-3 py-3">
      {{ data.msg || '暂无评论 — 点击「重新分析」生成（需配置模型）' }}
    </div>
    <div v-else-if="data.status === 'error'" class="text-sm text-red-400 py-3">
      {{ data.msg || '生成失败' }}
    </div>

    <!-- commentary text -->
    <div v-else class="text-sm text-text-2 whitespace-pre-line leading-relaxed">{{ data.text }}</div>

    <!-- footer: meta + stale hint -->
    <div v-if="data.status === 'ok'" class="mt-3 flex items-center gap-3 text-xs text-text-3">
      <span>{{ data.data_as_of ? '基于 ' + data.data_as_of + ' 数据' : '' }}</span>
      <span v-if="data.model">· {{ data.model }}</span>
      <span v-if="data.stale" class="text-amber-400">· 数据已更新，评论可能过时</span>
    </div>
  </div>
</template>
