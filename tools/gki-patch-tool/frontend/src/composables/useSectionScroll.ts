import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

export function scrollPanelToSection(
  panel: HTMLElement | null | undefined,
  sectionId: string,
  extraOffset = 8,
) {
  if (!panel || !sectionId) return
  const target = panel.querySelector(`#${CSS.escape(sectionId)}`) as HTMLElement | null
  if (!target) return

  const nav = panel.querySelector('.analysis-section-nav') as HTMLElement | null
  const navHeight = nav?.offsetHeight ?? 0
  const panelTop = panel.getBoundingClientRect().top
  const targetTop = target.getBoundingClientRect().top
  const top = panel.scrollTop + (targetTop - panelTop) - navHeight - extraOffset

  panel.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

export function useSectionScroll(panelRef: Ref<HTMLElement | null | undefined>) {
  function scrollToSection(sectionId: string) {
    scrollPanelToSection(panelRef.value, sectionId)
  }

  return { scrollToSection }
}

/** Highlight nav button for the section currently in view while scrolling the detail panel. */
export function useAnalysisSectionSpy(
  panelRef: Ref<HTMLElement | null | undefined>,
  sectionIds: Ref<string[]>,
  activeId: Ref<string>,
) {
  let paused = false
  let pauseTimer: ReturnType<typeof setTimeout> | null = null
  let raf = 0
  let attachedPanel: HTMLElement | null = null

  function computeActive() {
    if (paused) return
    const panel = panelRef.value
    const ids = sectionIds.value.filter(Boolean)
    if (!panel || !ids.length) return

    const nav = panel.querySelector('.analysis-section-nav') as HTMLElement | null
    const navHeight = nav?.offsetHeight ?? 0
    const anchorLine = panel.getBoundingClientRect().top + navHeight + 12

    if (panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 12) {
      activeId.value = ids[ids.length - 1]
      return
    }

    let current = ids[0]
    for (const id of ids) {
      const el = panel.querySelector(`#${CSS.escape(id)}`) as HTMLElement | null
      if (!el) continue
      if (el.getBoundingClientRect().top <= anchorLine) {
        current = id
      }
    }
    activeId.value = current
  }

  function onScroll() {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(computeActive)
  }

  function detach() {
    if (attachedPanel) {
      attachedPanel.removeEventListener('scroll', onScroll)
      attachedPanel = null
    }
    cancelAnimationFrame(raf)
  }

  function attach() {
    detach()
    const panel = panelRef.value
    if (!panel) return
    attachedPanel = panel
    panel.addEventListener('scroll', onScroll, { passive: true })
    computeActive()
  }

  function pauseSpy(ms = 700) {
    paused = true
    if (pauseTimer) clearTimeout(pauseTimer)
    pauseTimer = setTimeout(() => {
      paused = false
      computeActive()
    }, ms)
  }

  watch(
    [panelRef, sectionIds],
    () => {
      nextTick(() => attach())
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    if (pauseTimer) clearTimeout(pauseTimer)
    detach()
  })

  return { pauseSpy, refreshSpy: computeActive }
}
