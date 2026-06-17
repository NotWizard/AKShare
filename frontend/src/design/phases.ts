// Phase colors + labels — mirror dashboard/config.py PHASE_COLORS / PHASE_LABELS.
// Single source for badges, phase-background segments, timelines.

export const PHASE_COLORS: Record<string, string> = {
  // Merrill clock
  recovery: '#10b981',
  overheating: '#f59e0b',
  stagflation: '#ef4444',
  recession: '#3b82f6',
  // Credit cycle
  easing: '#10b981',
  tightening: '#ef4444',
  neutral: '#64748b',
  // Inventory cycle
  active_restocking: '#10b981',
  passive_restocking: '#f59e0b',
  active_destocking: '#ef4444',
  passive_destocking: '#3b82f6',
  // Debt cycle
  leveraging: '#10b981',
  deleveraging: '#ef4444',
  stable: '#f59e0b',
  beautiful_deleveraging: '#10b981',
  ugly_deleveraging: '#ef4444',
}

export const PHASE_LABELS: Record<string, string> = {
  recovery: '复苏', overheating: '过热', stagflation: '滞胀', recession: '衰退',
  easing: '宽松', tightening: '紧缩', neutral: '中性',
  active_restocking: '主动补库', passive_restocking: '被动补库',
  active_destocking: '主动去库', passive_destocking: '被动去库',
  leveraging: '加杠杆', deleveraging: '去杠杆', stable: '稳定',
  beautiful_deleveraging: '美丽去杠杆', ugly_deleveraging: '丑陋去杠杆',
}

export const phaseColor = (p: string | null | undefined): string =>
  PHASE_COLORS[p ?? ''] ?? '#64748b'
export const phaseLabel = (p: string | null | undefined): string =>
  PHASE_LABELS[p ?? ''] ?? (p ?? '')
