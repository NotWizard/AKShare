import { createRouter, createWebHistory } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    icon?: string
    /** Does the global 5Y/10Y/20Y/ALL date filter affect this page? */
    dateFilter?: boolean
    /** Which dataset the global 🔄 button refreshes here (null = none). */
    refreshKind?: 'macro' | 'crcl' | null
  }
}

// Static literal `import('../pages/X.vue')` per route: Rollup can only
// pre-analyse literals, so the previous template-string form (`../pages/${p}.vue`)
// emitted a wildcard chunk map that pulled every page into the graph.
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', component: () => import('../pages/Overview.vue'), meta: { title: '综合概览', icon: '◉', dateFilter: true, refreshKind: 'macro' } },
    { path: '/merrill-clock', component: () => import('../pages/MerrillClock.vue'), meta: { title: '美林时钟', icon: '◐', dateFilter: true, refreshKind: 'macro' } },
    { path: '/credit-cycle', component: () => import('../pages/CreditCycle.vue'), meta: { title: '信用周期', icon: '◈', dateFilter: true, refreshKind: 'macro' } },
    { path: '/inventory-cycle', component: () => import('../pages/InventoryCycle.vue'), meta: { title: '库存周期', icon: '▣', dateFilter: true, refreshKind: 'macro' } },
    { path: '/debt-cycle', component: () => import('../pages/DebtCycle.vue'), meta: { title: '债务周期', icon: '◆', dateFilter: true, refreshKind: 'macro' } },
    { path: '/real-estate', component: () => import('../pages/RealEstate.vue'), meta: { title: '房地产市场', icon: '▧', dateFilter: true, refreshKind: 'macro' } },
    { path: '/demographics', component: () => import('../pages/Demographics.vue'), meta: { title: '人口与城镇化', icon: '◎', dateFilter: true, refreshKind: 'macro' } },
    { path: '/fiscal-external', component: () => import('../pages/FiscalExternal.vue'), meta: { title: '财政与外需', icon: '◫', dateFilter: true, refreshKind: 'macro' } },
    // CRCL reads its own DB and ignores the macro date filter → the global bar
    // hides those controls instead of showing dead ones (FE-H4).
    { path: '/crcl-monitor', component: () => import('../pages/CrclMonitor.vue'), meta: { title: 'CRCL 监控', icon: '◒', dateFilter: false, refreshKind: 'crcl' } },
    { path: '/ai-settings', component: () => import('../pages/AISettings.vue'), meta: { title: 'AI 设置', icon: '⚙', dateFilter: false, refreshKind: null } },
    { path: '/:pathMatch(.*)*', redirect: '/overview' },
  ],
})

router.afterEach((to) => {
  if (to.meta?.title) document.title = `${to.meta.title} · 宏观经济分析平台`
})

// A deploy replaces the hashed chunk files, so an old tab's lazy import 404s and
// the sidebar link silently does nothing. Reload once to pick up the new
// index.html; the sessionStorage stamp keeps a genuinely broken chunk from
// looping (and expires so a later deploy can still self-heal).
const RELOAD_STAMP = 'chunk-reload-at'
const RELOAD_COOLDOWN_MS = 30_000
router.onError((err, to) => {
  const msg = String((err as Error)?.message ?? err)
  if (!/dynamically imported module|Importing a module script failed/i.test(msg)) return
  const last = Number(sessionStorage.getItem(RELOAD_STAMP) ?? 0)
  if (Date.now() - last < RELOAD_COOLDOWN_MS) {
    console.error('[router] 页面资源加载失败（重载后仍失败）', err)
    return
  }
  sessionStorage.setItem(RELOAD_STAMP, String(Date.now()))
  window.location.assign(to.fullPath)
})
