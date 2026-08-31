/**
 * External notify inbox for GKI patch 分析 / 升级合入.
 * Same pattern as Modem：只入库，人工「采用并填入」后再启动任务.
 */
import crypto from 'crypto'
import fs from 'fs'
import path from 'path'
import { config as serverConfig } from '../../config'

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
  /** 通知更倾向的任务类型；缺省 both（分析与合入都可用） */
  taskKind?: GkiNoticeTaskKind
  payload: Record<string, unknown>
  receivedAt: string
  updatedAt: string
  appliedAt?: string
  dismissedAt?: string
}

export type IngestGkiNoticeInput = {
  text?: string
  title?: string
  message?: string
  source?: string
  sourceId?: string
  from_tag?: string
  to_tag?: string
  fromTag?: string
  toTag?: string
  task_kind?: string
  taskKind?: string
  notice_type?: string
  intent?: string
  [key: string]: unknown
}

export type IngestGkiNoticeOptions = {
  storePath?: string
  preferNoticeId?: string
  preferReceivedAt?: string
}

export type GkiNoticeParseResult = {
  rawText: string
  fromTag?: string
  toTag?: string
  taskKind: GkiNoticeTaskKind
  confidence: number
  warnings: string[]
}

function noticesRootDir(dataDir = serverConfig.dataDir) {
  return path.resolve(dataDir, 'gki-patch')
}

export function defaultGkiNoticesStorePath(dataDir = serverConfig.dataDir) {
  return path.resolve(noticesRootDir(dataDir), 'external-notices.json')
}

function ensureParent(filePath: string) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
}

function readStore(storePath: string): GkiExternalNotice[] {
  if (!fs.existsSync(storePath)) return []
  try {
    const raw = JSON.parse(fs.readFileSync(storePath, 'utf-8'))
    return Array.isArray(raw) ? (raw as GkiExternalNotice[]) : []
  } catch {
    return []
  }
}

function writeStore(storePath: string, items: GkiExternalNotice[]) {
  ensureParent(storePath)
  fs.writeFileSync(storePath, JSON.stringify(items, null, 2), 'utf-8')
}

function asTrimmedString(value: unknown) {
  if (value == null) return ''
  return String(value).trim()
}

function pickTag(input: IngestGkiNoticeInput, ...keys: string[]): string {
  for (const key of keys) {
    const v = asTrimmedString(input[key])
    if (v) return v
  }
  return ''
}

function buildNoticeText(input: IngestGkiNoticeInput): string {
  const direct = asTrimmedString(input.text) || asTrimmedString(input.message)
  if (direct) return direct

  const title = asTrimmedString(input.title)
  const fromTag = pickTag(input, 'from_tag', 'fromTag')
  const toTag = pickTag(input, 'to_tag', 'toTag')
  if (fromTag && toTag) return `${fromTag} -> ${toTag}`
  const parts = [title, fromTag, toTag].filter(Boolean)
  return parts.join(' ')
}

/** Android / GKI style tags, e.g. android13-5.15-2025-09_r9 */
const GKI_TAG_TOKEN = 'android\\d+(?:[._-][\\w.+]+)+'
const GKI_TAG_RE = new RegExp(`\\b${GKI_TAG_TOKEN}\\b`, 'gi')

/**
 * GKI 外部通知（TONES）只驱动「分析任务」，不创建升级合入任务。
 * 文案里即使出现「GKI升级」「升级到」，也一律按分析处理。
 * 仅当显式 task_kind=upgrade 时保留合入（兼容调试），默认 analysis。
 */
export function resolveGkiNoticeTaskKind(
  hints?: {
    taskKind?: string
    task_kind?: string
    notice_type?: string
    intent?: string
    text?: string
  },
): GkiNoticeTaskKind {
  const explicit = [
    hints?.taskKind,
    hints?.task_kind,
    hints?.notice_type,
    hints?.intent,
  ]
    .map(v => asTrimmedString(v).toLowerCase())
    .find(Boolean)

  if (explicit === 'upgrade' || explicit === '合入' || explicit === '入库') return 'upgrade'
  if (explicit === 'both' || explicit === 'all') return 'both'
  // 默认 / 文案推断：一律分析（含「本次GKI升级从…升级到…」）
  return 'analysis'
}

function extractTagPairFromText(rawText: string): { fromTag?: string; toTag?: string } {
  const patterns = [
    // 从 A 升级到 B / 从 A 到 B
    new RegExp(
      `从\\s*(${GKI_TAG_TOKEN})\\s*(?:升级到|升到|到)\\s*(${GKI_TAG_TOKEN})`,
      'i',
    ),
    // 当前 tag 点是 A … 升级到 B
    new RegExp(
      `当前\\s*tag\\s*点?\\s*是\\s*(${GKI_TAG_TOKEN})[\\s\\S]{0,40}?(?:需要)?升级到\\s*(${GKI_TAG_TOKEN})`,
      'i',
    ),
    // A → B / A -> B / A 至 B
    new RegExp(
      `(${GKI_TAG_TOKEN})\\s*(?:→|->|－|~|～|至)\\s*(${GKI_TAG_TOKEN})`,
      'i',
    ),
  ]

  for (const re of patterns) {
    const m = rawText.match(re)
    if (m?.[1] && m?.[2]) {
      return { fromTag: m[1], toTag: m[2] }
    }
  }

  const tags = Array.from(rawText.matchAll(GKI_TAG_RE)).map(m => m[0])
  const unique = [...new Set(tags)]
  if (unique.length >= 2) {
    return { fromTag: unique[0], toTag: unique[1] }
  }
  if (unique.length === 1) {
    return { fromTag: unique[0] }
  }
  return {}
}

