/**
 * TAHP — AI 适配调试 · Agent 自动适配（桥接 Agent）
 *
 * 将关联 Skill + 表单参数投递到 Hermes Agent Bridge，经 TaskStream 推送进度。
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
  ADAPT_AUDIT_SKILL_ID,
  buildAdaptAgentInstructions,
  buildAdaptAgentPrompts,
  buildAdaptAgentUserMessage,
} from './adapt-agent-prompts'
import { saveAgentPromptLog } from './prompt-log'
import { uploadAdaptDebugFromCtx } from './quality-run-upload'
import { DEFAULT_ADAPT_WORKSPACE } from './adapt-layout/types'
import {
  isInteractiveCarrierDomain,
  shouldAutoApproveAdaptCommands,
  validateEccConfigForm,
  validateSpnConfigForm,
  normalizeEccRelatedSkills,
  normalizeSpnRelatedSkills,
} from './ecc-config-form'
import {
  extractAdaptAgentFileChanges,
  extractAdaptAgentSkillRefs,
  extractPathsFromExecuteCode,
} from './adapt-agent-report'
import { filterPipelineChangedFiles } from './adapt-pipeline/workspace-changed-files'
import { detectUnhealthyAgentRun, humanizeAgentError } from './adapt-agent-health'
import {
  APPROVAL_AUTO_ONCE_MS,
  findUserInputMarkers,
  buildUserInputResumeMessage,
  type ParsedUserInputRequest,
  type ApprovalRequestPayload,
} from './bug-analysis-interaction'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

export { ADAPT_AUDIT_SKILL_ID, buildAdaptAgentPrompts } from './adapt-agent-prompts'

const AUDIT_SECTION_MARKERS = [
  '## Skill 遵从性自检',
  '# 编码规范审核报告',
  '## 编码规范审核报告',
]

export interface AdaptAgentFieldMeta {
  name: string
  label: string
  required?: boolean
}

export interface AdaptAgentRunInput {
  domainId: string
  domainLabel: string
  module: string
  relatedSkills: string[]
  formData: Record<string, string>
  formFields?: AdaptAgentFieldMeta[]
  userNotes?: string
  workspaceId?: string
  interactionMode?: boolean
}

export interface AdaptAgentTaskCtx {
  taskId: string
  workspaceId: string
  domainId: string
  domainLabel: string
  module: string
  relatedSkills: string[]
  formData: Record<string, string>
  formFields?: AdaptAgentFieldMeta[]
  userNotes?: string
  startedAt: string
  status: 'pending' | 'running' | 'waiting_user_input' | 'waiting_user' | 'completed' | 'failed'
  interactionMode?: boolean
  sessionId?: string
  userInputScanIndex?: number
  phase?: string
  progress?: number
  skillsUsed: string[]
  toolsUsed: Array<{ name: string; status: 'running' | 'done' | 'error'; preview?: string }>
  fileChanges: Array<{ path: string; action: string; tool: string; at: string }>
  planNotes: string[]
  llmResponse?: string
  /** 多轮对话累积输出（用于手动结束任务时生成完整报告） */
  transcript?: string
  /** 从完整输出中切出的自检/审核章节（报告末尾） */
  auditReport?: string
  auditSkillId?: string
  promptLogDir?: string
  completedAt?: string
  error?: string
}

const taskCtx = new Map<string, AdaptAgentTaskCtx>()

interface PendingUserInputEntry {
  request: ParsedUserInputRequest
  expiresAt: number
  timeoutTimer: ReturnType<typeof setTimeout>
}

interface PendingApprovalEntry {
  timer: ReturnType<typeof setTimeout>
  resolved: boolean
  payload: ApprovalRequestPayload
}

interface AdaptTaskRuntime {
  sessionId: string
  userInputPause?: ParsedUserInputRequest
  /** 递增后使尚未执行的 interrupt 回调失效，避免误伤新一轮对话 */
  interruptGeneration?: number
}

const pendingUserInputByTask = new Map<string, PendingUserInputEntry>()
const pendingApprovalsByTask = new Map<string, Map<string, PendingApprovalEntry>>()
const taskRuntime = new Map<string, AdaptTaskRuntime>()
const seenUserInputIdsByTask = new Map<string, Set<string>>()
const adaptRunInProgress = new Set<string>()

async function waitAdaptRunIdle(taskId: string, timeoutMs = 60_000): Promise<void> {
  const start = Date.now()
  while (adaptRunInProgress.has(taskId)) {
    if (Date.now() - start > timeoutMs) {
      throw new Error('等待上一轮 Agent 结束超时')
    }
    await new Promise<void>(resolve => { setTimeout(resolve, 80) })
  }
}

function touchAdaptTaskRuntime(taskId: string, sessionId: string): AdaptTaskRuntime {
  const prev = taskRuntime.get(taskId)
  const next: AdaptTaskRuntime = {
    ...prev,
    sessionId,
  }
  taskRuntime.set(taskId, next)
  return next
}

function getSeenUserInputIds(taskId: string): Set<string> {
  let s = seenUserInputIdsByTask.get(taskId)
  if (!s) {
    s = new Set()
    seenUserInputIdsByTask.set(taskId, s)
  }
  return s
}

