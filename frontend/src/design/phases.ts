// Phase colors + labels — 双主题（暗亮同 hue、异明度；语义：绿=扩张/红=收缩/琥珀=中性·过热/蓝=衰退）。
// 读当前主题（stores/theme.ts）——图表重建时随 chartTheme() 一并换肤。

import { isLight } from '@/stores/theme'

const DARK: Record<string, string> = {
  // Merrill clock
  recovery: '#34d399',
  overheating: '#fbbf24',
  stagflation: '#f87171',
  recession: '#60a5fa',
  // Credit cycle
  easing: '#34d399',
  tightening: '#f87171',
  neutral: '#7c8da5',
  // Inventory cycle
  active_restocking: '#34d399',
  passive_restocking: '#fbbf24',
  active_destocking: '#f87171',
  passive_destocking: '#60a5fa',
  // Debt cycle
  leveraging: '#34d399',
  deleveraging: '#f87171',
  stable: '#fbbf24',
  beautiful_deleveraging: '#34d399',
  ugly_deleveraging: '#f87171',
  leveraging_boom: '#34d399',
  leveraging_bust: '#f87171',
  stable_growth: '#fbbf24',
  stable_contraction: '#60a5fa',
}

const LIGHT: Record<string, string> = {
  recovery: '#059669',
  overheating: '#b45309',
  stagflation: '#dc2626',
  recession: '#2563eb',
  easing: '#059669',
  tightening: '#dc2626',
  neutral: '#64748b',
  active_restocking: '#059669',
  passive_restocking: '#b45309',
  active_destocking: '#dc2626',
  passive_destocking: '#2563eb',
  leveraging: '#059669',
  deleveraging: '#dc2626',
  stable: '#b45309',
  beautiful_deleveraging: '#059669',
  ugly_deleveraging: '#dc2626',
  leveraging_boom: '#059669',
  leveraging_bust: '#dc2626',
  stable_growth: '#b45309',
  stable_contraction: '#2563eb',
}

export const PHASE_LABELS: Record<string, string> = {
  recovery: '复苏', overheating: '过热', stagflation: '滞胀', recession: '衰退',
  easing: '宽松', tightening: '紧缩', neutral: '中性',
  active_restocking: '主动补库', passive_restocking: '被动补库',
  active_destocking: '主动去库', passive_destocking: '被动去库',
  leveraging: '加杠杆', deleveraging: '去杠杆', stable: '稳定',
  beautiful_deleveraging: '美丽去杠杆', ugly_deleveraging: '丑陋去杠杆',
  leveraging_boom: '加杠杆繁荣', stable_growth: '稳定增长',
  leveraging_bust: '加杠杆衰退', stable_contraction: '稳定收缩',
}

export const phaseColor = (p: string | null | undefined): string =>
  (isLight() ? LIGHT : DARK)[p ?? ''] ?? (isLight() ? '#64748b' : '#7c8da5')
export const phaseLabel = (p: string | null | undefined): string =>
  PHASE_LABELS[p ?? ''] ?? (p ?? '')
