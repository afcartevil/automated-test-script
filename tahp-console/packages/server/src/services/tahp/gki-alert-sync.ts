/**
 * Catch-up pull of Feishu「GKI升级管理」bitable rows where 异常告警=1
 * into the GKI external-notices inbox. Does not require EA to stay running.
 */
import fs from 'fs'
import path from 'path'
import { config as serverConfig, getTahpConsoleHome } from '../../config'
import { logger } from '../logger'
import {
  FEISHU_BITABLE_NOTICE_SOURCE,
  ingestFeishuBitableAlertNotice,
  listGkiNoticesForFeishuRecord,
  parseGkiAlertRecord,
  type GkiAlertRecord,
} from './gki-upgrade-notices'

export const DEFAULT_GKI_ALERT_BITABLE_URL =
  'https://transsioner.feishu.cn/wiki/JJglwZtIuiBXqbkARAPcSQesntc?table=tblV2q5qJffkFuPE&view=vewLOPzQfs'

const DEFAULT_OPEN_BASE = 'https://open.feishu.cn'
const ALERT_RULE_FIELDS = [
  'GKI升级告警',
  '专项未及时安排',
  '专项版本未按时发布',
  '测试验收未及时安排',
  '测试结果汇总未按时提供',
  '代码未按时入库',
] as const

export type GkiAlertSyncConfig = {
  enabled: boolean
  bitableUrl: string
  intervalSec: number
}

export type GkiAlertRecordState = {
  clearedAt?: string
  lastSeenAlerting: boolean
  activeSourceId?: string
}

export type GkiAlertSyncState = {
  lastSyncAt?: string
  lastError?: string | null
  lastCreatedCount?: number
  lastSkippedCount?: number
  lastFetchedCount?: number
  records: Record<string, GkiAlertRecordState>
}

export type GkiAlertSyncStatus = {
  config: GkiAlertSyncConfig
  state: GkiAlertSyncState
  feishuConfigured: boolean
  resolved?: {
    baseToken?: string
    tableId?: string
    viewId?: string
  }
}

export type GkiAlertSyncResult = {
  ok: boolean
  createdCount: number
  skippedCount: number
  fetchedCount: number
  error?: string
  lastSyncAt: string
  noticesCreated: string[]
}

type FeishuCreds = {
  appId: string
  appSecret: string
  openBase: string
}

type ResolvedBitable = {
  baseToken: string
  tableId: string
  viewId?: string
  wikiToken?: string
}

type FetchedAlertRow = {
  recordId: string
  record: GkiAlertRecord
  alertRule: string
}

function trim(value: unknown): string {
  return String(value ?? '').trim()
}

function alertSyncRoot(dataDir = serverConfig.dataDir) {
  return path.resolve(dataDir, 'gki-patch')
}

export function defaultAlertSyncConfigPath(dataDir = serverConfig.dataDir) {
  return path.resolve(alertSyncRoot(dataDir), 'alert-sync-config.json')
}

export function defaultAlertSyncStatePath(dataDir = serverConfig.dataDir) {
  return path.resolve(alertSyncRoot(dataDir), 'alert-sync-state.json')
}

function machineSettingsPath(): string {
  const override = process.env.GKI_USER_SETTINGS?.trim()
  if (override) return path.resolve(override)
  return path.resolve(getTahpConsoleHome(), 'gki-patch-settings.json')
}

function ensureParent(filePath: string) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
}

function readJsonFile<T>(filePath: string, fallback: T): T {
  if (!fs.existsSync(filePath)) return fallback
  try {
    const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
    return (raw && typeof raw === 'object' ? raw : fallback) as T
  } catch {
    return fallback
  }
}

function writeJsonFile(filePath: string, data: unknown) {
  ensureParent(filePath)
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, 'utf-8')
}

export function getDefaultGkiAlertSyncConfig(): GkiAlertSyncConfig {
  return {
    enabled: true,
    bitableUrl: DEFAULT_GKI_ALERT_BITABLE_URL,
    intervalSec: 1800,
  }
}

