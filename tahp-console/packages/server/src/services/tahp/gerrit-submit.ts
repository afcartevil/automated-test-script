/**
 * TAHP — Gerrit 提交编排（适配流水线 gerrit 阶段）
 *
 * 走 Agent Bridge 调用 gerrit-submit Skill，按域逐次提交。
 */
import { randomBytes } from 'crypto'
import { logger } from '../logger'
import { getTaskStream } from './task-stream'
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
import { assertHarnessCliReady } from './harness-version-gate'
import {
  isGerritConfigured,
  writeRuntimeCredFile,
  getGerritConfig,
  DEFAULT_GERRIT_HOST,
} from './gerrit-credentials'
import { GERRIT_NOT_CONFIGURED_ERROR } from './gerrit-review'
import type { BuildContext, GerritChangeRef, PipelineDomain } from './adapt-pipeline/types'

export const GERRIT_SUBMIT_SKILL_ID = 'gerrit-submit'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

export interface DomainFileConflict {
  file: string
  domain_ids: string[]
}

export interface GerritDomainSubmitInput {
  runId: string
  projectCode: string
  domain: PipelineDomain
  buildContext: BuildContext
}

export interface GerritSubmitTaskCtx {
  taskId: string
  runId: string
  domainId: string
  startedAt: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  llmResponse?: string
  changeUrl?: string
  changeNumber?: string
  changeId?: string
  alreadySubmitted?: boolean
  error?: string
  completedAt?: string
}

const taskCtx = new Map<string, GerritSubmitTaskCtx>()
const taskRuntime = new Map<string, { sessionId: string; interruptRequested: boolean }>()

function genTaskId(): string {
  return `task-gerrit-submit-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function agentSessionIdForTask(taskId: string): string {
  return `tahp-gerrit-submit-${taskId}`
}

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

/** 跨域 changed_files 交集检测 */
export function detectDomainFileConflicts(
  domains: Array<Pick<PipelineDomain, 'domain_id' | 'changed_files'>>,
): DomainFileConflict[] {
  const fileToDomains = new Map<string, string[]>()
  for (const d of domains) {
    for (const raw of d.changed_files ?? []) {
      const file = raw.replace(/\\/g, '/').trim()
      if (!file) continue
      const list = fileToDomains.get(file) ?? []
      list.push(d.domain_id)
      fileToDomains.set(file, list)
    }
  }
  const conflicts: DomainFileConflict[] = []
  for (const [file, ids] of fileToDomains) {
    const unique = [...new Set(ids)]
    if (unique.length > 1) conflicts.push({ file, domain_ids: unique })
  }
  return conflicts.sort((a, b) => a.file.localeCompare(b.file))
}

export interface GerritSubmitParseResult {
  changeUrl?: string
  changeNumber?: string
  changeId?: string
  /** push 返回 no new changes：本地 commit 已是 CR 当前 patch set，等价于已提交 */
  alreadySubmitted?: boolean
}

function stripUrlTail(url: string): string {
  return url.replace(/[.,;)\]]+$/g, '')
}

/**
 * 从 Agent 输出解析 Gerrit CR 信息。
 *
 * Agent 正文常复述历史 CR 链接（补读远端 pane 时也会带出上一次任务的输出），
 * 因此优先取 skill 约定的 `GERRIT_CHANGE_URL:` 回报行，其次取**最后**一个 URL。
 */
export function parseGerritSubmitResult(text: string): GerritSubmitParseResult {
  const result: GerritSubmitParseResult = {}

  const reported = [...text.matchAll(/GERRIT_CHANGE_URL:\s*(\S+)/gi)].pop()
  if (reported) {
    result.changeUrl = stripUrlTail(reported[1])
  } else {
    const urls = [...text.matchAll(/https?:\/\/gerrit[^\s)>'"`\]]+/gi)]
    const last = urls[urls.length - 1]
    if (last) result.changeUrl = stripUrlTail(last[0])
  }

  if (result.changeUrl) {
    const numFromUrl = result.changeUrl.match(/\/(\d+)\/?$/)
    if (numFromUrl) result.changeNumber = numFromUrl[1]
  }

  const changeIdMatch = text.match(/Change-Id:\s*(I[0-9a-f]+)/i)
  if (changeIdMatch) result.changeId = changeIdMatch[1]

  if (!result.changeNumber) {
    const numMatch = text.match(/Change\s*#?\s*(\d{6,})/i)
    if (numMatch) result.changeNumber = numMatch[1]
  }

  if (/no new changes/i.test(text)) result.alreadySubmitted = true

  return result
}

