import { onBeforeUnmount, ref, type Ref } from 'vue'

export type ScrollSnapshot = {
  panelTop: number
  patchListTop: number | null
}

export function usePanelScrollReturn(
  panelRef: Ref<HTMLElement | null | undefined>,
  patchListScrollRef: Ref<HTMLElement | null | undefined>,
) {
  const returnSnapshot = ref<ScrollSnapshot | null>(null)

  function saveBeforeNavigate() {
    const panel = panelRef.value
    if (!panel) return
    const patchList = patchListScrollRef.value
    returnSnapshot.value = {
      panelTop: panel.scrollTop,
      patchListTop: patchList ? patchList.scrollTop : null,
    }
  }

  function scrollToSavedOrTop() {
    const panel = panelRef.value
    if (!panel) return

    if (returnSnapshot.value) {
      const snap = returnSnapshot.value
      returnSnapshot.value = null
      panel.scrollTo({ top: snap.panelTop, behavior: 'smooth' })
      const patchList = patchListScrollRef.value
      if (patchList && snap.patchListTop != null) {
        patchList.scrollTo({ top: snap.patchListTop, behavior: 'smooth' })
      }
      return
    }

    panel.scrollTo({ top: 0, behavior: 'smooth' })
    patchListScrollRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function cleanup() {
    returnSnapshot.value = null
  }

  onBeforeUnmount(cleanup)

  return {
    returnSnapshot,
    saveBeforeNavigate,
    scrollToSavedOrTop,
    cleanup,
  }
}
