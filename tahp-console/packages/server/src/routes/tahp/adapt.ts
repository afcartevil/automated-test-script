/**
 * TAHP AI 适配调试 REST 路由
 * 处理：Agent 自动适配、布局管理、配置保存
 */
import Router from '@koa/router'
import type { Context } from 'koa'
import { logger } from '../../services/logger'
import { safeFileStore } from '../../services/safe-file-store'
import { tahpPaths } from '../../services/tahp/paths'
import { join } from 'path'
import {
  startAdaptAgentRun,
  getAdaptAgentTask,
  readAdaptAgentReport,
  buildAdaptAgentPrompts,
  submitAdaptUserInput,
  continueAdaptAgentRun,
  respondAdaptApproval,
  completeAdaptAgentRun,
  cancelAdaptAgentRun,
  type AdaptAgentRunInput,
  type AdaptAgentFieldMeta,
} from '../../services/tahp/adapt-agent'
import {
  listAdaptDomainLayouts,
  getAdaptDomainLayout,
  saveAdaptDomainConfig,
  resetAdaptDomainLayout,
  pullPublishedAdaptLayouts,
  forcePushAdaptLayouts,
  submitAdaptDomainLayout,
  getAdaptDomainLayoutReview,
} from '../../services/tahp/adapt-layout/service'
import { AdaptLayoutCloudError } from '../../services/tahp/adapt-layout/cloud-backend'
import { DEFAULT_ADAPT_WORKSPACE, isAdaptWorkspaceId } from '../../services/tahp/adapt-layout/types'
import { isCentralConfigured } from '../../services/tahp/runtime-mode'
import { centralClient } from '../../services/tahp/sync/central-client'
import {
  pullOrReadLineLayouts,
} from '../../services/tahp/adapt-layout/line-cache'

export const tahpAdaptRoutes = new Router()

const CONFIG_PATH = join(tahpPaths.projectRoot, '.adapt-config', 'config.json')

interface AdaptConfig {
  domain: string
  projectCode: string
  soc: string
  kernelVersion: string
  preVendor?: string
  postVendor?: string
  formData: Record<string, any>
}