export function buildConflictChanges(
  domains: PipelineDomain[],
  conflicts: DomainFileConflict[],
): GerritChangeRef[] {
  const conflictDomains = new Set(conflicts.flatMap(c => c.domain_ids))
  return domains
    .filter(d => d.enabled && d.status === 'done' && (d.changed_files?.length ?? 0) > 0)
    .map(d => ({
      domain_id: d.domain_id,
      repo: d.workspace_id,
      status: conflictDomains.has(d.domain_id) ? 'blocked_conflict' as const : 'pending',
      files: d.changed_files ?? [],
      error: conflictDomains.has(d.domain_id)
        ? `与域 ${conflicts.filter(c => c.domain_ids.includes(d.domain_id)).flatMap(c => c.domain_ids).filter(id => id !== d.domain_id).join(', ')} 存在文件冲突`
        : undefined,
    }))
}

export async function probeGerritSubmit(): Promise<{ available: boolean; reason?: string }> {
  if (!isGerritConfigured()) {
    return { available: false, reason: GERRIT_NOT_CONFIGURED_ERROR }
  }
  try {
    const manager = getAgentBridgeManager()
    if (!manager.running) {
      return { available: false, reason: 'Agent Bridge 未运行' }
    }
    return { available: true }
  } catch {
    return { available: false, reason: 'Agent Bridge 检测失败' }
  }
}

export function getGerritSubmitTask(taskId: string): GerritSubmitTaskCtx | undefined {
  return taskCtx.get(taskId)
}

function buildInstructions(
  input: GerritDomainSubmitInput,
  cred?: { credFilePath: string; host: string },
): string {
  const skillPath = tahpSkillMdPath(GERRIT_SUBMIT_SKILL_ID)
  const skillsDir = getTahpSkillsRoot()
  const gerritHost = cred?.host || getGerritConfig()?.host || DEFAULT_GERRIT_HOST
  const credLine = cred?.credFilePath
    ? `Gerrit 凭证文件：${cred.credFilePath}；Host: ${gerritHost}`
    : ''

  const base = `你是 TAHP 适配流水线的 Gerrit 提交助手。必须使用 gerrit-submit Skill 完成提交。

# 必须遵守
1. 先 Read Skill：\`${skillPath}\`（\`${GERRIT_SUBMIT_SKILL_ID}\`）
2. 根据本域变更文件的绝对路径识别各自所属 git 仓库，按仓库分别 commit 并 push 到 Gerrit
3. commit message 遵循 skill 内 commit-template.md
4. 仅提交本域列出的变更文件，不要提交其他域的文件；禁止跨仓混提
5. commit 模板 \`ID:\` 使用流水线提供的「提交 ID」（多仓相同）；若未提供提交 ID 则按 Skill 默认规则处理，不要因此失败；DESCRIPTION 仍按各仓实际 diff 填写
6. **push 前先判幂等**（Skill「是否需要 push」）：本地 HEAD 已是该 CR 的当前 patch set 时不要重复 push，直接回报既有 URL；push 输出 \`no new changes\` 属于**已提交成功**，不得记为失败
7. 回报的 Change URL **只能**来自本次执行的输出，禁止复述历史 CR 链接或旧 CR 号
8. 每个仓完成后单独一行打印 \`GERRIT_CHANGE_URL: <url>\`，并给出 Change-Id

# 禁止（违反会导致卡死在 less pager、长时间无结果）
- **禁止**使用 terminal / execute_code / 本机 shell 执行 git 或 asf 命令
- **必须** Read \`~/.claude/skills/asf-bridge/SKILL.md\`，用 \`asf --json bridge cmd\` 在 Linux 构建机执行；PROBE/SUBMIT 脚本见 Skill 内 remote-harness.md（base64 一次发送，禁止交互式 pager）
- 若 bridge cmd 返回 \`complete=false\`，按 asf-bridge skill 用 \`bridge read\` 补读，**不要**改用 terminal 重跑
${credLine ? `${credLine}\n` : ''}
# 工程 Skill 根目录
\`${skillsDir}\`
`

  const tahpCtx = buildFullTahpSystemContext(
    `提交域 ${input.domain.domain_label}`,
    { scenario: 'adapt_debug', preferredSkillIds: [GERRIT_SUBMIT_SKILL_ID] },
  )
  return tahpCtx ? `${base}\n\n${tahpCtx}` : base
}

