/**
 * TAHP 任务 REST 路由 — 调用 MCP tahp_execute / tahp_status / tahp_correct / tahp_list_tasks.
 *
 * MCP tool/call 返回 { content: [{ type:"text", text: "<json-string>" }], isError?: bool }
 * 我们解包 content[0].text 后回前端.
 */
import Router from '@koa/router'
import type { Context } from 'koa'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'
import { logger } from '../../services/logger'

export const tahpTaskRoutes = new Router()

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

async function callTool(ctx: Context, name: string, args: Record<string, unknown>) {
  try {
    const raw = await getMcpBridge().callTool(name, args)
    const data = unwrapToolResult(raw)
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message, name }, '[tahp-task] tool call failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
}

// POST /api/tahp/tasks — 启动任务
tahpTaskRoutes.post('/api/tahp/tasks', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const { document_path, module, domain, constraints_extra } = body
  if (!document_path || !module || !domain) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少必填: document_path / module / domain' }
    return
  }
  await callTool(ctx, 'tahp_execute', { document_path, module, domain, constraints_extra })
})

// GET /api/tahp/tasks — 列出任务
tahpTaskRoutes.get('/api/tahp/tasks', async (ctx) => {
  const includeCompleted = ctx.query.include_completed !== 'false'
  await callTool(ctx, 'tahp_list_tasks', { include_completed: includeCompleted })
})

// GET /api/tahp/tasks/:id — 任务详情
tahpTaskRoutes.get('/api/tahp/tasks/:id', async (ctx) => {
  await callTool(ctx, 'tahp_status', { task_id: ctx.params.id })
})

// POST /api/tahp/tasks/:id/correct — 纠偏
tahpTaskRoutes.post('/api/tahp/tasks/:id/correct', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const feedback = body.feedback
  if (typeof feedback !== 'string' || !feedback.trim()) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 feedback' }
    return
  }
  await callTool(ctx, 'tahp_correct', { task_id: ctx.params.id, feedback })
})
