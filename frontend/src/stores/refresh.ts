// Refresh store — drives the SSE progress bar + manifest result (P3 wires UI).
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export const useRefreshStore = defineStore('refresh', () => {
  const running = ref(false)
  const progress = ref(0)          // 0..1
  const lastResult = ref<{ msg: string; ts: string | null } | null>(null)

  async function loadStatus() {
    const r = await api.getRefreshStatus()
    lastResult.value = { msg: r.msg, ts: r.ts }
    running.value = !!r.busy
  }

  // SSE-driven refresh: open /api/v1/refresh/stream, parse progress + done.
  async function stream() {
    if (running.value) return
    running.value = true
    progress.value = 0
    try {
      const resp = await fetch('/api/v1/refresh/stream')
      const reader = resp.body?.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (reader) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop() ?? ''
        for (const ev of events) {
          const line = ev.split('\n').find((l) => l.startsWith('data: '))
          if (!line) continue
          const payload = JSON.parse(line.slice(6))
          if (payload.progress !== undefined) progress.value = payload.progress
          if (payload.done) lastResult.value = { msg: payload.result?.msg ?? '', ts: payload.result?.ts ?? null }
        }
      }
    } finally {
      running.value = false
      progress.value = 1
    }
  }

  return { running, progress, lastResult, loadStatus, stream }
})
