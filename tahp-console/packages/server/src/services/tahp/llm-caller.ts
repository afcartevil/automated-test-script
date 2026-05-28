/**
 * 轻量 LLM 单次调用工具 — 专为知识库 Skill 生成设计
 *
 * 复用 handle-api-run.ts 中的 resolveGatewayUpstream，直接调用 LLM，
 * 无需 chat session、history 等完整链路。
 * 支持 Anthropic direct 和 OpenAI-compatible 两种模式。
 */
import { request as httpsRequest } from 'https'
import { request as httpRequest } from 'http'
import { resolveGatewayUpstream } from '../hermes/run-chat/handle-api-run'
import { logger } from '../logger'

const CALL_TIMEOUT_MS = 120_000
const DEFAULT_MAX_TOKENS = 4096

export interface LLMCallerOptions {
  /** Hermes profile（默认 "default"） */
  profile?: string
  /** 最大输出 token 数 */
  maxTokens?: number
  /** 模型名（可选，不传则用配置中的 default model） */
  model?: string
}

/**
 * 单次调用配置的 LLM，返回完整响应文本。
 * 失败时抛出 Error，包含友好提示。
 */
export async function callTahpLLM(
  systemPrompt: string,
  userContent: string,
  opts: LLMCallerOptions = {},
): Promise<string> {
  const profile = opts.profile ?? 'default'
  const maxTokens = opts.maxTokens ?? DEFAULT_MAX_TOKENS

  let upstream: string
  let apiKey: string | undefined
  let providerType: 'anthropic' | 'openai-chat' | 'default'
  let defaultModel: string | undefined

  try {
    const config = resolveGatewayUpstream(profile)
    upstream = config.upstream
    apiKey = config.apiKey
    providerType = config.providerType
    defaultModel = config.defaultModel
  } catch (err: any) {
    throw new Error(`LLM 配置解析失败: ${err?.message}。请在控制台设置 LLM Provider。`)
  }

  const model = opts.model || defaultModel || 'claude-3-5-sonnet-20241022'

  // ─── Anthropic direct mode ───────────────────────────────────────────
  if (providerType === 'anthropic') {
    if (!apiKey) throw new Error('Anthropic API Key 未配置')
    return callAnthropic(apiKey, model, systemPrompt, userContent, maxTokens)
  }

  // ─── OpenAI-compatible mode ──────────────────────────────────────────
  if (providerType === 'openai-chat') {
    if (!apiKey) throw new Error('LLM API Key 未配置')
    const baseUrl = upstream.replace(/\/+$/, '')
    return callOpenAICompat(baseUrl, apiKey, model, systemPrompt, userContent, maxTokens)
  }

  // ─── Default/gateway mode（兜底） ────────────────────────────────────
  // 走 gateway 的 /v1/chat/completions
  const baseUrl = upstream.replace(/\/+$/, '')
  return callOpenAICompat(baseUrl, apiKey, model, systemPrompt, userContent, maxTokens)
}

/** Anthropic /v1/messages (non-streaming) */
async function callAnthropic(
  apiKey: string,
  model: string,
  system: string,
  userMsg: string,
  maxTokens: number,
): Promise<string> {
  const body = JSON.stringify({
    model,
    max_tokens: maxTokens,
    system,
    messages: [{ role: 'user', content: userMsg }],
  })

  const url = new URL('https://api.anthropic.com/v1/messages')
  return new Promise<string>((resolve, reject) => {
    const req = httpsRequest({
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (c: Buffer) => chunks.push(c))
      res.on('end', () => {
        try {
          const text = Buffer.concat(chunks).toString('utf-8')
          const json = JSON.parse(text)
          if (json.error) {
            reject(new Error(`Anthropic API 错误: ${json.error.message || JSON.stringify(json.error)}`))
            return
          }
          const content = json.content?.[0]?.text ?? ''
          if (!content) reject(new Error('Anthropic 返回空内容'))
          else resolve(content)
        } catch (e: any) {
          reject(new Error(`Anthropic 响应解析失败: ${e.message}`))
        }
      })
      res.on('error', reject)
    })
    req.setTimeout(CALL_TIMEOUT_MS, () => { req.destroy(); reject(new Error('LLM 调用超时（120s）')) })
    req.on('error', reject)
    req.write(body)
    req.end()
  })
}

