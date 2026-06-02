/**
 * API Server run handler — handles runs that stream from upstream /v1/responses.
 *
 * resolveRunSource: probes the agent bridge socket; if unavailable, falls back to 'api' mode.
 * resolveGatewayUpstream: reads gateway URL + API key from profile config.yaml.
 */

import { createConnection } from 'net'
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import yaml from 'js-yaml'
import type { Server, Socket } from 'socket.io'
import { getSystemPrompt } from '../../../lib/llm-prompt'
import {
  getSession,
  createSession,
  addMessage,
  updateSessionStats,
  getSessionDetailPaginated,
} from '../../../db/hermes/session-store'
import { updateUsage } from '../../../db/hermes/usage-store'
import { logger } from '../../logger'
import { contentBlocksToString, extractTextForPreview, isContentBlockArray, convertContentBlocks } from './content-blocks'
import { convertHistoryFormat } from './message-format'
import { readSseFrames } from './sse-utils'
import { extractResponseText } from './response-utils'
import { applyResponseStreamEvent, flushResponseRunToDb } from './response-stream'
import { buildCompressedHistory, getOrCreateSession } from './compression'
import { calcAndUpdateUsage, estimateUsageTokensFromMessages } from './usage'
import { handleMessage } from './message-format'
import { countTokens, SUMMARY_PREFIX } from '../../../lib/context-compressor'
import { getCompressionSnapshot } from '../../../db/hermes/compression-snapshot'
import { getProfileDir, getActiveEnvPath, getActiveConfigPath } from '../../hermes/hermes-profile'
import type { ContentBlock, SessionState, ChatRunSource } from './types'
import { buildFullTahpSystemContext, extractInputText, extractPreferredSkillIds } from '../../tahp/context-injector'

// ---------------------------------------------------------------------------
// Bridge availability probe (cached, TTL = 10 s)
// ---------------------------------------------------------------------------

let _bridgeAvailable: boolean | null = null
let _bridgeLastCheck = 0
const BRIDGE_CHECK_TTL_MS = 10_000

function probeBridgeSync(): boolean {
  // Fast check: probe Windows TCP bridge port 18765 (or Unix socket).
  // We do a synchronous-style check by caching the last async result.
  return _bridgeAvailable ?? false
}

async function probeBridgeAsync(): Promise<boolean> {
  const now = Date.now()
  if (_bridgeAvailable !== null && now - _bridgeLastCheck < BRIDGE_CHECK_TTL_MS) {
    return _bridgeAvailable
  }
  return new Promise((resolve) => {
    const isWin = process.platform === 'win32'
    const opts = isWin
      ? { host: '127.0.0.1', port: 18765 }
      : { path: '/tmp/hermes-agent-bridge.sock' }
    const socket = createConnection(opts as any)
    const timer = setTimeout(() => {
      socket.destroy()
      _bridgeAvailable = false
      _bridgeLastCheck = Date.now()
      resolve(false)
    }, 1500)
    socket.once('connect', () => {
      clearTimeout(timer)
      socket.destroy()
      _bridgeAvailable = true
      _bridgeLastCheck = Date.now()
      resolve(true)
    })
    socket.once('error', () => {
      clearTimeout(timer)
      _bridgeAvailable = false
      _bridgeLastCheck = Date.now()
      resolve(false)
    })
  })
}

// Kick off an initial probe at module load time so the first call has a cached result.
probeBridgeAsync().catch(() => {})

// ---------------------------------------------------------------------------
// resolveRunSource — returns 'cli' only when bridge is actually reachable
// ---------------------------------------------------------------------------

export function resolveRunSource(source?: string, _sessionId?: string): ChatRunSource {
  // Explicit override from caller
  if (source === 'api_server') return 'api_server'
  if (source === 'cli') {
    // Honour explicit 'cli' only if bridge is available; otherwise fall back.
    return probeBridgeSync() ? 'cli' : 'api_server'
  }
  // Default: use bridge when available, otherwise API mode
  return probeBridgeSync() ? 'cli' : 'api_server'
}

// Async variant — refreshes the probe and returns the correct source.
export async function resolveRunSourceAsync(source?: string, sessionId?: string): Promise<ChatRunSource> {
  await probeBridgeAsync()
  return resolveRunSource(source, sessionId)
}

// ---------------------------------------------------------------------------
// Gateway upstream resolver — reads profile config.yaml
// ---------------------------------------------------------------------------

interface GatewayConfig {
  upstream: string
  apiKey: string | undefined
  /** 'anthropic' → 用 /v1/messages 适配器；'openai-chat' → 用 /v1/chat/completions 适配器；'default' → 原有 /v1/responses */
  providerType: 'anthropic' | 'openai-chat' | 'default'
  /** config.yaml 里当前激活的模型名（客户端未指定时的回退值） */
  defaultModel?: string
}

// 已知 provider 的固定 base_url（key 存 profile .env，无需 custom_providers）
const KNOWN_PROVIDER_BASE_URLS: Record<string, string> = {
  anthropic:    'https://api.anthropic.com',
  deepseek:     'https://api.deepseek.com',
  openai:       'https://api.openai.com',
  moonshot:     'https://api.moonshot.cn',
  openrouter:   'https://openrouter.ai/api',
  alibaba:      'https://dashscope.aliyuncs.com/compatible-mode',
  minimax:      'https://api.minimax.chat',
  gemini:       'https://generativelanguage.googleapis.com',
  xai:          'https://api.x.ai',
  stepfun:      'https://api.stepfun.com',
  deepinfra:    'https://api.deepinfra.com/v1/openai',
  zai:          'https://open.bigmodel.cn/api/paas',
  arcee:        'https://models.arcee.ai',
}

