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

export type GkiNoticeKind = 'upgrade' | 'alert'

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
  /** 通知更倾向的任务类型；缺省 both（分析与合入都可用） */
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
  payload: Record<string, unknown>
  receivedAt: string
  updatedAt: string
  appliedAt?: string
  dismissedAt?: string
  dismissReason?: string
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

export type IngestGkiNoticeResult = {
  notice: GkiExternalNotice
  created: boolean
  notices: GkiExternalNotice[]
  createdCount: number
}

export type GkiAlertRecord = {
  branches: string
  platform: string
  projects: string
  currentGkiVersion: string
  kernelVersion: string
  socVendor: string
  startDate: string
  dueDate: string
  designatedProject?: string
  raw: Record<string, unknown>
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

function extractAlertRule(text: string): string {
  const m = text.match(/命中规则[：:]\s*([^\n。]+)/)
  return asTrimmedString(m?.[1]).replace(/[。．]\s*$/, '')
}

function extractBalancedJsonArray(text: string, from: number): string | null {
  if (text[from] !== '[') return null
  let depth = 0
  let inStr = false
  let escape = false
  for (let i = from; i < text.length; i += 1) {
    const ch = text[i]
    if (inStr) {
      if (escape) {
        escape = false
        continue
      }
      if (ch === '\\') {
        escape = true
        continue
      }
      if (ch === '"') inStr = false
      continue
    }
    if (ch === '"') {
      inStr = true
      continue
    }
    if (ch === '[') depth += 1
    else if (ch === ']') {
      depth -= 1
      if (depth === 0) return text.slice(from, i + 1)
    }
  }
  return null
}

function parseJsonArrayText(raw: string): Record<string, unknown>[] {
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(item => item && typeof item === 'object' && !Array.isArray(item)) as Record<string, unknown>[]
  } catch {
    return []
  }
}

function extractAlertJsonArray(text: string): Record<string, unknown>[] {
  const raw = String(text || '')
  const marker = raw.search(/明细|JSON/)
  const windows = marker >= 0 ? [raw.slice(marker), raw] : [raw]
  for (const slice of windows) {
    let from = 0
    while (from < slice.length) {
      const start = slice.indexOf('[', from)
      if (start < 0) break
      const block = extractBalancedJsonArray(slice, start)
      if (block) {
        const rows = parseJsonArrayText(block)
        if (rows.some(row => pickAlertField(row, '当前GKI版本', '分支', '平台', '启动日期'))) {
          return rows
        }
      }
      from = start + 1
    }
  }
  return []
}

function pickAlertField(rec: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const v = asTrimmedString(rec[key])
    if (v) return v
  }
  return ''
}

function normalizeMultiline(value: string): string {
  return value
    .replace(/\\n/g, '\n')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map(part => part.trim())
    .filter(Boolean)
    .join('\n')
}

export function parseGkiAlertRecord(raw: unknown): GkiAlertRecord | null {
  const rec = asRecord(raw)
  const branches = normalizeMultiline(pickAlertField(rec, '分支', 'branch', 'branches'))
  const platform = pickAlertField(rec, '平台', 'platform')
  const projects = pickAlertField(rec, '项目', 'project', 'projects')
  const currentGkiVersion = pickAlertField(rec, '当前GKI版本', 'currentGkiVersion', 'current_gki', 'from_tag', 'fromTag')
  const kernelVersion = pickAlertField(rec, 'kernel版本', 'kernelVersion', 'kernel', 'kernel_version')
  const socVendor = pickAlertField(rec, 'SOC厂商', 'socVendor', 'soc', 'vendor')
  const startDate = pickAlertField(rec, '启动日期', 'startDate', 'start_date')
  const dueDate = pickAlertField(rec, '完成日期', 'dueDate', 'due_date', 'end_date', 'finish_date')
  const designatedProject = pickAlertField(rec, '指定项目', 'designatedProject', 'designated_project')
  if (!branches && !platform && !projects && !currentGkiVersion) return null
  return {
    branches,
    platform,
    projects,
    currentGkiVersion,
    kernelVersion,
    socVendor,
    startDate,
    dueDate,
    designatedProject: designatedProject || undefined,
    raw: rec,
  }
}

export function parseGkiAlertRecords(text: string): GkiAlertRecord[] {
  return extractAlertJsonArray(text).map(parseGkiAlertRecord).filter((row): row is GkiAlertRecord => Boolean(row))
}

function parseGkiAlertRecordsFromInput(text: string, input: IngestGkiNoticeInput): GkiAlertRecord[] {
  const combined = [text, input.title, input.message, input.text]
    .map(value => asTrimmedString(value))
    .filter(Boolean)
    .join('\n')
  const fromText = parseGkiAlertRecords(combined)
  if (fromText.length) return fromText
  const nested = [input.records, input.items, input.alerts]
  for (const candidate of nested) {
    if (!Array.isArray(candidate)) continue
    const rows = candidate.map(parseGkiAlertRecord).filter((row): row is GkiAlertRecord => Boolean(row))
    if (rows.length) return rows
  }
  return []
}

