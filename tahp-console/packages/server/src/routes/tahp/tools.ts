/**
 * 7 个底层工具适配 — 单步调用入口.
 * 支持的工具:
 *   - tahp_analyze_log
 *   - tahp_code_review
 *   - tahp_api_migration
 */
import Router from '@koa/router'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'

export const tahpToolsRoutes = new Router()

const ALLOWED_TOOLS = new Set([
  'tahp_analyze_log',
  'tahp_code_review',
  'tahp_api_migration',
])

interface ToolCallResult { content?: Array<{ type: string; text?: string }> }
function unwrap(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r?.content?.[0]?.text) return raw
  try { return JSON.parse(r.content[0].text || '') } catch { return r.content[0].text }
}

// POST /api/tahp/tools/:name — body 即 arguments
tahpToolsRoutes.post('/api/tahp/tools/:name', async (ctx) => {
  const name = ctx.params.name
  if (!ALLOWED_TOOLS.has(name)) {
    ctx.status = 400
    ctx.body = { success: false, error: `不支持的工具: ${name}` }
    return
  }
  const args = (ctx.request.body || {}) as Record<string, unknown>
  try {
    const raw = await getMcpBridge().callTool(name, args)
    ctx.body = { success: true, data: unwrap(raw) }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/tools — 列出当前 MCP server 暴露的工具
tahpToolsRoutes.get('/api/tahp/tools', async (ctx) => {
  try {
    const tools = await getMcpBridge().listTools()
    ctx.body = { success: true, data: tools }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
