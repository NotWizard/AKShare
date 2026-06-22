// Refresh store — drives the SSE progress bar + manifest result.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export const useRefreshStore = defineStore('refresh', () => {
  const running = ref(false)
  const progress = ref(0)          // 0..1
  const lastResult = ref<{ msg: string; ts: string | null } | null>(null)
  let abortController: AbortController | null = null

  async function loadStatus() {
    try {
      const r = await api.getRefreshStatus()
      lastResult.value = { msg: r.msg, ts: r.ts }
      running.value = !!r.busy
    } catch {
      // offline / backend down — don't crash onMounted
      lastResult.value = { msg: '后端未连接', ts: null }
    }
  }

  // SSE-driven refresh: open /api/v1/refresh/stream, parse progress + done.
  async function stream() {
    if (running.value) return
    abortController = new AbortController()
    running.value = true
    progress.value = 0
    try {
      const resp = await fetch('/api/v1/refresh/stream', {
        signal: abortController.signal,
      })
      if (!resp.ok || !resp.body) {
        lastResult.value = { msg: `刷新失败: HTTP ${resp.status}`, ts: null }
        return
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
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
              lastResult.value = {
                msg: payload.result?.msg ?? '刷新完成',
                ts: payload.result?.ts ?? null,
              }
            }
          } catch { /* skip unparseable SSE event */ }
        }
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

  return { running, progress, lastResult, loadStatus, stream, cancel }
})
