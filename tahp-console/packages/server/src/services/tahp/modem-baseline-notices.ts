/**
 * External notify inbox for Modem 升级.
 * Baseline upgrade is done by other tools; they POST a notice here.
 * EasyAdapter only stores it — operator confirms in UI then starts the run.
 */
import crypto from 'crypto'
import fs from 'fs'
import path from 'path'
import { config as serverConfig } from '../../config'

export type ModemExternalNoticeStatus = 'pending' | 'applied' | 'dismissed'

export type ModemExternalNotice = {
  noticeId: string
  status: ModemExternalNoticeStatus
  text: string
  title?: string
  source: string
  sourceId?: string
  platform?: string
  version?: string
  tosVersion?: string
  payload: Record<string, unknown>
  receivedAt: string
  updatedAt: string
  appliedAt?: string
  dismissedAt?: string
}

export type IngestModemNoticeInput = {
  text?: string
  title?: string
  message?: string
  source?: string
  sourceId?: string
  platform?: string
  version?: string
  tosVersion?: string
  tos?: string
  [key: string]: unknown
}

export type IngestModemNoticeOptions = {
  storePath?: string
  /** 采用中心下发的 noticeId（Socket 推送场景） */
  preferNoticeId?: string
  /** 采用中心 receivedAt，便于 ack 水位与中心一致 */
  preferReceivedAt?: string
}

function noticesRootDir(dataDir = serverConfig.dataDir) {
  return path.resolve(dataDir, 'modem-patch')
}

export function defaultNoticesStorePath(dataDir = serverConfig.dataDir) {
  return path.resolve(noticesRootDir(dataDir), 'external-notices.json')
}

function ensureParent(filePath: string) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
}

function readStore(storePath: string): ModemExternalNotice[] {
  if (!fs.existsSync(storePath)) return []
  try {
    const raw = JSON.parse(fs.readFileSync(storePath, 'utf-8'))
    return Array.isArray(raw) ? (raw as ModemExternalNotice[]) : []
  } catch {
    return []
  }
}

function writeStore(storePath: string, items: ModemExternalNotice[]) {
  ensureParent(storePath)
  fs.writeFileSync(storePath, JSON.stringify(items, null, 2), 'utf-8')
}

function asTrimmedString(value: unknown) {
  if (value == null) return ''
  return String(value).trim()
}

function buildNoticeText(input: IngestModemNoticeInput): string {
  const direct = asTrimmedString(input.text) || asTrimmedString(input.message)
  if (direct) return direct

  const title = asTrimmedString(input.title)
  const platform = asTrimmedString(input.platform)
  const version = asTrimmedString(input.version)
  const tos = asTrimmedString(input.tosVersion) || asTrimmedString(input.tos)
  const parts = [title, platform, version, tos].filter(Boolean)
  return parts.join(' ')
}

export function resolveModemNotifyToken(env: NodeJS.ProcessEnv = process.env): string {
  return asTrimmedString(env.MODEM_BASELINE_NOTIFY_TOKEN)
}

/** Returns true when request token matches configured secret (or no secret configured). */
export function verifyModemNotifyToken(
  provided: string | undefined,
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  const expected = resolveModemNotifyToken(env)
  if (!expected) return true
  return asTrimmedString(provided) === expected
}

export function extractModemNotifyToken(headers: Record<string, unknown>, queryToken?: unknown): string {
  const auth = asTrimmedString(headers.authorization || headers.Authorization)
  if (auth.toLowerCase().startsWith('bearer ')) {
    return auth.slice(7).trim()
  }
  const headerToken = asTrimmedString(
    headers['x-modem-notify-token'] || headers['X-Modem-Notify-Token'],
  )
  if (headerToken) return headerToken
  return asTrimmedString(queryToken)
}

export function ingestModemBaselineNotice(
  raw: IngestModemNoticeInput | string,
  options?: IngestModemNoticeOptions,
): { notice: ModemExternalNotice; created: boolean } {
  const storePath = options?.storePath || defaultNoticesStorePath()
  const input: IngestModemNoticeInput = typeof raw === 'string'
    ? { text: raw }
    : (raw && typeof raw === 'object' ? raw : {})

  const text = buildNoticeText(input)
  if (!text) {
    throw new Error('notice_text_required')
  }

  const source = asTrimmedString(input.source) || 'tones'
  const sourceId = asTrimmedString(input.sourceId) || undefined
  const preferNoticeId = asTrimmedString(options?.preferNoticeId)
  const preferReceivedAt = asTrimmedString(options?.preferReceivedAt)
  const items = readStore(storePath)

  if (preferNoticeId) {
    const byId = items.find(item => item.noticeId === preferNoticeId)
    if (byId) {
      return { notice: byId, created: false }
    }
  }

  if (sourceId) {
    const existing = items.find(item => item.source === source && item.sourceId === sourceId)
    if (existing) {
      return { notice: existing, created: false }
    }
  }

  const now = new Date().toISOString()
  const notice: ModemExternalNotice = {
    noticeId: preferNoticeId || `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`,
    status: 'pending',
    text,
    title: asTrimmedString(input.title) || undefined,
    source,
    sourceId,
    platform: asTrimmedString(input.platform) || undefined,
    version: asTrimmedString(input.version) || undefined,
    tosVersion: asTrimmedString(input.tosVersion) || asTrimmedString(input.tos) || undefined,
    payload: typeof raw === 'string' ? { text: raw } : { ...input },
    receivedAt: preferReceivedAt || now,
    updatedAt: now,
  }

  items.unshift(notice)
  writeStore(storePath, items.slice(0, 500))
  return { notice, created: true }
}

export function listModemBaselineNotices(
  filter?: { status?: ModemExternalNoticeStatus | 'all' },
  options?: { storePath?: string },
): ModemExternalNotice[] {
  const storePath = options?.storePath || defaultNoticesStorePath()
  const items = readStore(storePath)
  const status = filter?.status || 'pending'
  if (status === 'all') return items
  return items.filter(item => item.status === status)
}

export function updateModemBaselineNoticeStatus(
  noticeId: string,
  status: 'applied' | 'dismissed',
  options?: { storePath?: string },
): ModemExternalNotice {
  const storePath = options?.storePath || defaultNoticesStorePath()
  const items = readStore(storePath)
  const index = items.findIndex(item => item.noticeId === noticeId)
  if (index < 0) throw new Error('notice_not_found')

  const now = new Date().toISOString()
  const current = items[index]
  const next: ModemExternalNotice = {
    ...current,
    status,
    updatedAt: now,
    appliedAt: status === 'applied' ? now : current.appliedAt,
    dismissedAt: status === 'dismissed' ? now : current.dismissedAt,
  }
  items[index] = next
  writeStore(storePath, items)
  return next
}
