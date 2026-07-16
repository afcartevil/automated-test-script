import { ref } from 'vue'

export type PatchBrief = {
  sha?: string
  full_sha?: string
  title?: string
  score?: number
  key_risk?: string
  crash_risk?: string
  llm_analyzed?: boolean
  summary?: string
  insertions?: number
  deletions?: number
}

const visible = ref(false)
const patches = ref<PatchBrief[]>([])
const position = ref({ x: 0, y: 0 })

let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function clearShowTimer() {
  if (showTimer) {
    clearTimeout(showTimer)
    showTimer = null
  }
}

function clearHideTimer() {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

function positionAt(el: HTMLElement, x: number, y: number) {
  const pad = 12
  const vw = window.innerWidth
  const vh = window.innerHeight
  let left = x + pad
  let top = y + pad
  el.style.left = `${left}px`
  el.style.top = `${top}px`
  const rect = el.getBoundingClientRect()
  if (rect.right > vw - pad) {
    left = Math.max(pad, x - rect.width - pad)
  }
  if (rect.bottom > vh - pad) {
    top = Math.max(pad, y - rect.height - pad)
  }
  if (left < pad) left = pad
  if (top < pad) top = pad
  position.value = { x: left, y: top }
}

export function usePatchPopover() {
  function showPatches(patchesList: PatchBrief[], x: number, y: number, delayMs = 1000) {
    clearHideTimer()
    clearShowTimer()
    if (!patchesList.length) return
    showTimer = setTimeout(() => {
      patches.value = patchesList
      visible.value = true
      showTimer = null
      requestAnimationFrame(() => {
        const el = document.getElementById('patch-analysis-popover')
        if (el) positionAt(el as HTMLElement, x, y)
      })
    }, delayMs)
  }

  function scheduleHide() {
    clearShowTimer()
    clearHideTimer()
    if (!visible.value) return
    hideTimer = setTimeout(() => {
      visible.value = false
      hideTimer = null
    }, 300)
  }

  function cancelHide() {
    clearHideTimer()
  }

  function hideNow() {
    clearShowTimer()
    clearHideTimer()
    visible.value = false
  }

  return {
    visible,
    patches,
    position,
    showPatches,
    scheduleHide,
    cancelHide,
    hideNow,
  }
}
