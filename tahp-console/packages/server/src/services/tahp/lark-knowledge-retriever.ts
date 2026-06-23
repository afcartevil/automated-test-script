import { execFile } from 'child_process'
import { promisify } from 'util'
import type { LarkHit } from './chat-retrieval/types'

const execFileAsync = promisify(execFile)

const CACHE = new Map<string, { hits: LarkHit[]; at: number }>()
const CACHE_TTL_MS = 5 * 60 * 1000
const TIMEOUT_MS = Number(process.env.TAHP_LARK_SEARCH_TIMEOUT_MS || 4000)

function larkEnabled(): boolean {
  return process.env.TAHP_LARK_SEARCH_ENABLED === '1' || process.env.TAHP_LARK_SEARCH_ENABLED === 'true'
}

async function larkCliAvailable(): Promise<boolean> {
  try {
    await execFileAsync(process.platform === 'win32' ? 'where.exe' : 'which', ['lark-cli'], {
      timeout: 2000,
      windowsHide: true,
    })
    return true
  } catch {
    return false
  }
}

export async function searchLarkKnowledge(
  query: string,
  options?: { module_hint?: string; limit?: number },
): Promise<LarkHit[]> {
  if (!larkEnabled() || !query.trim()) return []
  const cacheKey = `${query}::${options?.limit ?? 3}`
  const cached = CACHE.get(cacheKey)
  if (cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.hits

  if (!(await larkCliAvailable())) return []

  const limit = options?.limit ?? 3
  const spaceIds = process.env.TAHP_LARK_DEFAULT_SPACE_IDS?.trim()
  const args = ['drive', '+search', '--query', query, '--page-size', String(Math.min(limit, 5)), '--format', 'json']
  if (spaceIds) args.push('--space-ids', spaceIds)

  try {
    const { stdout } = await execFileAsync('lark-cli', args, {
      timeout: TIMEOUT_MS,
      windowsHide: true,
      maxBuffer: 2 * 1024 * 1024,
    })
    const parsed = JSON.parse(stdout) as { data?: { items?: Array<Record<string, unknown>> } }
    const items = parsed?.data?.items || (Array.isArray(parsed) ? parsed : [])
    const hits: LarkHit[] = []
    for (const item of items.slice(0, limit)) {
      const title = String(item.title || item.name || '未命名文档')
      const url = item.url ? String(item.url) : undefined
      hits.push({
        title,
        url,
        doc_type: item.type ? String(item.type) : undefined,
        excerpt: title,
        relevance: 70,
      })
    }
    CACHE.set(cacheKey, { hits, at: Date.now() })
    return hits
  } catch {
    return []
  }
}