// 已知 provider 的 env key 名（与 config-helpers.ts PROVIDER_ENV_MAP 保持一致）
const KNOWN_PROVIDER_ENV_KEYS: Record<string, string> = {
  anthropic:    'ANTHROPIC_API_KEY',
  deepseek:     'DEEPSEEK_API_KEY',
  openai:       'OPENAI_API_KEY',
  moonshot:     'MOONSHOT_API_KEY',
  openrouter:   'OPENROUTER_API_KEY',
  alibaba:      'DASHSCOPE_API_KEY',
  minimax:      'MINIMAX_API_KEY',
  gemini:       'GEMINI_API_KEY',
  xai:          'XAI_API_KEY',
  stepfun:      'STEPFUN_API_KEY',
  zai:          'GLM_API_KEY',
  arcee:        'ARCEE_API_KEY',
}

/**
 * resolveGatewayUpstream — 读取当前激活的 provider 配置，决定 LLM 上游路由
 *
 * 优先级（高→低）：
 *   1. TAHP_LLM_UPSTREAM 环境变量（自定义代理，最高覆盖）
 *   2. config.yaml → 当前激活 provider → custom_providers 数组（UI 保存的配置）
 *   3. config.yaml → 当前激活 provider → profile .env（已知 provider 的 key）
 *   4. 兜底：http://127.0.0.1:8642（兼容旧版 hermes gateway）
 *
 * upstream 类型：
 *   anthropic://direct  → 走 /v1/messages 适配器
 *   http(s)://xxx       → 走 /v1/chat/completions 适配器（OpenAI 兼容，支持所有国内模型）
 *   http://127.0.0.1:8642 → 走原有 /v1/responses（兜底）
 */
export function resolveGatewayUpstream(profile: string): GatewayConfig {
  const defaultGatewayPort = 8642
  const defaultHost = '127.0.0.1'

  // ── 1. TAHP_LLM_UPSTREAM 优先覆盖 ────────────────────────────────
  const tahpUpstream = process.env.TAHP_LLM_UPSTREAM?.trim()
  if (tahpUpstream) {
    const apiKey = process.env.TAHP_API_KEY?.trim() || process.env.ANTHROPIC_API_KEY?.trim() || undefined
    const providerType = tahpUpstream.includes('anthropic') ? 'anthropic' : 'openai-chat'
    logger.info('[resolve-upstream] TAHP_LLM_UPSTREAM=%s', tahpUpstream)
    return { upstream: tahpUpstream, apiKey, providerType }
  }

  // ── 辅助：从 profile .env 读取指定 key ────────────────────────────
  function readProfileEnv(key: string): string | undefined {
    try {
      const p = getActiveEnvPath()
      if (!existsSync(p)) return undefined
      const raw = readFileSync(p, 'utf-8')
      const m = raw.match(new RegExp(`^${key}\\s*=\\s*(.+)`, 'm'))
      let val = m?.[1]?.trim()
      if (!val) return undefined
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'")))
        val = val.slice(1, -1).trim()
      return val && !val.startsWith('#') ? val : undefined
    } catch { return undefined }
  }

  // ── 2. 读取 config.yaml，找当前激活的 provider 配置 ──────────────
  try {
    const configPath = getActiveConfigPath()
    if (existsSync(configPath)) {
      const raw = readFileSync(configPath, 'utf-8')
      const cfg = (yaml.load(raw, { json: true }) as any) || {}

      // 当前激活的 provider key（如 "deepseek"、"anthropic"、"custom:mymodel"）
      const activeProvider = String(cfg?.model?.provider || '').trim()
      const providerKey = activeProvider.startsWith('custom:')
        ? activeProvider.slice(7)
        : activeProvider

      const customProviders: any[] = cfg?.custom_providers || []

      // 先在 custom_providers 里找该 provider 的配置（name 精确匹配或 provider key 匹配）
      const cpEntry = customProviders.find((p: any) =>
        p.name === providerKey || p.name === activeProvider
      )

      if (cpEntry) {
        const apiKey = cpEntry.api_key?.trim()
        const baseUrl = String(cpEntry.base_url || '').replace(/\/+$/, '')
        if (apiKey && baseUrl) {
          const defaultModel = String(cfg?.model?.default || cpEntry.model || '').trim() || undefined
          if (baseUrl.includes('anthropic.com')) {
            logger.info('[resolve-upstream] anthropic direct (custom_providers name=%s model=%s)', cpEntry.name, defaultModel)
            return { upstream: 'anthropic://direct', apiKey, providerType: 'anthropic', defaultModel }
          }
          logger.info('[resolve-upstream] openai-chat direct (custom_providers name=%s base_url=%s model=%s)', cpEntry.name, baseUrl, defaultModel)
          return { upstream: baseUrl, apiKey, providerType: 'openai-chat', defaultModel }
        }
      }

      // 如果是已知 provider，从 profile .env 读 key，base_url 用固定值
      if (providerKey && KNOWN_PROVIDER_BASE_URLS[providerKey]) {
        const envKey = KNOWN_PROVIDER_ENV_KEYS[providerKey]
        const apiKey = envKey ? readProfileEnv(envKey) : undefined
        const baseUrl = KNOWN_PROVIDER_BASE_URLS[providerKey]
        if (apiKey) {
          const knownDefaultModel = String(cfg?.model?.default || '').trim() || undefined
          if (providerKey === 'anthropic') {
            logger.info('[resolve-upstream] anthropic direct (known provider, profile .env key=%s model=%s)', envKey, knownDefaultModel)
            return { upstream: 'anthropic://direct', apiKey, providerType: 'anthropic', defaultModel: knownDefaultModel }
          }
          logger.info('[resolve-upstream] openai-chat direct (known provider=%s base_url=%s model=%s)', providerKey, baseUrl, knownDefaultModel)
          return { upstream: baseUrl, apiKey, providerType: 'openai-chat', defaultModel: knownDefaultModel }
        }
      }

      logger.warn('[resolve-upstream] active provider=%s but no api_key found in custom_providers or profile .env', activeProvider || '(none)')
    }
  } catch (err: any) {
    logger.warn('[resolve-upstream] failed to read config.yaml: %s', err?.message)
  }

  // ── 3. Hermes CLI profile config.yaml（兼容旧版 hermes gateway run）─
  try {
    const profileDir = getProfileDir(profile)
    const configPath = join(profileDir, 'config.yaml')
    if (existsSync(configPath)) {
      const raw = readFileSync(configPath, 'utf-8')
      const cfg = (yaml.load(raw, { json: true }) as any) || {}
      const extra = cfg?.platforms?.api_server?.extra
      if (extra) {
        const port = typeof extra?.port === 'number' ? extra.port : parseInt(extra?.port, 10) || defaultGatewayPort
        const host = extra?.host || defaultHost
        const upstream = `http://${host}:${port}`
        let apiKey: string | undefined
        try {
          const envPath = join(profileDir, '.env')
          if (existsSync(envPath)) {
            const envContent = readFileSync(envPath, 'utf-8')
            const match = envContent.match(/^API_SERVER_KEY\s*=\s*"?([^"\n]+)"?/m)
            apiKey = match?.[1]?.trim() || undefined
          }
        } catch {}
        logger.info('[resolve-upstream] hermes profile config: upstream=%s profile=%s', upstream, profile)
        return { upstream, apiKey, providerType: 'default' }
      }
    }
  } catch { /* fall through */ }

  // ── 4. 兜底 ──────────────────────────────────────────────────────
  logger.warn('[resolve-upstream] no upstream configured — falling back to http://%s:%d', defaultHost, defaultGatewayPort)
  return { upstream: `http://${defaultHost}:${defaultGatewayPort}`, apiKey: undefined, providerType: 'default' }
}

