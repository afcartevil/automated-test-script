/**
 * External notify inbox for Modem 升级.
 * MergeTool POSTs a notice here after baseline upgrade.
 * EasyAdapter only stores it — operator confirms in UI then starts the run.
 */
import crypto from 'crypto'
import fs from 'fs'
import path from 'path'
import { config as serverConfig } from '../../config'

export type ModemExternalNoticeStatus = 'pending' | 'applied' | 'dismissed'

export type ModemBaselineManifestFields = {
  /** 任务关联 manifest，如 tOS_mtk_A16_vnd_trunk.xml */
  trunk?: string
  /** 新基线 manifest，如 t-alps-release-b0.mp1.rc-V12.9.xml */
  newBaseline?: string
  /** 老基线 manifest，如 t-alps-release-b0.mp1.rc-V11.9.xml */
  oldBaseline?: string
}

export type ModemExternalNotice = {
  noticeId: string
  status: ModemExternalNoticeStatus
  text: string
  source: string
  sourceId?: string
  version?: string
  trunk?: string
  newBaseline?: string
  oldBaseline?: string
  payload: Record<string, unknown>
  receivedAt: string
  updatedAt: string
  appliedAt?: string
  dismissedAt?: string
}

/** MergeTool 外部通知唯一契约 */
export type IngestModemNoticeInput = {
  source?: string
  sourceId?: string
  trunk?: string
  newBaseline?: string
  oldBaseline?: string
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

/** 从基线/manifest 文件名提取版本，如 …-V12.9.xml → V12.9 */
export function extractVersionFromBaselineName(name: string): string | undefined {
  const raw = asTrimmedString(name)
  if (!raw) return undefined
  const dashed = raw.match(/-V(\d+(?:\.\d+){0,4})(?:\.xml)?$/i)
  if (dashed) return `V${dashed[1]}`
  const loose = raw.match(/\bV(\d+(?:\.\d+){0,4})\b/i)
  return loose ? `V${loose[1]}` : undefined
}

/** 从「任务：xxx.xml 基线升级」取值里抽出 manifest 名 */
export function normalizeTaskTrunkValue(value: string): string {
  const raw = asTrimmedString(value)
  if (!raw) return ''
  const xml = raw.match(/([^\s：:]+?\.xml)\b/i)
  if (xml) return xml[1]
  return raw.replace(/\s*基线升级\s*$/u, '').trim()
}

/** 从展示文案「任务：/新基线：/老基线：」解析字段（采用并填入时用） */
export function parseModemBaselineManifestText(text: string): ModemBaselineManifestFields {
  const raw = String(text ?? '')
  const pick = (label: string) => {
    const re = new RegExp(`^\\s*${label}\\s*[:：]\\s*(.+)\\s*$`, 'im')
    const match = raw.match(re)
    return match ? asTrimmedString(match[1]) : ''
  }
  const trunk = normalizeTaskTrunkValue(pick('任务'))
  const newBaseline = pick('新基线')
  const oldBaseline = pick('老基线')
  return {
    trunk: trunk || undefined,
    newBaseline: newBaseline || undefined,
    oldBaseline: oldBaseline || undefined,
  }
}

export function formatModemBaselineManifestText(fields: ModemBaselineManifestFields): string {
  const trunk = asTrimmedString(fields.trunk)
  const newBaseline = asTrimmedString(fields.newBaseline)
  const oldBaseline = asTrimmedString(fields.oldBaseline)
  if (!trunk || !newBaseline || !oldBaseline) return ''
  return [
    `任务：${trunk} 基线升级`,
    `新基线：${newBaseline}`,
    `老基线：${oldBaseline}`,
  ].join('\n')
}

export function resolveModemBaselineManifestFields(
  input: IngestModemNoticeInput,
): ModemBaselineManifestFields {
  return {
    trunk: normalizeTaskTrunkValue(asTrimmedString(input.trunk)) || undefined,
    newBaseline: asTrimmedString(input.newBaseline) || undefined,
    oldBaseline: asTrimmedString(input.oldBaseline) || undefined,
  }
}

function buildNoticeText(input: IngestModemNoticeInput): string {
  return formatModemBaselineManifestText(resolveModemBaselineManifestFields(input))
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
  if (typeof raw === 'string' || !raw || typeof raw !== 'object') {
    throw new Error('notice_fields_required')
  }
  const input: IngestModemNoticeInput = raw

  const manifests = resolveModemBaselineManifestFields(input)
  const text = formatModemBaselineManifestText(manifests)
  if (!text) {
    throw new Error('notice_fields_required')
  }

  const source = asTrimmedString(input.source) || 'MergeTool'
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
    source,
    sourceId,
    version: extractVersionFromBaselineName(manifests.newBaseline || '') || undefined,
    trunk: manifests.trunk,
    newBaseline: manifests.newBaseline,
    oldBaseline: manifests.oldBaseline,
    payload: { ...input },
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