/** OpenAI-compatible /v1/chat/completions (non-streaming) */
async function callOpenAICompat(
  baseUrl: string,
  apiKey: string | undefined,
  model: string,
  system: string,
  userMsg: string,
  maxTokens: number,
): Promise<string> {
  const body = JSON.stringify({
    model,
    max_tokens: maxTokens,
    messages: [
      { role: 'system', content: system },
      { role: 'user',   content: userMsg },
    ],
  })

  // 构建 chat completions 端点 URL
  // 重要：部分 upstream 已包含路径（如 deepinfra baseUrl=https://api.deepinfra.com/v1/openai），
  // 直接拼接 /v1/chat/completions 会产生 /v1/v1/chat/completions 的双重路径错误。
  let chatUrl: string
  const normalizedBase = baseUrl.replace(/\/+$/, '')
  try {
    const urlForCheck = new URL(normalizedBase)
    const path = urlForCheck.pathname.replace(/\/+$/, '')
    if (path.endsWith('/v1') || path.includes('/v1/')) {
      // baseUrl 已包含 /v1 路径，直接追加 /chat/completions
      chatUrl = `${normalizedBase}/chat/completions`
    } else if (path === '' || path === '/') {
      // baseUrl 是纯域名，追加 /v1/chat/completions
      chatUrl = `${normalizedBase}/v1/chat/completions`
    } else {
      // 非标准路径（如 alibaba /compatible-mode），在 baseUrl 后追加 /v1/chat/completions
      chatUrl = `${normalizedBase}/v1/chat/completions`
    }
  } catch {
    // URL 解析失败，fallback 到简单拼接
    chatUrl = `${normalizedBase}/v1/chat/completions`
  }
  let parsedUrl: URL
  try {
    parsedUrl = new URL(chatUrl)
  } catch {
    throw new Error(`无效的 LLM upstream URL: ${baseUrl}`)
  }

  const isHttps = parsedUrl.protocol === 'https:'
  const reqFn = isHttps ? httpsRequest : httpRequest
  const port = parsedUrl.port
    ? parseInt(parsedUrl.port, 10)
    : isHttps ? 443 : 80

  const headers: Record<string, string | number> = {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
  }
  if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`

  return new Promise<string>((resolve, reject) => {
    const req = reqFn({
      hostname: parsedUrl.hostname,
      port,
      path: parsedUrl.pathname + parsedUrl.search,
      method: 'POST',
      headers,
    }, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (c: Buffer) => chunks.push(c))
      res.on('end', () => {
        try {
          const text = Buffer.concat(chunks).toString('utf-8')
          const json = JSON.parse(text)
          if (json.error) {
            reject(new Error(`LLM API 错误: ${json.error.message || JSON.stringify(json.error)}`))
            return
          }
          const content: string = json.choices?.[0]?.message?.content ?? ''
          if (!content) reject(new Error('LLM 返回空内容'))
          else resolve(content)
        } catch (e: any) {
          reject(new Error(`LLM 响应解析失败: ${e.message}`))
        }
      })
      res.on('error', reject)
    })
    req.setTimeout(CALL_TIMEOUT_MS, () => { req.destroy(); reject(new Error('LLM 调用超时（120s）')) })
    req.on('error', reject)
    req.write(body)
    req.end()
  }).then(result => {
    logger.info({ model, baseUrl }, '[llm-caller] openai-compat call succeeded')
    return result
  }).catch(err => {
    logger.warn({ model, baseUrl, err: err?.message }, '[llm-caller] openai-compat call failed')
    throw err
  })
}