export function parseGkiUpgradeNotice(
  text: string,
  hints?: {
    fromTag?: string
    toTag?: string
    taskKind?: string
    task_kind?: string
    notice_type?: string
    intent?: string
  },
): GkiNoticeParseResult {
  const rawText = String(text ?? '').trim()
  const warnings: string[] = []
  let fromTag = asTrimmedString(hints?.fromTag) || undefined
  let toTag = asTrimmedString(hints?.toTag) || undefined

  if (!fromTag || !toTag) {
    const extracted = extractTagPairFromText(rawText)
    fromTag = fromTag || extracted.fromTag
    toTag = toTag || extracted.toTag
  }

  const taskKind = resolveGkiNoticeTaskKind({
    taskKind: hints?.taskKind,
    task_kind: hints?.task_kind,
    notice_type: hints?.notice_type,
    intent: hints?.intent,
    text: rawText,
  })

  let confidence = 0.15
  if (fromTag) confidence += 0.4
  if (toTag) confidence += 0.4
  if (fromTag && toTag && rawText.includes(fromTag) && rawText.includes(toTag)) {
    confidence = Math.min(1, confidence + 0.05)
  }
  if (!fromTag) warnings.push('no_from_tag_detected')
  if (!toTag) warnings.push('no_to_tag_detected')

  return { rawText, fromTag, toTag, taskKind, confidence, warnings }
}

export function resolveGkiNotifyToken(env: NodeJS.ProcessEnv = process.env): string {
  return asTrimmedString(env.GKI_UPGRADE_NOTIFY_TOKEN)
}

export function verifyGkiNotifyToken(
  provided: string | undefined,
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  const expected = resolveGkiNotifyToken(env)
  if (!expected) return true
  return asTrimmedString(provided) === expected
}

export function extractGkiNotifyToken(headers: Record<string, unknown>, queryToken?: unknown): string {
  const auth = asTrimmedString(headers.authorization || headers.Authorization)
  if (auth.toLowerCase().startsWith('bearer ')) {
    return auth.slice(7).trim()
  }
  const headerToken = asTrimmedString(
    headers['x-gki-notify-token'] || headers['X-Gki-Notify-Token'],
  )
  if (headerToken) return headerToken
  return asTrimmedString(queryToken)
}

export function ingestGkiUpgradeNotice(
  raw: IngestGkiNoticeInput | string,
  options?: IngestGkiNoticeOptions,
): { notice: GkiExternalNotice; created: boolean } {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  const input: IngestGkiNoticeInput = typeof raw === 'string'
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

  const hintFrom = pickTag(input, 'from_tag', 'fromTag')
  const hintTo = pickTag(input, 'to_tag', 'toTag')
  const parsed = parseGkiUpgradeNotice(text, {
    fromTag: hintFrom || undefined,
    toTag: hintTo || undefined,
    taskKind: asTrimmedString(input.taskKind) || undefined,
    task_kind: asTrimmedString(input.task_kind) || undefined,
    notice_type: asTrimmedString(input.notice_type) || undefined,
    intent: asTrimmedString(input.intent) || undefined,
  })

  const now = new Date().toISOString()
  const notice: GkiExternalNotice = {
    noticeId: preferNoticeId || `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`,
    status: 'pending',
    text,
    title: asTrimmedString(input.title) || undefined,
    source,
    sourceId,
    fromTag: parsed.fromTag,
    toTag: parsed.toTag,
    taskKind: parsed.taskKind,
    payload: typeof raw === 'string' ? { text: raw } : { ...input },
    receivedAt: preferReceivedAt || now,
    updatedAt: now,
  }

  items.unshift(notice)
  writeStore(storePath, items.slice(0, 500))
  return { notice, created: true }
}

export function listGkiUpgradeNotices(
  filter?: { status?: GkiExternalNoticeStatus | 'all' },
  options?: { storePath?: string },
): GkiExternalNotice[] {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  const items = readStore(storePath)
  const status = filter?.status || 'pending'
  if (status === 'all') return items
  return items.filter(item => item.status === status)
}

export function updateGkiUpgradeNoticeStatus(
  noticeId: string,
  status: 'applied' | 'dismissed',
  options?: { storePath?: string },
): GkiExternalNotice {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  const items = readStore(storePath)
  const index = items.findIndex(item => item.noticeId === noticeId)
  if (index < 0) throw new Error('notice_not_found')

  const now = new Date().toISOString()
  const current = items[index]
  const next: GkiExternalNotice = {
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
