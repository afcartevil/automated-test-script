/**
 * TAHP AI 适配调试 REST 路由
 * 处理：Agent 自动适配、布局管理、配置保存
 */
import Router from '@koa/router'
import { logger } from '../../services/logger'
import { safeFileStore } from '../../services/safe-file-store'
import { tahpPaths } from '../../services/tahp/paths'
import { join } from 'path'
import {
  startAdaptAgentRun,
  getAdaptAgentTask,
  readAdaptAgentReport,
  buildAdaptAgentPrompts,
  type AdaptAgentRunInput,
  type AdaptAgentFieldMeta,
} from '../../services/tahp/adapt-agent'
import {
  listAdaptDomainLayouts,
  getAdaptDomainLayout,
  saveAdaptDomainConfig,
  resetAdaptDomainLayout,
  pullAndMergeAdaptLayouts,
  forcePushAdaptLayouts,
} from '../../services/tahp/adapt-layout/service'

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

  if (!domainId) return { error: '缺少 domain_id' }
  return { domainId, domainLabel, module, relatedSkills, formData, userNotes, formFields }
}

const DOMAIN_ID_RE = /^[a-zA-Z0-9_-]+$/

tahpAdaptRoutes.get('/api/tahp/adapt/layouts', async (ctx) => {
  try {
    const data = await listAdaptDomainLayouts()
    ctx.body = { success: true, data }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptRoutes.get('/api/tahp/adapt/layouts/:domainId', async (ctx) => {
  const domainId = ctx.params.domainId
  if (!DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 domainId' }
    return
  }
  const record = await getAdaptDomainLayout(domainId)
  ctx.body = { success: true, data: record }
})

tahpAdaptRoutes.put('/api/tahp/adapt/layouts/:domainId', async (ctx) => {
  const domainId = ctx.params.domainId
  if (!DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 domainId' }
    return
  }
  const body = (ctx.request.body || {}) as Record<string, unknown>
  try {
    const result = await saveAdaptDomainConfig(domainId, {
      fields: body.fields,
      related_skills: body.related_skills ?? body.relatedSkills,
    })
    ctx.body = { success: true, data: result }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptRoutes.delete('/api/tahp/adapt/layouts/:domainId', async (ctx) => {
  const domainId = ctx.params.domainId
  if (!DOMAIN_ID_RE.test(domainId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '无效的 domainId' }
    return
  }
  await resetAdaptDomainLayout(domainId)
  ctx.body = { success: true, data: { deleted: domainId } }
})

tahpAdaptRoutes.post('/api/tahp/adapt/layouts/sync/pull', async (ctx) => {
  const result = await pullAndMergeAdaptLayouts()
  ctx.body = { success: true, data: result }
})

tahpAdaptRoutes.post('/api/tahp/adapt/layouts/sync/push', async (ctx) => {
  const result = await forcePushAdaptLayouts()
  if (!result.cloud_pushed && result.cloud_error) {
    ctx.status = 502
    ctx.body = { success: false, error: result.cloud_error, data: result }
    return
  }
  ctx.body = { success: true, data: result }
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