function alertRecordKey(record: GkiAlertRecord): string {
  const raw = [
    record.platform,
    record.currentGkiVersion,
    record.startDate,
    record.dueDate,
    record.branches,
    record.projects,
    record.designatedProject || '',
  ].join('|')
  return crypto.createHash('sha1').update(raw).digest('hex').slice(0, 10)
}

function displayProject(record: GkiAlertRecord): string {
  return record.designatedProject || record.projects
}

function formatAlertNoticeText(record: GkiAlertRecord, rule: string): string {
  const project = displayProject(record)
  const lines = [
    rule ? `【GKI升级管理-异常告警】${rule}` : '【GKI升级管理-异常告警】',
    record.platform || project
      ? `平台 ${record.platform || '-'} · 项目 ${project || '-'}`
      : '',
    record.currentGkiVersion ? `当前GKI版本 ${record.currentGkiVersion}` : '',
    record.branches ? `分支 ${record.branches.replace(/\n/g, ' / ')}` : '',
    [
      record.startDate ? `启动 ${record.startDate}` : '',
      record.dueDate ? `完成 ${record.dueDate}` : '',
      record.kernelVersion,
      record.socVendor,
    ].filter(Boolean).join(' · '),
  ]
  return lines.filter(Boolean).join('\n')
}

