/**
 * 质量门禁路由 — 转发到 MCP tahp_gate_check.
 */
import Router from '@koa/router'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'

export const tahpGateRoutes = new Router()

interface ToolCallResult { content?: Array<{ type: string; text?: string }> }
function unwrap(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r?.content?.[0]?.text) return raw
  try { return JSON.parse(r.content[0].text || '') } catch { return r.content[0].text }
}

tahpGateRoutes.post('/api/tahp/gate-check', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  if (!body.task_id && !body.module) {
    ctx.status = 400
    ctx.body = { success: false, error: '需提供 task_id 或 module' }
    return
  }
  const args: Record<string, unknown> = { level: body.level || 'all' }
  if (body.task_id) args.task_id = body.task_id
  if (body.module) args.module = body.module
  try {
    const raw = await getMcpBridge().callTool('tahp_gate_check', args)
    ctx.body = { success: true, data: unwrap(raw) }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