// POST /api/tahp/adapt/config/save — 保存配置
tahpAdaptRoutes.post('/api/tahp/adapt/config/save', async (ctx) => {
  try {
    const config = (ctx.request.body || {}) as AdaptConfig
    await safeFileStore.writeText(CONFIG_PATH, JSON.stringify(config, null, 2))
    ctx.body = { success: true, data: { success: true } }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[tahp-adapt-save-config] write failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

function parseFormFields(body: Record<string, unknown>): AdaptAgentFieldMeta[] | undefined {
  const raw = body.form_fields ?? body.formFields
  if (!Array.isArray(raw)) return undefined
  const fields: AdaptAgentFieldMeta[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const f = item as Record<string, unknown>
    const name = String(f.name || '').trim()
    const label = String(f.label || name).trim()
    if (!name) continue
    fields.push({ name, label, required: f.required === true })
  }
  return fields.length ? fields : undefined
}

function parseAdaptAgentRunBody(body: Record<string, unknown>): AdaptAgentRunInput | { error: string } {
  const domainId = String(body.domain_id || body.domainId || '').trim()
  const domainLabel = String(body.domain_label || body.domainLabel || domainId).trim()
  const module = String(body.module || 'telephony').trim()
  const relatedSkills = Array.isArray(body.related_skills)
    ? body.related_skills.map(s => String(s).trim()).filter(Boolean)
    : Array.isArray(body.relatedSkills)
      ? body.relatedSkills.map(s => String(s).trim()).filter(Boolean)
      : []
  const formData = (body.form_data || body.formData || {}) as Record<string, string>
  const userNotes = typeof body.user_notes === 'string' ? body.user_notes
    : typeof body.userNotes === 'string' ? body.userNotes : undefined
  const formFields = parseFormFields(body)
  const workspaceId = String(body.workspace_id || body.workspaceId || DEFAULT_ADAPT_WORKSPACE).trim()
  const interactionMode = body.interaction_mode === true || body.interactionMode === true

  if (!domainId) return { error: '缺少 domain_id' }
  if (!isAdaptWorkspaceId(workspaceId)) return { error: `无效的工作区: ${workspaceId}` }
  return { domainId, domainLabel, module, relatedSkills, formData, userNotes, formFields, workspaceId, interactionMode }
}

const DOMAIN_ID_RE = /^[a-zA-Z0-9_-]+$/
const WORKSPACE_ID_RE = /^[a-zA-Z0-9_-]+$/

function parseWorkspaceId(raw: string | undefined): string | null {
  const ws = String(raw || DEFAULT_ADAPT_WORKSPACE).trim()
  if (!WORKSPACE_ID_RE.test(ws)) return null
  if (!isAdaptWorkspaceId(ws)) return null
  return ws
}

async function handleListLayouts(ctx: Context, workspaceId: string) {
  try {
    const data = await listAdaptDomainLayouts(workspaceId)
    ctx.body = { success: true, data }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
}

tahpAdaptRoutes.get('/api/tahp/adapt/workspaces/:workspaceId/layouts', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  if (!workspaceId) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的工作区 ID' }
    return
  }
  await handleListLayouts(ctx, workspaceId)
})

tahpAdaptRoutes.get('/api/tahp/adapt/layouts', async (ctx) => {
  await handleListLayouts(ctx, DEFAULT_ADAPT_WORKSPACE)
})

tahpAdaptRoutes.get('/api/tahp/adapt/layouts/lines', async (ctx) => {
  const fetcher = isCentralConfigured()
    ? async () => {
        const data = await centralClient.fetchPublishedLineLayouts()
        return data
      }
    : undefined
  const result = await pullOrReadLineLayouts(fetcher)
  ctx.body = {
    success: true,
    data: {
      lines: result.cache?.lines ?? [],
      pulled: result.pulled,
      from_cache: !result.pulled,
      updated_at: result.cache?.updated_at,
      error: result.error,
    },
  }
})

async function handleGetDomainLayout(ctx: Context, workspaceId: string, domainId: string) {
  const record = await getAdaptDomainLayout(domainId, workspaceId)
  ctx.body = { success: true, data: record }
}

tahpAdaptRoutes.get('/api/tahp/adapt/workspaces/:workspaceId/layouts/:domainId', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  const domainId = ctx.params.domainId
  if (!workspaceId || !DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 workspaceId 或 domainId' }
    return
  }
  await handleGetDomainLayout(ctx, workspaceId, domainId)
})

tahpAdaptRoutes.get('/api/tahp/adapt/layouts/:domainId', async (ctx) => {
  const domainId = ctx.params.domainId
  if (!DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 domainId' }
    return
  }
  await handleGetDomainLayout(ctx, DEFAULT_ADAPT_WORKSPACE, domainId)
})

async function handleSaveDomainLayout(ctx: Context, workspaceId: string, domainId: string) {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  try {
    const result = await saveAdaptDomainConfig(domainId, {
      fields: body.fields,
      related_skills: body.related_skills ?? body.relatedSkills,
    }, workspaceId)
    ctx.body = { success: true, data: result }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
}

tahpAdaptRoutes.put('/api/tahp/adapt/workspaces/:workspaceId/layouts/:domainId', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  const domainId = ctx.params.domainId
  if (!workspaceId || !DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 workspaceId 或 domainId' }
    return
  }
  await handleSaveDomainLayout(ctx, workspaceId, domainId)
})

tahpAdaptRoutes.put('/api/tahp/adapt/layouts/:domainId', async (ctx) => {
  const domainId = ctx.params.domainId
  if (!DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 domainId' }
    return
  }
  await handleSaveDomainLayout(ctx, DEFAULT_ADAPT_WORKSPACE, domainId)
})

function respondLayoutError(ctx: Context, err: unknown, fallbackStatus = 400): void {
  if (err instanceof AdaptLayoutCloudError) {
    ctx.status = err.httpStatus || 502
    ctx.body = {
      success: false,
      error: err.message,
      data: { code: err.code, ...(err.details || {}) },
    }
    return
  }
  ctx.status = fallbackStatus
  ctx.body = { success: false, error: (err as Error).message }
}

async function handleResetDomainLayout(ctx: Context, workspaceId: string, domainId: string) {
  await resetAdaptDomainLayout(domainId, workspaceId)
  ctx.body = { success: true, data: { deleted: domainId } }
}

tahpAdaptRoutes.delete('/api/tahp/adapt/workspaces/:workspaceId/layouts/:domainId', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  const domainId = ctx.params.domainId
  if (!workspaceId || !DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 workspaceId 或 domainId' }
    return
  }
  await handleResetDomainLayout(ctx, workspaceId, domainId)
})