function isInteractiveAdapt(ctx: AdaptAgentTaskCtx): boolean {
  return isInteractiveCarrierDomain(ctx.domainId, ctx.interactionMode)
}

function isInteractiveAdaptComplete(fullResponse: string): boolean {
  return /##\s*升级\/适配结果摘要/.test(fullResponse)
    && /##\s*文件修改清单/.test(fullResponse)
}

const PATH_ISSUE_RE = /(?:路径|path|prj_path|目录|文件).{0,48}(?:不存在|无法访问|无效|未找到)|(?:does not exist|ENOENT|no such file)/i

function detectAdaptExecutionFailure(ctx: AdaptAgentTaskCtx, fullResponse: string): string | undefined {
  if (ctx.fileChanges.length > 0) return undefined

  if (PATH_ISSUE_RE.test(fullResponse)) {
    const line = fullResponse.split('\n').map(l => l.trim()).find(l => PATH_ISSUE_RE.test(l))
    return line || '项目路径无效或不可访问，请检查表单中的 prj_path 是否存在于映射工作区内'
  }

  const hasPlanning = /##\s*任务规划/.test(fullResponse)
  const hasResult = /##\s*(?:执行结果|文件修改清单|任务规划回顾)/.test(fullResponse)
  if (ctx.toolsUsed.length > 0 && hasPlanning && !hasResult) {
    return 'Agent 仅完成规划未产生文件修改，请检查 prj_path 是否在映射工作区（mapped_root）内且可写'
  }

  return undefined
}

function buildAdaptUserInputResumeMessage(
  request: ParsedUserInputRequest,
  values: Record<string, string>,
): string {
  return buildUserInputResumeMessage(request, values).replace(
    '请根据以上配置继续执行后续步骤（含必要的配置持久化），并继续 Bug 分析流程。',
    '请根据以上配置继续执行 CarrierConfig 适配流程（含必要的配置持久化）。',
  )
}

function getOrCreateApprovalBucket(taskId: string): Map<string, PendingApprovalEntry> {
  let bucket = pendingApprovalsByTask.get(taskId)
  if (!bucket) {
    bucket = new Map()
    pendingApprovalsByTask.set(taskId, bucket)
  }
  return bucket
}

function clearApprovalTimers(taskId: string) {
  const bucket = pendingApprovalsByTask.get(taskId)
  if (!bucket) return
  for (const entry of bucket.values()) clearTimeout(entry.timer)
  pendingApprovalsByTask.delete(taskId)
}

function registerAdaptApproval(taskId: string, payload: ApprovalRequestPayload) {
  const bucket = getOrCreateApprovalBucket(taskId)
  if (bucket.has(payload.approval_id)) return

  const ctx = taskCtx.get(taskId)
  const autoApproveNow = !!ctx && shouldAutoApproveAdaptCommands(ctx.domainId)

  if (autoApproveNow) {
    // ECC 无人值守：立即同意，不弹窗、不等待
    const timer = setTimeout(() => {}, 0)
    bucket.set(payload.approval_id, { timer, resolved: false, payload })
    emit(taskId, 'task.approval_requested', {
      approval_id: payload.approval_id,
      command: payload.command,
      description: payload.description,
      choices: payload.choices,
      allow_permanent: payload.allow_permanent !== false,
      timeout_ms: 0,
      deadline_at: Date.now(),
      auto_action: 'once',
      message: 'ECC 配置无人值守：危险命令已自动同意',
    })
    void respondAdaptApproval(taskId, payload.approval_id, 'once')
    return
  }

  const timeoutMs = payload.timeout_ms && payload.timeout_ms > 0 ? payload.timeout_ms : APPROVAL_AUTO_ONCE_MS
  const deadline = Date.now() + timeoutMs

  emit(taskId, 'task.approval_requested', {
    approval_id: payload.approval_id,
    command: payload.command,
    description: payload.description,
    choices: payload.choices,
    allow_permanent: payload.allow_permanent !== false,
    timeout_ms: timeoutMs,
    deadline_at: deadline,
    auto_action: 'once',
    message: 'Agent 请求执行危险命令，请在弹窗中确认（60s 无响应将自动同意一次）',
  })

  const timer = setTimeout(() => {
    void respondAdaptApproval(taskId, payload.approval_id, 'once')
  }, timeoutMs)

  bucket.set(payload.approval_id, { timer, resolved: false, payload })
}

function invalidatePendingAdaptInterrupt(taskId: string) {
  const control = taskRuntime.get(taskId)
  if (!control) return
  control.userInputPause = undefined
  control.interruptGeneration = (control.interruptGeneration || 0) + 1
}

async function bridgeSessionAlive(sessionId: string): Promise<boolean> {
  try {
    await sharedBridgeClient.getHistory(sessionId)
    return true
  } catch {
    return false
  }
}

