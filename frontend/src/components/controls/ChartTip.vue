<script setup lang="ts">
import { ref, nextTick, onScopeDispose, useId } from 'vue'

defineProps<{ text: string }>()

const visible = ref(false)
const pop = ref<HTMLElement | null>(null)
const style = ref<Record<string, string>>({})
// Stable id so the trigger can point at the Teleported popup via
// aria-describedby — without it the whole data-lineage text (the only place the
// derivation is documented) is unreachable for screen readers.
const popId = `chart-tip-${useId()}`

// Teleport to <body> so NO ancestor's overflow can ever clip the popup, and
// position via the icon's viewport rect with flip/clamp — always visible.
async function show(e: MouseEvent | FocusEvent) {
  const target = e.currentTarget as HTMLElement
  const r = target.getBoundingClientRect()
  clearHide()
  visible.value = true
  await nextTick()
  const ph = pop.value?.offsetHeight ?? 100
  const pw = Math.min(340, window.innerWidth - 24)

  // prefer below the icon; flip above if it would overflow the bottom
  let top = r.bottom + 8
  if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 8)
  // left-align with the icon, clamp into the viewport
  let left = r.left
  if (left + pw > window.innerWidth - 12) left = window.innerWidth - pw - 12
  if (left < 12) left = 12

  style.value = { top: `${top}px`, left: `${left}px`, width: `${pw}px` }
}

// The popup is pointer-interactive (text must be selectable), but it lives in
// <body> — so leaving the icon starts a short grace period that entering the
// popup cancels. blur / Escape close immediately.
let hideTimer: ReturnType<typeof setTimeout> | null = null
function clearHide() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
}
function scheduleHide() {
  clearHide()
  hideTimer = setTimeout(() => { visible.value = false; hideTimer = null }, 150)
}
function hide() {
  clearHide()
  visible.value = false
}
onScopeDispose(clearHide)
</script>

<template>
  <span
    class="inline-flex items-center align-middle ml-1 text-text-3 text-xs cursor-help select-none rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
    tabindex="0"
    role="button"
    aria-label="查看图表说明"
    :aria-expanded="visible"
    :aria-describedby="visible ? popId : undefined"
    @mouseenter="show"
    @mouseleave="scheduleHide"
    @focus="show"
    @blur="hide"
    @keydown.escape.stop="hide"
  >ⓘ
    <Teleport to="body">
      <div v-if="visible && text" :id="popId" ref="pop" role="tooltip" class="chart-tip-pop" :style="style"
           @mouseenter="clearHide" @mouseleave="hide">{{ text }}</div>
    </Teleport>
  </span>
</template>

<style scoped>
.chart-tip-pop {
  position: fixed;
  z-index: 9000;
  background: #1e293b;
  color: #f1f5f9;
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.5;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  white-space: pre-line;
  word-break: break-word;
  /* selectable: the tooltip documents 取数 lineage users need to read/copy */
  pointer-events: auto;
  user-select: text;
}
</style>