function asIngestResult(notice: GkiExternalNotice, created: boolean): IngestGkiNoticeResult {
  return { notice, created, notices: [notice], createdCount: created ? 1 : 0 }
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
  const alertRecords = parseGkiAlertRecords(rawText)
  if ((!fromTag || !toTag) && alertRecords[0]?.currentGkiVersion) {
    fromTag = fromTag || alertRecords[0].currentGkiVersion
  }

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

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function gkiKindToken(value: unknown): string {
  return asTrimmedString(value).toLowerCase()
}

/** 中心「我的任务」/task-notify 包是否为 GKI patch 通知 */
export function isGkiTaskNotice(pkg: unknown): boolean {
  const rec = asRecord(pkg)
  const payload = asRecord(rec.payload)
  const tokens = [
    rec.notice_type,
    rec.noticeType,
    rec.kind,
    rec.module,
    rec.patch_kind,
    payload.notice_type,
    payload.noticeType,
    payload.patch_kind,
    payload.module,
  ].map(gkiKindToken)
  return tokens.some(token => token === 'gki' || token === 'gki-patch' || token.includes('gki-patch'))
}

function tagsFromNext(next: unknown): { from_tag?: string; to_tag?: string } {
  const raw = asTrimmedString(next)
  if (!raw) return {}
  try {
    const url = raw.includes('://') ? new URL(raw) : new URL(raw, 'http://local.invalid')
    const from = asTrimmedString(url.searchParams.get('from_tag') || url.searchParams.get('fromTag'))
    const to = asTrimmedString(url.searchParams.get('to_tag') || url.searchParams.get('toTag'))
    return {
      from_tag: from || undefined,
      to_tag: to || undefined,
    }
  } catch {
    return {}
  }
}

/**
 * 把中心任务包写入 GKI 工作台「外部通知」。
 * 与 /baseline-notify 互补：我的任务走 /task-notify + my-packages，原先不会进 workbench inbox。
 */
export function ingestGkiNoticeFromTaskPackage(
  pkg: Record<string, unknown>,
  options?: IngestGkiNoticeOptions,
): IngestGkiNoticeResult {
  const payload = asRecord(pkg.payload)
  const extra = asRecord(pkg.extra)
  const fromNext = tagsFromNext(pkg.next)
  const packageId = asTrimmedString(pkg.package_id || pkg.packageId || payload.package_id || pkg.noticeId)
  const fromTag = pickTag(payload, 'from_tag', 'fromTag')
    || pickTag(extra, 'from_tag', 'fromTag')
    || pickTag(pkg, 'from_tag', 'fromTag')
    || fromNext.from_tag
    || ''
  const toTag = pickTag(payload, 'to_tag', 'toTag')
    || pickTag(extra, 'to_tag', 'toTag')
    || pickTag(pkg, 'to_tag', 'toTag')
    || fromNext.to_tag
    || ''
  const title = asTrimmedString(pkg.title || payload.title)
  const text = buildNoticeText({
    ...payload,
    ...extra,
    ...pkg,
    title,
    from_tag: fromTag,
    to_tag: toTag,
  }) || title || 'GKI Patch 通知'

  return ingestGkiUpgradeNotice(
    {
      ...payload,
      ...extra,
      ...pkg,
      source: asTrimmedString(pkg.source) || 'central-task',
      sourceId: asTrimmedString(pkg.sourceId || payload.sourceId) || packageId || undefined,
      title: title || undefined,
      text,
      from_tag: fromTag || undefined,
      to_tag: toTag || undefined,
      notice_type: asTrimmedString(pkg.notice_type || payload.notice_type) || 'gki-patch',
    },
    {
      ...options,
      preferNoticeId: asTrimmedString(options?.preferNoticeId) || packageId || undefined,
    },
  )
}

export function tryIngestGkiNoticeFromTaskPackage(
  pkg: unknown,
  options?: IngestGkiNoticeOptions,
): IngestGkiNoticeResult | null {
  if (!isGkiTaskNotice(pkg)) return null
  try {
    return ingestGkiNoticeFromTaskPackage(asRecord(pkg), options)
  } catch {
    return null
  }
}

export function tryIngestGkiNoticesFromTaskPackages(
  packages: unknown[],
  options?: IngestGkiNoticeOptions,
): number {
  let count = 0
  for (const pkg of packages) {
    if (tryIngestGkiNoticeFromTaskPackage(pkg, options)) count += 1
  }
  return count
}

export function ingestGkiUpgradeNotice(
  raw: IngestGkiNoticeInput | string,
  options?: IngestGkiNoticeOptions,
): IngestGkiNoticeResult {
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
  const alertRecords = parseGkiAlertRecordsFromInput(text, input)
  if (alertRecords.length > 0) {
    const combined = [text, input.title, input.message].map(v => asTrimmedString(v)).filter(Boolean).join('\n')
    return ingestAlertNotices(input, combined || text, alertRecords, {
      storePath,
      source,
      sourceId,
      preferNoticeId,
      preferReceivedAt,
    })
  }

  const items = readStore(storePath)

  if (preferNoticeId) {
    const byId = items.find(item => item.noticeId === preferNoticeId)
    if (byId) {
      return asIngestResult(byId, false)
    }
  }

  if (sourceId) {
    const existing = items.find(item => item.source === source && item.sourceId === sourceId)
    if (existing) {
      return asIngestResult(existing, false)
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
    kind: 'upgrade',
    payload: typeof raw === 'string' ? { text: raw } : { ...input },
    receivedAt: preferReceivedAt || now,
    updatedAt: now,
  }

  items.unshift(notice)
  writeStore(storePath, items.slice(0, 500))
  return asIngestResult(notice, true)
}

function ingestAlertNotices(
  input: IngestGkiNoticeInput,
  rawText: string,
  records: GkiAlertRecord[],
  ctx: {
    storePath: string
    source: string
    sourceId?: string
    preferNoticeId?: string
    preferReceivedAt?: string
  },
): IngestGkiNoticeResult {
  const items = readStore(ctx.storePath)
  const now = new Date().toISOString()
  const parentSourceId = ctx.preferNoticeId || ctx.sourceId || ''
  const rule = extractAlertRule(rawText)
  const taskKind = resolveGkiNoticeTaskKind({
    taskKind: asTrimmedString(input.taskKind) || undefined,
    task_kind: asTrimmedString(input.task_kind) || undefined,
    notice_type: asTrimmedString(input.notice_type) || undefined,
    intent: asTrimmedString(input.intent) || undefined,
    text: rawText,
  })
  const notices: GkiExternalNotice[] = []
  let createdCount = 0
  let storeDirty = false

  if (parentSourceId) {
    const parentIdx = items.findIndex(item => (
      item.noticeId === parentSourceId && item.kind !== 'alert'
    ))
    if (parentIdx >= 0) {
      items.splice(parentIdx, 1)
      storeDirty = true
    }
  }

  for (const record of records) {
    const childSourceId = parentSourceId
      ? `${parentSourceId}#${alertRecordKey(record)}`
      : alertRecordKey(record)
    const existing = items.find(item => (
      item.noticeId === childSourceId
      || (item.source === ctx.source && item.sourceId === childSourceId)
    ))
    if (existing) {
      const nextProject = displayProject(record)
      if (nextProject && existing.projects !== nextProject) {
        existing.projects = nextProject
        existing.updatedAt = now
        storeDirty = true
      }
      notices.push(existing)
      continue
    }

    const projectLabel = displayProject(record) || record.platform
    const notice: GkiExternalNotice = {
      noticeId: childSourceId,
      status: 'pending',
      text: formatAlertNoticeText(record, rule),
      title: ['异常告警', record.platform, projectLabel].filter(Boolean).join(' · '),
      source: ctx.source,
      sourceId: childSourceId,
      parentSourceId: parentSourceId || undefined,
      fromTag: record.currentGkiVersion || undefined,
      taskKind,
      kind: 'alert',
      alertRule: rule || undefined,
      branches: record.branches || undefined,
      platform: record.platform || undefined,
      projects: displayProject(record) || undefined,
      currentGkiVersion: record.currentGkiVersion || undefined,
      kernelVersion: record.kernelVersion || undefined,
      socVendor: record.socVendor || undefined,
      startDate: record.startDate || undefined,
      dueDate: record.dueDate || undefined,
      payload: {
        ...input,
        alertRecord: record.raw,
        rawText,
      },
      receivedAt: ctx.preferReceivedAt || now,
      updatedAt: now,
    }
    items.unshift(notice)
    notices.push(notice)
    createdCount += 1
    storeDirty = true
  }

  if (storeDirty) {
    writeStore(ctx.storePath, items.slice(0, 500))
  }
  const first = notices[0]
  if (!first) {
    throw new Error('notice_text_required')
  }
  return {
    notice: first,
    created: createdCount > 0,
    notices,
    createdCount,
  }
}

function noticeAlertBlob(item: GkiExternalNotice): string {
  const payload = asRecord(item.payload)
  return [
    item.text,
    item.title,
    payload.text,
    payload.message,
    payload.rawText,
  ].map(value => asTrimmedString(value)).filter(Boolean).join('\n')
}

function isUnsplitAlertNotice(item: GkiExternalNotice): boolean {
  if (item.kind === 'alert') return false
  return parseGkiAlertRecords(noticeAlertBlob(item)).length > 0
}

/** 把收件箱里尚未拆开的异常告警整包，按 JSON 明细拆成多条。无新消息时刷新也能生效。 */
export function resplitStoredGkiAlertNotices(options?: { storePath?: string }): number {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  const items = readStore(storePath)
  let createdCount = 0
  for (const item of items) {
    if (!isUnsplitAlertNotice(item)) continue
    const blob = noticeAlertBlob(item)
    const result = ingestGkiUpgradeNotice(
      {
        ...asRecord(item.payload),
        source: item.source,
        sourceId: item.sourceId || item.noticeId,
        title: item.title,
        text: blob,
        notice_type: 'gki-patch',
      },
      {
        storePath,
        preferNoticeId: item.noticeId,
        preferReceivedAt: item.receivedAt,
      },
    )
    createdCount += result.createdCount
  }
  syncStoredAlertNoticeProjects({ storePath })
  return createdCount
}

function syncStoredAlertNoticeProjects(options: { storePath: string }) {
  const items = readStore(options.storePath)
  const now = new Date().toISOString()
  let dirty = false
  for (const item of items) {
    if (item.kind !== 'alert') continue
    const record = parseGkiAlertRecord(asRecord(item.payload).alertRecord)
    const nextProject = record ? displayProject(record) : ''
    if (!nextProject || item.projects === nextProject) continue
    item.projects = nextProject
    item.updatedAt = now
    dirty = true
  }
  if (dirty) writeStore(options.storePath, items)
}

export function listGkiUpgradeNotices(
  filter?: { status?: GkiExternalNoticeStatus | 'all' },
  options?: { storePath?: string },
): GkiExternalNotice[] {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  resplitStoredGkiAlertNotices({ storePath })
  const items = readStore(storePath)
  const status = filter?.status || 'pending'
  if (status === 'all') return items
  return items.filter(item => item.status === status)
}

export function updateGkiUpgradeNoticeStatus(
  noticeId: string,
  status: 'applied' | 'dismissed' | 'pending',
  options?: { storePath?: string; reason?: string },
): GkiExternalNotice {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  const items = readStore(storePath)
  const index = items.findIndex(item => item.noticeId === noticeId)
  if (index < 0) throw new Error('notice_not_found')

  const current = items[index]
  if (status === 'pending' && current.status !== 'dismissed') {
    throw new Error('restore_only_dismissed')
  }

  const reason = asTrimmedString(options?.reason)
  if (status === 'dismissed' && !reason) {
    throw new Error('dismiss_reason_required')
  }

  const now = new Date().toISOString()
  const next: GkiExternalNotice = {
    ...current,
    status,
    updatedAt: now,
    appliedAt: status === 'applied' ? now : current.appliedAt,
    dismissedAt: status === 'dismissed' ? now : undefined,
    dismissReason: status === 'dismissed' ? reason : undefined,
  }
  items[index] = next
  writeStore(storePath, items)
  return next
}

export function deleteGkiUpgradeNotice(
  noticeId: string,
  options?: { storePath?: string },
): { noticeId: string } {
  const storePath = options?.storePath || defaultGkiNoticesStorePath()
  const items = readStore(storePath)
  const index = items.findIndex(item => item.noticeId === noticeId)
  if (index < 0) throw new Error('notice_not_found')
  if (items[index].status === 'pending') {
    throw new Error('cannot_delete_pending')
  }
  items.splice(index, 1)
  writeStore(storePath, items)
  return { noticeId }
}