tahpAdaptRoutes.delete('/api/tahp/adapt/layouts/:domainId', async (ctx) => {
  const domainId = ctx.params.domainId
  if (!DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 domainId' }
    return
  }
  await handleResetDomainLayout(ctx, DEFAULT_ADAPT_WORKSPACE, domainId)
})

async function handleSubmitDomainLayout(ctx: Context, workspaceId: string, domainId: string) {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const comment = typeof body.comment === 'string' ? body.comment.trim() : undefined
  try {
    const data = await submitAdaptDomainLayout(domainId, workspaceId, comment)
    ctx.body = { success: true, data }
  } catch (err) {
    respondLayoutError(ctx, err, 400)
  }
}

tahpAdaptRoutes.post('/api/tahp/adapt/workspaces/:workspaceId/layouts/:domainId/submit', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  const domainId = ctx.params.domainId
  if (!workspaceId || !DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 workspaceId 或 domainId' }
    return
  }
  await handleSubmitDomainLayout(ctx, workspaceId, domainId)
})

async function handleGetDomainReview(ctx: Context, workspaceId: string, domainId: string) {
  try {
    const data = await getAdaptDomainLayoutReview(domainId, workspaceId)
    ctx.body = { success: true, data }
  } catch (err) {
    respondLayoutError(ctx, err, 500)
  }
}

tahpAdaptRoutes.get('/api/tahp/adapt/workspaces/:workspaceId/layouts/:domainId/review', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  const domainId = ctx.params.domainId
  if (!workspaceId || !DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 workspaceId 或 domainId' }
    return
  }
  await handleGetDomainReview(ctx, workspaceId, domainId)
})

tahpAdaptRoutes.post('/api/tahp/adapt/workspaces/:workspaceId/layouts/sync/pull', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  if (!workspaceId) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的工作区 ID' }
    return
  }
  const result = await pullPublishedAdaptLayouts(workspaceId, { force: true })
  ctx.body = { success: true, data: result }
})

tahpAdaptRoutes.post('/api/tahp/adapt/workspaces/:workspaceId/layouts/sync/push', async (ctx) => {
  const workspaceId = parseWorkspaceId(ctx.params.workspaceId)
  if (!workspaceId) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的工作区 ID' }
    return
  }
  const result = await forcePushAdaptLayouts(workspaceId)
  ctx.status = 410
  ctx.body = { success: false, error: result.cloud_error, data: result }
})

tahpAdaptRoutes.post('/api/tahp/adapt/layouts/sync/pull', async (ctx) => {
  const result = await pullPublishedAdaptLayouts(DEFAULT_ADAPT_WORKSPACE, { force: true })
  ctx.body = { success: true, data: result }
})

tahpAdaptRoutes.post('/api/tahp/adapt/layouts/sync/push', async (ctx) => {
  const result = await forcePushAdaptLayouts(DEFAULT_ADAPT_WORKSPACE)
  ctx.status = 410
  ctx.body = { success: false, error: result.cloud_error, data: result }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-prompt-preview', async (ctx) => {
  const parsed = parseAdaptAgentRunBody((ctx.request.body || {}) as Record<string, unknown>)
  if ('error' in parsed) {
    ctx.status = 400
    ctx.body = { success: false, error: parsed.error }
    return
  }
  if (!parsed.relatedSkills?.length) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少关联 Skill' }
    return
  }
  const prompts = buildAdaptAgentPrompts(parsed)
  ctx.body = {
    success: true,
    data: {
      system_prompt: prompts.systemPrompt,
      user_prompt: prompts.userPrompt,
      system_prompt_chars: prompts.systemPrompt.length,
      user_prompt_chars: prompts.userPrompt.length,
    },
  }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-run', async (ctx) => {
  const parsed = parseAdaptAgentRunBody((ctx.request.body || {}) as Record<string, unknown>)
  if ('error' in parsed) {
    ctx.status = 400
    ctx.body = { success: false, error: parsed.error }
    return
  }

  const result = startAdaptAgentRun(parsed)

  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }

  ctx.body = { success: true, data: { task_id: result.taskId, status: 'starting', mode: 'agent' } }
})

