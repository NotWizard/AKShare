// Refresh store — drives the SSE progress bar + manifest result + sources health.
// Two independent datasets share one store so a page can never own refresh state
// privately (FE-H4: CrclMonitor did, so the global bar's buttons were dead and a
// second concurrent collection could be started by navigating away and back):
//   · macro  → POST /refresh      + /refresh/stream?job_id=…      → lastRefreshedAt
//   · crcl   → POST /crcl/refresh + /crcl/refresh/stream?job_id=… → crclRefreshedAt
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, BASE, invalidateCache } from '../api/client'
import type { SourcesHealth } from '../api/types'

export type RefreshKind = 'macro' | 'crcl'

export const useRefreshStore = defineStore('refresh', () => {
  const running = ref(false)
  const progress = ref(0)          // 0..1
  const kind = ref<RefreshKind>('macro')   // which dataset the current run touches
  const lastResult = ref<{ msg: string; ts: string | null } | null>(null)
  const lastRefreshedAt = ref(0)   // macro: bumped on SSE done; pages refetch by depending on it
  const crclRefreshedAt = ref(0)   // crcl: same contract, separate dataset
  const health = ref<SourcesHealth | null>(null)
  let abortController: AbortController | null = null

  async function loadStatus() {
    try {
      const r = await api.getRefreshStatus()
      lastResult.value = { msg: r.msg, ts: r.ts }
      running.value = !!r.busy
      if (r.busy) kind.value = 'macro'
    } catch {
      // offline / backend down — don't crash onMounted
      lastResult.value = { msg: '后端未连接', ts: null }
    }
    loadHealth()
  }

  async function loadHealth() {
    try {
      health.value = await api.getSourcesHealth()
    } catch {
      health.value = null  // 后端不可达 → 灰点
    }
  }

  // The dataset changed → every cached response is now potentially stale.
  function markRefreshed(k: RefreshKind) {
    invalidateCache()
    if (k === 'crcl') crclRefreshedAt.value = Date.now()
    else lastRefreshedAt.value = Date.now()
  }

  // SSE-driven refresh, two steps since F4:
  //   1. POST /refresh (or /crcl/refresh) — the ONLY thing that starts work; it
  //      carries the local capability token and returns a job_id;
  //   2. GET …/refresh/stream?job_id=… — a pure subscription.
  // That split is what makes an <img src=".../refresh/stream"> or a browser
  // prefetch harmless: a GET without a minted job_id can no longer collect.
  // macro full=true 追加 ?full=1 绕过发布日历（全量抓取）。
  async function stream(full = false, k: RefreshKind = 'macro') {
    if (running.value) return
    abortController = new AbortController()
    running.value = true
    kind.value = k
    progress.value = 0
    try {
      const started = k === 'crcl' ? await api.triggerCrclRefresh() : await api.triggerRefresh(full)
      if (!started.job_id) {
        // busy / pool saturated — the backend already said why in msg
        lastResult.value = { msg: started.msg ?? '刷新未启动', ts: started.ts ?? null }
        return
      }
      const base = k === 'crcl' ? '/crcl/refresh/stream' : '/refresh/stream'
      const path = `${base}?job_id=${encodeURIComponent(started.job_id)}`
      const resp = await fetch(`${BASE}${path}`, {
        signal: abortController.signal,
      })
      if (!resp.ok || !resp.body) {
        lastResult.value = { msg: `刷新失败: HTTP ${resp.status}`, ts: null }
        return
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      let sawDone = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop() ?? ''
        for (const ev of events) {
          const line = ev.split('\n').find((l) => l.startsWith('data: '))
          if (!line) continue
          // a single malformed event must not kill the whole stream
          try {
            const payload = JSON.parse(line.slice(6))
            if (payload.progress !== undefined) progress.value = payload.progress
            if (payload.done) {
              sawDone = true
              lastResult.value = {
                msg: payload.result?.msg ?? (k === 'crcl' ? 'CRCL 采集完成' : '刷新完成'),
                ts: payload.result?.ts ?? null,
              }
              markRefreshed(k)
              loadHealth()  // manifest 已变，健康灯同步
            }
          } catch { /* skip unparseable SSE event */ }
        }
      }
      // 流被对端提前关闭（未收到 done）——不谎报成功，但仍让页面重取已落库的部分
      if (!sawDone) {
        lastResult.value = { msg: '采集流意外结束，结果可能不完整', ts: null }
        markRefreshed(k)
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        lastResult.value = { msg: '刷新已取消', ts: null }
      } else {
        lastResult.value = { msg: `刷新异常: ${(e as Error).message}`, ts: null }
      }
    } finally {
      running.value = false
      abortController = null
    }
  }

  function cancel() {
    abortController?.abort()
  }

  return {
    running, progress, kind, lastResult, lastRefreshedAt, crclRefreshedAt, health,
    loadStatus, loadHealth, stream, cancel,
  }
})