export function readGkiAlertSyncConfig(options?: { configPath?: string }): GkiAlertSyncConfig {
  const configPath = options?.configPath || defaultAlertSyncConfigPath()
  const defaults = getDefaultGkiAlertSyncConfig()
  const fromMachine = readJsonFile<Record<string, unknown>>(machineSettingsPath(), {})
  const alertFromMachine = (fromMachine.alert_sync && typeof fromMachine.alert_sync === 'object')
    ? fromMachine.alert_sync as Record<string, unknown>
    : {}
  const stored = readJsonFile<Partial<GkiAlertSyncConfig>>(configPath, {})
  const enabledRaw = alertFromMachine.enabled ?? stored.enabled
  const intervalRaw = alertFromMachine.interval_sec ?? alertFromMachine.intervalSec ?? stored.intervalSec
  return {
    enabled: enabledRaw === undefined ? defaults.enabled : Boolean(enabledRaw),
    bitableUrl: trim(
      alertFromMachine.bitable_url
      || alertFromMachine.bitableUrl
      || stored.bitableUrl,
    ) || defaults.bitableUrl,
    intervalSec: Math.max(60, Number(intervalRaw) || defaults.intervalSec),
  }
}

export function writeGkiAlertSyncConfig(
  patch: Partial<GkiAlertSyncConfig>,
  options?: { configPath?: string },
): GkiAlertSyncConfig {
  const configPath = options?.configPath || defaultAlertSyncConfigPath()
  const next = {
    ...readGkiAlertSyncConfig({ configPath }),
    ...patch,
  }
  next.bitableUrl = trim(next.bitableUrl) || DEFAULT_GKI_ALERT_BITABLE_URL
  next.intervalSec = Math.max(60, Number(next.intervalSec) || 1800)
  next.enabled = Boolean(next.enabled)
  writeJsonFile(configPath, next)

  // Mirror into machine settings so GKI Settings UI can share the same keys later.
  try {
    const machinePath = machineSettingsPath()
    const machine = readJsonFile<Record<string, unknown>>(machinePath, {})
    machine.alert_sync = {
      enabled: next.enabled,
      bitable_url: next.bitableUrl,
      interval_sec: next.intervalSec,
    }
    writeJsonFile(machinePath, machine)
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gki-alert-sync] mirror machine settings failed')
  }
  return next
}

export function readGkiAlertSyncState(options?: { statePath?: string }): GkiAlertSyncState {
  const statePath = options?.statePath || defaultAlertSyncStatePath()
  const raw = readJsonFile<Partial<GkiAlertSyncState>>(statePath, {})
  return {
    lastSyncAt: trim(raw.lastSyncAt) || undefined,
    lastError: raw.lastError === undefined ? null : (raw.lastError as string | null),
    lastCreatedCount: Number(raw.lastCreatedCount) || 0,
    lastSkippedCount: Number(raw.lastSkippedCount) || 0,
    lastFetchedCount: Number(raw.lastFetchedCount) || 0,
    records: (raw.records && typeof raw.records === 'object')
      ? raw.records as Record<string, GkiAlertRecordState>
      : {},
  }
}

function writeGkiAlertSyncState(state: GkiAlertSyncState, options?: { statePath?: string }) {
  writeJsonFile(options?.statePath || defaultAlertSyncStatePath(), state)
}

export function readFeishuAppCredentials(): FeishuCreds | null {
  const machine = readJsonFile<Record<string, unknown>>(machineSettingsPath(), {})
  const feishu = (machine.feishu && typeof machine.feishu === 'object')
    ? machine.feishu as Record<string, unknown>
    : {}
  const appId = trim(
    process.env.FEISHU_APP_ID
    || process.env.GKI_FEISHU_APP_ID
    || feishu.app_id
    || feishu.appId,
  )
  const appSecret = trim(
    process.env.FEISHU_APP_SECRET
    || process.env.GKI_FEISHU_APP_SECRET
    || feishu.app_secret
    || feishu.appSecret,
  )
  const openBase = trim(
    process.env.FEISHU_OPEN_BASE
    || feishu.open_base
    || feishu.openBase
    || DEFAULT_OPEN_BASE,
  ).replace(/\/+$/, '') || DEFAULT_OPEN_BASE
  if (!appId || !appSecret) return null
  return { appId, appSecret, openBase }
}

