/**
 * TAHP — Gerrit Code Review Agent 编排
 *
 * 固定使用 gerrit_code_review Skill，经 Agent Bridge 执行评审，
 * 通过 TaskStream 推送进度，支持多轮会话。
 */
import { randomBytes } from 'crypto'
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { getTaskStream } from './task-stream'
import { tahpPaths } from './paths'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeChatStarted,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import {
  buildFullTahpSystemContext,
  getTahpSkillsRoot,
  tahpSkillMdPath,
} from './context-injector'
import { saveAgentPromptLog } from './prompt-log'
import { humanizeAgentError } from './adapt-agent-health'
import { extractModules, extractP0TestSuggestions } from './gerrit-review-report'
import { recommendTestCases } from './gerrit-case-recommendation'
import {
  isGerritConfigured,
  writeRuntimeCredFile,
  getGerritConfig,
  DEFAULT_GERRIT_HOST,
} from './gerrit-credentials'

export const GERRIT_NOT_CONFIGURED_ERROR =
  'gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号'

export const GERRIT_REVIEW_SKILL_ID = 'gerrit_code_review'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

export interface GerritReviewMessage {
  role: 'user' | 'assistant'
  content: string
  taskId?: string
  at: string
}

export interface GerritReviewSessionCtx {
  sessionId: string
  messages: GerritReviewMessage[]
  lastTaskId?: string
  lastResponse?: string
  createdAt: string
  updatedAt: string
}

export interface GerritReviewTaskCtx {
  taskId: string
  sessionId: string
  userMessage: string
  startedAt: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  llmResponse?: string
  p0Items?: string[]
  skillsUsed: string[]
  toolsUsed: Array<{ name: string; status: 'running' | 'done' | 'error' }>
  completedAt?: string
  error?: string
}

const sessionCtx = new Map<string, GerritReviewSessionCtx>()
const taskCtx = new Map<string, GerritReviewTaskCtx>()
const taskRuntime = new Map<string, { sessionId: string; interruptRequested: boolean }>()

function genSessionId(): string {
  return `sess-gerrit-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function genTaskId(): string {
  return `task-gerrit-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const obj = args as Record<string, unknown>
  const keys = Object.keys(obj)
  if (keys.length === 0) return ''
  const k = keys[0]
  const v = obj[k]
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return `(${k}=${s.length > 60 ? s.slice(0, 60) + '…' : s})`
}

export function buildGerritReviewInstructions(
  userMessage: string,
  cred?: { credFilePath: string; host: string },
): string {
  const skillPath = tahpSkillMdPath(GERRIT_REVIEW_SKILL_ID)
  const skillsDir = getTahpSkillsRoot()
  const gerritHost = cred?.host || getGerritConfig()?.host || DEFAULT_GERRIT_HOST
  const credFileLine = cred?.credFilePath
    ? `7. 调用 \`fetch_review_bundle.py\` 时**必须**使用 \`--cred-file ${cred.credFilePath}\`，禁止依赖默认 cred.json 或编造凭证。\n8. Gerrit Host: ${gerritHost}`
    : ''

  const base = `你是 TAHP「Gerrit Code Review」专家，负责使用传音 Gerrit 评审 Skill 对代码变更进行结构化审查。

# 必须遵守
1. **先 Read 主控 Skill 全文**：\`${skillPath}\`（\`${GERRIT_REVIEW_SKILL_ID}\`），严格按其中工作流执行。
2. 用户输入可能是 Gerrit change URL、topic URL、\`topic:xxx\` 或纯 change number；按 Skill 调用 \`fetch_review_bundle.py\` 拉取 diff。
3. 分析报告必须包含以下 5 个章节（与 Skill report-template 一致）：
   - ## 1. 基本信息
   - ## 2. 问题统计
   - ## 3. 详细问题列表和改善建议
   - ## 4. 影响范围
   - ## 5. 测试建议（必须含 \`### P0 - 必须测试\`、\`### P1 - 强烈建议\`、\`### P2 - 建议测试\`）
4. Topic 评审须产出**一份合并报告**，P0 列表去重合并。
5. 必须真实调用工具执行 fetch 与分析；禁止编造 diff 内容。
6. 完成后在终端摘要中打印 report_path。
${credFileLine ? `${credFileLine}\n` : ''}
# 工程 Skill 根目录
\`${skillsDir}\`
`

  const tahpCtx = buildFullTahpSystemContext(userMessage, {
    scenario: 'adapt_debug',
    preferredSkillIds: [GERRIT_REVIEW_SKILL_ID],
  })
  return tahpCtx ? `${base}\n\n${tahpCtx}` : base
}

