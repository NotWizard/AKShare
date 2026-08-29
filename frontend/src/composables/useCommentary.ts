// 一次 GET /commentary，多卡共享同一响应（M4c 呈现层）。
// 模块级共享态，不进 pinia：单一消费者族、无跨组件写入（YAGNI 同 AISettings 注释先例）。
// 单飞 Promise 去重并发、refresh tick 去重跨页导航、generating 2s 轮询（订阅计数启停）。
import { ref } from 'vue'
import { useRefreshStore } from '@/stores/refresh'
import { api } from '@/api/client'
import type { Commentary } from '@/api/types'

const EMPTY: Commentary = { status: 'empty', msg: null, hint: null, stale: false, regenerating: false, overall: '', sections: {}, provenance: null }

const data = ref<Commentary>(EMPTY)   // 模块级：任意细分页共享同一响应
let inflight: Promise<void> | null = null
let loadedTick = -1                   // 绑定 refresh.lastRefreshedAt；只挡同 tick 且非 generating 的重取
let subs = 0                          // 挂载中的消费者数 → 轮询启停
let pollTimer: ReturnType<typeof setInterval> | null = null

export function useCommentary() {
  const refresh = useRefreshStore()

  async function load() {
    if (inflight) return inflight                       // 并发去重：共享同一请求
    const tick = refresh.lastRefreshedAt
    if (loadedTick === tick && data.value.status !== 'generating') return  // 跨页复用
    inflight = (async () => {
      try { data.value = await api.getCommentary() }
      catch (e) {
        // error last-good：有文本 → 保留内容只记 msg；无文本 → 转 error 态
        const hasText = !!data.value.overall || Object.keys(data.value.sections).length > 0
        data.value = hasText
          ? { ...data.value, msg: (e as Error).message }
          : { ...data.value, status: 'error', msg: (e as Error).message }
      }
      loadedTick = tick
      inflight = null
      armPoll()
    })()
    return inflight
  }

  function armPoll() {                                  // generating → 2s 轮询（同 CommentaryCard 节奏）
    if (data.value.status === 'generating' && subs > 0 && !pollTimer) {
      pollTimer = setInterval(() => void load(), 2000)
    }
    if ((data.value.status !== 'generating' || subs <= 0) && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function enter() { subs++; void load() }              // onMounted
  function leave() { subs--; if (subs <= 0) armPoll() } // onUnmounted：订阅归零停轮询

  // 外部成功重取/重生成后同步模块态（Overview 的 CommentaryCard 有独立 fetch，
  // 不同步会让细分页切片在 loadedTick 去重下一直显示旧批次）。
  function adopt(c: Commentary) {
    data.value = c
    loadedTick = refresh.lastRefreshedAt
  }

  return { data, enter, leave, adopt }
}
