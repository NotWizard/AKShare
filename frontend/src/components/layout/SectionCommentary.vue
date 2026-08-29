<script setup lang="ts">
// 细分页板块切片（M4c 呈现层）— 经 useCommentary 共享一次 GET /commentary 响应。
// 四态对齐 CommentaryCard：empty 无 hint 不渲染 / 有 hint 极小 CTA、generating 脉冲、
// stale「数据已更新」徽章、fetch 失败保 last-good 文本 + msg 附注。
import { computed, onMounted, onUnmounted } from 'vue'
import { useCommentary } from '@/composables/useCommentary'

const props = defineProps<{ section: string }>()

const LABELS: Record<string, string> = {
  merrill: '美林时钟', credit: '信用周期', inventory: '库存周期',
  debt: '债务周期', real_estate: '房地产', fiscal_external: '财政与外需',
}

const { data, enter, leave } = useCommentary()
onMounted(enter)
onUnmounted(leave)

const text = computed(() => data.value.sections[props.section] ?? '')
// empty 无 hint / ok 但该板块无文本（legacy 批次 sections={}）→ 整体不渲染，页面零占位
const visible = computed(() => {
  const s = data.value.status
  if (s === 'generating' || s === 'error') return true
  if (s === 'empty') return !!data.value.hint
  return !!text.value
})
</script>

<template>
  <section
    v-if="visible"
    role="region"
    :aria-label="'AI 评论 — ' + LABELS[section]"
    class="bg-card border border-border rounded-xl p-4 transition-colors hover:border-border-hi"
  >
    <div class="flex items-center gap-2 mb-2">
      <div class="text-xs text-text-3 uppercase tracking-wide">AI 评论 · {{ LABELS[section] }}</div>
      <span v-if="data.status === 'ok' && data.stale" class="text-xs px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400">数据已更新</span>
    </div>

    <!-- 状态容器：role=status 向屏幕阅读器通告 generating→ok/error 等状态切换（同 CommentaryCard） -->
    <div role="status" aria-live="polite">
      <div v-if="data.status === 'generating'" class="text-sm text-text-2 py-3 animate-pulse">
        {{ data.msg || '评论生成中…' }}
      </div>
      <div v-else-if="data.status === 'empty'" class="text-xs text-text-3 py-2">
        {{ data.msg || '暂无评论' }}
        <RouterLink
          v-if="data.hint"
          :to="data.hint"
          class="ml-2 inline-block text-xs px-2.5 py-1 rounded-lg border border-border hover:border-border-hi text-text-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >前往 AI 设置</RouterLink>
      </div>
      <div v-else-if="data.status === 'error'" class="text-sm text-red-400 py-3">
        {{ data.msg || '评论加载失败' }}
      </div>
      <template v-else>
        <!-- ok：板块文本；fetch 失败有 last-good 时保留文本，msg 作附注 -->
        <div class="text-sm text-text-2 whitespace-pre-line leading-relaxed">{{ text }}</div>
        <div v-if="data.msg" class="text-xs text-red-400 mt-2">{{ data.msg }}</div>
      </template>
    </div>

    <!-- provenance 简行：model · 生成于 · tpl hash 前 8 位 -->
    <div v-if="data.status === 'ok' && data.provenance" class="mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-text-3">
      <span v-if="data.provenance.model">{{ data.provenance.model }}</span>
      <span v-if="data.provenance.generated_at">· 生成于 {{ data.provenance.generated_at }}</span>
      <span v-if="data.provenance.template_hash">· tpl {{ data.provenance.template_hash.slice(0, 8) }}</span>
    </div>
  </section>
</template>