// ---------------------------------------------------------------------------
// Anthropic direct mode adapter
// Converts Hermes session state → Anthropic /v1/messages, maps SSE events back
// to the OpenAI Responses API event format used by applyResponseStreamEvent.
// ---------------------------------------------------------------------------
const ANTHROPIC_API_BASE = 'https://api.anthropic.com'
const ANTHROPIC_API_VERSION = '2023-06-01'
const DEFAULT_ANTHROPIC_MODEL = 'claude-3-5-sonnet-20241022'
const DEFAULT_MAX_TOKENS = 8192

async function* streamAnthropicAsHermesEvents(
  resBody: ReadableStream<Uint8Array>,
): AsyncGenerator<{ type: string; data: any }> {
  let messageId = ''
  let inputTokens = 0
  let outputTokens = 0
  let modelName = ''
  let fullText = ''

  for await (const frame of readSseFrames(resBody)) {
    if (!frame.data || frame.data === '[DONE]') continue
    let parsed: any
    try { parsed = JSON.parse(frame.data) } catch { continue }
    const t: string = parsed.type || ''

    if (t === 'message_start') {
      messageId = parsed.message?.id || `anthr_${Date.now().toString(36)}`
      modelName = parsed.message?.model || ''
      inputTokens = parsed.message?.usage?.input_tokens || 0
      yield { type: 'response.created', data: { type: 'response.created', response: { id: messageId, model: modelName, status: 'in_progress' } } }
    } else if (t === 'content_block_delta' && parsed.delta?.type === 'text_delta') {
      const chunk: string = parsed.delta.text || ''
      if (chunk) {
        fullText += chunk
        yield { type: 'response.output_text.delta', data: { type: 'response.output_text.delta', delta: chunk } }
      }
    } else if (t === 'message_delta') {
      outputTokens = parsed.usage?.output_tokens || 0
    } else if (t === 'message_stop') {
      yield {
        type: 'response.completed',
        data: {
          type: 'response.completed',
          response: {
            id: messageId,
            model: modelName,
            output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: fullText }] }],
            usage: { input_tokens: inputTokens, output_tokens: outputTokens },
          },
        },
      }
    } else if (t === 'error') {
      yield { type: 'response.failed', data: { type: 'response.failed', error: parsed.error?.message || 'Anthropic API error' } }
    }
  }
}

