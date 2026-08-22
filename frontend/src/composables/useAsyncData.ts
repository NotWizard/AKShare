// useAsyncData — the ONE way a page loads data (see docs/AUDIT_FIXES.md FE-H2).
//
// Why it exists: pages used to hand-roll `loading` / `error` / `reqId`, and
// Overview.vue assigned `error` but never rendered it — with the backend down the
// first screen showed a fully-populated skeleton of `—` KPIs. Here the error is
// part of a 4-state machine that <PageState> consumes, so the failure branch
// can't be silently dropped.
//
// Guarantees:
//   · state is exactly one of idle | loading | ok | error;
//   · `data` lives in a shallowRef (chart payloads stay non-reactive / markRaw);
//   · every run gets a fresh AbortController — a superseded or unmounted request
//     is aborted, so a fast route change frees the connection instead of letting
//     ~25 responses drain into the 6-socket budget;
//   · a self-inflicted abort NEVER becomes a user-visible error.
import { computed, ref, shallowRef, watch, onScopeDispose, type ComputedRef, type Ref, type ShallowRef, type WatchSource } from 'vue'
import { ApiError } from '@/api/client'

export type AsyncState = 'idle' | 'loading' | 'ok' | 'error'

export interface UseAsyncDataOptions {
  /** Reactive sources that trigger a reload (filters, refresh stamps …). */
  watch?: WatchSource[]
  /** Fetch immediately (default true). */
  immediate?: boolean
}

export interface UseAsyncDataReturn<T> {
  state: Ref<AsyncState>
  data: ShallowRef<T | null>
  error: ShallowRef<ApiError | null>
  /** One-line, category-aware message for compact slots (GraphCard overlay). */
  errorText: ComputedRef<string | null>
  loading: ComputedRef<boolean>
  /** Re-run the fetcher (also used as the retry handler). */
  retry: () => Promise<void>
}

export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: UseAsyncDataOptions = {},
): UseAsyncDataReturn<T> {
  const state = ref<AsyncState>('idle')
  const data = shallowRef<T | null>(null)
  const error = shallowRef<ApiError | null>(null)

  let controller: AbortController | null = null
  let seq = 0
  let disposed = false

  async function run(): Promise<void> {
    if (disposed) return
    const mine = ++seq
    controller?.abort()          // supersede the in-flight request, free its socket
    const own = new AbortController()
    controller = own
    state.value = 'loading'
    error.value = null
    try {
      const result = await fetcher(own.signal)
      if (disposed || mine !== seq) return
      data.value = result
      state.value = 'ok'
    } catch (e) {
      if (disposed || mine !== seq) return   // superseded: its abort isn't a failure
      const err = e instanceof ApiError
        ? e
        : new ApiError('server', (e as Error)?.message || '未知错误')
      if (err.kind === 'aborted') return     // our own abort — keep the current state
      error.value = err
      state.value = 'error'
    } finally {
      if (controller === own) controller = null
    }
  }

  const sources = options.watch
  if (sources?.length) {
    watch(sources, () => { void run() }, { immediate: options.immediate !== false })
  } else if (options.immediate !== false) {
    void run()
  }

  onScopeDispose(() => {
    disposed = true
    controller?.abort()
  })

  return {
    state,
    data,
    error,
    errorText: computed(() => error.value?.message ?? null),
    loading: computed(() => state.value === 'loading'),
    retry: run,
  }
}
