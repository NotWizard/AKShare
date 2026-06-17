import { createRouter, createWebHistory } from 'vue-router'

const lazy = (p: string) => () => import(`../pages/${p}.vue`)

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', component: lazy('Overview'), meta: { title: '综合概览', icon: '◉' } },
    { path: '/merrill-clock', component: lazy('MerrillClock'), meta: { title: '美林时钟', icon: '◐' } },
    { path: '/credit-cycle', component: lazy('CreditCycle'), meta: { title: '信用周期', icon: '◈' } },
    { path: '/inventory-cycle', component: lazy('InventoryCycle'), meta: { title: '库存周期', icon: '▣' } },
    { path: '/debt-cycle', component: lazy('DebtCycle'), meta: { title: '债务周期', icon: '◆' } },
    { path: '/real-estate', component: lazy('RealEstate'), meta: { title: '房地产市场', icon: '▧' } },
  ],
})
