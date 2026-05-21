/**
 * 知识库语义搜索 — 转发到 MCP tahp_query_knowledge.
 */
import Router from '@koa/router'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'

export const tahpKnowledgeRoutes = new Router()

interface ToolCallResult {
  content?: Array<{ type: string; text?: string }>
}

function unwrap(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r?.content?.[0]?.text) return raw
  try { return JSON.parse(r.content[0].text || '') } catch { return r.content[0].text }
}

tahpKnowledgeRoutes.post('/api/tahp/knowledge/query', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const query = body.query
  if (typeof query !== 'string' || !query.trim()) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 query' }
    return
  }
  const args: Record<string, unknown> = { query }
  if (body.module) args.module = body.module
  if (body.cross_module !== undefined) args.cross_module = body.cross_module
  if (body.top_k !== undefined) args.top_k = body.top_k
  try {
    const raw = await getMcpBridge().callTool('tahp_query_knowledge', args)
    ctx.body = { success: true, data: unwrap(raw) }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