async function handleAnthropicDirect(
  apiKey: string,
  model: string | undefined,
  fullInstructions: string,
  input: string | ContentBlock[],
  session_id: string | undefined,
  runMarker: string | undefined,
  sessionMap: Map<string, SessionState>,
  nsp: ReturnType<Server['of']>,
  socket: Socket,
  emit: (event: string, payload: any) => void,
  dequeueNextQueuedRun: (socket: Socket, sessionId: string) => void,
  markCompleted: (event: string, runId?: string, queueLen?: number) => Promise<void>,
) {
  // Build Anthropic messages from session state (skip compression for simplicity)
  const anthropicMessages: { role: 'user' | 'assistant'; content: string }[] = []
  if (session_id) {
    const state = sessionMap.get(session_id)
    if (state?.messages) {
      // All messages except the last one (current user input already added to state)
      const history = state.messages.slice(0, -1)
      for (const m of history) {
        if (m.role !== 'user' && m.role !== 'assistant') continue
        const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
        if (!content.trim()) continue
        anthropicMessages.push({ role: m.role as 'user' | 'assistant', content })
      }
    }
  }
  // Append current user input
  const inputStr = typeof input === 'string' ? input : (input as any[]).map((b: any) => b.text || '').join('')
  anthropicMessages.push({ role: 'user', content: inputStr })

  const anthropicModel = model || DEFAULT_ANTHROPIC_MODEL
  const reqBody: Record<string, any> = {
    model: anthropicModel,
    max_tokens: DEFAULT_MAX_TOKENS,
    messages: anthropicMessages,
    stream: true,
  }
  if (fullInstructions?.trim()) reqBody.system = fullInstructions

  const abortController = new AbortController()
  if (session_id) {
    const state = sessionMap.get(session_id)
    if (state) { state.abortController = abortController; state.runId = undefined }
  }

  logger.info('[chat-run-socket] anthropic direct model=%s messages=%d', anthropicModel, anthropicMessages.length)

  let res: Response
  try {
    res = await fetch(`${ANTHROPIC_API_BASE}/v1/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': ANTHROPIC_API_VERSION,
      },
      body: JSON.stringify(reqBody),
      signal: abortController.signal,
    })
  } catch (err: any) {
    await markCompleted('run.failed')
    emit('run.failed', { event: 'run.failed', error: `Anthropic API 连接失败: ${err.message}` })
    return
  }

  if (!res.ok) {
    const errText = await res.text().catch(() => '')
    logger.error('[chat-run-socket] anthropic API error %d: %s', res.status, errText)
    await markCompleted('run.failed')
    emit('run.failed', { event: 'run.failed', error: `Anthropic API ${res.status}: ${errText}` })
    return
  }
  if (!res.body) {
    await markCompleted('run.failed')
    emit('run.failed', { event: 'run.failed', error: 'Anthropic API 响应流为空' })
    return
  }

  let responseId: string | undefined
  for await (const evt of streamAnthropicAsHermesEvents(res.body as ReadableStream<Uint8Array>)) {
    if (session_id) {
      const state = sessionMap.get(session_id)
      if (state) {
        const mapped = applyResponseStreamEvent(state, session_id, runMarker, evt.type, evt.data)
        if (mapped) {
          if (mapped.runId) { responseId = mapped.runId; state.runId = responseId }
          emit(mapped.event, mapped.payload)
        }
      }
    }
    if (evt.type === 'response.completed' || evt.type === 'response.failed') {
      const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
      await markCompleted(evt.type === 'response.completed' ? 'run.completed' : 'run.failed', responseId, queueLen)
      const finalData = evt.data.response || evt.data
      if (evt.type === 'response.completed' && session_id) {
        const usage = finalData.usage || {}
        updateUsage(session_id, {
          inputTokens: usage.input_tokens || 0,
          outputTokens: usage.output_tokens || 0,
          cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0,
          model: finalData.model || anthropicModel,
          profile: sessionMap.get(session_id)?.profile,
        })
      }
      const eventName = evt.type === 'response.completed' ? 'run.completed' : 'run.failed'
      const outputText = (finalData.output || []).map((o: any) =>
        (o.content || []).map((c: any) => c.text || '').join('')
      ).join('') || ''
      emit(eventName, { event: eventName, run_id: responseId, response_id: responseId, output: outputText, usage: finalData.usage, queue_remaining: queueLen })
      if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
      return
    }
  }
  // Stream ended without terminal event
  const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
  await markCompleted('run.failed', responseId, queueLen)
  emit('run.failed', { event: 'run.failed', error: 'Anthropic stream ended without completion' })
  if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
}

// ---------------------------------------------------------------------------
// OpenAI Chat Completions direct mode adapter
// 支持所有 OpenAI 兼容接口：DeepSeek、通义千问、Kimi、Moonshot、GLM 等
// ---------------------------------------------------------------------------

async function* streamOpenAIChatAsHermesEvents(
  resBody: ReadableStream<Uint8Array>,
  fallbackModel: string,
): AsyncGenerator<{ type: string; data: any }> {
  const messageId = `chatcmpl_${Date.now().toString(36)}`
  let yielded = false
  let fullText = ''
  let modelName = fallbackModel

  for await (const frame of readSseFrames(resBody)) {
    if (!frame.data || frame.data === '[DONE]') {
      if (frame.data === '[DONE]') break
      continue
    }
    let parsed: any
    try { parsed = JSON.parse(frame.data) } catch { continue }

    if (!yielded) {
      modelName = parsed.model || fallbackModel
      yield { type: 'response.created', data: { type: 'response.created', response: { id: messageId, model: modelName, status: 'in_progress' } } }
      yielded = true
    }

    const delta: string = parsed.choices?.[0]?.delta?.content || ''
    if (delta) {
      fullText += delta
      yield { type: 'response.output_text.delta', data: { type: 'response.output_text.delta', delta } }
    }

    // finish_reason 出现即流结束
    const finishReason = parsed.choices?.[0]?.finish_reason
    if (finishReason) {
      const usage = parsed.usage || {}
      yield {
        type: 'response.completed',
        data: {
          type: 'response.completed',
          response: {
            id: messageId,
            model: modelName,
            output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: fullText }] }],
            usage: { input_tokens: usage.prompt_tokens || 0, output_tokens: usage.completion_tokens || 0 },
          },
        },
      }
      return
    }
  }

  // 流结束但未收到 finish_reason（部分 provider 的行为）
  yield {
    type: 'response.completed',
    data: {
      type: 'response.completed',
      response: {
        id: messageId,
        model: modelName,
        output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: fullText }] }],
        usage: { input_tokens: 0, output_tokens: 0 },
      },
    },
  }
}

async function handleOpenAIChatDirect(
  baseUrl: string,
  apiKey: string,
  model: string | undefined,
  fullInstructions: string,
  input: string | ContentBlock[],
  session_id: string | undefined,
  runMarker: string | undefined,
  sessionMap: Map<string, SessionState>,
  nsp: ReturnType<Server['of']>,
  socket: Socket,
  emit: (event: string, payload: any) => void,
  dequeueNextQueuedRun: (socket: Socket, sessionId: string) => void,
  markCompleted: (event: string, runId?: string, queueLen?: number) => Promise<void>,
) {
  // 从会话历史构造 messages 数组
  const messages: { role: 'system' | 'user' | 'assistant'; content: string }[] = []
  if (fullInstructions?.trim()) {
    messages.push({ role: 'system', content: fullInstructions })
  }
  if (session_id) {
    const state = sessionMap.get(session_id)
    if (state?.messages) {
      const history = state.messages.slice(0, -1)
      for (const m of history) {
        if (m.role !== 'user' && m.role !== 'assistant') continue
        const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
        if (c.trim()) messages.push({ role: m.role as 'user' | 'assistant', content: c })
      }
    }
  }
  const inputStr = typeof input === 'string' ? input : (input as any[]).map((b: any) => b.text || '').join('')
  messages.push({ role: 'user', content: inputStr })

  // 兼容各 provider 的路径：优先 /v1/chat/completions，baseUrl 可能已含 /v1
  const chatUrl = baseUrl.endsWith('/v1')
    ? `${baseUrl}/chat/completions`
    : `${baseUrl}/v1/chat/completions`

  const chatModel = model || 'deepseek-chat'  // caller 已传入 configModel，'deepseek-chat' 仅作最终保底
  const reqBody = { model: chatModel, messages, stream: true }

  const abortController = new AbortController()
  if (session_id) {
    const state = sessionMap.get(session_id)
    if (state) { state.abortController = abortController; state.runId = undefined }
  }

  logger.info('[chat-run-socket] openai-chat direct url=%s model=%s msgs=%d', chatUrl, chatModel, messages.length)

  let res: Response
  try {
    res = await fetch(chatUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${apiKey}` },
      body: JSON.stringify(reqBody),
      signal: abortController.signal,
    })
  } catch (err: any) {
    await markCompleted('run.failed')
    emit('run.failed', { event: 'run.failed', error: `LLM API 连接失败 (${chatUrl}): ${err.message}` })
    return
  }

  if (!res.ok) {
    const errText = await res.text().catch(() => '')
    logger.error('[chat-run-socket] openai-chat API error %d: %s', res.status, errText)
    await markCompleted('run.failed')
    emit('run.failed', { event: 'run.failed', error: `LLM API ${res.status}: ${errText}` })
    return
  }
  if (!res.body) {
    await markCompleted('run.failed')
    emit('run.failed', { event: 'run.failed', error: 'LLM API 响应流为空' })
    return
  }

  let responseId: string | undefined
  for await (const evt of streamOpenAIChatAsHermesEvents(res.body as ReadableStream<Uint8Array>, chatModel)) {
    if (session_id) {
      const state = sessionMap.get(session_id)
      if (state) {
        const mapped = applyResponseStreamEvent(state, session_id, runMarker, evt.type, evt.data)
        if (mapped) {
          if (mapped.runId) { responseId = mapped.runId; state.runId = responseId }
          emit(mapped.event, mapped.payload)
        }
      }
    }
    if (evt.type === 'response.completed' || evt.type === 'response.failed') {
      const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
      await markCompleted(evt.type === 'response.completed' ? 'run.completed' : 'run.failed', responseId, queueLen)
      const finalData = evt.data.response || evt.data
      if (evt.type === 'response.completed' && session_id) {
        const usage = finalData.usage || {}
        updateUsage(session_id, {
          inputTokens: usage.input_tokens || 0, outputTokens: usage.output_tokens || 0,
          cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0,
          model: finalData.model || chatModel,
          profile: sessionMap.get(session_id)?.profile,
        })
      }
      const eventName = evt.type === 'response.completed' ? 'run.completed' : 'run.failed'
      const outputText = (finalData.output || []).map((o: any) =>
        (o.content || []).map((c: any) => c.text || '').join('')
      ).join('') || ''
      emit(eventName, { event: eventName, run_id: responseId, response_id: responseId, output: outputText, usage: finalData.usage, queue_remaining: queueLen })
      if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
      return
    }
  }
  const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
  await markCompleted('run.failed', responseId, queueLen)
  emit('run.failed', { event: 'run.failed', error: 'LLM stream ended without completion' })
  if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
}

