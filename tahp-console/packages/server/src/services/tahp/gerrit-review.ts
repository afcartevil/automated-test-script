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
import { recommendTestCasesWithMeta } from './gerrit-case-recommendation'
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
const forceCancelTimers = new Map<string, ReturnType<typeof setTimeout>>()

const GERRIT_FORCE_CANCEL_MS = 5000

function gerritReviewMaxDurationMs(): number {
  const raw = process.env.GERRIT_REVIEW_MAX_DURATION_MS
  if (!raw) return 25 * 60_000
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : 25 * 60_000
}

function gerritReviewHeartbeatMs(): number {
  const raw = process.env.GERRIT_REVIEW_HEARTBEAT_MS
  if (!raw) return 60_000
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : 60_000
}

function agentSessionIdForTask(taskId: string): string {
  return `tahp-gerrit-${taskId}`
}

function isInterruptRequested(taskId: string): boolean {
  return taskRuntime.get(taskId)?.interruptRequested === true
}

function clearForceCancelTimer(taskId: string): void {
  const timer = forceCancelTimers.get(taskId)
  if (timer) {
    clearTimeout(timer)
    forceCancelTimers.delete(taskId)
  }
}

function emitTaskCancelled(taskId: string, ctx: GerritReviewTaskCtx, message: string): void {
  if (ctx.status === 'completed' || ctx.status === 'failed' || ctx.status === 'cancelled') return
  ctx.status = 'cancelled'
  ctx.error = message
  ctx.completedAt = new Date().toISOString()
  emit(taskId, 'task.cancelled', { error: message, message })
}

