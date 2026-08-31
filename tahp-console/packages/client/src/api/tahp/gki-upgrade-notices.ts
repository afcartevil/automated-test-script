import { tahpGet, tahpPost } from './client'

export type GkiNoticeTaskKind = 'analysis' | 'upgrade' | 'both'

export type GkiExternalNoticeStatus = 'pending' | 'applied' | 'dismissed'

export type GkiExternalNotice = {
  noticeId: string
  status: GkiExternalNoticeStatus
  text: string
  title?: string
  source: string
  sourceId?: string
  fromTag?: string
  toTag?: string
  taskKind?: GkiNoticeTaskKind
  receivedAt: string
  updatedAt: string
  appliedAt?: string
  dismissedAt?: string
}

export type GkiNoticeParseResult = {
  rawText: string
  fromTag?: string
  toTag?: string
  taskKind: GkiNoticeTaskKind
  confidence: number
  warnings: string[]
}

export function listGkiUpgradeNotices(
  status: GkiExternalNoticeStatus | 'all' = 'pending',
): Promise<{ items: GkiExternalNotice[] }> {
  const query = new URLSearchParams({ status })
  return tahpGet<{ items: GkiExternalNotice[] }>(`/api/tahp/gki-patch/notices?${query.toString()}`)
}

export function applyGkiUpgradeNotice(noticeId: string): Promise<GkiExternalNotice> {
  return tahpPost<GkiExternalNotice>(
    `/api/tahp/gki-patch/notices/${encodeURIComponent(noticeId)}/apply`,
    {},
  )
}

export function dismissGkiUpgradeNotice(noticeId: string): Promise<GkiExternalNotice> {
  return tahpPost<GkiExternalNotice>(
    `/api/tahp/gki-patch/notices/${encodeURIComponent(noticeId)}/dismiss`,
    {},
  )
}

export function parseGkiUpgradeNotice(input: {
  text: string
  fromTag?: string
  toTag?: string
  taskKind?: string
  task_kind?: string
  notice_type?: string
  intent?: string
}): Promise<GkiNoticeParseResult> {
  return tahpPost<GkiNoticeParseResult>('/api/tahp/gki-patch/parse-notice', input)
}