function buildAdaptConversationHistory(ctx: AdaptAgentTaskCtx): Array<{ role: string; content: string }> {
  const history: Array<{ role: string; content: string }> = []
  history.push({ role: 'user', content: buildAdaptAgentUserMessage(ctx) })
  const assistant = ctx.transcript?.trim() || ctx.llmResponse?.trim()
  if (assistant) {
    history.push({ role: 'assistant', content: assistant })
  }
  return history
}

function requestAdaptUserInputPause(
  taskId: string,
  ctx: AdaptAgentTaskCtx,
  request: ParsedUserInputRequest,
  sessionId: string,
) {
  const seen = getSeenUserInputIds(taskId)
  if (seen.has(request.requestId)) return
  seen.add(request.requestId)

  const expiresAt = Date.now() + request.timeoutSec * 1000
  const control = taskRuntime.get(taskId) || { sessionId }
  control.userInputPause = request
  taskRuntime.set(taskId, control)

  const timeoutTimer = setTimeout(() => {
    void autoSubmitEmptyAdaptUserInput(taskId, request.requestId)
  }, request.timeoutSec * 1000)

  pendingUserInputByTask.set(taskId, { request, expiresAt, timeoutTimer })

  ctx.status = 'waiting_user_input'
  ctx.phase = 'WAITING_USER_INPUT'
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.user_input_requested', {
    request_id: request.requestId,
    title: request.title,
    message: request.message,
    fields: request.fields,
    timeout_sec: request.timeoutSec,
    deadline_at: expiresAt,
    persist_key: request.persistKey,
    message_hint: '请在弹窗中填写并确认；超时后将以空值/默认值继续',
  })

  // 不在此处 interrupt：异步 interrupt 易与下一轮 user_input_resume / continue 竞态，导致「Agent 运行被中断」
}

async function autoSubmitEmptyAdaptUserInput(taskId: string, requestId: string) {
  const pending = pendingUserInputByTask.get(taskId)
  if (!pending || pending.request.requestId !== requestId) return
  const emptyValues: Record<string, string> = {}
  for (const f of pending.request.fields) {
    emptyValues[f.name] = f.default || ''
  }
  await submitAdaptUserInput(taskId, requestId, emptyValues, 'auto_timeout')
}

function genTaskId(): string {
  return `task-adapt-agent-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function truncateStr(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max)}…`
}

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const obj = args as Record<string, unknown>
  const keys = Object.keys(obj)
  if (keys.length === 0) return ''
  const prio = ['command', 'cmd', 'path', 'file', 'file_path', 'old_string', 'new_string', 'skill', 'query']
  const picked: string[] = []
  for (const k of prio) {
    if (k in obj) {
      const v = obj[k]
      if (typeof v === 'string') picked.push(`${k}=${truncateStr(v, 80)}`)
      else if (v != null) picked.push(`${k}=${truncateStr(JSON.stringify(v), 80)}`)
      if (picked.length >= 2) break
    }
  }
  if (picked.length === 0 && keys[0]) {
    const v = obj[keys[0]]
    picked.push(`${keys[0]}=${truncateStr(typeof v === 'string' ? v : JSON.stringify(v), 80)}`)
  }
  return picked.length ? `(${picked.join(', ')})` : ''
}

const FILE_WRITE_TOOLS = new Set([
  'write', 'write_file', 'edit', 'str_replace', 'str_replace_based_edit_tool', 'apply_patch',
  'Write', 'Edit', 'MultiEdit', 'patch',
])

const READ_ONLY_TOOLS = new Set(['read_file', 'read', 'Read'])

const EXECUTE_CODE_TOOLS = new Set(['execute_code', 'run_python', 'python'])

function extractFilePathFromArgs(args: unknown): string | undefined {
  if (!args || typeof args !== 'object') return undefined
  const obj = args as Record<string, unknown>
  for (const k of ['path', 'file_path', 'file', 'target_file', 'notebook_path']) {
    const v = obj[k]
    if (typeof v === 'string' && v.trim()) {
      const p = v.trim()
      if (/old_string|new_string/.test(p)) continue
      return p
    }
  }
  return undefined
}

function toolArgsPreview(toolName: string, args: unknown): string {
  if (args && typeof args === 'object') {
    const obj = args as Record<string, unknown>
    if (EXECUTE_CODE_TOOLS.has(toolName) && typeof obj.code === 'string') {
      return obj.code.slice(0, 4000)
    }
  }
  return summarizeArgs(args)
}

function pathsFromToolArgs(toolName: string, args: unknown): string[] {
  const paths: string[] = []
  if (FILE_WRITE_TOOLS.has(toolName) && !READ_ONLY_TOOLS.has(toolName)) {
    const p = extractFilePathFromArgs(args)
    if (p) paths.push(p)
  }
  if (EXECUTE_CODE_TOOLS.has(toolName) && args && typeof args === 'object') {
    const obj = args as Record<string, unknown>
    const code = typeof obj.code === 'string' ? obj.code : undefined
    if (code) paths.push(...extractPathsFromExecuteCode(code))
  }
  return paths
}

