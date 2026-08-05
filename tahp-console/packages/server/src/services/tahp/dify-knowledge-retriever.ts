import { logger } from '../logger'
import { getSecret, setSecret, hasSecret } from './secret-store'

export interface DifyHit {
  title: string
  dataset: string
  excerpt: string
  score: number
  kb_tag: string
}

export interface DifyStreamResult {
  answer: string
  hits: DifyHit[]
  conversation_id?: string
  message_id?: string
}

export interface DifyStreamCallbacks {
  onDelta: (chunk: string) => void
  onEnd: (result: DifyStreamResult) => void
}

const DEFAULT_KB_TAGS = [
  '全局搜索',
  '蜂窝通信',
  '器件',
  '内核',
  '媒体显示',
  '功耗温升',
  '近场通信',
  '公共知识',
  '方案设计',
  '代码规范',
]

const MODULE_TO_KB_TAG: Record<string, string> = {
  telephony: '蜂窝通信',
  'kernel-driver': '内核',
  'power-mgmt': '功耗温升',
  shared: '公共知识',
}

/**
 * First-run bootstrap seed for zero-config Windows delivery.
 * On first resolve, encrypted via DPAPI LocalMachine into ~/.tahp-console/secrets.json.
 * Prefer env override TAHP_DIFY_API_KEY for local override; set TAHP_DIFY_SEARCH_ENABLED=0 to disable.
 */
const DIFY_API_KEY_BOOTSTRAP = 'app-pIT6s5BvzERFSszjXsLo125d'

let cachedKbTags: string[] | null = null
let cachedKbTagsAt = 0
const KB_TAGS_CACHE_MS = 10 * 60 * 1000

let resolvedKeyCache: string | null | undefined
let bootstrapAttempted = false

function snippetChars(): number {
  return Number(process.env.TAHP_KB_SNIPPET_CHARS || 800)
}

function timeoutMs(): number {
  return Number(process.env.TAHP_DIFY_TIMEOUT_MS || 45000)
}

/**
 * Resolve Dify API key: env plaintext → DPAPI secrets store → first-run bootstrap.
 */
export function resolveDifyApiKey(): string {
  if (resolvedKeyCache) return resolvedKeyCache

  const fromEnv = process.env.TAHP_DIFY_API_KEY?.trim()
  if (fromEnv) {
    if (!hasSecret('dify_api_key')) {
      try {
        setSecret('dify_api_key', fromEnv)
        logger.info('[dify-kb] persisted env API key into DPAPI secrets store')
      } catch (err) {
        logger.warn('[dify-kb] failed to persist env key to secrets store: %s', err)
      }
    }
    resolvedKeyCache = fromEnv
    return fromEnv
  }

  const fromStore = getSecret('dify_api_key')
  if (fromStore) {
    resolvedKeyCache = fromStore
    return fromStore
  }

  if (!bootstrapAttempted) {
    bootstrapAttempted = true
    try {
      setSecret('dify_api_key', DIFY_API_KEY_BOOTSTRAP)
      logger.info('[dify-kb] bootstrapped Dify API key into DPAPI secrets store (zero-config)')
    } catch (err) {
      logger.warn('[dify-kb] DPAPI bootstrap failed, using in-memory seed: %s', err)
    }
  }

  resolvedKeyCache = DIFY_API_KEY_BOOTSTRAP
  return DIFY_API_KEY_BOOTSTRAP
}

/** Default ON when a key can be resolved; set TAHP_DIFY_SEARCH_ENABLED=0 to disable. */
export function difyEnabled(): boolean {
  const flag = process.env.TAHP_DIFY_SEARCH_ENABLED
  if (flag === '0' || flag === 'false') return false
  try {
    return Boolean(resolveDifyApiKey())
  } catch {
    return false
  }
}

export function difyFallbackLocalEnabled(): boolean {
  const flag = process.env.TAHP_DIFY_FALLBACK_LOCAL
  return flag !== '0' && flag !== 'false'
}

function apiBase(): string {
  return (process.env.TAHP_DIFY_API_BASE || 'https://dify-service-hk.transsion.com/v1').replace(/\/$/, '')
}

function apiKey(): string {
  return resolveDifyApiKey()
}

