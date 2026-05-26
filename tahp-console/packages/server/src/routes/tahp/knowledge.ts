/**
 * 知识库语义搜索 + 沉淀写入.
 *
 * GET  /api/tahp/knowledge/query  — 转发到 MCP tahp_query_knowledge
 * POST /api/tahp/knowledge/save   — 写入 knowledge-base/<module>/docs/*.md
 */
import Router from '@koa/router'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'
import { tahpPaths } from '../../services/tahp/paths'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { load as yamlLoad, dump as yamlDump } from 'js-yaml'

export const tahpKnowledgeRoutes = new Router()

interface ToolCallResult {
  content?: Array<{ type: string; text?: string }>
}

function unwrap(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r?.content?.[0]?.text) return raw
  try { return JSON.parse(r.content[0].text || '') } catch { return r.content[0].text }
}

// ─── Save knowledge entry ──────────────────────────────────────────────────────
tahpKnowledgeRoutes.post('/api/tahp/knowledge/save', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const { title, content, module: mod, tags, domain, author, category } = body

  if (typeof title !== 'string' || !title.trim()) {
    ctx.status = 400; ctx.body = { success: false, error: '缺少 title' }; return
  }
  if (typeof content !== 'string' || !content.trim()) {
    ctx.status = 400; ctx.body = { success: false, error: '缺少 content' }; return
  }
  if (typeof mod !== 'string' || !mod.trim()) {
    ctx.status = 400; ctx.body = { success: false, error: '缺少 module' }; return
  }

  const validModules = ['telephony', 'kernel-driver', 'power-mgmt', 'shared']
  const safeModule = validModules.includes(mod) ? mod : 'shared'

  // Generate entry ID and file path
  const now   = new Date()
  const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
  const rand4 = String(Math.floor(Math.random() * 9000) + 1000)
  const entryId = `kb-${safeModule}-${dateStr}-${rand4}`

  const docsDir = join(tahpPaths.knowledgeDir, safeModule, 'docs')
  if (!existsSync(docsDir)) mkdirSync(docsDir, { recursive: true })

  const filePath = join(docsDir, `${entryId}.md`)

  const frontmatter = {
    id:           entryId,
    title:        title.trim(),
    module:       safeModule,
    category:     (typeof category === 'string' && category.trim()) ? category.trim() : 'practice_note',
    type:         'practice_note',
    author:       (typeof author === 'string' && author.trim()) ? author.trim() : 'user',
    domain:       (typeof domain === 'string' && domain.trim()) ? domain.trim() : undefined,
    tags:         Array.isArray(tags) ? tags : (typeof tags === 'string' ? tags.split(',').map((t: string) => t.trim()).filter(Boolean) : [safeModule]),
    confidence:   0.85,
    referenced_by: [],
    source:       'chat_extract',
    created_at:   now.toISOString(),
    updated_at:   now.toISOString(),
  }

  const yamlStr  = yamlDump(frontmatter, { lineWidth: -1 }).trimEnd()
  const fileContent = `---\n${yamlStr}\n---\n\n${content.trim()}\n`

  writeFileSync(filePath, fileContent, 'utf-8')

  // Update module index.yaml
  const indexPath = join(tahpPaths.knowledgeDir, safeModule, 'index.yaml')
  let index: any = { entries: { auto: [], cases: [], docs: [] }, module: safeModule, updated: dateStr, version: '1.0' }
  if (existsSync(indexPath)) {
    try { index = yamlLoad(readFileSync(indexPath, 'utf-8')) as any } catch { /* ignore */ }
  }
  if (!index.entries) index.entries = {}
  if (!Array.isArray(index.entries.docs)) index.entries.docs = []
  const alreadyIn = index.entries.docs.some((e: any) => (typeof e === 'string' ? e : e.id) === entryId)
  if (!alreadyIn) {
    index.entries.docs.push({ id: entryId, title: title.trim() })
    index.updated = dateStr
    writeFileSync(indexPath, yamlDump(index, { lineWidth: -1 }), 'utf-8')
  }

  ctx.body = { success: true, data: { id: entryId, file: `knowledge-base/${safeModule}/docs/${entryId}.md` } }
})

// ─── Query knowledge ───────────────────────────────────────────────────────────
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