function buildGerritReviewUserMessage(
  message: string,
  session: GerritReviewSessionCtx,
): string {
  const lines: string[] = ['# Gerrit Code Review 任务', '']

  if (session.messages.length > 1 || session.lastResponse) {
    lines.push('## 对话历史（摘要）')
    const recent = session.messages.slice(-6, -1)
    for (const m of recent) {
      const preview = m.content.length > 500 ? m.content.slice(0, 500) + '…' : m.content
      lines.push(`- **${m.role === 'user' ? '用户' : '助手'}**: ${preview}`)
    }
    if (session.lastResponse) {
      lines.push('')
      lines.push('## 上一轮评审输出（节选，供追问参考）')
      lines.push(session.lastResponse.slice(0, 4000))
    }
    lines.push('')
  }

  lines.push('## 当前用户输入')
  lines.push(message.trim())
  lines.push('')
  lines.push('请按 gerrit_code_review Skill 执行评审；若为追问，在上一轮结论基础上补充分析。')
  return lines.join('\n')
}

async function runAgentChat(
  sessionId: string,
  instructions: string,
  userMessage: string,
  cb: {
    onText: (delta: string) => void
    onToolStarted: (toolName: string, args: unknown, toolCallId: unknown) => void
    onToolCompleted: (toolName: string, isError: boolean, toolCallId: unknown) => void
    onReasoning?: (text: string) => void
  },
): Promise<{ fullResponse: string }> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error(
      'Agent Bridge 未运行。请确认 hermes-agent-main 已初始化（npm run setup:agent）。',
    )
  }

  const started: AgentBridgeChatStarted = await sharedBridgeClient.chat(
    sessionId,
    userMessage,
    undefined,
    instructions,
    'default',
  )

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''
  let lastChunk: AgentBridgeOutput | null = null

  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 250 })) {
    lastChunk = chunk
    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'tool.started') {
        cb.onToolStarted((ev.tool_name as string) || 'unknown-tool', ev.args, ev.tool_call_id)
      } else if (evType === 'tool.completed') {
        cb.onToolCompleted((ev.tool_name as string) || 'unknown-tool', ev.is_error === true, ev.tool_call_id)
      } else if ((evType === 'reasoning.delta' || evType === 'thinking.delta') && cb.onReasoning) {
        cb.onReasoning(String(ev.text || ''))
      }
    }
    if (chunk.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      if (cleaned) {
        fullResponse += cleaned
        cb.onText(cleaned)
      }
    }
    if (chunk.done) {
      if (chunk.status === 'error') {
        throw new Error(humanizeAgentError(chunk.error || 'Agent 运行出错'))
      }
      if (chunk.status === 'interrupted') throw new Error('Agent 运行被中断')
      break
    }
  }

  if (!lastChunk?.done) throw new Error('Agent 流式输出意外终止')
  if (lastChunk.error) {
    throw new Error(humanizeAgentError(lastChunk.error))
  }
  return { fullResponse }
}