export function parseBitableUrl(url: string): ResolvedBitable | null {
  const raw = trim(url)
  if (!raw) return null
  try {
    const parsed = new URL(raw)
    const tableId = trim(parsed.searchParams.get('table') || '')
    const viewId = trim(parsed.searchParams.get('view') || '') || undefined
    const pathParts = parsed.pathname.split('/').filter(Boolean)
    const wikiIdx = pathParts.findIndex(part => part === 'wiki')
    const baseIdx = pathParts.findIndex(part => part === 'base')
    if (wikiIdx >= 0 && pathParts[wikiIdx + 1] && tableId) {
      return {
        baseToken: '',
        tableId,
        viewId,
        wikiToken: pathParts[wikiIdx + 1],
      }
    }
    if (baseIdx >= 0 && pathParts[baseIdx + 1] && tableId) {
      return {
        baseToken: pathParts[baseIdx + 1],
        tableId,
        viewId,
      }
    }
  } catch {
    return null
  }
  return null
}

let tokenCache: { appId: string; token: string; expireAt: number } | null = null

async function getTenantAccessToken(creds: FeishuCreds): Promise<string> {
  const now = Date.now()
  if (
    tokenCache
    && tokenCache.appId === creds.appId
    && tokenCache.token
    && tokenCache.expireAt > now + 60_000
  ) {
    return tokenCache.token
  }
  const resp = await fetch(`${creds.openBase}/open-apis/auth/v3/tenant_access_token/internal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app_id: creds.appId, app_secret: creds.appSecret }),
  })
  const data = await resp.json() as {
    code?: number
    msg?: string
    tenant_access_token?: string
    expire?: number
  }
  const token = trim(data.tenant_access_token)
  if (!token || (data.code !== undefined && data.code !== 0)) {
    throw new Error(data.msg || 'feishu_tenant_token_failed')
  }
  tokenCache = {
    appId: creds.appId,
    token,
    expireAt: now + Math.max(60, Number(data.expire) || 7200) * 1000,
  }
  return token
}

async function feishuGet<T>(creds: FeishuCreds, apiPath: string): Promise<T> {
  const token = await getTenantAccessToken(creds)
  const resp = await fetch(`${creds.openBase}${apiPath}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await resp.json() as { code?: number; msg?: string; data?: T }
  if (data.code !== undefined && data.code !== 0) {
    throw new Error(data.msg || `feishu_get_failed:${apiPath}`)
  }
  return (data.data || {}) as T
}

async function feishuPost<T>(creds: FeishuCreds, apiPath: string, body: unknown): Promise<T> {
  const token = await getTenantAccessToken(creds)
  const resp = await fetch(`${creds.openBase}${apiPath}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  const data = await resp.json() as { code?: number; msg?: string; data?: T }
  if (data.code !== undefined && data.code !== 0) {
    throw new Error(data.msg || `feishu_post_failed:${apiPath}`)
  }
  return (data.data || {}) as T
}

export async function resolveBitableCoordinates(
  url: string,
  creds: FeishuCreds,
): Promise<ResolvedBitable> {
  const parsed = parseBitableUrl(url)
  if (!parsed?.tableId) throw new Error('invalid_bitable_url')
  if (parsed.baseToken) return parsed
  if (!parsed.wikiToken) throw new Error('invalid_bitable_url')
  const node = await feishuGet<{ node?: { obj_token?: string; obj_type?: string } }>(
    creds,
    `/open-apis/wiki/v2/spaces/get_node?token=${encodeURIComponent(parsed.wikiToken)}`,
  )
  const baseToken = trim(node.node?.obj_token)
  if (!baseToken) throw new Error('wiki_node_missing_obj_token')
  return {
    baseToken,
    tableId: parsed.tableId,
    viewId: parsed.viewId,
    wikiToken: parsed.wikiToken,
  }
}

function cellToPlain(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim()
  }
  if (Array.isArray(value)) {
    return value.map(cellToPlain).filter(Boolean).join('\n').trim()
  }
  if (typeof value === 'object') {
    const rec = value as Record<string, unknown>
    if (rec.text != null) return cellToPlain(rec.text)
    if (rec.name != null) return cellToPlain(rec.name)
    if (rec.value != null) return cellToPlain(rec.value)
    if (Array.isArray(rec.users)) {
      return rec.users.map((u: any) => trim(u?.name || u?.en_name || u?.id)).filter(Boolean).join(', ')
    }
    // Do not stringify raw link record ids here — callers resolve them separately.
    if (Array.isArray(rec.link_record_ids)) return ''
  }
  return ''
}

/** Feishu link cells usually return ["recXXXX"] (or objects with record_id). */
export function extractLinkRecordIds(value: unknown): string[] {
  const out: string[] = []
  const push = (raw: unknown) => {
    const id = trim(raw)
    if (id.startsWith('rec')) out.push(id)
  }
  if (value == null) return out
  if (typeof value === 'string') {
    push(value)
    return out
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      if (typeof item === 'string' || typeof item === 'number') {
        push(item)
      } else if (item && typeof item === 'object') {
        const rec = item as Record<string, unknown>
        push(rec.record_id || rec.id || rec.link_record_id)
        if (Array.isArray(rec.link_record_ids)) {
          for (const id of rec.link_record_ids) push(id)
        }
      }
    }
    return [...new Set(out)]
  }
  if (typeof value === 'object') {
    const rec = value as Record<string, unknown>
    push(rec.record_id || rec.id)
    if (Array.isArray(rec.link_record_ids)) {
      for (const id of rec.link_record_ids) push(id)
    }
  }
  return [...new Set(out)]
}

export function looksLikeFeishuRecordId(value: string): boolean {
  return /^rec[A-Za-z0-9]+$/.test(trim(value))
}

/** Feishu datetime/date cells are usually unix seconds (or ms). Prefer Asia/Shanghai calendar day. */
export function formatFeishuDateCell(value: unknown): string {
  if (value == null || value === '') return ''
  if (typeof value === 'object' && !Array.isArray(value)) {
    const rec = value as Record<string, unknown>
    if (rec.value != null) return formatFeishuDateCell(rec.value)
    if (rec.text != null) return formatFeishuDateCell(rec.text)
  }
  if (Array.isArray(value)) {
    return value.map(formatFeishuDateCell).filter(Boolean)[0] || ''
  }
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return ''
    // Already a date / datetime string
    if (/^\d{4}[-/]\d{1,2}[-/]\d{1,2}/.test(text)) {
      return text.replace(/\//g, '-').slice(0, 10)
    }
    if (/^\d+$/.test(text)) return formatFeishuDateCell(Number(text))
    const parsed = Date.parse(text)
    if (!Number.isNaN(parsed)) return formatEpochMs(parsed)
    return text.slice(0, 10)
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    // seconds (~1e9) vs milliseconds (~1e12)
    const ms = value > 1e12 ? value : value > 1e9 ? value * 1000 : NaN
    if (!Number.isFinite(ms)) return String(value)
    return formatEpochMs(ms)
  }
  return ''
}

function formatEpochMs(ms: number): string {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date(ms))
  } catch {
    const d = new Date(ms)
    const y = d.getUTCFullYear()
    const m = String(d.getUTCMonth() + 1).padStart(2, '0')
    const day = String(d.getUTCDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }
}

function cellToNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'boolean') return value ? 1 : 0
  const plain = cellToPlain(value)
  if (!plain) return null
  if (plain === '是' || plain.toLowerCase() === 'true') return 1
  if (plain === '否' || plain.toLowerCase() === 'false') return 0
  const n = Number(plain)
  return Number.isFinite(n) ? n : null
}

function splitPlatformProjects(combined: string): { platform: string; projects: string } {
  const text = trim(combined)
  if (!text) return { platform: '', projects: '' }
  const colon = text.indexOf(':')
  if (colon < 0) return { platform: text, projects: '' }
  const platform = trim(text.slice(0, colon))
  let projects = trim(text.slice(colon + 1))
  const m = projects.match(/^\[(.*)\]$/)
  if (m) projects = trim(m[1])
  return { platform, projects }
}

function pickField(fields: Record<string, unknown>, ...names: string[]): unknown {
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(fields, name) && fields[name] != null) {
      return fields[name]
    }
  }
  return undefined
}

export function mapFeishuFieldsToAlertRecord(
  fields: Record<string, unknown>,
  options?: { currentGkiVersionText?: string },
): GkiAlertRecord | null {
  const branches = cellToPlain(pickField(fields, '分支', 'branch', 'branches'))
  const platformProject = cellToPlain(pickField(fields, '平台|项目', '平台／项目'))
  const split = splitPlatformProjects(platformProject)
  const platform = cellToPlain(pickField(fields, '平台', 'platform')) || split.platform
  const projects = cellToPlain(pickField(fields, '项目', 'project', 'projects')) || split.projects
  const designatedProject = cellToPlain(pickField(fields, '指定项目', 'designatedProject'))
  const rawGki = pickField(fields, '当前GKI版本', 'currentGkiVersion', 'current_gki')
  let currentGkiVersion = trim(options?.currentGkiVersionText) || cellToPlain(rawGki)
  // Link field fallback: avoid showing raw rec* ids as the version tag.
  if (looksLikeFeishuRecordId(currentGkiVersion) || extractLinkRecordIds(rawGki).includes(currentGkiVersion)) {
    if (!trim(options?.currentGkiVersionText)) currentGkiVersion = ''
  }
  const kernelVersion = cellToPlain(pickField(fields, 'kernel版本', 'kernelVersion', 'kernel'))
  const socVendor = cellToPlain(pickField(fields, 'SOC厂商', 'socVendor', 'SOC'))
  const startDate = formatFeishuDateCell(pickField(fields, '启动日期', 'startDate'))
  const dueDate = formatFeishuDateCell(pickField(fields, '完成日期', 'dueDate', '完成日期'))

  const raw: Record<string, unknown> = {
    分支: branches,
    平台: platform,
    项目: projects,
    指定项目: designatedProject,
    当前GKI版本: currentGkiVersion,
    kernel版本: kernelVersion,
    SOC厂商: socVendor,
    启动日期: startDate,
    完成日期: dueDate,
  }
  return parseGkiAlertRecord(raw)
}

export function detectAlertRule(fields: Record<string, unknown>): string {
  const hits = ALERT_RULE_FIELDS.filter(name => {
    const n = cellToNumber(fields[name])
    return n === 1
  })
  return hits.join('、')
}

export function isAlertingFields(fields: Record<string, unknown>): boolean {
  const n = cellToNumber(pickField(fields, '异常告警'))
  if (n === 1) return true
  if (n === 0) return false
  // Fallback: any rule sub-field
  return ALERT_RULE_FIELDS.some(name => cellToNumber(fields[name]) === 1)
}

async function listTableFields(
  creds: FeishuCreds,
  baseToken: string,
  tableId: string,
): Promise<Array<Record<string, unknown>>> {
  const data = await feishuGet<{ items?: Array<Record<string, unknown>> }>(
    creds,
    `/open-apis/bitable/v1/apps/${encodeURIComponent(baseToken)}/tables/${encodeURIComponent(tableId)}/fields?page_size=100`,
  )
  return data.items || []
}

function findLinkTableId(
  fields: Array<Record<string, unknown>>,
  fieldName: string,
): string {
  const hit = fields.find(item => trim(item.field_name || item.name) === fieldName)
  if (!hit) return ''
  const property = (hit.property && typeof hit.property === 'object')
    ? hit.property as Record<string, unknown>
    : {}
  return trim(
    property.table_id
    || property.link_table_id
    || property.tableId
    || hit.table_id,
  )
}

function primaryTextFromLinkedFields(fields: Record<string, unknown>): string {
  const preferred = [
    'GKI版本',
    '版本',
    'Tag',
    'tag',
    '名称',
    '标题',
  ]
  for (const name of preferred) {
    const text = cellToPlain(fields[name])
    if (text && !looksLikeFeishuRecordId(text)) return text
  }
  for (const [key, value] of Object.entries(fields)) {
    if (/告警|时间|EOL|Boot|SPL/i.test(key)) continue
    const text = cellToPlain(value)
    if (text && !looksLikeFeishuRecordId(text) && /android\d+/i.test(text)) return text
  }
  for (const value of Object.values(fields)) {
    const text = cellToPlain(value)
    if (text && !looksLikeFeishuRecordId(text) && /android\d+/i.test(text)) return text
  }
  return ''
}

async function resolveLinkedRecordTexts(
  creds: FeishuCreds,
  baseToken: string,
  linkTableId: string,
  recordIds: string[],
): Promise<Map<string, string>> {
  const result = new Map<string, string>()
  const unique = [...new Set(recordIds.map(trim).filter(id => id.startsWith('rec')))]
  if (!linkTableId || unique.length === 0) return result

  const chunkSize = 50
  for (let i = 0; i < unique.length; i += chunkSize) {
    const chunk = unique.slice(i, i + chunkSize)
    try {
      const data = await feishuPost<{
        records?: Array<{ record_id?: string; fields?: Record<string, unknown> }>
        items?: Array<{ record_id?: string; fields?: Record<string, unknown> }>
      }>(
        creds,
        `/open-apis/bitable/v1/apps/${encodeURIComponent(baseToken)}/tables/${encodeURIComponent(linkTableId)}/records/batch_get`,
        { record_ids: chunk },
      )
      for (const item of data.records || data.items || []) {
        const id = trim(item.record_id)
        if (!id) continue
        const text = primaryTextFromLinkedFields(item.fields || {})
        if (text) result.set(id, text)
      }
    } catch (err) {
      // Fallback: fetch one-by-one if batch_get unavailable.
      logger.warn({ err: (err as Error).message, linkTableId }, '[gki-alert-sync] batch_get linked records failed; fallback get')
      for (const id of chunk) {
        try {
          const one = await feishuGet<{ record?: { record_id?: string; fields?: Record<string, unknown> } }>(
            creds,
            `/open-apis/bitable/v1/apps/${encodeURIComponent(baseToken)}/tables/${encodeURIComponent(linkTableId)}/records/${encodeURIComponent(id)}`,
          )
          const text = primaryTextFromLinkedFields(one.record?.fields || {})
          if (text) result.set(id, text)
        } catch {
          /* ignore single miss */
        }
      }
    }
  }
  return result
}

function resolveCurrentGkiVersionText(
  fields: Record<string, unknown>,
  linkedTexts: Map<string, string>,
): string {
  const raw = pickField(fields, '当前GKI版本', 'currentGkiVersion', 'current_gki')
  const ids = extractLinkRecordIds(raw)
  const fromLinks = ids.map(id => linkedTexts.get(id) || '').filter(Boolean)
  if (fromLinks.length) return fromLinks.join(' / ')
  const plain = cellToPlain(raw)
  if (plain && !looksLikeFeishuRecordId(plain)) return plain
  return ''
}

async function fetchAlertingRows(
  creds: FeishuCreds,
  coords: ResolvedBitable,
): Promise<FetchedAlertRow[]> {
  const rawItems: Array<{ recordId: string; fields: Record<string, unknown> }> = []
  let pageToken = ''
  for (let page = 0; page < 50; page += 1) {
    const body: Record<string, unknown> = {
      page_size: 100,
      automatic_fields: false,
    }
    if (coords.viewId) body.view_id = coords.viewId
    if (pageToken) body.page_token = pageToken
    // Prefer server-side filter; fall back to client filter if formula filter rejected.
    body.filter = {
      conjunction: 'and',
      conditions: [
        {
          field_name: '异常告警',
          operator: 'is',
          value: ['1'],
        },
      ],
    }

    let data: {
      items?: Array<{ record_id?: string; fields?: Record<string, unknown> }>
      has_more?: boolean
      page_token?: string
    }
    try {
      data = await feishuPost(
        creds,
        `/open-apis/bitable/v1/apps/${encodeURIComponent(coords.baseToken)}/tables/${encodeURIComponent(coords.tableId)}/records/search`,
        body,
      )
    } catch (err) {
      if (page === 0 && /filter|field|formula|条件/i.test((err as Error).message)) {
        const { filter: _drop, ...rest } = body
        data = await feishuPost(
          creds,
          `/open-apis/bitable/v1/apps/${encodeURIComponent(coords.baseToken)}/tables/${encodeURIComponent(coords.tableId)}/records/search`,
          rest,
        )
      } else {
        throw err
      }
    }

    for (const item of data.items || []) {
      const recordId = trim(item.record_id)
      const fields = item.fields || {}
      if (!recordId || !isAlertingFields(fields)) continue
      rawItems.push({ recordId, fields })
    }

    if (!data.has_more || !data.page_token) break
    pageToken = String(data.page_token)
  }

  let linkTableId = ''
  try {
    const tableFields = await listTableFields(creds, coords.baseToken, coords.tableId)
    linkTableId = findLinkTableId(tableFields, '当前GKI版本')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gki-alert-sync] list fields for link resolve failed')
  }
  // Known link table on GKI升级管理 base (fallback when field meta omits table id).
  if (!linkTableId) linkTableId = 'tblicAE8Tk5dbIts'

  const allLinkIds = rawItems.flatMap(item => (
    extractLinkRecordIds(pickField(item.fields, '当前GKI版本', 'currentGkiVersion', 'current_gki'))
  ))
  const linkedTexts = await resolveLinkedRecordTexts(
    creds,
    coords.baseToken,
    linkTableId,
    allLinkIds,
  )

  const rows: FetchedAlertRow[] = []
  for (const item of rawItems) {
    const currentGkiVersionText = resolveCurrentGkiVersionText(item.fields, linkedTexts)
    const record = mapFeishuFieldsToAlertRecord(item.fields, { currentGkiVersionText })
    if (!record) continue
    rows.push({
      recordId: item.recordId,
      record,
      alertRule: detectAlertRule(item.fields),
    })
  }
  return rows
}

function resolveActiveSourceId(
  recordId: string,
  state: GkiAlertRecordState | undefined,
  existingNotices: ReturnType<typeof listGkiNoticesForFeishuRecord>,
): { sourceId: string; shouldCreate: boolean; skipReason?: string } {
  const pending = existingNotices.find(item => item.status === 'pending')
  if (pending) {
    return {
      sourceId: trim(pending.sourceId || pending.noticeId) || recordId,
      shouldCreate: false,
      skipReason: 'exists:pending',
    }
  }

  const terminal = existingNotices.find(item => (
    item.status === 'applied' || item.status === 'dismissed'
  ))
  const generationSuffix = trim(state?.clearedAt)

  // Already handled and never cleared since → do not re-remind.
  if (terminal && !generationSuffix) {
    return {
      sourceId: trim(terminal.sourceId || terminal.noticeId) || recordId,
      shouldCreate: false,
      skipReason: `terminal:${terminal.status}`,
    }
  }

  if (generationSuffix) {
    const sourceId = `${recordId}#${generationSuffix}`
    const exists = existingNotices.find(item => (
      item.sourceId === sourceId || item.noticeId === sourceId
    ))
    if (exists) {
      return { sourceId, shouldCreate: false, skipReason: `exists:${exists.status}` }
    }
    return { sourceId, shouldCreate: true }
  }

  if (existingNotices.length === 0) {
    return { sourceId: recordId, shouldCreate: true }
  }

  const any = existingNotices[0]
  return {
    sourceId: trim(any?.sourceId || any?.noticeId) || recordId,
    shouldCreate: false,
    skipReason: 'exists:other',
  }
}

export function planAlertIngest(
  row: { recordId: string },
  state: GkiAlertRecordState | undefined,
  existingNotices: ReturnType<typeof listGkiNoticesForFeishuRecord>,
): { sourceId: string; shouldCreate: boolean; skipReason?: string } {
  return resolveActiveSourceId(row.recordId, state, existingNotices)
}

export async function getGkiAlertSyncStatus(options?: {
  configPath?: string
  statePath?: string
}): Promise<GkiAlertSyncStatus> {
  const config = readGkiAlertSyncConfig(options)
  const state = readGkiAlertSyncState(options)
  const creds = readFeishuAppCredentials()
  const parsed = parseBitableUrl(config.bitableUrl)
  return {
    config,
    state,
    feishuConfigured: Boolean(creds),
    resolved: parsed
      ? {
          baseToken: parsed.baseToken || undefined,
          tableId: parsed.tableId,
          viewId: parsed.viewId,
        }
      : undefined,
  }
}

export async function syncGkiAlertsFromBitable(options?: {
  configPath?: string
  statePath?: string
  storePath?: string
  force?: boolean
}): Promise<GkiAlertSyncResult> {
  const now = new Date().toISOString()
  const config = readGkiAlertSyncConfig(options)
  const state = readGkiAlertSyncState(options)

  if (!config.enabled && !options?.force) {
    const result: GkiAlertSyncResult = {
      ok: true,
      createdCount: 0,
      skippedCount: 0,
      fetchedCount: 0,
      lastSyncAt: now,
      noticesCreated: [],
      error: 'sync_disabled',
    }
    state.lastSyncAt = now
    state.lastError = 'sync_disabled'
    state.lastCreatedCount = 0
    state.lastSkippedCount = 0
    state.lastFetchedCount = 0
    writeGkiAlertSyncState(state, options)
    return result
  }

  const creds = readFeishuAppCredentials()
  if (!creds) {
    const result: GkiAlertSyncResult = {
      ok: false,
      createdCount: 0,
      skippedCount: 0,
      fetchedCount: 0,
      lastSyncAt: now,
      noticesCreated: [],
      error: 'feishu_not_configured',
    }
    state.lastSyncAt = now
    state.lastError = result.error
    writeGkiAlertSyncState(state, options)
    return result
  }

  try {
    const coords = await resolveBitableCoordinates(config.bitableUrl, creds)
    const rows = await fetchAlertingRows(creds, coords)
    const alertingIds = new Set(rows.map(row => row.recordId))

    // Mark cleared generations for records that stopped alerting.
    for (const [recordId, recState] of Object.entries(state.records)) {
      if (recState.lastSeenAlerting && !alertingIds.has(recordId)) {
        recState.lastSeenAlerting = false
        recState.clearedAt = now
        recState.activeSourceId = undefined
      }
    }

    let createdCount = 0
    let skippedCount = 0
    const noticesCreated: string[] = []

    for (const row of rows) {
      const prev = state.records[row.recordId] || { lastSeenAlerting: false }
      const existing = listGkiNoticesForFeishuRecord(row.recordId, { storePath: options?.storePath })
      const plan = planAlertIngest(row, prev, existing)

      if (!plan.shouldCreate) {
        // Still allow silent field refresh on exact sourceId.
        ingestFeishuBitableAlertNotice({
          sourceId: plan.sourceId,
          recordId: row.recordId,
          record: row.record,
          alertRule: row.alertRule,
        }, { storePath: options?.storePath })
        skippedCount += 1
        state.records[row.recordId] = {
          ...prev,
          lastSeenAlerting: true,
          activeSourceId: plan.sourceId,
          // Keep clearedAt so future re-open after another clear still works.
          clearedAt: prev.clearedAt,
        }
        continue
      }

      const ingested = ingestFeishuBitableAlertNotice({
        sourceId: plan.sourceId,
        recordId: row.recordId,
        record: row.record,
        alertRule: row.alertRule,
      }, { storePath: options?.storePath })

      if (ingested.created) {
        createdCount += 1
        noticesCreated.push(ingested.notice.noticeId)
      } else {
        skippedCount += 1
      }
      state.records[row.recordId] = {
        lastSeenAlerting: true,
        activeSourceId: plan.sourceId,
        // Generation watermark consumed once a notice exists for this open cycle.
        clearedAt: undefined,
      }
    }

    state.lastSyncAt = now
    state.lastError = null
    state.lastCreatedCount = createdCount
    state.lastSkippedCount = skippedCount
    state.lastFetchedCount = rows.length
    writeGkiAlertSyncState(state, options)

    logger.info(
      {
        createdCount,
        skippedCount,
        fetchedCount: rows.length,
        tableId: coords.tableId,
      },
      '[gki-alert-sync] sync done',
    )

    return {
      ok: true,
      createdCount,
      skippedCount,
      fetchedCount: rows.length,
      lastSyncAt: now,
      noticesCreated,
    }
  } catch (err) {
    const message = (err as Error).message || 'sync_failed'
    state.lastSyncAt = now
    state.lastError = message
    writeGkiAlertSyncState(state, options)
    logger.warn({ err: message }, '[gki-alert-sync] sync failed')
    return {
      ok: false,
      createdCount: 0,
      skippedCount: 0,
      fetchedCount: 0,
      lastSyncAt: now,
      noticesCreated: [],
      error: message,
    }
  }
}

/** Optional in-process timer while Console is alive (not a delivery requirement). */
let syncTimer: ReturnType<typeof setInterval> | null = null

export function startGkiAlertSyncTimer(): void {
  stopGkiAlertSyncTimer()
  const config = readGkiAlertSyncConfig()
  if (!config.enabled) return
  const ms = Math.max(60, config.intervalSec) * 1000
  syncTimer = setInterval(() => {
    void syncGkiAlertsFromBitable().catch(() => undefined)
  }, ms)
  if (typeof syncTimer.unref === 'function') syncTimer.unref()
}

export function stopGkiAlertSyncTimer(): void {
  if (syncTimer) {
    clearInterval(syncTimer)
    syncTimer = null
  }
}
