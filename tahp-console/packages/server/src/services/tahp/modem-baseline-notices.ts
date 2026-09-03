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

export type ModemPlatformTaskStatus = 'pending' | 'in_progress' | 'done' | 'failed' | 'skipped'

export type ModemPlatformTask = {
  platform: string
  status: ModemPlatformTaskStatus
  runId?: string
  updatedAt?: string
}

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
  /** AP 分支拆解出的 modem 平台任务（命中静态映射表时初始化） */
  platformTasks?: ModemPlatformTask[]
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
  /** AP 分支→平台 映射表路径（测试注入） */
  apTrunkMapPath?: string
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

// ---- AP 分支 → modem 平台 静态映射 ----

export type ApTrunkPlatformMapping = {
  trunk: string
  /** 该 AP trunk 对应需升级的全部 modem 平台（外部基线升级一律走主干，不区分 tosVersion） */
  platforms: string[]
}

export type ApTrunkPlatformMapFile = {
  mappings?: ApTrunkPlatformMapping[]
}

function apTrunkPlatformMapCandidates() {
  const envOverride = process.env.MODEM_BASELINE_TOOL_ROOT?.trim()
  const candidates = [
    envOverride ? path.resolve(envOverride) : '',
    path.resolve(process.cwd(), '..', 'tools', 'modem-patch-tool'),
    path.resolve(process.cwd(), 'tools', 'modem-patch-tool'),
  ].filter(Boolean)
  return Array.from(new Set(candidates))
}

export function defaultApTrunkPlatformMapPath() {
  const candidates = apTrunkPlatformMapCandidates()
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return path.resolve(candidate, 'config', 'ap-trunk-platforms.json')
  }
  return path.resolve(candidates[0] ?? path.resolve(process.cwd(), '..', 'tools', 'modem-patch-tool'), 'config', 'ap-trunk-platforms.json')
}

let apTrunkMapCache: { path: string; mtime: number; data: ApTrunkPlatformMapFile } | null = null

/**
 * 读取 AP 分支 → modem 平台 静态映射表。
 * 文件不存在或为空时返回空 platforms（调用方按无平台任务处理，兼容旧流程）。
 */
export function resolveApTrunkPlatforms(
  trunk: string,
  options?: { mapPath?: string },
): { platforms: string[] } {
  const mapPath = options?.mapPath || defaultApTrunkPlatformMapPath()
  if (!fs.existsSync(mapPath)) return { platforms: [] }
  try {
    const stat = fs.statSync(mapPath)
    const mtime = stat.mtimeMs
    if (apTrunkMapCache && apTrunkMapCache.path === mapPath && apTrunkMapCache.mtime === mtime) {
      const hit = (apTrunkMapCache.data.mappings || []).find(item => item.trunk === trunk)
      return hit ? { platforms: [...hit.platforms] } : { platforms: [] }
    }
    const raw = JSON.parse(fs.readFileSync(mapPath, 'utf-8')) as ApTrunkPlatformMapFile
    apTrunkMapCache = { path: mapPath, mtime, data: raw }
    const hit = (raw.mappings || []).find(item => item.trunk === trunk)
    return hit ? { platforms: [...hit.platforms] } : { platforms: [] }
  } catch {
    return { platforms: [] }
  }
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
  const resolved = manifests.trunk
    ? resolveApTrunkPlatforms(manifests.trunk, { mapPath: options?.apTrunkMapPath })
    : { platforms: [] as string[] }
  const platformTasks = resolved.platforms.length
    ? resolved.platforms.map(platform => ({ platform, status: 'pending' as const, updatedAt: now }))
    : undefined
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
    platformTasks,
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

/**
 * 更新某条通知下指定 modem 平台任务的状态（run 完成回写 / UI 手动 skip/重置）。
 */
export function updateModemBaselineNoticePlatformTask(
  noticeId: string,
  platform: string,
  patch: { status: ModemPlatformTaskStatus; runId?: string },
  options?: { storePath?: string },
): ModemExternalNotice {
  const storePath = options?.storePath || defaultNoticesStorePath()
  const items = readStore(storePath)
  const index = items.findIndex(item => item.noticeId === noticeId)
  if (index < 0) throw new Error('notice_not_found')

  const current = items[index]
  const tasks = Array.isArray(current.platformTasks) ? [...current.platformTasks] : []
  const taskIndex = tasks.findIndex(item => item.platform === platform)
  if (taskIndex < 0) throw new Error('platform_task_not_found')

  const now = new Date().toISOString()
  tasks[taskIndex] = {
    ...tasks[taskIndex],
    status: patch.status,
    runId: patch.runId ?? tasks[taskIndex].runId,
    updatedAt: now,
  }
  const next: ModemExternalNotice = { ...current, platformTasks: tasks, updatedAt: now }
  items[index] = next
  writeStore(storePath, items)
  return next
}

/** 判断通知是否所有平台任务均已完结（done/skipped）。无 platformTasks 视为已就绪。 */
export function isModemNoticePlatformTasksComplete(notice: ModemExternalNotice): boolean {
  if (!notice.platformTasks || !notice.platformTasks.length) return true
  return notice.platformTasks.every(item => item.status === 'done' || item.status === 'skipped')
}