export function resolveKbTag(userChoice?: string, moduleHint?: string): string {
  const chosen = userChoice?.trim()
  if (chosen) return chosen
  if (moduleHint && MODULE_TO_KB_TAG[moduleHint]) {
    return MODULE_TO_KB_TAG[moduleHint]
  }
  return '全局搜索'
}

export function mapResourcesToHits(
  resources: Array<Record<string, unknown>> | undefined,
  kbTag: string,
  limit = 8,
): DifyHit[] {
  if (!resources?.length) return []
  const maxLen = snippetChars()
  const hits: DifyHit[] = []
  const seen = new Set<string>()

  for (const item of [...resources].sort((a, b) => Number(b.score || 0) - Number(a.score || 0))) {
    const title = String(item.document_name || item.title || '未命名文档')
    const dedupeKey = `${title}::${String(item.content || '').slice(0, 80)}`
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)

    const rawContent = String(item.content || '')
    const excerpt = rawContent.length > maxLen ? `${rawContent.slice(0, maxLen)}…` : rawContent
    hits.push({
      title,
      dataset: String(item.dataset_name || '底软通信知识库'),
      excerpt,
      score: Math.round(Number(item.score || 0) * 100),
      kb_tag: kbTag,
    })
    if (hits.length >= limit) break
  }
  return hits
}

/** Parse Dify SSE lines from a buffer; exported for unit tests. */
export function parseDifySseLines(buffer: string): { events: Array<Record<string, unknown>>; rest: string } {
  const lines = buffer.split('\n')
  const rest = lines.pop() || ''
  const events: Array<Record<string, unknown>> = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed.startsWith('data:')) continue
    const payload = trimmed.slice(5).trim()
    if (!payload || payload === '[DONE]') continue
    try {
      events.push(JSON.parse(payload) as Record<string, unknown>)
    } catch {
      // ignore malformed frames
    }
  }
  return { events, rest }
}

export async function fetchDifyKbTags(): Promise<string[]> {
  if (cachedKbTags && Date.now() - cachedKbTagsAt < KB_TAGS_CACHE_MS) {
    return cachedKbTags
  }
  if (!difyEnabled()) return DEFAULT_KB_TAGS

  try {
    const res = await fetch(`${apiBase()}/parameters`, {
      headers: { Authorization: `Bearer ${apiKey()}` },
      signal: AbortSignal.timeout(8000),
    })
    if (!res.ok) return DEFAULT_KB_TAGS
    const body = await res.json() as {
      user_input_form?: Array<{ select?: { variable?: string; options?: string[] } }>
    }
    const form = body.user_input_form || []
    const kbField = form.find(item => item.select?.variable === 'kb_tag')
    const options = kbField?.select?.options?.filter(Boolean)
    if (options?.length) {
      cachedKbTags = options
      cachedKbTagsAt = Date.now()
      return options
    }
  } catch (err) {
    logger.warn('[dify-kb] failed to fetch kb_tags: %s', err)
  }
  return DEFAULT_KB_TAGS
}

export async function streamDifyChat(
  query: string,
  options: {
    kb_tag: string
    user?: string
    signal?: AbortSignal
  },
  callbacks: DifyStreamCallbacks,
): Promise<DifyStreamResult> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs())
  const signal = options.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let answer = ''
  let conversationId: string | undefined
  let messageId: string | undefined
  let resources: Array<Record<string, unknown>> | undefined

  try {
    const res = await fetch(`${apiBase()}/chat-messages`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        inputs: { kb_tag: options.kb_tag },
        query,
        response_mode: 'streaming',
        user: options.user || 'tahp-console',
      }),
      signal,
    })

    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`Dify API ${res.status}: ${text.slice(0, 300)}`)
    }
    if (!res.body) {
      throw new Error('Dify API response stream missing')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parsed = parseDifySseLines(buffer)
      buffer = parsed.rest

      for (const evt of parsed.events) {
        const eventType = String(evt.event || '')
        if (eventType === 'agent_message' || eventType === 'message') {
          const chunk = String(evt.answer || '')
          if (chunk) {
            answer += chunk
            callbacks.onDelta(chunk)
          }
          conversationId = conversationId || (evt.conversation_id ? String(evt.conversation_id) : undefined)
          messageId = messageId || (evt.message_id ? String(evt.message_id) : undefined)
        } else if (eventType === 'message_end') {
          conversationId = conversationId || (evt.conversation_id ? String(evt.conversation_id) : undefined)
          messageId = messageId || (evt.message_id ? String(evt.message_id) : undefined)
          const metadata = evt.metadata as { retriever_resources?: Array<Record<string, unknown>> } | undefined
          resources = metadata?.retriever_resources
        } else if (eventType === 'error') {
          throw new Error(String(evt.message || 'Dify stream error'))
        }
      }
    }

    if (buffer.trim()) {
      const parsed = parseDifySseLines(`${buffer}\n`)
      for (const evt of parsed.events) {
        if (evt.event === 'message_end') {
          const metadata = evt.metadata as { retriever_resources?: Array<Record<string, unknown>> } | undefined
          resources = metadata?.retriever_resources
        }
      }
    }
  } finally {
    clearTimeout(timer)
  }

  const hits = mapResourcesToHits(resources, options.kb_tag)
  const result: DifyStreamResult = {
    answer,
    hits,
    conversation_id: conversationId,
    message_id: messageId,
  }
  callbacks.onEnd(result)
  return result
}

