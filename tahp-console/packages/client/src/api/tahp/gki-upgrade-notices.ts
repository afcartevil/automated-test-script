import { tahpDelete, tahpGet, tahpPost } from './client'

export type GkiNoticeTaskKind = 'analysis' | 'upgrade' | 'both'

export type GkiNoticeKind = 'upgrade' | 'alert'

export type GkiExternalNoticeStatus = 'pending' | 'applied' | 'dismissed'

export type GkiExternalNotice = {
  noticeId: string
  status: GkiExternalNoticeStatus
  text: string
  title?: string
  source: string
  sourceId?: string
  parentSourceId?: string
  fromTag?: string
  toTag?: string
  taskKind?: GkiNoticeTaskKind
  kind?: GkiNoticeKind
  alertRule?: string
  branches?: string
  platform?: string
  projects?: string
  currentGkiVersion?: string
  kernelVersion?: string
  socVendor?: string
  startDate?: string
  dueDate?: string
  receivedAt: string
  updatedAt: string
  appliedAt?: string
  dismissedAt?: string
  dismissReason?: string
}

export function ingestGkiNoticeFromTask(pkg: Record<string, unknown>): Promise<{
  notice: GkiExternalNotice
  created: boolean
  notices?: GkiExternalNotice[]
  createdCount?: number
}> {
  return tahpPost<{ notice: GkiExternalNotice; created: boolean }>(
    '/api/tahp/gki-patch/notices/from-task',
    pkg,
  )
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

export function dismissGkiUpgradeNotice(noticeId: string, reason: string): Promise<GkiExternalNotice> {
  return tahpPost<GkiExternalNotice>(
    `/api/tahp/gki-patch/notices/${encodeURIComponent(noticeId)}/dismiss`,
    { reason },
  )
}

export function restoreGkiUpgradeNotice(noticeId: string): Promise<GkiExternalNotice> {
  return tahpPost<GkiExternalNotice>(
    `/api/tahp/gki-patch/notices/${encodeURIComponent(noticeId)}/restore`,
    {},
  )
}

export function deleteGkiUpgradeNotice(noticeId: string): Promise<{ noticeId: string }> {
  return tahpDelete<{ noticeId: string }>(
    `/api/tahp/gki-patch/notices/${encodeURIComponent(noticeId)}`,
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