function buildUserMessage(input: GerritDomainSubmitInput): string {
  const files = (input.domain.changed_files ?? []).map(f => `- ${f}`).join('\n')
  const branch = input.buildContext.target_branch?.trim()
  const issueId = input.buildContext.gerrit_issue_id?.trim()
  return [
    '# Gerrit 提交任务',
    '',
    `项目：${input.projectCode}`,
    `域：${input.domain.domain_label} (${input.domain.domain_id})`,
    branch ? `目标分支：${branch}（必须使用该分支）` : '目标分支：未指定（按 gerrit-submit Skill 默认推断远程分支）',
    issueId
      ? `提交 ID（commit 模板 ID 字段，多仓共用）：${issueId}`
      : '提交 ID：未指定（可选；未填时按 Skill 默认规则处理 ID 字段，不要因此失败）',
    '',
    '## 本域变更文件（绝对路径）',
    files || '（无文件列表，请根据 git status 确认）',
    '',
    '## 填写要求',
    '- 根据上述绝对路径识别各自所属 git 仓库（从文件路径向上找到仓根），按仓库分别 commit / push，禁止把不同仓库的文件混在一次提交里',
    issueId
      ? '- commit 模板 `ID:` 必须使用上方「提交 ID」（各仓相同）'
      : '- commit 模板 `ID:` 未指定，可按 Skill 默认规则填写或留空，不要因此中止提交',
    '- `DESCRIPTION` / `TYPE` / `TEST_SUGGESTIONS` 等按**本仓实际 diff** 填写，不要照搬其它仓',
    '- 若某仓工作区已干净且 HEAD 就是待提交的 commit，先查该 Change-Id 对应 CR：已是当前 patch set 就回报既有 URL，不要重复 push',
    '',
    '请使用 gerrit-submit Skill 完成 commit + push，并回报 Change URL。',
  ].join('\n')
}

async function runAgentChat(
  sessionId: string,
  instructions: string,
  userMessage: string,
  onLog: (line: string) => void,
): Promise<string> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error('Agent Bridge 未运行。请确认 hermes-agent-main 已初始化。')
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
      if (ev.event === 'tool.started' || ev.event === 'tool.completed') {
        const name = String(ev.tool_name || 'tool')
        onLog(`[tool] ${name}`)
      }
    }
    if (chunk.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      if (cleaned) {
        fullResponse += cleaned
        onLog(cleaned.trim())
      }
    }
    if (chunk.done) {
      if (chunk.status === 'error') throw new Error(humanizeAgentError(chunk.error || 'Agent 出错'))
      if (chunk.status === 'interrupted') throw new Error('Agent 运行被中断')
      break
    }
  }

  if (!lastChunk?.done) throw new Error('Agent 流式输出意外终止')
  if (lastChunk.error) throw new Error(humanizeAgentError(lastChunk.error))
  return fullResponse
}

export function startGerritDomainSubmit(
  input: GerritDomainSubmitInput,
): { ok: true; taskId: string } | { ok: false; error: string } {
  try {
    assertHarnessCliReady()
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }

  const files = input.domain.changed_files ?? []
  if (!files.length) {
    return { ok: false, error: `域 ${input.domain.domain_id} 无变更文件` }
  }

  const taskId = genTaskId()
  const now = new Date().toISOString()
  taskCtx.set(taskId, {
    taskId,
    runId: input.runId,
    domainId: input.domain.domain_id,
    startedAt: now,
    status: 'running',
  })

  emit(taskId, 'task.started', {
    run_id: input.runId,
    domain_id: input.domain.domain_id,
    skill: GERRIT_SUBMIT_SKILL_ID,
    message: `开始提交域 ${input.domain.domain_label}`,
  })

  setImmediate(() => {
    runGerritSubmitTask(taskId, input).catch(err => {
      logger.error({ err, taskId }, '[gerrit-submit] unhandled')
    })
  })

  return { ok: true, taskId }
}

async function runGerritSubmitTask(taskId: string, input: GerritDomainSubmitInput): Promise<void> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return

  const agentSessionId = agentSessionIdForTask(taskId)
  taskRuntime.set(taskId, { sessionId: agentSessionId, interruptRequested: false })

  try {
    const credFilePath = writeRuntimeCredFile()
    const cfg = getGerritConfig()
    const userMessage = buildUserMessage(input)
    const instructions = buildInstructions(input, {
      credFilePath,
      host: cfg?.host || DEFAULT_GERRIT_HOST,
    })
    saveAgentPromptLog(taskId, 'gerrit-submit', instructions, userMessage)

    const fullResponse = await runAgentChat(
      agentSessionId,
      instructions,
      userMessage,
      (line) => {
        if (line) emit(taskId, 'task.message', { level: 'stream', text: line })
      },
    )

    const parsed = parseGerritSubmitResult(fullResponse)
    ctx.llmResponse = fullResponse
    ctx.changeUrl = parsed.changeUrl
    ctx.changeNumber = parsed.changeNumber
    ctx.changeId = parsed.changeId
    ctx.alreadySubmitted = parsed.alreadySubmitted
    ctx.status = 'completed'
    ctx.completedAt = new Date().toISOString()

    emit(taskId, 'task.completed', {
      run_id: input.runId,
      domain_id: input.domain.domain_id,
      change_url: parsed.changeUrl,
      change_number: parsed.changeNumber,
      change_id: parsed.changeId,
      already_submitted: parsed.alreadySubmitted === true,
      response: fullResponse,
    })
  } catch (err) {
    const msg = humanizeAgentError((err as Error).message)
    ctx.status = 'failed'
    ctx.error = msg
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.failed', { error: msg, message: msg, domain_id: input.domain.domain_id })
  } finally {
    taskRuntime.delete(taskId)
    sharedBridgeClient.destroy(agentSessionId).catch(() => {})
  }
}
