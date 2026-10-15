/**
 * 效能看板：把已钉住项目的 session 用量上报到服务中心。
 * 没有 task-context 的闲聊不上报。失败只记日志，不打断聊天。
 */
import { mkdirSync, readFileSync, writeFileSync } from 'fs'
import { hostname } from 'os'
import { dirname, join } from 'path'
import { config } from '../../config'
import { readSessionUsageRow } from '../../db/hermes/sessions-db'
import { getSession } from '../../db/hermes/session-store'
import { sumSessionUsage } from '../../db/hermes/usage-store'
import { logger } from '../logger'
import { readCentralUserSession } from './central-user-session'
import { readJiraUsername } from './jira-user-config'
import { getTaskContext } from './task-context'
import { getLocalActor, isCentralConfigured } from './runtime-mode'
import { centralClient, type EfficiencySessionPayload } from './sync/central-client'

const PENDING_LIMIT = 200

function pendingPath(): string {
  return join(config.dataDir, 'efficiency-usage-pending.json')
}

function loadPending(): EfficiencySessionPayload[] {
  try {
    const parsed = JSON.parse(readFileSync(pendingPath(), 'utf8')) as { items?: EfficiencySessionPayload[] }
    return Array.isArray(parsed.items) ? parsed.items : []
  } catch {
    return []
  }
}

function savePending(items: EfficiencySessionPayload[]): void {
  const path = pendingPath()
  mkdirSync(dirname(path), { recursive: true })
  const trimmed = items.slice(-PENDING_LIMIT)
  writeFileSync(path, JSON.stringify({ items: trimmed }, null, 2) + '\n', 'utf8')
}

function upsertPending(items: EfficiencySessionPayload[], item: EfficiencySessionPayload): EfficiencySessionPayload[] {
  const key = item.client_id + '\t' + item.session_id
  const rest = items.filter(row => row.client_id + '\t' + row.session_id !== key)
  rest.push(item)
  return rest
}

/** 与质量报告执行人同一来源：Jira 用户名，才能对上账户管理里的显示名。 */
function efficiencyActor(): string {
  return readJiraUsername()
    || process.env.TAHP_JIRA_USERNAME?.trim()
    || process.env.JIRA_USERNAME?.trim()
    || readCentralUserSession()?.username
    || getLocalActor()
}

function toIso(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return new Date().toISOString()
  const ms = value > 1e12 ? value : value * 1000
  return new Date(ms).toISOString()
}

async function buildPayload(sessionId: string, projectCode: string, profile?: string): Promise<EfficiencySessionPayload | null> {
  const usage = sumSessionUsage(sessionId)
  const hermes = await readSessionUsageRow(sessionId, profile).catch(() => null)
  const local = getSession(sessionId)
  const tokens = hermes && (hermes.input_tokens + hermes.output_tokens) > 0 ? hermes : null
  const input = tokens?.input_tokens ?? usage?.input_tokens ?? 0
  const output = tokens?.output_tokens ?? usage?.output_tokens ?? 0
  const cacheRead = tokens?.cache_read_tokens ?? usage?.cache_read_tokens ?? 0
  const cacheWrite = tokens?.cache_write_tokens ?? usage?.cache_write_tokens ?? 0
  const reasoning = tokens?.reasoning_tokens ?? usage?.reasoning_tokens ?? 0
  if (input + output + cacheRead + cacheWrite + reasoning <= 0) return null
  const started = hermes?.started_at || local?.started_at || usage?.created_at || 0
  return {
    client_id: hostname() || 'unknown-host',
    session_id: sessionId,
    actor: efficiencyActor(),
    project_code: projectCode,
    model: hermes?.model || local?.model || usage?.model || '',
    provider: hermes?.provider || local?.provider || local?.billing_provider || '',
    input_tokens: input,
    output_tokens: output,
    cache_read_tokens: cacheRead,
    cache_write_tokens: cacheWrite,
    reasoning_tokens: reasoning,
    estimated_cost_usd: hermes?.estimated_cost_usd ?? local?.estimated_cost_usd ?? 0,
    actual_cost_usd: hermes?.actual_cost_usd ?? local?.actual_cost_usd ?? null,
    started_at: toIso(started),
  }
}

async function sendOne(item: EfficiencySessionPayload): Promise<boolean> {
  try {
    await centralClient.uploadEfficiencySession(item)
    return true
  } catch (err) {
    logger.warn({ err: (err as Error).message, session_id: item.session_id }, '[efficiency-usage] upload failed')
    return false
  }
}

async function deliver(payload: EfficiencySessionPayload): Promise<void> {
  const pending = loadPending()
  if (!isCentralConfigured()) {
    savePending(upsertPending(pending, payload))
    return
  }
  const queue = upsertPending(pending, payload)
  const left: EfficiencySessionPayload[] = []
  for (const item of queue) {
    const ok = await sendOne(item)
    if (!ok) left.push(item)
  }
  savePending(left)
}

/** 用量已写入本地库之后调用。无项目上下文则直接返回。 */
export async function reportSessionUsage(sessionId: string): Promise<void> {
  try {
    const id = String(sessionId || '').trim()
    if (!id) return
    const ctx = getTaskContext()
    if (!ctx?.project_code) return
    const payload = await buildPayload(id, ctx.project_code)
    if (!payload) return
    await deliver(payload)
  } catch (err) {
    logger.warn({ err: (err as Error).message, sessionId }, '[efficiency-usage] report skipped')
  }
}

/**
 * 适配流水线 AI 适配 Agent 结束一轮对话后上报。
 * 项目来自该次运行的 project_code，不读 task-context。同一 session 重复上报覆盖。
 * Hermes 把用量写入 default 档案的 state.db，与 Agent chat 使用的档案一致。
 */
export async function reportProjectSessionUsage(sessionId: string, projectCode: string, profile = 'default'): Promise<void> {
  try {
    const id = String(sessionId || '').trim()
    const code = String(projectCode || '').trim()
    if (!id || !code) return
    let payload = await buildPayload(id, code, profile)
    if (!payload) {
      await new Promise(resolve => setTimeout(resolve, 600))
      payload = await buildPayload(id, code, profile)
    }
    if (!payload) {
      logger.warn({ sessionId: id, projectCode: code }, '[efficiency-usage] pipeline session has no tokens')
      return
    }
    await deliver(payload)
  } catch (err) {
    logger.warn({ err: (err as Error).message, sessionId, projectCode }, '[efficiency-usage] pipeline report skipped')
  }
}