// ---------------------------------------------------------------------------
// Original loadSessionStateFromDb (unchanged)
// ---------------------------------------------------------------------------

export async function loadSessionStateFromDb(sid: string, _sessionMap: Map<string, SessionState>): Promise<SessionState> {
  try {
    const actualDetail = getSessionDetailPaginated(sid)

    const messages = actualDetail?.messages ? handleMessage(actualDetail.messages, sid) : []

    let inputTokens: number
    let outputTokens: number
    const snapshot = getCompressionSnapshot(sid)
    if (snapshot && snapshot.lastMessageIndex >= 0 && snapshot.lastMessageIndex < messages.length) {
      const newMessages = messages.slice(snapshot.lastMessageIndex + 1)
      const newUsage = estimateUsageTokensFromMessages(newMessages)
      inputTokens = countTokens(SUMMARY_PREFIX + snapshot.summary) +
        newUsage.inputTokens
      outputTokens = newUsage.outputTokens
    } else {
      const usage = estimateUsageTokensFromMessages(messages)
      inputTokens = usage.inputTokens
      outputTokens = usage.outputTokens
    }

    logger.info('[chat-run-socket] loaded session %s from DB (%d messages)', sid, messages.length)
    return {
      messages,
      isWorking: false,
      events: [],
      inputTokens,
      outputTokens,
      queue: [],
    }
  } catch (err) {
    logger.warn(err, '[chat-run-socket] failed to load session %s from DB', sid)
    return { messages: [], isWorking: false, events: [], queue: [] }
  }
}