/**
 * Mode A retrieval: call Dify streaming only to harvest retriever_resources.
 * Answer text is discarded. Fail-open → [].
 */
export async function searchDifyKnowledge(
  query: string,
  options?: {
    kb_tag?: string
    module_hint?: string
    user?: string
    limit?: number
    signal?: AbortSignal
  },
): Promise<DifyHit[]> {
  if (!difyEnabled() || !query.trim()) return []
  const kb_tag = resolveKbTag(options?.kb_tag, options?.module_hint)
  try {
    const result = await streamDifyChat(
      query,
      { kb_tag, user: options?.user, signal: options?.signal },
      { onDelta: () => {}, onEnd: () => {} },
    )
    return result.hits.slice(0, options?.limit ?? 8)
  } catch (err) {
    logger.warn('[dify-kb] searchDifyKnowledge failed: %s', err)
    return []
  }
}

export interface DifyFusionResult {
  answer: string
  hits: DifyHit[]
  kb_tag: string
}

/**
 * Fusion retrieval (App Key only): call Dify Agent once, KEEP both the answer
 * (as context for local LLM fusion) and retriever_resources (as citation card).
 * Fail-open → null (caller falls back to local-only answer).
 */
export async function fetchDifyFusion(
  query: string,
  options?: {
    kb_tag?: string
    module_hint?: string
    user?: string
    limit?: number
    signal?: AbortSignal
  },
): Promise<DifyFusionResult | null> {
  if (!difyEnabled() || !query.trim()) return null
  const kb_tag = resolveKbTag(options?.kb_tag, options?.module_hint)
  try {
    const result = await streamDifyChat(
      query,
      { kb_tag, user: options?.user, signal: options?.signal },
      { onDelta: () => {}, onEnd: () => {} },
    )
    return {
      answer: (result.answer || '').trim(),
      hits: result.hits.slice(0, options?.limit ?? 8),
      kb_tag,
    }
  } catch (err) {
    logger.warn('[dify-kb] fetchDifyFusion failed: %s', err)
    return null
  }
}

/**
 * Build the system-prompt context block that asks the local LLM to fuse
 * the Dify answer with local KB/Skill hits into a single de-duplicated reply.
 */
export function buildDifyFusionBlock(answer: string, kbTag: string): string {
  const trimmed = (answer || '').trim()
  if (!trimmed) return ''
  return [
    '# 底软通信知识库（Dify）回答（外部权威来源，请融合）',
    '',
    `> kb_tag: ${kbTag}。以下为底软通信 Dify 知识库对本问题的回答。`,
    '请将其与上方「本地知识库 / Skill 命中」融合，输出**一份统一、去重、标注来源**的答复：',
    '- 两者一致的结论合并陈述；仅一方有的内容予以补充；',
    '- 冲突时以更具体、有出处者为准，并简要说明差异来源（本地案例 vs 底软通信知识库）；',
    '- 不要复述本段原文，也不要输出「以下为 Dify 回答」之类的元信息。',
    '',
    '---',
    trimmed,
    '---',
  ].join('\n')
}