function recordFileChanges(
  taskId: string,
  ctx: AdaptAgentTaskCtx,
  toolName: string,
  paths: string[],
): void {
  for (const filePath of paths) {
    if (!filePath?.trim() || filePath.endsWith('SKILL.md')) continue
    const action = toolName === 'write_file' || toolName === 'write' || toolName === 'Write'
      ? 'create'
      : 'modify'
    if (ctx.fileChanges.some(c => c.path === filePath)) continue
    const change = { path: filePath, action, tool: toolName, at: new Date().toISOString() }
    ctx.fileChanges.push(change)
    emit(taskId, 'task.file_change', { ...change, status: 'started' })
  }
}

/** 从 Agent 完整输出中提取末尾的自检/审核报告（含 Skill 遵从性 + 编码规范两段） */
export function extractAdaptAuditReport(fullResponse: string): string | undefined {
  const skillIdx = fullResponse.lastIndexOf('## Skill 遵从性自检')
  if (skillIdx >= 0) return fullResponse.slice(skillIdx).trim()

  let codingIdx = -1
  for (const marker of AUDIT_SECTION_MARKERS) {
    if (marker === '## Skill 遵从性自检') continue
    const idx = fullResponse.lastIndexOf(marker)
    if (idx > codingIdx) codingIdx = idx
  }
  if (codingIdx < 0) return undefined
  return fullResponse.slice(codingIdx).trim()
}

async function runAgentChat(
  sessionId: string,
  instructions: string | undefined,
  userMessage: string,
  cb: {
    onText: (delta: string) => void
    onToolStarted: (toolName: string, args: unknown, toolCallId: unknown) => void
    onToolCompleted: (toolName: string, isError: boolean, toolCallId: unknown) => void
    onReasoning?: (text: string) => void
    onApprovalRequested?: (payload: ApprovalRequestPayload) => void
  },
  options?: { conversationHistory?: unknown[] },
): Promise<{ fullResponse: string; bridgeError: string | null; interrupted: boolean }> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error(
      'Agent Bridge 未运行。请确认 hermes CLI 已安装且 agent-bridge 已启动（服务端日志 [agent-bridge]）。',
    )
  }

  const started: AgentBridgeChatStarted = await sharedBridgeClient.chat(
    sessionId,
    userMessage,
    options?.conversationHistory,
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
      } else if (evType === 'approval.requested' && cb.onApprovalRequested) {
        cb.onApprovalRequested({
          approval_id: String(ev.approval_id || ''),
          command: String(ev.command || ''),
          description: String(ev.description || ''),
          choices: Array.isArray(ev.choices) ? ev.choices.map(String) : ['once', 'deny'],
          allow_permanent: ev.allow_permanent !== false,
          timeout_ms: typeof ev.timeout_ms === 'number' ? ev.timeout_ms : APPROVAL_AUTO_ONCE_MS,
        })
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
      if (chunk.status === 'interrupted') {
        return { fullResponse, bridgeError: lastChunk.error ?? null, interrupted: true }
      }
      break
    }
  }

  if (!lastChunk?.done) throw new Error('Agent 流式输出意外终止')
  if (lastChunk.error) {
    throw new Error(humanizeAgentError(lastChunk.error))
  }
  return { fullResponse, bridgeError: lastChunk.error ?? null, interrupted: false }
}

function reportDir(): string {
  const d = join(tahpPaths.reportsDir, 'adapt-agent')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function getAdaptAgentTask(taskId: string): AdaptAgentTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export function startAdaptAgentRun(input: AdaptAgentRunInput): { ok: true; taskId: string } | { ok: false; error: string } {
  if (!input.relatedSkills?.length) {
    return { ok: false, error: '缺少关联 Skill' }
  }
  const requiredKeys = (input.formFields || []).filter(f => f.required).map(f => f.name)
  for (const k of requiredKeys) {
    if (!String(input.formData[k] || '').trim()) {
      const label = input.formFields?.find(f => f.name === k)?.label || k
      return { ok: false, error: `缺少必填参数: ${label}` }
    }
  }

  if (input.domainId === 'ecc-config') {
    const eccErr = validateEccConfigForm(input.formData)
    if (eccErr) return { ok: false, error: eccErr }
  }
  if (input.domainId === 'spn-config') {
    const spnErr = validateSpnConfigForm(input.formData)
    if (spnErr) return { ok: false, error: spnErr }
  }

  const relatedSkills = input.domainId === 'ecc-config'
    ? normalizeEccRelatedSkills(input.relatedSkills)
    : input.domainId === 'spn-config'
      ? normalizeSpnRelatedSkills(input.relatedSkills)
      : [...input.relatedSkills]

  const taskId = genTaskId()
  const ctx: AdaptAgentTaskCtx = {
    taskId,
    workspaceId: input.workspaceId || DEFAULT_ADAPT_WORKSPACE,
    domainId: input.domainId,
    domainLabel: input.domainLabel,
    module: input.module,
    relatedSkills,
    formData: { ...input.formData },
    formFields: input.formFields ? [...input.formFields] : undefined,
    userNotes: input.userNotes,
    interactionMode: isInteractiveCarrierDomain(input.domainId, input.interactionMode === true),
    startedAt: new Date().toISOString(),
    status: 'running',
    skillsUsed: [],
    toolsUsed: [],
    fileChanges: [],
    planNotes: [],
    userInputScanIndex: 0,
  }
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.started', {
    mode: 'agent',
    workspace_id: ctx.workspaceId,
    domain_id: input.domainId,
    domain_label: input.domainLabel,
    related_skills: input.relatedSkills,
    message: `${input.domainLabel} Agent 自动适配已启动`,
  })

  setImmediate(() => {
    runAdaptAgentTask(taskId).catch(err => {
      logger.error({ err, taskId }, '[adapt-agent] unhandled')
    })
  })

  return { ok: true, taskId }
}