function reportDir(): string {
  const d = join(tahpPaths.reportsDir, 'gerrit-review')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function getGerritReviewSession(sessionId: string): GerritReviewSessionCtx | undefined {
  return sessionCtx.get(sessionId)
}

export function getGerritReviewTask(taskId: string): GerritReviewTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export async function cancelGerritReviewTask(
  taskId: string,
): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running'; error?: string }> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (ctx.status === 'completed' || ctx.status === 'failed' || ctx.status === 'cancelled') {
    return { ok: false, error: `任务已结束，当前状态: ${ctx.status}` }
  }

  const agentSessionId = `tahp-gerrit-${taskId}`
  const control = taskRuntime.get(taskId) || { sessionId: agentSessionId, interruptRequested: false }
  control.interruptRequested = true
  taskRuntime.set(taskId, control)

  emit(taskId, 'task.message', { level: 'warn', text: '已请求停止评审，等待 Agent 结束...' })
  logger.warn({ taskId, sessionId: control.sessionId }, '[gerrit-review] interrupt requested')

  setImmediate(() => {
    sharedBridgeClient.interrupt(control.sessionId, '用户手动停止 Gerrit 评审').catch((err) => {
      logger.warn({ err: (err as Error).message, taskId }, '[gerrit-review] interrupt rpc failed')
    })
  })
  return { ok: true, action: 'interrupted_running' }
}

export function sendGerritReviewChat(input: {
  sessionId?: string
  message: string
}): { ok: true; sessionId: string; taskId: string } | { ok: false; error: string } {
  const message = String(input.message || '').trim()
  if (!message) return { ok: false, error: '消息不能为空' }
  if (!isGerritConfigured()) {
    return { ok: false, error: GERRIT_NOT_CONFIGURED_ERROR }
  }

  let session: GerritReviewSessionCtx
  if (input.sessionId && sessionCtx.has(input.sessionId)) {
    session = sessionCtx.get(input.sessionId)!
  } else {
    const sessionId = genSessionId()
    session = {
      sessionId,
      messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    sessionCtx.set(sessionId, session)
  }

  const taskId = genTaskId()
  const now = new Date().toISOString()
  session.messages.push({ role: 'user', content: message, taskId, at: now })
  session.updatedAt = now
  session.lastTaskId = taskId

  const ctx: GerritReviewTaskCtx = {
    taskId,
    sessionId: session.sessionId,
    userMessage: message,
    startedAt: now,
    status: 'running',
    skillsUsed: [],
    toolsUsed: [],
  }
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.started', {
    mode: 'agent',
    session_id: session.sessionId,
    skill: GERRIT_REVIEW_SKILL_ID,
    message: 'Gerrit Code Review 已启动',
  })

  setImmediate(() => {
    runGerritReviewTask(taskId).catch(err => {
      logger.error({ err, taskId }, '[gerrit-review] unhandled')
    })
  })

  return { ok: true, sessionId: session.sessionId, taskId }
}