function scheduleForceCancel(taskId: string, sessionId: string): void {
  clearForceCancelTimer(taskId)
  const timer = setTimeout(() => {
    forceCancelTimers.delete(taskId)
    const ctx = taskCtx.get(taskId)
    if (!ctx || ctx.status !== 'running') return
    logger.warn({ taskId, sessionId }, '[gerrit-review] force cancel after interrupt timeout')
    emitTaskCancelled(taskId, ctx, '评审已被用户停止')
    sharedBridgeClient.destroy(sessionId).catch(() => {})
    taskRuntime.delete(taskId)
  }, GERRIT_FORCE_CANCEL_MS)
  forceCancelTimers.set(taskId, timer)
}

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
3. 分析报告必须包含以下 5 个章节（与 Skill report-template.md 一致），并写入 \`report_path=\` 指定的 **Markdown（.md）** 文件：
   - ## 1. 基本信息
   - ## 2. 问题统计
   - ## 3. 详细问题列表和改善建议
   - ## 4. 影响范围
   - ## 5. 测试建议（必须含 \`### P0 - 必须测试\`、\`### P1 - 强烈建议\`、\`### P2 - 建议测试\`）
4. Topic 评审须产出**一份合并 Markdown 报告**，P0 列表去重合并。
5. 必须真实调用工具执行 fetch 与分析；禁止编造 diff 内容。
6. 完成后在终端摘要中打印 report_path 与可点击的 report_url（Markdown 文件）。
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

async function autoApproveGerritCommand(
  taskId: string,
  approvalId: string,
  command: string,
  seenApprovals: Set<string>,
): Promise<void> {
  if (!approvalId || seenApprovals.has(approvalId)) return
  seenApprovals.add(approvalId)

  const preview = command.trim().slice(0, 160) || '(命令)'
  emit(taskId, 'task.skill_use', {
    skill_id: 'terminal_approval',
    source: 'approval',
    message: `自动批准执行: ${preview}`,
  })
  logger.info({ taskId, approvalId, command: preview }, '[gerrit-review] auto-approve command')

  try {
    await sharedBridgeClient.approvalRespond(approvalId, 'once')
    emit(taskId, 'task.tool_completed', {
      skill_id: 'terminal_approval',
      error: false,
      message: `已自动批准: ${preview}`,
    })
  } catch (err) {
    logger.warn({ err: (err as Error).message, taskId, approvalId }, '[gerrit-review] approval respond failed')
  }
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
  taskId?: string,
): Promise<{ fullResponse: string }> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error(
      'Agent Bridge 未运行。请确认 hermes-agent-main 已初始化（npm run setup:agent）。',
    )
  }

  if (taskId && isInterruptRequested(taskId)) {
    throw new Error('Agent 运行被中断')
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
  const seenApprovals = new Set<string>()
  const startedAt = Date.now()
  let lastHeartbeatAt = startedAt
  const maxDurationMs = gerritReviewMaxDurationMs()
  const heartbeatMs = gerritReviewHeartbeatMs()

  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 250 })) {
    if (taskId && isInterruptRequested(taskId)) {
      await sharedBridgeClient.interrupt(sessionId, '用户手动停止 Gerrit 评审').catch(() => {})
      throw new Error('Agent 运行被中断')
    }

    const now = Date.now()
    if (now - startedAt > maxDurationMs) {
      throw new Error(`Gerrit 评审超时（超过 ${Math.round(maxDurationMs / 60_000)} 分钟），请缩小变更范围或稍后重试`)
    }
    if (taskId && now - lastHeartbeatAt >= heartbeatMs) {
      const elapsedMin = Math.max(1, Math.round((now - startedAt) / 60_000))
      emit(taskId, 'task.phase', {
        phase: 'EXECUTING',
        progress: 20,
        message: `Agent 仍在执行评审…（已运行 ${elapsedMin} 分钟）`,
      })
      lastHeartbeatAt = now
    }

    let hadProgress = false
    lastChunk = chunk
    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'approval.requested' && taskId) {
        hadProgress = true
        void autoApproveGerritCommand(
          taskId,
          String(ev.approval_id || ''),
          String(ev.command || ev.description || ''),
          seenApprovals,
        )
      } else if (evType === 'tool.started') {
        hadProgress = true
        cb.onToolStarted((ev.tool_name as string) || 'unknown-tool', ev.args, ev.tool_call_id)
      } else if (evType === 'tool.completed') {
        hadProgress = true
        cb.onToolCompleted((ev.tool_name as string) || 'unknown-tool', ev.is_error === true, ev.tool_call_id)
      } else if ((evType === 'reasoning.delta' || evType === 'thinking.delta') && cb.onReasoning) {
        hadProgress = true
        cb.onReasoning(String(ev.text || ''))
      }
    }
    if (chunk.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      if (cleaned) {
        hadProgress = true
        fullResponse += cleaned
        cb.onText(cleaned)
      }
    }
    if (hadProgress) {
      lastHeartbeatAt = now
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

  const agentSessionId = agentSessionIdForTask(taskId)
  const control = taskRuntime.get(taskId) || { sessionId: agentSessionId, interruptRequested: false }
  control.interruptRequested = true
  taskRuntime.set(taskId, control)

  emit(taskId, 'task.message', { level: 'warn', text: '已请求停止评审，等待 Agent 结束...' })
  logger.warn({ taskId, sessionId: control.sessionId }, '[gerrit-review] interrupt requested')

  setImmediate(() => {
    void (async () => {
      try {
        await sharedBridgeClient.interrupt(control.sessionId, '用户手动停止 Gerrit 评审')
      } catch (err) {
        logger.warn({ err: (err as Error).message, taskId }, '[gerrit-review] interrupt rpc failed')
        await sharedBridgeClient.destroy(control.sessionId).catch(() => {})
      }
    })()
  })
  scheduleForceCancel(taskId, control.sessionId)
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
  const agentSessionId = agentSessionIdForTask(taskId)

  const preControl = taskRuntime.get(taskId)
  if (preControl?.interruptRequested) {
    ctx.status = 'cancelled'
    ctx.error = '评审已取消'
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.cancelled', { error: ctx.error, message: ctx.error })
    taskRuntime.delete(taskId)
    return
  }
  taskRuntime.set(taskId, {
    sessionId: agentSessionId,
    interruptRequested: preControl?.interruptRequested === true,
  })
  if (isInterruptRequested(taskId)) {
    ctx.status = 'cancelled'
    ctx.error = '评审已取消'
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.cancelled', { error: ctx.error, message: ctx.error })
    taskRuntime.delete(taskId)
    return
  }

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

    if (isInterruptRequested(taskId)) {
      throw new Error('Agent 运行被中断')
    }

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
    }, taskId)

    emit(taskId, 'task.phase', { phase: 'RECOMMENDING', progress: 92, message: '正在通过 LLM 语义匹配推荐测试用例…' })
    const p0 = extractP0TestSuggestions(fullResponse)
    const moduleInfo = extractModules(fullResponse)
    const {
      cases: recommendedCases,
      source: recommendSource,
      coverage,
      aiGeneratedCases,
      aiGenerationError,
    } = await recommendTestCasesWithMeta(
      p0.items,
      moduleInfo.modules,
    )
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
      recommend_source: recommendSource,
      coverage_score: coverage.score,
      coverage_reason: coverage.reason,
      coverage_gaps: coverage.gaps,
      ai_generated_cases: aiGeneratedCases,
      ai_generation_error: aiGenerationError,
      skills_used: ctx.skillsUsed,
      duration_ms: Date.now() - startMs,
      message: recommendSource === 'llm'
        ? `评审完成，提取 ${p0.items.length} 条 P0 测试建议，LLM 推荐 ${recommendedCases.length} 个测试用例`
        : `评审完成，提取 ${p0.items.length} 条 P0 测试建议，关键词规则推荐 ${recommendedCases.length} 个测试用例（LLM 未命中或不可用）`,
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
          recommend_source: recommendSource,
          coverage_score: coverage.score,
          coverage_reason: coverage.reason,
          coverage_gaps: coverage.gaps,
          ai_generated_cases: aiGeneratedCases,
          ai_generation_error: aiGenerationError,
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
    clearForceCancelTimer(taskId)
    taskRuntime.delete(taskId)
    sharedBridgeClient.destroy(agentSessionId).catch(() => {})
  }
}

export function readGerritReviewReport(taskId: string): unknown {
  const p = join(reportDir(), `${taskId}.json`)
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf-8')) } catch { return null }
}