type AdaptTurnOptions =
  | { mode: 'initial' }
  | { mode: 'user_input_resume'; request: ParsedUserInputRequest; values: Record<string, string> }
  | { mode: 'continue'; userMessage: string }

function appendAdaptTranscript(ctx: AdaptAgentTaskCtx, chunk: string) {
  const text = chunk.trim()
  if (!text) return
  ctx.transcript = ctx.transcript?.trim()
    ? `${ctx.transcript.trim()}\n\n${text}`
    : text
}

function cleanupAdaptSession(taskId: string, ctx: AdaptAgentTaskCtx) {
  clearApprovalTimers(taskId)
  pendingUserInputByTask.delete(taskId)
  taskRuntime.delete(taskId)
  seenUserInputIdsByTask.delete(taskId)
  if (ctx.sessionId) {
    sharedBridgeClient.destroy(ctx.sessionId).catch(() => {})
  }
}

async function finalizeAdaptAgentTask(
  taskId: string,
  ctx: AdaptAgentTaskCtx,
  fullResponse: string,
  startMs: number,
  opts?: { userEnded?: boolean },
): Promise<void> {
  const auditReport = extractAdaptAuditReport(fullResponse)
  ctx.auditReport = auditReport
  ctx.auditSkillId = ADAPT_AUDIT_SKILL_ID
  ctx.llmResponse = fullResponse
  ctx.status = 'completed'
  ctx.completedAt = new Date().toISOString()

  emit(taskId, 'task.step', {
    step_id: 'agent-run',
    status: 'completed',
    message: `Agent 完成，${fullResponse.length} 字，工具 ${ctx.toolsUsed.length} 次，文件变更 ${ctx.fileChanges.length} 项`,
  })
  if (auditReport) {
    emit(taskId, 'task.step', {
      step_id: 'self-audit',
      status: 'completed',
      message: `自检审核已写入报告末尾（${auditReport.length} 字）`,
    })
    emit(taskId, 'task.audit_completed', {
      audit_skill: ADAPT_AUDIT_SKILL_ID,
      audit_report: auditReport,
      message: '编码规范与 Skill 遵从性自检已完成',
    })
  } else {
    emit(taskId, 'task.step', {
      step_id: 'self-audit',
      status: 'warning',
      message: '未检测到报告末尾的审核章节（请确认 Agent 已 Read transsion-coding-standards-review）',
    })
  }
  emit(taskId, 'task.phase', {
    phase: 'COMPLETED',
    progress: 100,
    message: opts?.userEnded ? '用户手动结束，报告已生成' : 'Agent 自动适配完成',
  })

  const reportSnapshot = {
    task_id: taskId,
    ...ctx,
    llm_response: fullResponse,
    audit_report: auditReport,
    audit_skill: ADAPT_AUDIT_SKILL_ID,
    duration_ms: Date.now() - startMs,
  }
  const normalizedFiles = extractAdaptAgentFileChanges(reportSnapshot as Record<string, unknown>)
    .filter(fc => filterPipelineChangedFiles([fc.path]).length > 0)
  const normalizedSkills = extractAdaptAgentSkillRefs(reportSnapshot as Record<string, unknown>)

  for (const fc of normalizedFiles) {
    const known = ctx.fileChanges.find(c => c.path === fc.path)
    if (!known) {
      ctx.fileChanges.push({
        path: fc.path,
        action: fc.action || 'modify',
        tool: fc.tool || 'detected',
        at: new Date().toISOString(),
      })
    }
    emit(taskId, 'task.file_change', {
      path: fc.path,
      tool: fc.tool || known?.tool || 'detected',
      action: fc.action || known?.action || 'modify',
      status: 'completed',
    })
  }

  emit(taskId, 'task.completed', {
    status: 'completed',
    mode: 'agent',
    response: fullResponse,
    audit_report: auditReport,
    audit_skill: ADAPT_AUDIT_SKILL_ID,
    skills_used: normalizedSkills,
    files_modified: normalizedFiles.map(c => c.path),
    duration_ms: Date.now() - startMs,
    message: opts?.userEnded
      ? '用户手动结束任务，报告已生成'
      : auditReport ? 'Agent 自动适配完成（含末尾自检审核）' : 'Agent 自动适配完成',
    user_ended: opts?.userEnded === true,
  })

  try {
    writeFileSync(
      join(reportDir(), `${taskId}.json`),
      JSON.stringify({
        ...reportSnapshot,
        started_at: ctx.startedAt,
        completed_at: ctx.completedAt,
        workspace_id: ctx.workspaceId,
        domain: ctx.domainId,
        domain_label: ctx.domainLabel,
        files_modified: normalizedFiles.map(c => c.path),
        file_changes: normalizedFiles,
        skills_used: normalizedSkills,
        related_skills: ctx.relatedSkills,
      }, null, 2),
      'utf-8',
    )
  } catch (e) {
    logger.warn({ err: (e as Error).message, taskId }, '[adapt-agent] report write failed')
  }

  void uploadAdaptDebugFromCtx(ctx)
}

