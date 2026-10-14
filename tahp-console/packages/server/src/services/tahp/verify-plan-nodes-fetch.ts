/**
 * 中心「任务中心 → 质量验测 → 定时任务 → 项目节点信息表」在线取数：
 * 收到中心 /task-notify 的 verify.plan.nodes.fetch 事件后，用 lark-cli（user 身份）读
 * 飞书《升级项目关键信息表》「项目信息」中「是否已完成升级=升级中」的项目，
 * 取 STR4 / STR4A / FR / STR5 节点日期（统一 yyyy/mm/dd），回传中心。
 * 契约对齐中心 easyadapter_bff services/task-center/project-nodes.ts。
 */
import { execFile } from 'child_process'
import { existsSync } from 'fs'
import { dirname, join } from 'path'
import { promisify } from 'util'
import { logger } from '../logger'
import { centralClient } from './sync/central-client'

const execFileAsync = promisify(execFile)

export const UPGRADE_INFO_URL = process.env.TAHP_UPGRADE_INFO_URL
  || 'https://transsioner.feishu.cn/wiki/MY1Ow3QDmiWBHFktmeocWbrUnfd?sheet=VvfD3p'
export const PROJECT_INFO_SHEET = '项目信息'
export const UPGRADING_STATUS = '升级中'
export const PROJECT_INFO_SOURCE = '升级项目关键信息表（飞书在线）'

const NAME_FIELD = '项目名称'
const STATUS_FIELD = '是否已完成升级'
/** 节点键 → 飞书表字段名（STR5 列名带空格） */
export const NODE_FIELD_MAP = { STR4: 'STR4', STR4A: 'STR4A', FR: 'FR', STR5: 'STR 5' } as const
export type PlanNodeKey = keyof typeof NODE_FIELD_MAP | 'STR6'

const LARK_TIMEOUT_MS = Number(process.env.TAHP_VERIFY_PLAN_NODES_TIMEOUT_MS || 60_000)

export interface UpgradingProjectNodes {
  name: string
  status: string
  nodes: Record<PlanNodeKey, string | null>
}

// ─── lark-cli 调用 ────────────────────────────────────────────────────────
// Windows 下 npm shim（lark-cli.cmd/.ps1）无法被 execFile 直接执行，
// 解析 shim 旁的全局包入口 scripts/run.js，用当前 node 直调；POSIX 回落 shim 本身。

interface LarkCliCmd { cmd: string; prefix: string[] }
let larkCliCmdCache: LarkCliCmd | null = null

async function resolveLarkCli(): Promise<LarkCliCmd> {
  if (larkCliCmdCache) return larkCliCmdCache
  const { stdout } = await execFileAsync(process.platform === 'win32' ? 'where.exe' : 'which', ['lark-cli'], {
    timeout: 3000,
    windowsHide: true,
  })
  const first = stdout.split(/\r?\n/).map(s => s.trim()).find(Boolean)
  if (!first) throw new Error('lark-cli 不在 PATH 中')
  const runJs = join(dirname(first), 'node_modules', '@larksuite', 'cli', 'scripts', 'run.js')
  if (existsSync(runJs)) {
    larkCliCmdCache = { cmd: process.execPath, prefix: [runJs] }
    return larkCliCmdCache
  }
  if (process.platform !== 'win32') {
    larkCliCmdCache = { cmd: first, prefix: [] }
    return larkCliCmdCache
  }
  throw new Error(`无法定位 lark-cli 入口（${first}）`)
}

async function runLarkCli(args: string[]): Promise<Record<string, unknown>> {
  const cli = await resolveLarkCli()
  const { stdout } = await execFileAsync(cli.cmd, [...cli.prefix, ...args, '--format', 'json'], {
    timeout: LARK_TIMEOUT_MS,
    windowsHide: true,
    maxBuffer: 16 * 1024 * 1024,
  })
  const payload = JSON.parse(stdout) as { ok?: boolean; error?: { message?: string } }
  if (payload.ok === false) throw new Error(payload.error?.message || 'lark-cli 返回失败')
  return payload as Record<string, unknown>
}

// ─── 飞书表读取 ──────────────────────────────────────────────────────────

interface BitableRef { appToken: string; tableId: string }

async function resolveProjectInfoBitable(): Promise<BitableRef> {
  const payload = await runLarkCli(['sheets', '+workbook-info', '--url', UPGRADE_INFO_URL, '--as', 'user'])
  const data = payload.data as { sheets?: Array<Record<string, unknown>> } | undefined
  const sheets = Array.isArray(data?.sheets) ? data.sheets : []
  let wantedSheetId = ''
  try { wantedSheetId = new URL(UPGRADE_INFO_URL).searchParams.get('sheet') || '' } catch { /* 忽略非法 URL */ }
  const sheet = sheets.find(s => s.resource_type === 'bitable' && wantedSheetId && s.sheet_id === wantedSheetId)
    || sheets.find(s => s.resource_type === 'bitable' && s.sheet_name === PROJECT_INFO_SHEET)
  const appToken = String(sheet?.bitable_app_token || '').trim()
  const tableId = String(sheet?.bitable_table_id || '').trim()
  if (!appToken || !tableId) throw new Error(`未在在线表中找到「${PROJECT_INFO_SHEET}」bitable 页`)
  return { appToken, tableId }
}

