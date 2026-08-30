<script setup lang="ts">
// AI 评论卡片（M4 批次形状：overall + provenance；细分页板块切片见 SectionCommentary）。
// 轮询设计（FE-H3）：
//   · setTimeout 链 → 天然串行，请求不会重叠或乱序到达；
//   · 总体 deadline（2 分钟）→ LLM 任务死掉也不会永远轮询；
//   · 取数瞬时失败不覆盖 status（后端几秒后成功仍能收敛），只有 deadline
//     或后端明确 error 才终止；
//   · 卸载时清理 timer 并 abort 在途请求。
// 每次成功取数都 adopt() 进 useCommentary 模块态——细分页切片才不会吃到旧批次。
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRefreshStore } from '@/stores/refresh'
import { useCommentary } from '@/composables/useCommentary'
import { api, ApiError } from '@/api/client'
import type { Commentary } from '@/api/types'

const EMPTY: Commentary = { status: 'empty', msg: null, hint: null, stale: false, regenerating: false, overall: '', sections: {}, provenance: null }
const POLL_INTERVAL_MS = 2000
const POLL_DEADLINE_MS = 300_000   // 推理模型（kimi-k3）一次生成可达 3-4 分钟

const data = ref<Commentary>({ ...EMPTY })
const loading = ref(false)
const pollNote = ref<string | null>(null)   // 轮询期间的软提示（不覆盖 status）
const refresh = useRefreshStore()
const { adopt } = useCommentary()

let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollUntil = 0
let controller: AbortController | null = null
let reqId = 0

/** 后端在重新生成时会带回上一版 → 展示旧评论 + 「重新生成中」标记。 */
const regenerating = computed(() => data.value.status === 'generating' && data.value.regenerating && !!data.value.overall)

function stopPolling() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
}

/** 取一次评论。返回 false 表示这次是瞬时网络失败（状态保持不变）。 */
async function pullOnce(): Promise<boolean> {
  const mine = ++reqId
  controller?.abort()
  controller = new AbortController()
  try {
    const r = await api.getCommentary({ signal: controller.signal })
    if (mine !== reqId) return true
    data.value = r
    adopt(r)                       // 同步模块态：细分页切片共享同一批次
    pollNote.value = null
    return true
  } catch (e) {
    if (mine !== reqId) return true
    const err = e as ApiError
    if (err?.kind === 'aborted') return true
    // 瞬时失败绝不写 status='error'：旧实现里一次网络抖动就把卡片永久钉死在
    // 「生成失败」，即使后端几秒后已经成功。
    pollNote.value = `暂时取不到评论（${err?.message ?? '未知错误'}），继续重试…`
    return false
  }
}

function schedulePoll() {
  stopPolling()
  pollTimer = setTimeout(async () => {
    pollTimer = null
    await pullOnce()
    if (data.value.status !== 'generating') { pollNote.value = null; return }
    if (Date.now() >= pollUntil) {
      // 生成任务超出 deadline（LLM 进程可能已死）→ 报超时，停止轮询
      data.value = { ...data.value, status: 'error', msg: '生成超时（2 分钟未完成），请重试' }
      pollNote.value = null
      return
    }
    schedulePoll()
  }, POLL_INTERVAL_MS)
}

function startPolling() {
  pollUntil = Date.now() + POLL_DEADLINE_MS
  schedulePoll()
}

async function pull() {
  await pullOnce()
  if (data.value.status === 'generating') startPolling()
  else stopPolling()
}

async function regenerate() {
  loading.value = true
  pollNote.value = null
  try {
    const r = await api.regenerateCommentary()
    data.value = r
    if (r.status === 'ok') adopt(r)
    // If backend kicked off async generation, poll until done.
    if (r.status === 'generating') startPolling()
  } catch (e) {
    // 前端 30s abort 但后端仍在生成 → 转轮询等结果，不误报失败
    const err = e as ApiError
    if (err?.kind === 'timeout') { startPolling(); return }
    // 用户主动触发的 POST 失败是确定性的失败 → 可以写 error
    data.value = { ...data.value, status: 'error', msg: (e as Error).message }
  } finally {
    loading.value = false
  }
}

onMounted(pull)
onUnmounted(() => { stopPolling(); controller?.abort() })
// 数据刷新后 backend 已重生成评论；重取（若仍 generating 则继续轮询）
watch(() => refresh.lastRefreshedAt, pull)
</script>

<template>
  <div class="bg-card border border-border rounded-xl p-4 transition-colors hover:border-border-hi">
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-2">
        <div class="text-xs text-text-3 uppercase tracking-wide">AI 宏观分析评论</div>
        <span v-if="data.status === 'ok' && data.stale" class="text-xs px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400">数据已更新</span>
      </div>
      <button
        class="text-xs px-2.5 py-1 rounded-lg border border-border hover:border-border-hi text-text-2 transition-colors disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        :disabled="loading || data.status === 'generating'"
        @click="regenerate"
      >
        {{ data.status === 'generating' ? '生成中…' : '重新分析' }}
      </button>
    </div>

    <!-- 状态容器：role=status 向屏幕阅读器通告 generating→ok/error 等状态切换 -->
    <div role="status" aria-live="polite">
      <!-- generating: 若后端带回了上一版，先展示旧评论而不是空白 -->
      <div v-if="data.status === 'generating' && !regenerating" class="text-sm text-text-2 py-3 animate-pulse">
        {{ data.msg || '评论生成中…' }}
      </div>
      <div v-else-if="data.status === 'empty'" class="text-sm text-text-3 py-3">
        {{ data.msg || '暂无评论 — 点击「重新分析」生成（需配置模型）' }}
        <RouterLink
          v-if="data.hint"
          :to="data.hint"
          class="ml-2 inline-block text-xs px-2.5 py-1 rounded-lg border border-border hover:border-border-hi text-text-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >前往 AI 设置</RouterLink>
      </div>
      <div v-else-if="data.status === 'error'" class="text-sm text-red-400 py-3">
        {{ data.msg || '生成失败' }}
      </div>

      <!-- overall commentary (ok，或 generating 时的上一版) -->
      <div v-else class="text-sm text-text-2 whitespace-pre-line leading-relaxed">{{ data.overall }}</div>
    </div>

    <!-- footer: provenance + regenerating/poll hints -->
    <div v-if="(data.status === 'ok' || regenerating) && data.provenance" class="mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-text-3">
      <span v-if="data.provenance.model">{{ data.provenance.model }}</span>
      <span v-if="data.provenance.generated_at">· 生成于 {{ data.provenance.generated_at }}</span>
      <span v-if="data.provenance.data_as_of?.derived_monthly">· 数据截至 {{ data.provenance.data_as_of.derived_monthly }}</span>
      <span v-if="data.provenance.template_hash">· tpl {{ data.provenance.template_hash.slice(0, 8) }}</span>
      <span v-if="data.provenance.profile">· {{ data.provenance.profile }}</span>
      <span v-if="regenerating" class="text-accent animate-pulse">· 正在重新生成，以上为上一版</span>
    </div>
    <div v-if="pollNote" role="status" aria-live="polite" class="mt-2 text-[11px] text-text-4">{{ pollNote }}</div>
  </div>
</template>