// ---------------------------------------------------------------------------
// handleApiRun — now wires upstream + apiKey from gateway config
// ---------------------------------------------------------------------------

export async function handleApiRun(
  nsp: ReturnType<Server['of']>,
  socket: Socket,
  data: { input: string | ContentBlock[]; session_id?: string; model?: string; provider?: string; instructions?: string; source?: string },
  profile: string,
  sessionMap: Map<string, SessionState>,
  skipUserMessage = false,
  dequeueNextQueuedRun: (socket: Socket, sessionId: string, fallbackProfile?: string) => void,
) {
  const { input, session_id, model, provider, instructions } = data

  // Build full instructions with system prompt + workspace context
  let fullInstructions = instructions
    ? `${getSystemPrompt()}\n${instructions}`
    : getSystemPrompt()
  if (session_id) {
    const sessionRow = getSession(session_id)
    if (sessionRow?.workspace) {
      const workspaceCtx = `[Current working directory: ${sessionRow.workspace}]`
      fullInstructions = `\n${workspaceCtx}\n${fullInstructions}`
    }
  }

  // ── 注入 TAHP 工程上下文（Skill 按需加载规范 + skills / 约束 / playbooks）──
  try {
    const inputText = extractInputText(input)
    const preferredSkillIds = [
      ...extractPreferredSkillIds(inputText),
      ...(instructions ? extractPreferredSkillIds(instructions) : []),
    ]
    const tahpCtx = buildFullTahpSystemContext(inputText, { preferredSkillIds })
    if (tahpCtx) {
      fullInstructions = `${fullInstructions}\n\n${tahpCtx}`
    }
  } catch (ctxErr) {
    logger.warn('[chat-run] 工程上下文注入失败（跳过）: %s', ctxErr)
  }

  // Resolve gateway upstream URL + API key from profile config
  const { upstream, apiKey, providerType, defaultModel: configModel } = resolveGatewayUpstream(profile)
  logger.info('[chat-run-socket] api run profile=%s upstream=%s', profile, upstream)

  // ── 上游健康检查（非阻塞，仅警告）────────────────────────────────
  // TAHP 模式：不强依赖 Hermes gateway，健康检查失败只 warn，不中断请求。
  // 连接失败时在 fetch 阶段再处理具体错误。
  // 只要 providerType 不是 'default'（兜底 8642）就跳过 gateway 健康检查
  const isTahpDirectMode = providerType !== 'default'
  if (!isTahpDirectMode) {
    // 仅在未配置直连模式时才做 gateway 健康检查
    try {
      const healthRes = await fetch(`${upstream}/health`, { signal: AbortSignal.timeout(3000) })
      if (!healthRes.ok) {
        logger.warn('[chat-run-socket] gateway health check returned %d for profile=%s', healthRes.status, profile)
      }
    } catch {
      const emit = (event: string, payload: any) => {
        const tagged = session_id ? { ...payload, session_id } : payload
        if (session_id) {
          nsp.to(`session:${session_id}`).emit(event, tagged)
        } else if (socket.connected) {
          socket.emit(event, tagged)
        }
      }
      if (session_id) {
        const state = sessionMap.get(session_id)
        if (state) {
          state.isWorking = false
          state.profile = undefined
          state.activeRunMarker = undefined
        }
      }
      emit('run.failed', {
        event: 'run.failed',
        error: [
          `LLM 服务不可达（${upstream}）。`,
          `请选择以下任一方式配置：`,
          `① 设置环境变量 TAHP_LLM_UPSTREAM=http://your-api-proxy 和 TAHP_API_KEY=sk-xxx`,
          `② 启动本地 Hermes gateway：hermes gateway run`,
          `③ 在 tahp-console/.env 中配置 ANTHROPIC_API_KEY=sk-ant-xxx`,
        ].join('\n'),
      })
      return
    }
  } else {
    logger.info('[chat-run-socket] TAHP direct mode — skipping gateway health check, upstream=%s', upstream)
  }

  const runMarker = session_id
    ? `resp_run_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
    : undefined

  const now = Math.floor(Date.now() / 1000)
  if (session_id) {
    let state = sessionMap.get(session_id)
    if (!state) {
      state = getSession(session_id)
        ? await loadSessionStateFromDb(session_id, sessionMap)
        : { messages: [], isWorking: false, events: [], queue: [] }
      sessionMap.set(session_id, state)
    }
    state.isWorking = true
    state.profile = profile
    state.source = 'api_server'
    state.activeRunMarker = runMarker

    if (!skipUserMessage) {
      const inputStr = contentBlocksToString(input)
      state.messages.push({
        id: state.messages.length + 1,
        session_id,
        runMarker,
        role: 'user',
        content: inputStr,
        timestamp: now,
      })

      if (!getSession(session_id)) {
        const previewText = extractTextForPreview(input)
        const preview = previewText.replace(/[\r\n]/g, ' ').substring(0, 100)
        createSession({ id: session_id, profile, source: 'api_server', model, provider, title: preview })
      }

      addMessage({
        session_id,
        role: 'user',
        content: inputStr,
        timestamp: now,
      })
    } else {
      const inputStr = contentBlocksToString(input)
      state.messages.push({
        id: state.messages.length + 1,
        session_id,
        runMarker,
        role: 'user',
        content: inputStr,
        timestamp: now,
      })
      if (!getSession(session_id)) {
        const previewText = extractTextForPreview(input)
        const preview = previewText.replace(/[\r\n]/g, ' ').substring(0, 100)
        createSession({ id: session_id, profile, source: 'api_server', model, provider, title: preview })
      }
      addMessage({
        session_id,
        role: 'user',
        content: inputStr,
        timestamp: now,
      })
    }

    socket.join(`session:${session_id}`)
  }

  const emit = (event: string, payload: any) => {
    const tagged = session_id ? { ...payload, session_id } : payload
    if (session_id) {
      nsp.to(`session:${session_id}`).emit(event, tagged)
    } else if (socket.connected) {
      socket.emit(event, tagged)
    }
  }
  try {
    // ── Anthropic 直连 (/v1/messages) ──────────────────────────────────────
    if (providerType === 'anthropic' && upstream === 'anthropic://direct' && apiKey) {
      await handleAnthropicDirect(
        apiKey, model || configModel, fullInstructions, input,
        session_id, runMarker, sessionMap, nsp, socket, emit,
        (s, sid) => dequeueNextQueuedRun(s, sid),
        async (event, runId?, queueLen?) => {
          if (session_id) await markApiCompleted(nsp, socket, session_id, sessionMap, { event, run_id: runId })
        },
      )
      return
    }

    // ── OpenAI Chat Completions 直连（DeepSeek/通义/Kimi 等 OpenAI 兼容 provider）──
    if (providerType === 'openai-chat' && apiKey) {
      await handleOpenAIChatDirect(
        upstream, apiKey, model || configModel, fullInstructions, input,
        session_id, runMarker, sessionMap, nsp, socket, emit,
        (s, sid) => dequeueNextQueuedRun(s, sid),
        async (event, runId?, queueLen?) => {
          if (session_id) await markApiCompleted(nsp, socket, session_id, sessionMap, { event, run_id: runId })
        },
      )
      return
    }

    const body: Record<string, any> = { input }
    if (model) body.model = model
    body.instructions = fullInstructions
    if (session_id) {
      const sessionRow = getSession(session_id)
      const compressed = await buildCompressedHistory(session_id, profile, upstream, apiKey, emit, sessionMap, {
        model: sessionRow?.model || model,
        provider: sessionRow?.provider || provider,
      })
      if (compressed.length > 0) {
        body.conversation_history = compressed
      }
    }

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
    if (isContentBlockArray(input)) {
      const parts = await convertContentBlocks(input)
      body.input = [{ role: 'user', content: parts }]
    }

    if (body.conversation_history && Array.isArray(body.conversation_history)) {
      body.conversation_history = convertHistoryFormat(body.conversation_history)
    }
    body.stream = true
    body.store = false

    const abortController = new AbortController()
    if (session_id) {
      const state = getOrCreateSession(sessionMap, session_id)
      state.isWorking = true
      state.runId = undefined
      state.abortController = abortController
    }

    const res = await fetch(`${upstream}/v1/responses`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: abortController.signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
      if (session_id) await markApiCompleted(nsp, socket, session_id, sessionMap, { event: 'run.failed' })
      emit('run.failed', { event: 'run.failed', error: `Upstream ${res.status}: ${text}`, queue_remaining: queueLen })
      if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
      return
    }
    if (!res.body) {
      const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
      if (session_id) await markApiCompleted(nsp, socket, session_id, sessionMap, { event: 'run.failed' })
      emit('run.failed', { event: 'run.failed', error: 'Upstream response stream missing', queue_remaining: queueLen })
      if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
      return
    }

    let responseId: string | undefined
    for await (const frame of readSseFrames(res.body)) {
      let parsed: any
      try {
        parsed = JSON.parse(frame.data)
      } catch {
        continue
      }
      const upstreamEvent = parsed.type || frame.event || parsed.event
      logger.info('[chat-run-socket] upstream response event: %s', upstreamEvent)

      if (session_id) {
        const state = sessionMap.get(session_id)
        if (state) {
          const mapped = applyResponseStreamEvent(state, session_id, runMarker, upstreamEvent, parsed)
          if (mapped) {
            if (mapped.runId) {
              responseId = mapped.runId
              state.runId = responseId
            }
            emit(mapped.event, mapped.payload)
          }
        }
      }

      if (upstreamEvent === 'response.completed' || upstreamEvent === 'response.failed') {
        if (session_id && sessionMap.get(session_id)?.activeRunMarker !== runMarker) {
          logger.info({
            sessionId: session_id,
            runId: responseId,
            event: upstreamEvent,
          }, '[chat-run-socket] suppressing stale API terminal event')
          return
        }
        if (session_id && sessionMap.get(session_id)?.isAborting) {
          logger.info({
            sessionId: session_id,
            runId: responseId,
            event: upstreamEvent,
          }, '[chat-run-socket][abort] suppressing upstream terminal event during abort')
          return
        }
        const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
        const nextQueuedRun = session_id && queueLen > 0
          ? sessionMap.get(session_id)?.queue?.[0]
          : undefined
        if (session_id) await markApiCompleted(nsp, socket, session_id, sessionMap, {
          event: upstreamEvent === 'response.completed' ? 'run.completed' : 'run.failed',
          run_id: responseId,
          keepWorking: Boolean(nextQueuedRun),
          nextSource: nextQueuedRun?.source,
        })
        const finalOutput = parsed.response || parsed
        const finalText = extractResponseText(finalOutput)
        if (upstreamEvent === 'response.completed' && session_id) {
          const usage = finalOutput.usage || {}
          updateUsage(session_id, {
            inputTokens: usage.input_tokens ?? usage.inputTokens ?? 0,
            outputTokens: usage.output_tokens ?? usage.outputTokens ?? 0,
            cacheReadTokens: usage.cache_read_tokens ?? usage.cacheReadTokens ?? 0,
            cacheWriteTokens: usage.cache_write_tokens ?? usage.cacheWriteTokens ?? 0,
            reasoningTokens: usage.reasoning_tokens ?? usage.reasoningTokens ?? 0,
            model: finalOutput.model || '',
            profile: sessionMap.get(session_id)?.profile,
          })
        }
        const eventName = upstreamEvent === 'response.completed' ? 'run.completed' : 'run.failed'
        emit(eventName, {
          event: eventName,
          run_id: responseId || finalOutput.id,
          response_id: responseId || finalOutput.id,
          output: finalText,
          usage: finalOutput.usage,
          error: finalOutput.error || parsed.error,
          queue_remaining: queueLen,
        })
        if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
        return
      }
    }
    const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
    if (session_id && sessionMap.get(session_id)?.activeRunMarker !== runMarker) {
      logger.info({
        sessionId: session_id,
        runId: responseId,
      }, '[chat-run-socket] suppressing stale API stream end')
      return
    }
    if (session_id) await markApiCompleted(nsp, socket, session_id, sessionMap, { event: 'run.failed', run_id: responseId })
    emit('run.failed', {
      event: 'run.failed',
      run_id: responseId,
      response_id: responseId,
      error: 'Response stream ended without a terminal event',
      queue_remaining: queueLen,
    })
    if (session_id && queueLen > 0) dequeueNextQueuedRun(socket, session_id)
  } catch (err: any) {
    const queueLen = session_id ? sessionMap.get(session_id)?.queue?.length ?? 0 : 0
    if (session_id) {
      const state = sessionMap.get(session_id)
      if (state?.activeRunMarker !== runMarker || err?.name === 'AbortError') {
        logger.info({
          sessionId: session_id,
                 runMarker,
          error: err?.message || String(err),
        }, '[chat-run-socket] suppressing stale/aborted API stream error')
        return
      }
      void markApiCompleted(nsp, socket, session_id, sessionMap, { event: 'run.failed' }).then(() => {
        emit('run.failed', { event: 'run.failed', error: err.message, queue_remaining: queueLen })
        if (queueLen > 0) dequeueNextQueuedRun(socket, session_id)
      })
    } else {
      emit('run.failed', { event: 'run.failed', error: err.message })
    }
  }
}

async function markApiCompleted(
  nsp: ReturnType<Server['of']>,
  _socket: Socket,
  sessionId: string,
  sessionMap: Map<string, SessionState>,
  info: { event: string; run_id?: string; keepWorking?: boolean; nextSource?: ChatRunSource },
) {
  const state = sessionMap.get(sessionId)
  if (state) {
    if (state.isAborting) {
      logger.info({
        sessionId,
        runId: state.runId,
      }, '[chat-run-socket][abort] terminal upstream event observed; abort handler will finish cleanup')
      return
    }
    state.isWorking = Boolean(info.keepWorking)
    state.abortController = undefined
    state.runId = undefined
    state.events = []
    flushResponseRunToDb(state, sessionId)
    state.responseRun = undefined
    state.activeRunMarker = undefined
    if (info.keepWorking) {
      state.source = info.nextSource
    } else {
      state.profile = undefined
    }
  }
}
