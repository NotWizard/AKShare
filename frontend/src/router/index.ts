import { createRouter, createWebHistory } from 'vue-router'

// P1 ships CreditCycle (flagship); the other five are P2 placeholders that
// render a "待迁移" panel so the app is fully navigable from day one.
const CreditCycle = () => import('../pages/CreditCycle.vue')
const Placeholder = () => import('../pages/Placeholder.vue')

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/credit-cycle' },
    { path: '/overview', component: Placeholder, props: { pageTitle: '综合概览' }, meta: { title: '综合概览', icon: '◉' } },
    { path: '/merrill-clock', component: Placeholder, props: { pageTitle: '美林时钟' }, meta: { title: '美林时钟', icon: '◐' } },
    { path: '/credit-cycle', component: CreditCycle, meta: { title: '信用周期', icon: '◈' } },
    { path: '/inventory-cycle', component: Placeholder, props: { pageTitle: '库存周期' }, meta: { title: '库存周期', icon: '▣' } },
    { path: '/debt-cycle', component: Placeholder, props: { pageTitle: '债务周期' }, meta: { title: '债务周期', icon: '◆' } },
    { path: '/real-estate', component: Placeholder, props: { pageTitle: '房地产市场' }, meta: { title: '房地产市场', icon: '▧' } },
  ],
})
