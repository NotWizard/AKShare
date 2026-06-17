// Chart helpers — color alpha + consecutive-phase segmentation.

export function hexA(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

export interface PhaseSeg { x0: string; x1: string; phase: string }

// Merge consecutive equal-phase rows into [x0,x1] segments (mirror
// add_phase_background's segment-merging that kept shape count low).
export function mergePhaseSegments(
  rows: Array<Record<string, string | number | null>>,
  phaseKey = 'phase',
  dateKey = 'date',
): PhaseSeg[] {
  const segs: PhaseSeg[] = []
  let cur = ''
  let start: string | null = null
  let prev: string | null = null
  for (const r of rows) {
    const d = r[dateKey] as string | null
    const p = (r[phaseKey] as string) ?? ''
    if (!d || !p) continue          // skip null dates and empty/unknown phases
    if (p !== cur) {
      if (cur && start && prev) segs.push({ x0: start, x1: prev, phase: cur })
      cur = p
      start = d
    }
    prev = d
  }
  if (cur && start && prev) segs.push({ x0: start, x1: prev, phase: cur })
  return segs
}
