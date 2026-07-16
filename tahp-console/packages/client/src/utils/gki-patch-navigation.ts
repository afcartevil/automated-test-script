export const GKI_PATCH_PATH_TO_ROUTE: Record<string, string> = {
  '/dashboard': 'tahp.gki-patch.dashboard',
  '/analysis': 'tahp.gki-patch.analysis',
  '/crash': 'tahp.gki-patch.crash',
  '/upgrade': 'tahp.gki-patch.upgrade',
  '/patches': 'tahp.gki-patch.patches',
  '/settings': 'tahp.gki-patch.settings',
}

export interface GkiPatchNavMessage {
  type: 'ea-gki-patch-nav'
  path: string
  query?: Record<string, string>
}

export function isGkiPatchNavMessage(data: unknown): data is GkiPatchNavMessage {
  if (!data || typeof data !== 'object') return false
  const msg = data as GkiPatchNavMessage
  return msg.type === 'ea-gki-patch-nav' && typeof msg.path === 'string'
}