async function runAdaptAgentTask(taskId: string, turn: AdaptTurnOptions = { mode: 'initial' }): Promise<void> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return

  if (adaptRunInProgress.has(taskId)) {
    logger.warn({ taskId, turn: turn.mode }, '[adapt-agent] run already in progress')
    return
  }
  adaptRunInProgress.add(taskId)

  const isContinue = turn.mode !== 'initial'
  const agentSessionId = ctx.sessionId || `tahp-adapt-agent-${taskId}`
  ctx.sessionId = agentSessionId
  touchAdaptTaskRuntime(taskId, agentSessionId)

  const taskStartMs = turn.mode === 'initial' ? Date.now() : Date.parse(ctx.startedAt) || Date.now()

  try {
    let userMessage: string
    let instructions: string | undefined
    let conversationHistory: unknown[] | undefined

    if (turn.mode === 'user_input_resume') {
      userMessage = buildAdaptUserInputResumeMessage(turn.request, turn.values)
      invalidatePendingAdaptInterrupt(taskId)
      const sessionAlive = await bridgeSessionAlive(agentSessionId)
      if (sessionAlive) {
        instructions = undefined
        conversationHistory = undefined
      } else {
        conversationHistory = buildAdaptConversationHistory(ctx)
        instructions = buildAdaptAgentInstructions(ctx, userMessage)
      }
      saveAgentPromptLog(taskId, 'adapt-agent', instructions || '(user input resume)', userMessage)
    } else if (turn.mode === 'continue') {
      userMessage = turn.userMessage
      invalidatePendingAdaptInterrupt(taskId)
      const sessionAlive = await bridgeSessionAlive(agentSessionId)
      if (sessionAlive) {
        instructions = undefined
        conversationHistory = undefined
      } else {
        conversationHistory = buildAdaptConversationHistory(ctx)
        instructions = buildAdaptAgentInstructions(ctx, userMessage)
      }
      saveAgentPromptLog(taskId, 'adapt-agent', instructions || '(continue chat)', userMessage)
    } else {
      userMessage = buildAdaptAgentUserMessage(ctx)
      instructions = buildAdaptAgentInstructions(ctx, userMessage)
      const promptLog = saveAgentPromptLog(taskId, 'adapt-agent', instructions, userMessage)
      ctx.promptLogDir = promptLog.promptDir
    }

    if (!isContinue) {
      emit(taskId, 'task.phase', { phase: 'PREPARING', progress: 5, message: '准备 Agent 指令与 Skill 上下文...' })
      emit(taskId, 'task.plan', {
        message: `主控 Skill: ${ctx.relatedSkills[0]}；关联 ${ctx.relatedSkills.length} 个 Skill`,
        skills: ctx.relatedSkills,
      })
      emit(taskId, 'task.phase', { phase: 'CONNECTING_AGENT', progress: 12, message: '连接 Agent Bridge...' })
      getAgentBridgeManager()
      emit(taskId, 'task.step', { step_id: 'connect-agent', status: 'completed', message: 'Agent Bridge 已就绪' })
    }

    const execMsg = isContinue
      ? (turn.mode === 'continue' ? '继续对话...' : '根据用户输入继续执行...')
      : 'Agent 按 Skill SOP 执行适配...'
    emit(taskId, 'task.phase', { phase: 'EXECUTING', progress: 20, message: execMsg })

    if (isContinue) {
      ctx.llmResponse = ''
    }

    const { fullResponse, bridgeError, interrupted } = await runAgentChat(agentSessionId, instructions, userMessage, {
      onText: (delta) => {
        const fullSoFar = (ctx.llmResponse || '') + delta
        ctx.llmResponse = fullSoFar
        emit(taskId, 'task.message', { level: 'stream', text: delta })
        if (/任务规划|当前步骤|下一步|##\s*\d/i.test(delta)) {
          const note = delta.trim().slice(0, 500)
          if (note) ctx.planNotes.push(note)
        }

        if (isInteractiveAdapt(ctx)) {
          const inputHits = findUserInputMarkers(fullSoFar, ctx.userInputScanIndex ?? 0)
          for (const hit of inputHits) {
            ctx.userInputScanIndex = hit.startIndex + hit.rawBlock.length
            requestAdaptUserInputPause(taskId, ctx, hit, agentSessionId)
          }
        }
      },
      onToolStarted: (toolName, args, toolCallId) => {
        if (!ctx.skillsUsed.includes(toolName)) ctx.skillsUsed.push(toolName)
        const preview = toolArgsPreview(toolName, args)
        ctx.toolsUsed.push({ name: toolName, status: 'running', preview })
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          args: preview,
          message: `🛠 调用: ${toolName}${summarizeArgs(args)}`,
        })
        recordFileChanges(taskId, ctx, toolName, pathsFromToolArgs(toolName, args))
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        const t = ctx.toolsUsed.find(x => x.name === toolName && x.status === 'running')
        if (t) t.status = isError ? 'error' : 'done'
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `✗ 失败: ${toolName}` : `✓ 完成: ${toolName}`,
        })
      },
      onReasoning: () => {},
      onApprovalRequested: (payload) => {
        if (payload.approval_id) registerAdaptApproval(taskId, payload)
      },
    }, { conversationHistory })

    const runtimeAfter = taskRuntime.get(taskId)
    if (runtimeAfter?.userInputPause || pendingUserInputByTask.has(taskId)) {
      appendAdaptTranscript(ctx, fullResponse)
      ctx.status = 'waiting_user_input'
      ctx.phase = 'WAITING_USER_INPUT'
      taskCtx.set(taskId, ctx)
      return
    }

    if (interrupted) {
      throw new Error('Agent 运行被中断')
    }

    appendAdaptTranscript(ctx, fullResponse)

    if (isInteractiveAdapt(ctx) && !isInteractiveAdaptComplete(fullResponse)) {
      ctx.status = 'waiting_user'
      ctx.phase = 'WAITING_USER'
      taskCtx.set(taskId, ctx)
      emit(taskId, 'task.phase', {
        phase: 'WAITING_USER',
        progress: 60,
        message: '等待补充信息；可点击「补充信息继续对话」或「结束任务」',
      })
      return
    }

    const agentDurationMs = Date.now() - taskStartMs
    const unhealthy = detectUnhealthyAgentRun({
      fullResponse,
      toolsUsedCount: ctx.toolsUsed.length,
      durationMs: agentDurationMs,
      bridgeError,
    })
    if (unhealthy) throw new Error(unhealthy)

    const executionFailure = detectAdaptExecutionFailure(ctx, fullResponse)
    if (executionFailure) throw new Error(executionFailure)

    const reportText = ctx.transcript?.trim() || fullResponse
    await finalizeAdaptAgentTask(taskId, ctx, reportText, taskStartMs)
  } catch (err) {
    const runtime = taskRuntime.get(taskId)
    if (runtime?.userInputPause) {
      logger.info({ taskId, requestId: runtime.userInputPause.requestId }, '[adapt-agent] paused for user input')
      return
    }
    const msg = humanizeAgentError((err as Error).message)
    ctx.status = 'failed'
    ctx.error = msg
    emit(taskId, 'task.failed', { error: msg, message: msg })
    void uploadAdaptDebugFromCtx(ctx)
  } finally {
    adaptRunInProgress.delete(taskId)
    const latest = taskCtx.get(taskId)
    if (latest && (latest.status === 'completed' || latest.status === 'failed')) {
      cleanupAdaptSession(taskId, latest)
    }
  }
}

