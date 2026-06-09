/**
 * TAHP AI 适配调试 REST 路由
 * 处理：启动适配任务、查询状态、保存/获取配置
 */
import Router from '@koa/router'
import type { Context } from 'koa'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'
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

// 配置存储文件路径
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

interface ToolCallResult {
  content?: Array<{ type: string; text?: string }>
  isError?: boolean
}

function unwrapToolResult(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r || !Array.isArray(r.content)) return raw
  const first = r.content[0]
  if (!first || first.type !== 'text') return r
  try {
    return JSON.parse(first.text || '')
  } catch {
    return { text: first.text }
  }
}

// POST /api/tahp/adapt/launch — 启动适配任务
tahpAdaptRoutes.post('/api/tahp/adapt/launch', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as AdaptConfig
    const { domain, projectCode, soc, kernelVersion, formData } = body

    if (!domain || !projectCode || !soc) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少必填: domain / projectCode / soc' }
      return
    }

    // 构建 AI 适配任务描述
    const taskDesc = `
AI 适配调试 - ${domain}
项目: ${projectCode}
SoC: ${soc}
Kernel: ${kernelVersion}
前置条件: ${JSON.stringify(formData, null, 2)}
    `.trim()

    // 调用 MCP 启动任务 (tahp_execute)
    try {
      const raw = await getMcpBridge().callTool('tahp_execute', {
        document_path: `adapt-${domain}-${Date.now()}`,
        module: 'adaptation',
        domain,
        constraints_extra: {
          projectCode,
          soc,
          kernelVersion,
          formData,
        },
      })

      const data = unwrapToolResult(raw)
      ctx.body = { success: true, data }
    } catch (mcpErr) {
      logger.warn({ err: (mcpErr as Error).message }, '[tahp-adapt] MCP call failed')
      ctx.status = 500
      ctx.body = { success: false, error: (mcpErr as Error).message }
    }
  } catch (err) {
    logger.error({ err }, '[tahp-adapt-launch] unexpected error')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/adapt/status/:taskId — 查询任务状态
tahpAdaptRoutes.get('/api/tahp/adapt/status/:taskId', async (ctx) => {
  try {
    const { taskId } = ctx.params
    const raw = await getMcpBridge().callTool('tahp_status', { task_id: taskId })
    const data = unwrapToolResult(raw)
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[tahp-adapt-status] tool call failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

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

// GET /api/tahp/adapt/layouts — 列出已持久化的域表单布局（启动时合并云端）
tahpAdaptRoutes.get('/api/tahp/adapt/layouts', async (ctx) => {
  try {
    const data = await listAdaptDomainLayouts()
    ctx.body = { success: true, data }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/adapt/layouts/:domainId
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

// PUT /api/tahp/adapt/layouts/:domainId — 保存布局并尝试同步云端
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

// DELETE /api/tahp/adapt/layouts/:domainId — 恢复内置默认字段
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

// POST /api/tahp/adapt/layouts/sync/pull — 强制从云端拉取合并
tahpAdaptRoutes.post('/api/tahp/adapt/layouts/sync/pull', async (ctx) => {
  const result = await pullAndMergeAdaptLayouts()
  ctx.body = { success: true, data: result }
})

// POST /api/tahp/adapt/layouts/sync/push — 强制推送本地 manifest 到云端
tahpAdaptRoutes.post('/api/tahp/adapt/layouts/sync/push', async (ctx) => {
  const result = await forcePushAdaptLayouts()
  if (!result.cloud_pushed && result.cloud_error) {
    ctx.status = 502
    ctx.body = { success: false, error: result.cloud_error, data: result }
    return
  }
  ctx.body = { success: true, data: result }
})

// POST /api/tahp/adapt/agent-prompt-preview — 预览 Agent 系统/用户提示词（不启动任务）
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

// POST /api/tahp/adapt/agent-run — Agent Bridge 自动适配（实时事件走 /tahp-run）
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

// GET /api/tahp/adapt/agent-run/:taskId — 任务快照
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

// GET /api/tahp/adapt/config/get — 获取已保存的配置
tahpAdaptRoutes.get('/api/tahp/adapt/config/get', async (ctx) => {
  try {
    const content = await safeFileStore.readText(CONFIG_PATH)
    const config = JSON.parse(content) as AdaptConfig
    ctx.body = { success: true, data: config }
  } catch (err: any) {
    if (err?.code === 'ENOENT') {
      // 尚未保存过配置，返回 null
      ctx.body = { success: true, data: null }
    } else {
      logger.warn({ err: (err as Error).message }, '[tahp-adapt-get-config] read failed')
      ctx.body = { success: true, data: null }
    }
  }
})