async function runGerritReviewTask(taskId: string): Promise<void> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return
  const session = sessionCtx.get(ctx.sessionId)
  if (!session) return

  const startMs = Date.now()
  const agentSessionId = `tahp-gerrit-${taskId}`

  const preControl = taskRuntime.get(taskId)
  if (preControl?.interruptRequested) {
    ctx.status = 'cancelled'
    ctx.error = '评审已取消'
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.cancelled', { error: ctx.error, message: ctx.error })
    taskRuntime.delete(taskId)
    return
  }
  taskRuntime.set(taskId, { sessionId: agentSessionId, interruptRequested: false })

  try {
    const credFilePath = writeRuntimeCredFile()
    const cfg = getGerritConfig()
    const userMessage = buildGerritReviewUserMessage(ctx.userMessage, session)
    const instructions = buildGerritReviewInstructions(userMessage, {
      credFilePath,
      host: cfg?.host || DEFAULT_GERRIT_HOST,
    })
    saveAgentPromptLog(taskId, 'gerrit-review', instructions, userMessage)

    emit(taskId, 'task.phase', { phase: 'PREPARING', progress: 5, message: '准备 Gerrit Review 指令...' })
    emit(taskId, 'task.plan', {
      message: `主控 Skill: ${GERRIT_REVIEW_SKILL_ID}`,
      skills: [GERRIT_REVIEW_SKILL_ID],
    })

    emit(taskId, 'task.phase', { phase: 'CONNECTING_AGENT', progress: 12, message: '连接 Agent Bridge...' })
    getAgentBridgeManager()

    emit(taskId, 'task.phase', { phase: 'EXECUTING', progress: 20, message: 'Agent 执行 Gerrit Code Review...' })

    const { fullResponse } = await runAgentChat(agentSessionId, instructions, userMessage, {
      onText: (delta) => {
        ctx.llmResponse = (ctx.llmResponse || '') + delta
        emit(taskId, 'task.message', { level: 'stream', text: delta })
      },
      onToolStarted: (toolName, args, toolCallId) => {
        if (!ctx.skillsUsed.includes(toolName)) ctx.skillsUsed.push(toolName)
        ctx.toolsUsed.push({ name: toolName, status: 'running' })
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          message: `调用: ${toolName}${summarizeArgs(args)}`,
        })
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        const t = ctx.toolsUsed.find(x => x.name === toolName && x.status === 'running')
        if (t) t.status = isError ? 'error' : 'done'
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `失败: ${toolName}` : `完成: ${toolName}`,
        })
      },
      onReasoning: (text) => {
        if (text) emit(taskId, 'task.message', { level: 'reasoning', text })
      },
    })

    const p0 = extractP0TestSuggestions(fullResponse)
    const moduleInfo = extractModules(fullResponse)
    const recommendedCases = recommendTestCases(p0.items, moduleInfo.modules)
    ctx.llmResponse = fullResponse
    ctx.p0Items = p0.items
    ctx.status = 'completed'
    ctx.completedAt = new Date().toISOString()

    session.lastResponse = fullResponse
    session.messages.push({
      role: 'assistant',
      content: fullResponse,
      taskId,
      at: ctx.completedAt,
    })
    session.updatedAt = ctx.completedAt

    emit(taskId, 'task.phase', { phase: 'COMPLETED', progress: 100, message: 'Gerrit Code Review 完成' })
    emit(taskId, 'task.completed', {
      status: 'completed',
      mode: 'agent',
      session_id: ctx.sessionId,
      response: fullResponse,
      llm_response: fullResponse,
      p0_items: p0.items,
      p0_raw_section: p0.rawSection,
      modules: moduleInfo.modules,
      modules_display: moduleInfo.display,
      recommended_cases: recommendedCases,
      skills_used: ctx.skillsUsed,
      duration_ms: Date.now() - startMs,
      message: `评审完成，提取 ${p0.items.length} 条 P0 测试建议，推荐 ${recommendedCases.length} 个测试用例`,
    })

    try {
      writeFileSync(
        join(reportDir(), `${taskId}.json`),
        JSON.stringify({
          task_id: taskId,
          session_id: ctx.sessionId,
          user_message: ctx.userMessage,
          started_at: ctx.startedAt,
          completed_at: ctx.completedAt,
          llm_response: fullResponse,
          p0_items: p0.items,
          p0_raw_section: p0.rawSection,
          modules: moduleInfo.modules,
          modules_display: moduleInfo.display,
          recommended_cases: recommendedCases,
          skills_used: ctx.skillsUsed,
          duration_ms: Date.now() - startMs,
        }, null, 2),
        'utf-8',
      )
    } catch (e) {
      logger.warn({ err: (e as Error).message, taskId }, '[gerrit-review] report write failed')
    }
  } catch (err) {
    const control = taskRuntime.get(taskId)
    const interruptedByUser = control?.interruptRequested === true
      || String((err as Error).message || '').includes('被中断')
    const msg = interruptedByUser
      ? '评审已被用户停止'
      : humanizeAgentError((err as Error).message)
    ctx.status = interruptedByUser ? 'cancelled' : 'failed'
    ctx.error = msg
    ctx.completedAt = new Date().toISOString()
    if (interruptedByUser) {
      emit(taskId, 'task.cancelled', { error: msg, message: msg })
    } else {
      emit(taskId, 'task.failed', { error: msg, message: msg })
    }
  } finally {
    taskRuntime.delete(taskId)
    sharedBridgeClient.destroy(agentSessionId).catch(() => {})
  }
}

export function readGerritReviewReport(taskId: string): unknown {
  const p = join(reportDir(), `${taskId}.json`)
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf-8')) } catch { return null }
}