tahpAdaptRoutes.get('/api/tahp/adapt/agent-run/:taskId', async (ctx) => {
  const { taskId } = ctx.params
  const live = getAdaptAgentTask(taskId)
  const report = readAdaptAgentReport(taskId)
  if (!live && !report) {
    ctx.status = 404
    ctx.body = { success: false, error: '任务不存在' }
    return
  }
  ctx.body = { success: true, data: { live, report } }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-run/:taskId/user-input', async (ctx) => {
  const { taskId } = ctx.params
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const requestId = String(body.request_id || body.requestId || '').trim()
  const values = (body.values || {}) as Record<string, string>
  if (!requestId) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 request_id' }
    return
  }
  const result = await submitAdaptUserInput(taskId, requestId, values)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { request_id: requestId } }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-run/:taskId/continue', async (ctx) => {
  const { taskId } = ctx.params
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const message = String(body.message || '').trim()
  const result = await continueAdaptAgentRun(taskId, message)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { ok: true } }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-run/:taskId/complete', async (ctx) => {
  const { taskId } = ctx.params
  const result = await completeAdaptAgentRun(taskId)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { ok: true } }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-run/:taskId/cancel', async (ctx) => {
  const { taskId } = ctx.params
  const result = await cancelAdaptAgentRun(taskId)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { ok: true } }
})

tahpAdaptRoutes.post('/api/tahp/adapt/agent-run/:taskId/approval', async (ctx) => {
  const { taskId } = ctx.params
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const approvalId = String(body.approval_id || body.approvalId || '').trim()
  const choice = String(body.choice || 'once').trim()
  if (!approvalId) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 approval_id' }
    return
  }
  const result = await respondAdaptApproval(taskId, approvalId, choice)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { approval_id: approvalId, choice } }
})

tahpAdaptRoutes.get('/api/tahp/adapt/config/get', async (ctx) => {
  try {
    const content = await safeFileStore.readText(CONFIG_PATH)
    const config = JSON.parse(content) as AdaptConfig
    ctx.body = { success: true, data: config }
  } catch (err: any) {
    if (err?.code === 'ENOENT') {
      ctx.body = { success: true, data: null }
    } else {
      logger.warn({ err: (err as Error).message }, '[tahp-adapt-get-config] read failed')
      ctx.body = { success: true, data: null }
    }
  }
})

// ─── 适配前置（中心拉取，只读） ─────────────────────────────────────────

tahpAdaptRoutes.get('/api/tahp/adapt/prereqs/projects', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 503
    ctx.body = { success: false, error: '未配置中心连接（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN）' }
    return
  }
  try {
    const data = await centralClient.listAdaptPrereqProjects()
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[adapt-prereqs] list projects failed')
    ctx.status = 502
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptRoutes.get('/api/tahp/adapt/prereqs/resolve', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 503
    ctx.body = { success: false, error: '未配置中心连接（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN）' }
    return
  }
  const q = ctx.query as Record<string, string>
  const projectCode = String(q.project_code || '').trim()
  if (!projectCode) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 project_code' }
    return
  }
  try {
    const data = await centralClient.resolveAdaptPrereqs({
      project_code: projectCode,
      campaign_id: q.campaign_id?.trim() || undefined,
      workspace_id: q.workspace_id?.trim() || undefined,
      domain_id: q.domain_id?.trim() || undefined,
    })
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message, projectCode }, '[adapt-prereqs] resolve failed')
    ctx.status = 502
    ctx.body = { success: false, error: (err as Error).message }
  }
})
