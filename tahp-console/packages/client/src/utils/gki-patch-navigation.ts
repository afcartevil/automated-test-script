export const GKI_PATCH_PATH_TO_ROUTE: Record<string, string> = {
  '/dashboard': 'tahp.gki-patch.dashboard',
  '/analysis': 'tahp.gki-patch.analysis',
  '/crash': 'tahp.gki-patch.crash',
  '/upgrade': 'tahp.gki-patch.upgrade',
  '/patches': 'tahp.gki-patch.patches',
  '/settings': 'tahp.gki-patch.settings',
}

export const GKI_PATCH_ROUTE_TO_PATH: Record<string, string> = Object.fromEntries(
  Object.entries(GKI_PATCH_PATH_TO_ROUTE).map(([path, name]) => [name, path]),
)

/** iframe → EasyAdapter parent：请求切换 EA 侧栏路由 */
export interface GkiPatchNavMessage {
  type: 'ea-gki-patch-nav'
  path: string
  query?: Record<string, string>
}

/** EasyAdapter parent → iframe：在已加载 SPA 内切换路由（避免整页重载） */
export interface GkiPatchNavigateMessage {
  type: 'ea-gki-patch-navigate'
  path: string
  query?: Record<string, string>
}

/** EasyAdapter parent → iframe：采用外部通知并填入升级表单 Tag */
export interface GkiPatchApplyNoticeMessage {
  type: 'ea-gki-patch-apply-notice'
  fromTag: string
  toTag: string
  text?: string
  noticeId?: string
}

export function isGkiPatchNavMessage(data: unknown): data is GkiPatchNavMessage {
  if (!data || typeof data !== 'object') return false
  const msg = data as GkiPatchNavMessage
  return msg.type === 'ea-gki-patch-nav' && typeof msg.path === 'string'
}

export function isGkiPatchNavigateMessage(data: unknown): data is GkiPatchNavigateMessage {
  if (!data || typeof data !== 'object') return false
  const msg = data as GkiPatchNavigateMessage
  return msg.type === 'ea-gki-patch-navigate' && typeof msg.path === 'string'
}

export function isGkiPatchApplyNoticeMessage(data: unknown): data is GkiPatchApplyNoticeMessage {
  if (!data || typeof data !== 'object') return false
  const msg = data as GkiPatchApplyNoticeMessage
  return (
    msg.type === 'ea-gki-patch-apply-notice'
    && typeof msg.fromTag === 'string'
    && typeof msg.toTag === 'string'
  )
}

export function buildGkiFrameSrc(
  status: { appBaseUrl?: string; appUrl: string },
  gkiPath: string,
  query: Record<string, unknown> = {},
): string {
  const base = status.appBaseUrl || status.appUrl.replace(/\/?$/, '')
  const normalizedBase = base.endsWith('/app') ? base : `${base.replace(/\/$/, '')}/app`
  const path = gkiPath.startsWith('/') ? gkiPath : `/${gkiPath}`
  const params = new URLSearchParams({ embedded: '1' })
  for (const [key, value] of Object.entries(query)) {
    const raw = Array.isArray(value) ? value[0] : value
    if (raw == null || raw === '') continue
    params.set(key, String(raw))
  }
  return `${normalizedBase}${path}?${params.toString()}`
}