export async function submitAdaptUserInput(
  taskId: string,
  requestId: string,
  values: Record<string, string>,
  source: 'user' | 'auto_timeout' = 'user',
): Promise<{ ok: boolean; error?: string }> {
  const pending = pendingUserInputByTask.get(taskId)
  if (!pending || pending.request.requestId !== requestId) {
    return { ok: false, error: '配置请求不存在或已过期' }
  }

  for (const field of pending.request.fields) {
    if (field.required && !String(values[field.name] ?? '').trim()) {
      return { ok: false, error: `请填写必填项：${field.label}` }
    }
  }

  if (pending.timeoutTimer) clearTimeout(pending.timeoutTimer)
  const request = pending.request
  pendingUserInputByTask.delete(taskId)

  emit(taskId, 'task.user_input_submitted', {
    request_id: requestId,
    values,
    source,
    message: source === 'auto_timeout' ? '配置输入超时，已以默认值/空值继续' : '用户已提交配置',
  })

  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务 ${taskId}` }

  const control = taskRuntime.get(taskId)
  if (control) control.userInputPause = undefined

  invalidatePendingAdaptInterrupt(taskId)

  ctx.status = 'running'
  ctx.error = undefined
  taskCtx.set(taskId, ctx)

  try {
    await waitAdaptRunIdle(taskId)
    await runAdaptAgentTask(taskId, { mode: 'user_input_resume', request, values })
  } catch (err) {
    logger.error({ err: (err as Error).message, taskId }, '[adapt-agent] user input resume unhandled')
    return { ok: false, error: (err as Error).message }
  }

  return { ok: true }
}

export async function continueAdaptAgentRun(taskId: string, message: string): Promise<{ ok: boolean; error?: string }> {
  const text = message.trim()
  if (!text) return { ok: false, error: '消息不能为空' }

  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (ctx.status !== 'waiting_user') {
    return { ok: false, error: `任务状态不可继续: ${ctx.status}` }
  }

  invalidatePendingAdaptInterrupt(taskId)

  ctx.status = 'running'
  ctx.error = undefined
  taskCtx.set(taskId, ctx)
  emit(taskId, 'task.message', {
    level: 'user',
    text: `\n\n**用户**\n\n${text}\n\n`,
  })

  try {
    await waitAdaptRunIdle(taskId)
    await runAdaptAgentTask(taskId, { mode: 'continue', userMessage: text })
  } catch (err) {
    logger.error({ err: (err as Error).message, taskId }, '[adapt-agent] continue unhandled')
    return { ok: false, error: (err as Error).message }
  }

  return { ok: true }
}

export async function completeAdaptAgentRun(taskId: string): Promise<{ ok: boolean; error?: string }> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (!isInteractiveAdapt(ctx)) {
    return { ok: false, error: '仅交互式适配任务支持手动结束' }
  }
  if (ctx.status === 'completed' || ctx.status === 'failed') {
    return { ok: false, error: '任务已结束' }
  }
  if (ctx.status !== 'waiting_user' && ctx.status !== 'waiting_user_input' && ctx.status !== 'running') {
    return { ok: false, error: `当前状态无法结束: ${ctx.status}` }
  }

  const pending = pendingUserInputByTask.get(taskId)
  if (pending?.timeoutTimer) clearTimeout(pending.timeoutTimer)
  pendingUserInputByTask.delete(taskId)
  clearApprovalTimers(taskId)

  const runtime = taskRuntime.get(taskId)
  if (runtime) runtime.userInputPause = undefined

  const sessionId = ctx.sessionId
  if (sessionId) {
    await sharedBridgeClient.interrupt(sessionId, '用户结束任务').catch(() => {})
  }

  emit(taskId, 'task.message', {
    level: 'user',
    text: '\n\n**用户**\n\n（手动结束当前任务，生成报告）\n\n',
  })

  const taskStartMs = Date.parse(ctx.startedAt) || Date.now()
  let reportText = ctx.transcript?.trim() || ctx.llmResponse?.trim() || ''
  if (!reportText) {
    reportText = '用户手动结束任务；当前无 Agent 文本输出。'
  } else if (!reportText.includes('用户手动结束')) {
    reportText += '\n\n---\n\n**用户手动结束任务**（会话已关闭，报告已落盘）'
  }

  ctx.status = 'running'
  taskCtx.set(taskId, ctx)

  try {
    await finalizeAdaptAgentTask(taskId, ctx, reportText, taskStartMs, { userEnded: true })
    return { ok: true }
  } catch (err) {
    const msg = humanizeAgentError((err as Error).message)
    ctx.status = 'failed'
    ctx.error = msg
    emit(taskId, 'task.failed', { error: msg, message: msg })
    return { ok: false, error: msg }
  } finally {
    const latest = taskCtx.get(taskId)
    if (latest && (latest.status === 'completed' || latest.status === 'failed')) {
      cleanupAdaptSession(taskId, latest)
    }
  }
}

/**
 * 终止一个正在执行的适配任务（任意域，含非交互域）。
 * 中断桥接会话、标记失败、发出 task.failed 事件并清理运行时资源，
 * 使前端能立即退出「大模型思考中」状态并允许重新发起。
 */
export async function cancelAdaptAgentRun(taskId: string): Promise<{ ok: boolean; error?: string }> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (ctx.status === 'completed' || ctx.status === 'failed') {
    return { ok: false, error: '任务已结束' }
  }

  const pending = pendingUserInputByTask.get(taskId)
  if (pending?.timeoutTimer) clearTimeout(pending.timeoutTimer)
  pendingUserInputByTask.delete(taskId)
  clearApprovalTimers(taskId)

  const runtime = taskRuntime.get(taskId)
  if (runtime) runtime.userInputPause = undefined

  const sessionId = ctx.sessionId
  if (sessionId) {
    await sharedBridgeClient.interrupt(sessionId, '用户终止任务').catch(() => {})
  }

  const msg = '任务已被用户终止'
  ctx.status = 'failed'
  ctx.error = msg
  ctx.completedAt = new Date().toISOString()
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.failed', { error: msg, message: msg, cancelled: true })

  cleanupAdaptSession(taskId, ctx)
  adaptRunInProgress.delete(taskId)
  return { ok: true }
}

export async function respondAdaptApproval(
  taskId: string,
  approvalId: string,
  choice: string,
): Promise<{ ok: boolean; error?: string }> {
  const bucket = pendingApprovalsByTask.get(taskId)
  const entry = bucket?.get(approvalId)
  if (!entry || entry.resolved) {
    return { ok: false, error: '审批请求不存在或已处理' }
  }
  entry.resolved = true
  clearTimeout(entry.timer)
  bucket?.delete(approvalId)
  if (bucket && bucket.size === 0) pendingApprovalsByTask.delete(taskId)

  try {
    await sharedBridgeClient.approvalRespond(approvalId, choice)
    emit(taskId, 'task.approval_resolved', { approval_id: approvalId, choice })
    return { ok: true }
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }
}

export function readAdaptAgentReport(taskId: string): unknown {
  const p = join(reportDir(), `${taskId}.json`)
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf-8')) } catch { return null }
}
