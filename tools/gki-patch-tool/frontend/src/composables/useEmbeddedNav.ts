export function isEmbeddedMode(): boolean {
  const q = new URLSearchParams(window.location.search).get('embedded')
  return q === '1' || q === 'true'
}

export function requestParentNav(path: string, query: Record<string, string> = {}): boolean {
  if (!isEmbeddedMode() || window.parent === window) return false
  window.parent.postMessage({ type: 'ea-gki-patch-nav', path, query }, '*')
  return true
}

export function useEmbeddedNav() {
  function onLinkClick(
    event: MouseEvent,
    path: string,
    query: Record<string, string> = {},
  ) {
    if (requestParentNav(path, query)) {
      event.preventDefault()
    }
  }

  return { onLinkClick, isEmbedded: isEmbeddedMode() }
}