async function listUpgradingRows(ref: BitableRef): Promise<{ rows: unknown[][]; fields: string[] }> {
  const fields = [NAME_FIELD, ...Object.values(NODE_FIELD_MAP)]
  const filterJson = JSON.stringify({ logic: 'and', conditions: [[STATUS_FIELD, '==', UPGRADING_STATUS]] })
  const rows: unknown[][] = []
  let fieldNames: string[] = []
  let offset = 0
  for (;;) {
    const payload = await runLarkCli([
      'base', '+record-list',
      '--base-token', ref.appToken, '--table-id', ref.tableId, '--as', 'user',
      ...fields.flatMap(f => ['--field-id', f]),
      '--filter-json', filterJson,
      '--limit', '200', '--offset', String(offset),
    ])
    const data = payload.data as { data?: unknown[][]; fields?: string[]; has_more?: boolean } | undefined
    const batch = Array.isArray(data?.data) ? data.data : []
    rows.push(...batch)
    if (Array.isArray(data?.fields) && data.fields.length) fieldNames = data.fields
    if (!data?.has_more || !batch.length) break
    offset += batch.length
  }
  return { rows, fields: fieldNames }
}

// ─── 值映射（纯函数，供单测） ─────────────────────────────────────────────

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** 节点日期归一化为 yyyy/mm/dd；空值/NA → null */
export function parseNodeDate(value: unknown): string | null {
  if (value == null || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    // 飞书 datetime 字段原始毫秒值：按 UTC+8 取日
    const d = new Date(value + 8 * 3600 * 1000)
    return `${d.getUTCFullYear()}/${pad2(d.getUTCMonth() + 1)}/${pad2(d.getUTCDate())}`
  }
  const text = String(value).trim()
  if (!text || /^(NA|N\/A|-|—)$/i.test(text)) return null
  // ISO datetime（2026-11-16T00:00:00.000+08:00）或 yyyy/m/d、yyyy-m-d：直接取日期部分
  const ymd = text.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (ymd) return `${ymd[1]}/${pad2(Number(ymd[2]))}/${pad2(Number(ymd[3]))}`
  // 兼容美式短日期等（9/20/26）
  const parsed = new Date(text)
  if (!Number.isNaN(parsed.getTime())) {
    return `${parsed.getFullYear()}/${pad2(parsed.getMonth() + 1)}/${pad2(parsed.getDate())}`
  }
  return null
}

/** record-list 返回的列对齐行数组 → 回传契约（STR6 恒 null，仅兼容中心类型） */
export function mapBitableRows(rows: unknown[][], fields: string[]): UpgradingProjectNodes[] {
  const nameIdx = fields.indexOf(NAME_FIELD)
  const projects: UpgradingProjectNodes[] = []
  for (const row of rows) {
    if (!Array.isArray(row)) continue
    const name = String(nameIdx >= 0 ? row[nameIdx] ?? '' : '').trim()
    if (!name) continue
    const nodes: Record<PlanNodeKey, string | null> = { STR4: null, STR4A: null, FR: null, STR5: null, STR6: null }
    for (const [key, field] of Object.entries(NODE_FIELD_MAP)) {
      const idx = fields.indexOf(field)
      nodes[key as PlanNodeKey] = idx >= 0 ? parseNodeDate(row[idx]) : null
    }
    projects.push({ name, status: UPGRADING_STATUS, nodes })
  }
  return projects
}

// ─── 编排 ────────────────────────────────────────────────────────────────

export async function fetchUpgradingProjects(): Promise<{ sourceName: string; projects: UpgradingProjectNodes[] }> {
  const ref = await resolveProjectInfoBitable()
  const { rows, fields } = await listUpgradingRows(ref)
  return { sourceName: PROJECT_INFO_SOURCE, projects: mapBitableRows(rows, fields) }
}

let inflight = false

/** 处理中心取数请求：成功回传 projects，失败回传 error（不抛出，调用方 fire-and-forget） */
export async function handleVerifyPlanNodesFetch(payload: { request_id?: string } = {}): Promise<void> {
  const requestId = String(payload?.request_id || '').trim()
  if (!requestId) return
  if (inflight) {
    logger.info({ requestId }, '[verify-plan-nodes] fetch already in flight, skip')
    return
  }
  inflight = true
  try {
    const { sourceName, projects } = await fetchUpgradingProjects()
    await centralClient.reportVerifyPlanNodes({ request_id: requestId, source_name: sourceName, projects })
    logger.info({ requestId, projects: projects.length }, '[verify-plan-nodes] reported upgrading projects')
  } catch (err) {
    const message = ((err as Error).message || '取数失败').slice(0, 300)
    logger.warn({ requestId, err: message }, '[verify-plan-nodes] fetch failed')
    try {
      await centralClient.reportVerifyPlanNodes({ request_id: requestId, error: message })
    } catch (reportErr) {
      logger.warn({ requestId, err: (reportErr as Error).message }, '[verify-plan-nodes] error report failed')
    }
  } finally {
    inflight = false
  }
}
