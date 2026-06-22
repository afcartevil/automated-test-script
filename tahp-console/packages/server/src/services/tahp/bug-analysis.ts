/**
 * TAHP — AI Bug 分析编排（Agent 模式）
 *
 * 设计原则：
 *   - **所有 Bug 分析必须走 Claude Code Agent**（通过 hermes agent-bridge）
 *   - Agent 拥有完整 Skill / MCP 工具链（jira-mcp / transsion-harness / BSP 分析 skill）
 *   - **不允许降级到 BFF 直连 LLM**：若 agent 不可用或调用失败，任务直接失败
 *   - JIRA 信息由 Agent 自己用 Skill 拉取；BFF 只在 "预览 JIRA" 按钮和 JQL 候选枚举时使用 jira.ts
 *
 * 职责：
 *   - 维护 Bug 分析任务上下文（单条 / JQL 批量）
 *   - 把 Bug 任务投递到 Agent Bridge，监听并转发 tool.started / tool.completed / 文本 delta
 *   - 通过 TaskStream 推送 task.* 事件给前端实时显示
 *   - 支持"补充信息继续分析"（带前次上下文重跑）
 *
 * 报告落盘：
 *   reports/bug-analysis/<task-id>.json
 *
 * 任务日志：
 *   <appHome>/logs/bug-analysis/<task-id>.log（见 bug-analysis-logger.ts）
 *
 * 事件流（在 task-stream.ts 全局命名空间，前端通过 Socket.IO 订阅 /tahp-run）：
 *   task.started        启动
 *   task.phase          阶段切换（FETCH_JIRA_INFO / DOWNLOAD_JIRA_LOGS / MATCH_SKILLS / ANALYZING / GENERATING_REPORT）
 *   task.stage_detail   Agent 输出的 TAHP_STAGE 结构化阶段详情（供 UI 展示）
 *   task.step           子步骤完成
 *   task.message        Agent 流式 chunk（level=stream）或一般日志
 *   task.skill_use      Agent 真实调用了 tool / skill（来自 tool.started 事件）
 *   task.tool_completed Agent tool 调用完成
 *   task.completed      完成 + 摘要
 *   task.failed         失败 + error
 *
 * 任务 ID 前缀:
 *   单条:  task-bug-<ts>-<rand>
 *   批量:  task-bugjob-<ts>-<rand> （父）+ task-bug-* （子）
 */
import { randomBytes } from 'crypto'
import { existsSync, mkdirSync, writeFileSync, readFileSync, rmSync, unlinkSync } from 'fs'
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
  fetchIssue, searchJQL, parseIssueKey,
  type JiraIssue, type JiraIssueSummary, type JiraConfig,
} from './jira'
import { logBug, appendBugLog, deleteBugLog, removeDistillRequestsForTask, bugLogPath } from './bug-analysis-logger'
import { buildFullTahpSystemContext, getTahpSkillsRootForPrompt, tahpSkillMdRelativePath } from './context-injector'
import { saveAgentPromptLog } from './prompt-log'
import {
  BUG_UI_PHASE_PROGRESS,
  findBugStageMarkers,
  formatStageDetailLines,
  extractBugAnalysisReportBody,
  type ParsedBugStageMarker,
} from './bug-analysis-stages'

// ─── Agent Bridge 客户端（单例） ────────────────────────────────────────────
//
// 复用一个 AgentBridgeClient（短连接），交给每个 task 独立的 session_id。
// 任务结束后会 destroy(session) 释放 Agent Pool 资源。
//
// 超时设置较长（30 分钟）：考虑到 Agent 真正会跑日志下载等耗时操作。
const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

// ─── 类型定义 ────────────────────────────────────────────────────────────────

// 历史保留的模块类型：BFF 不再据此判断或加载约束，仅作为 Agent **可能**在最终
// 报告中回填的一个标签（可选）。前端不再让用户选择此字段。
export type TahpBugModule = 'telephony' | 'kernel-driver' | 'power-mgmt' | 'shared'

export interface BugAnalysisInput {
  rawInput: string                // 用户输入: JIRA key 或 URL
  userDescription?: string        // 用户对 Bug 的补充描述
  extraContext?: string           // 其他附加信息
}

export interface ContinueAnalysisInput {
  additionalInfo: string          // 补充上下文
}

export interface BugAnalysisTaskCtx {
  taskId: string
  parentJobId?: string            // 批量任务的父 job id
  jiraKey: string
  jiraUrl: string
  title?: string                  // Agent fetch_jira 回填的 Issue 标题
  rawInput?: string               // 用户原始输入（仅作为 prompt 兜底）
  module?: TahpBugModule          // 可选 · 由 Agent 后续在报告里回填；BFF 不识别
  userDescription?: string
  extraContext?: string
  startedAt: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  progress?: number
  issue?: JiraIssue               // （已废弃 BFF JIRA fetch；保留字段防旧报告兼容）
  prevResponse?: string           // 上一轮 Agent 输出
  corrections: string[]           // 历次补充信息
  skillsUsed: string[]
  llmResponse?: string
  completedAt?: string
  error?: string
  /** Agent fetch_jira 阶段 TAHP_STAGE 字段快照 */
  jiraSnapshot?: Record<string, string>
}

export interface BugAnalysisJobCtx {
  jobId: string
  type: 'single' | 'batch'
  jql?: string
  taskIds: string[]               // 关联的子任务
  startedAt: string
  status: 'running' | 'completed' | 'failed'
  total: number
  completed: number
  failed: number
}

interface TaskRuntimeControl {
  sessionId: string
  interruptRequested: boolean
}

// ─── 内存状态 ────────────────────────────────────────────────────────────────
const taskCtx = new Map<string, BugAnalysisTaskCtx>()
const jobCtx = new Map<string, BugAnalysisJobCtx>()
const taskRuntime = new Map<string, TaskRuntimeControl>()

const MAX_KEEP = 200

function pruneOldTasks() {
  if (taskCtx.size <= MAX_KEEP) return
  const ids = Array.from(taskCtx.keys())
  for (const id of ids.slice(0, taskCtx.size - MAX_KEEP)) taskCtx.delete(id)
}

// ─── ID 生成 ─────────────────────────────────────────────────────────────────

function genTaskId(prefix = 'task-bug'): string {
  return `${prefix}-${Date.now()}-${randomBytes(3).toString('hex')}`
}

// ─── 事件推送 helper ─────────────────────────────────────────────────────────

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function settleJobIfDone(job: BugAnalysisJobCtx, aborted = false, abortReason = '') {
  if (job.completed + job.failed < job.total) return
  job.status = job.completed === 0 ? 'failed' : 'completed'
  emit(job.jobId, 'task.completed', {
    status: job.status,
    type: 'batch',
    total: job.total,
    completed: job.completed,
    failed: job.failed,
    aborted,
    message: aborted
      ? `批量 Bug 分析已终止：成功 ${job.completed} / 失败 ${job.failed}。原因：${abortReason}`
      : `批量 Bug 分析完成：成功 ${job.completed} / 失败 ${job.failed}`,
  })
}

// ─── 状态查询 (供 route 使用) ────────────────────────────────────────────────

export function getBugTask(taskId: string): BugAnalysisTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export function listBugTasks(): BugAnalysisTaskCtx[] {
  return Array.from(taskCtx.values()).sort((a, b) => b.startedAt.localeCompare(a.startedAt))
}

export function getBugJob(jobId: string): BugAnalysisJobCtx | undefined {
  return jobCtx.get(jobId)
}

export function listBugJobs(): BugAnalysisJobCtx[] {
  return Array.from(jobCtx.values()).sort((a, b) => b.startedAt.localeCompare(a.startedAt))
}

// ─── 报告路径 ────────────────────────────────────────────────────────────────

function reportDir(): string {
  const d = join(tahpPaths.reportsDir, 'bug-analysis')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

function reportPath(taskId: string): string {
  return join(reportDir(), `${taskId}.json`)
}

export function readBugReport(taskId: string): unknown {
  const p = reportPath(taskId)
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf-8')) } catch { return null }
}

export function listBugReports(): unknown[] {
  const d = reportDir()
  if (!existsSync(d)) return []
  // 复用 sync API；批量场景这里数量不大，直接 fs readdirSync
  const fs = require('fs') as typeof import('fs')
  const files = fs.readdirSync(d).filter((f: string) => f.endsWith('.json'))
  const summaries: any[] = []
  for (const f of files) {
    try {
      const json = JSON.parse(fs.readFileSync(join(d, f), 'utf-8'))
      summaries.push({
        task_id: json.task_id,
        jira_key: json.jira_key,
        jira_url: json.jira_url,
        module: json.module,
        title: json.title,
        status: json.status,
        started_at: json.started_at,
        completed_at: json.completed_at,
        duration_ms: json.duration_ms,
        skills_used: json.skills_used || [],
        correction_of: json.correction_of,
      })
    } catch { /* skip corrupt */ }
  }
  return summaries.sort((a, b) => String(b.started_at || '').localeCompare(String(a.started_at || '')))
}

function promptDirFor(taskId: string): string {
  return join(tahpPaths.reportsDir, 'bug-analysis', 'prompts', taskId)
}

function isSafeTaskId(taskId: string): boolean {
  return !!taskId && !taskId.includes('..') && !/[\\/]/.test(taskId)
}

/** 永久删除任务的历史落盘数据（报告、提示词、日志）及内存态 */
export async function deleteBugReport(taskId: string): Promise<{ ok: boolean; error?: string }> {
  if (!isSafeTaskId(taskId)) return { ok: false, error: '无效的任务 ID' }

  const jsonPath = reportPath(taskId)
  let deleted = false
  try {
    if (existsSync(jsonPath)) {
      unlinkSync(jsonPath)
      deleted = true
    }
    const promptDir = promptDirFor(taskId)
    if (existsSync(promptDir)) {
      rmSync(promptDir, { recursive: true, force: true })
      deleted = true
    }
    if (existsSync(bugLogPath(taskId))) {
      await deleteBugLog(taskId)
      deleted = true
    }
    await removeDistillRequestsForTask(taskId)
    if (taskCtx.has(taskId)) {
      taskCtx.delete(taskId)
      deleted = true
    }
    taskRuntime.delete(taskId)
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }
  if (!deleted) return { ok: false, error: `找不到任务记录: ${taskId}` }
  return { ok: true }
}

// ─── Agent Bridge 执行 ──────────────────────────────────────────────────────
//
// 说明（已移除的 BFF 启发式中间层）：
//   早期版本里 BFF 会做 inferModule / pickSkillHints / loadConstraintsSummary
//   等关键字匹配来给 Agent "提示候选"。实际效果是：
//   (a) 关键字命中率有限，往往误导多于辅助；
//   (b) Agent 拿到 JIRA 详情后会自行判断 Bug 域，BFF 的提示反而是噪声；
//   (c) 约束加载的 yaml 一锅炖（含其它 domain），意义不大。
//   因此现在直接让 Agent 用 jira-mcp / transsion-harness / BSP 分析 skill
//   一手拉数据 + 自主决策，BFF 不再做任何 Bug 域判断。

// ─── Agent Bridge 调用 ──────────────────────────────────────────────────────
//
// 通过 hermes agent-bridge 将任务发给 Claude Code Agent，监听流式输出。
// 该函数：
//   - 把 chunk.delta 经 filterBridgeToolCallMarkupDelta 过滤 tool 调用残留 markup 后，
//     以纯文本流的形式回调（onText）
//   - 解析 chunk.events 中的 tool.started / tool.completed，转换成 onTool 回调
//   - 任何 status === 'error' / 抛错都直接 throw，调用方决定是否记录任务失败
//
// 返回完整 assistant 文本（已去除 markup）。

interface AgentRunCallbacks {
  onText: (delta: string) => void
  onToolStarted: (toolName: string, args: unknown, toolCallId: unknown) => void
  onToolCompleted: (toolName: string, isError: boolean, toolCallId: unknown) => void
  onReasoning?: (text: string) => void
}

async function runAgentChat(
  sessionId: string,
  instructions: string,
  userMessage: string,
  cb: AgentRunCallbacks,
): Promise<{ fullResponse: string; runId: string }> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error(
      'Agent Bridge 未运行。智能诊断必须依赖 Claude Code Agent（含完整 Skill / MCP 工具链），' +
      '请确认 hermes CLI 已正确安装并启动（检查服务端日志中的 [agent-bridge] starting 信息）。',
    )
  }

  let started: AgentBridgeChatStarted
  try {
    started = await sharedBridgeClient.chat(
      sessionId,
      userMessage,
      undefined, // conversation_history
      instructions,
      'default', // profile
    )
  } catch (err) {
    throw new Error(`Agent 启动失败: ${(err as Error).message}`)
  }

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''

  let lastChunk: AgentBridgeOutput | null = null
  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 100 })) {
    lastChunk = chunk

    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'tool.started') {
        const toolName = (ev.tool_name as string) || 'unknown-tool'
        cb.onToolStarted(toolName, ev.args, ev.tool_call_id)
      } else if (evType === 'tool.completed') {
        const toolName = (ev.tool_name as string) || 'unknown-tool'
        cb.onToolCompleted(toolName, ev.is_error === true, ev.tool_call_id)
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
        throw new Error(chunk.error || 'Agent 运行出错')
      }
      if (chunk.status === 'interrupted') {
        throw new Error('Agent 运行被中断')
      }
      break
    }
  }

  if (!lastChunk || !lastChunk.done) {
    throw new Error('Agent 流式输出意外终止（无终止 chunk）')
  }

  return { fullResponse, runId: started.run_id }
}

// ─── 解析 LLM 中的 <skill_use /> 标记 ────────────────────────────────────────

const SKILL_USE_RE = /<skill_use\s+([^/>]+?)\s*\/?>/g

interface SkillUseHit {
  name: string
  purpose?: string
  index: number
}

function findSkillUseHits(text: string, fromIndex = 0): SkillUseHit[] {
  const hits: SkillUseHit[] = []
  SKILL_USE_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = SKILL_USE_RE.exec(text)) !== null) {
    if (m.index < fromIndex) continue
    const attrs = m[1]
    const nameMatch = attrs.match(/name\s*=\s*"([^"]+)"/) || attrs.match(/name\s*=\s*'([^']+)'/)
    if (!nameMatch) continue
    const purposeMatch = attrs.match(/purpose\s*=\s*"([^"]+)"/) || attrs.match(/purpose\s*=\s*'([^']+)'/)
    hits.push({ name: nameMatch[1], purpose: purposeMatch?.[1], index: m.index })
  }
  return hits
}

// ─── 预备阶段（连接 Bridge，不计入 UI 五步进度） ─────────────────────────────

function emitPrepPhase(taskId: string, ctx: BugAnalysisTaskCtx, phase: 'PREPARING' | 'CONNECTING_AGENT', message: string) {
  const progress = phase === 'PREPARING' ? 5 : 10
  ctx.phase = phase
  ctx.progress = progress
  emit(taskId, 'task.phase', { phase, progress, message })
}

function applyParsedStageMarker(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
  marker: ParsedBugStageMarker,
) {
  if (marker.markerId === 'fetch_jira') {
    ctx.jiraSnapshot = { ...(ctx.jiraSnapshot || {}), ...marker.fields }
    if (marker.fields.issue_summary) ctx.title = marker.fields.issue_summary
  }
  ctx.phase = marker.phase
  const progress = marker.markerId === 'generate_report' && marker.status === 'success'
    ? 100
    : BUG_UI_PHASE_PROGRESS[marker.phase]
  ctx.progress = progress
  const message = marker.fields.message || ''
  emit(taskId, 'task.phase', {
    phase: marker.phase,
    progress,
    message,
  })
  const stepStatus = marker.status === 'success'
    ? 'completed'
    : marker.status === 'failed'
      ? 'failed'
      : 'running'
  emit(taskId, 'task.step', {
    step_id: marker.stepId,
    status: stepStatus,
    message,
  })
  emit(taskId, 'task.stage_detail', {
    stage_id: marker.markerId,
    phase: marker.phase,
    step_id: marker.stepId,
    status: marker.status,
    skill_used: marker.fields.skill_used || '',
    message,
    fields: marker.fields,
    detail_lines: formatStageDetailLines(marker.markerId, marker.fields),
  })
}

function ingestStageMarkersFromText(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
  fullText: string,
  state: { lastIndex: number },
) {
  const markers = findBugStageMarkers(fullText, state.lastIndex)
  for (const marker of markers) {
    state.lastIndex = Math.max(state.lastIndex, marker.startIndex + marker.rawBlock.length)
    applyParsedStageMarker(taskId, ctx, marker)
  }
}

function buildReportJiraSection(ctx: BugAnalysisTaskCtx): Record<string, unknown> {
  const snap = ctx.jiraSnapshot || {}
  const issue = ctx.issue
  if (issue) {
    return {
      key: issue.key,
      url: issue.url,
      summary: issue.summary,
      status: issue.status,
      priority: issue.priority,
      assignee: issue.assignee,
      reporter: issue.reporter,
      components: issue.components,
      labels: issue.labels,
      attachments: issue.attachments,
      description: issue.description?.slice(0, 5000),
      commentCount: issue.comments.length,
    }
  }
  const section: Record<string, unknown> = {
    key: ctx.jiraKey,
    url: ctx.jiraUrl,
    summary: snap.issue_summary || ctx.title || ctx.jiraKey,
  }
  if (snap.status) section.status = snap.status
  if (snap.priority) section.priority = snap.priority
  if (snap.assignee) section.assignee = snap.assignee
  if (snap.reporter) section.reporter = snap.reporter
  if (snap.description || snap.description_preview) {
    section.description = (snap.description || snap.description_preview).slice(0, 5000)
  }
  if (snap.fetch_ok) section.fetch_ok = snap.fetch_ok
  if (snap.skill_used) section.skill_used = snap.skill_used
  if (snap.comment_count) section.commentCount = Number(snap.comment_count) || snap.comment_count
  if (snap.attachment_count) section.attachmentCount = Number(snap.attachment_count) || snap.attachment_count
  if (snap.log_paths) section.log_paths = snap.log_paths
  if (Object.keys(snap).length === 0) {
    section.note = 'Agent 尚未回报 JIRA 拉取详情'
  }
  return section
}

// ─── 提示词构建（Agent 模式 + 工程 Skill 目录注入，路径均为相对工程根） ─────

const AGENT_INSTRUCTIONS_BASE = `你是 TAHP（TECNO AI Harness Platform）"智能诊断专家"，运行在传音 Android 底软集成部的 Agent 环境中。

# 执行原则
1. **必须真正调用 Skill / 工具**，不要假装使用；用户可在界面核对工具调用记录。
2. **优先拉取一手数据**：JIRA、附件、日志 —— 不要凭印象编造。
3. **失败即停止并显式上报**：任何步骤失败须说明原因，不要猜测兜底。
4. 中文输出，结构清晰、可执行。

# 强制执行步骤（必须严格按顺序，不得跳步）

## Step 1 — 拉取 JIRA 信息
1. **必须先 Read** Skill 文件：\`__JIRA_OPS_SKILL__\`
2. 严格按 \`jira-ops\` SKILL.md 的 SOP，拉取用户给出的 JIRA Issue 完整信息（标题、描述、状态、评论、附件清单）。
3. 完成后**立即**输出阶段标记 \`fetch_jira\`（见下文格式），\`status\` 填 \`success\` 或 \`failed\`。

## Step 2 — 下载 JIRA 日志
1. 继续遵循已 Read 的 \`jira-ops\` SKILL.md。
2. 从 Step 1 的 Issue 信息与 JIRA 附件中，下载/提取日志包（含描述中的 http(s) / UNC 日志链接）。
3. 完成后**立即**输出阶段标记 \`download_logs\`；若确无日志可下载，\`logs_downloaded: false\` 并说明原因，仍可 \`success\` 进入下一步。

## Step 3 — 匹配分析 Skill
1. 结合 JIRA **标题 + 描述 + 评论** 与已下载日志类型，在工程 Skill 根目录 \`__TAHP_SKILLS_REL_ROOT__\` 下**自主匹配** 1～3 个最相关的分析 Skill（参考系统提示词末尾「已扫描到的 Skills」索引，禁止编造 skillId）。
2. 对每个匹配到的 skillId，**必须 Read** \`__TAHP_SKILLS_REL_ROOT__/<skillId>/SKILL.md\` 全文。
3. 完成后**立即**输出阶段标记 \`match_skills\`，在 \`matched_skills\` 中列出匹配到的 skillId（逗号分隔）；若未匹配到，\`skills_matched: false\` 并说明原因。

## Step 4 — 大模型分析
1. 依据 Step 1～3 的 JIRA 信息、日志与已 Read 的 Skill SOP，执行根因分析。
2. 开始分析时输出 \`analyze\` 标记（\`status: running\`）；分析结论就绪后输出 \`analyze\`（\`status: success\`）。

## Step 5 — 生成分析报告
1. 输出完整 8 节 Markdown 报告（结构见下文）。
2. 报告正文开始输出前，先输出 \`generate_report\`（\`status: running\`）；报告全部写完后再输出 \`generate_report\`（\`status: success\`，\`report_ready: true\`）。

# 结构化阶段标记（每步完成后必须输出，供 BFF 解析更新 UI）

**在进入下一步之前**，必须输出一段标记块（可输出在分析报告正文之前，勿嵌入 8 节报告中间）：

\`\`\`
=== TAHP_STAGE:<stage_id> ===
status: running|success|failed
skill_used: <skill-id 或 none>
message: <一句话说明本步结果>
# 按阶段填写可选字段：
# fetch_jira: jira_key, fetch_ok, issue_summary, status, priority, assignee, reporter, description_preview, comment_count, attachment_count
# download_logs: logs_downloaded, log_paths, attachment_count
# match_skills: skills_matched, matched_skills, match_note
# analyze: analysis_started, matched_skills
# generate_report: report_ready
=== END_TAHP_STAGE ===
\`\`\`

\`stage_id\` 必须是：\`fetch_jira\` | \`download_logs\` | \`match_skills\` | \`analyze\` | \`generate_report\`

# 8 节分析报告（Step 5 正文，每节 H2 标题，不要省略）

### 1. 摘要 / TL;DR
### 2. 复现路径
### 3. 关键日志识别
### 4. 根因定位（最关键）
### 5. 影响范围
### 6. 修复建议
### 7. 验证方案
### 8. 风险与遗留问题

# 输出末尾（必填）
\`\`\`
=== TOOLS_INVOKED ===
- <工具/Skill 名>: <用途>
=== END ===
\`\`\`

# 红线
- 不要编造文件 / 函数 / 配置项名
- 不要给完整 patch，只给修改方向
- 工具失败时直接报错并停止该步骤
`

function buildBugAnalysisInstructions(userMessage: string): string {
  const skillsRel = getTahpSkillsRootForPrompt()
  const jiraOpsSkill = tahpSkillMdRelativePath('jira-ops')
  const base = AGENT_INSTRUCTIONS_BASE
    .replace(/__TAHP_SKILLS_REL_ROOT__/g, skillsRel)
    .replace(/__JIRA_OPS_SKILL__/g, jiraOpsSkill)
  const tahpCtx = buildFullTahpSystemContext(userMessage, { scenario: 'bug_analysis' })
  return tahpCtx ? `${base}\n\n${tahpCtx}` : base
}

function buildAgentUserMessage(ctx: BugAnalysisTaskCtx, correction?: string): string {
  const blocks: string[] = []
  blocks.push(`# 待分析 Bug`)
  blocks.push(`- JIRA Key: **${ctx.jiraKey}**`)
  blocks.push(`- JIRA URL: ${ctx.jiraUrl}`)

  if (ctx.userDescription) {
    blocks.push('')
    blocks.push('## 用户补充描述')
    blocks.push(ctx.userDescription)
  }
  if (ctx.extraContext) {
    blocks.push('')
    blocks.push('## 附加上下文（本地已有的日志摘要等）')
    blocks.push(ctx.extraContext)
  }

  if (ctx.prevResponse) {
    blocks.push('')
    blocks.push('## 上一轮 Agent 分析结果（请基于此更新 / 修正）')
    blocks.push(ctx.prevResponse.slice(0, 4000))
  }
  if (correction) {
    blocks.push('')
    blocks.push('## 用户本轮补充信息 / 修正意见')
    blocks.push(correction)
    blocks.push('')
    blocks.push('请基于上述补充重新生成完整的 8 节分析报告。')
  } else {
    blocks.push('')
    blocks.push('请严格按系统提示词的五步工作流执行：jira-ops 拉 JIRA → jira-ops 下载日志 → 匹配 Skill → 分析 → 输出 8 节报告；每步完成后输出 TAHP_STAGE 标记。')
  }

  return blocks.join('\n')
}

// ─── 单条 Bug 分析（核心执行 - Agent 模式） ─────────────────────────────────

async function runSingleBugAnalysis(
  ctx: BugAnalysisTaskCtx,
  correction?: string,        // 补充信息继续分析时传入
): Promise<void> {
  const startMs = Date.now()
  const taskId = ctx.taskId
  if (ctx.status === 'cancelled') return
  ctx.status = 'running'
  ctx.skillsUsed = ctx.skillsUsed || []
  taskCtx.set(taskId, ctx)
  pruneOldTasks()

  logBug(taskId, 'info', `开始 Bug 分析 (Agent 模式) task=${taskId} jira=${ctx.jiraKey}${correction ? ' (continue)' : ''}`)

  // 用于 destroy session 的 sessionId（即使提前 throw 也能回收）
  const agentSessionId = `tahp-bug-${taskId}`
  taskRuntime.set(taskId, { sessionId: agentSessionId, interruptRequested: false })

  const stageMarkerState = { lastIndex: 0 }

  try {
    const userMessage = buildAgentUserMessage(ctx, correction)
    const instructions = buildBugAnalysisInstructions(userMessage)
    const promptLog = saveAgentPromptLog(taskId, 'bug-analysis', instructions, userMessage)
    logBug(taskId, 'info', `Agent 提示词已落盘: ${promptLog.promptDir}`)
    emitPrepPhase(taskId, ctx, 'PREPARING', '准备提交给 Agent（提示词已落盘）...')

    emitPrepPhase(taskId, ctx, 'CONNECTING_AGENT', '连接 Agent Bridge...')
    const manager = getAgentBridgeManager()
    if (!manager.running) {
      throw new Error(
        'Agent Bridge 未运行。智能诊断必须由 Agent 执行（含 Skill 工具链）。' +
        '请检查 hermes CLI 是否已安装、agent-bridge 是否启动（查看服务端日志 [agent-bridge] 行）。',
      )
    }
    logBug(taskId, 'info', `Agent Bridge ready, session=${agentSessionId}`)

    let lastSkillHitIdx = 0
    let toolCallCount = 0

    const { fullResponse } = await runAgentChat(agentSessionId, instructions, userMessage, {
      onText: (delta) => {
        emit(taskId, 'task.message', { level: 'stream', text: delta })

        const fullSoFar = (ctx.llmResponse || '') + delta
        ctx.llmResponse = fullSoFar
        ingestStageMarkersFromText(taskId, ctx, fullSoFar, stageMarkerState)

        const hits = findSkillUseHits(fullSoFar, lastSkillHitIdx)
        for (const h of hits) {
          if (!ctx.skillsUsed.includes(h.name)) {
            ctx.skillsUsed.push(h.name)
            emit(taskId, 'task.skill_use', {
              skill_id: h.name,
              source: 'text_marker',
              purpose: h.purpose || '',
              message: `Skill 标记：${h.name}${h.purpose ? ' — ' + h.purpose : ''}`,
            })
            logBug(taskId, 'info', `skill_use (marker): ${h.name}`)
          }
          lastSkillHitIdx = Math.max(lastSkillHitIdx, h.index + 1)
        }
      },
      onToolStarted: (toolName, args, toolCallId) => {
        toolCallCount += 1
        if (!ctx.skillsUsed.includes(toolName)) ctx.skillsUsed.push(toolName)
        const argPreview = summarizeArgs(args)
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          args: argPreview,
          purpose: `Agent 真实调用工具 ${toolName}`,
          message: `🛠 Agent 调用：${toolName}${argPreview ? ` ${argPreview}` : ''}`,
        })
        logBug(taskId, 'info', `tool.started: ${toolName} ${argPreview}`)
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `✗ 工具失败：${toolName}` : `✓ 工具完成：${toolName}`,
        })
        logBug(taskId, isError ? 'warn' : 'info', `tool.completed: ${toolName} ${isError ? '(error)' : ''}`)
      },
      onReasoning: (text) => {
        if (text) emit(taskId, 'task.message', { level: 'reasoning', text })
      },
    })

    ctx.llmResponse = fullResponse
    ingestStageMarkersFromText(taskId, ctx, fullResponse, stageMarkerState)

    logBug(taskId, 'info', `Agent run complete (${fullResponse.length} chars, tools=${toolCallCount}, skills_recorded=${ctx.skillsUsed.join(',') || 'none'})`)

    ctx.phase = 'GENERATING_REPORT'
    ctx.progress = BUG_UI_PHASE_PROGRESS.GENERATING_REPORT
    emit(taskId, 'task.phase', {
      phase: 'GENERATING_REPORT',
      progress: BUG_UI_PHASE_PROGRESS.GENERATING_REPORT,
      message: '生成报告并落盘...',
    })
    emit(taskId, 'task.step', { step_id: 'generate-report', status: 'running', message: '正在落盘 JSON 报告...' })

    ctx.prevResponse = fullResponse
    if (correction) ctx.corrections.push(correction)

    const completedAt = new Date().toISOString()
    const durationMs = Date.now() - startMs
    ctx.status = 'completed'
    ctx.completedAt = completedAt
    ctx.phase = 'COMPLETED'
    ctx.progress = 100
    emit(taskId, 'task.phase', {
      phase: 'COMPLETED',
      progress: 100,
      message: 'Bug 分析完成',
    })

    const reportBody = extractBugAnalysisReportBody(fullResponse)
    const report = {
      task_id: taskId,
      jira_key: ctx.jiraKey,
      jira_url: ctx.jiraUrl,
      module: ctx.module,
      title: ctx.jiraSnapshot?.issue_summary || ctx.title || ctx.rawInput || ctx.jiraKey,
      status: 'completed',
      execution_mode: 'agent',
      agent_session_id: agentSessionId,
      started_at: ctx.startedAt,
      completed_at: completedAt,
      duration_ms: durationMs,
      user_description: ctx.userDescription,
      extra_context: ctx.extraContext,
      corrections: ctx.corrections,
      correction_of: undefined,
      skills_used: ctx.skillsUsed,
      tool_call_count: toolCallCount,
      llm_response: fullResponse,
      report_body: reportBody,
      jira: buildReportJiraSection(ctx),
    }
    try {
      writeFileSync(reportPath(taskId), JSON.stringify(report, null, 2), 'utf-8')
      emit(taskId, 'task.step', { step_id: 'generate-report', status: 'completed', message: '报告已落盘' })
      logBug(taskId, 'info', `report written: ${reportPath(taskId)}`)
    } catch (e) {
      logBug(taskId, 'error', `report write failed: ${(e as Error).message}`)
    }

    emit(taskId, 'task.completed', {
      status: 'completed',
      jira_key: ctx.jiraKey,
      module: ctx.module,
      duration_ms: durationMs,
      skills_used: ctx.skillsUsed,
      response_length: fullResponse.length,
      message: `Bug 分析完成（${ctx.jiraKey}），使用 Skill: ${ctx.skillsUsed.join(', ') || '无'}`,
    })

    // ── 更新父 job 状态 ───────────────────────────────────────────────────
    if (ctx.parentJobId) {
      const job = jobCtx.get(ctx.parentJobId)
      if (job) {
        job.completed += 1
        if (job.completed + job.failed >= job.total) {
          job.status = job.failed === 0 ? 'completed' : (job.completed === 0 ? 'failed' : 'completed')
          emit(job.jobId, 'task.completed', {
            status: job.status,
            type: 'batch',
            total: job.total,
            completed: job.completed,
            failed: job.failed,
            message: `批量 Bug 分析完成：成功 ${job.completed} / 失败 ${job.failed}`,
          })
        } else {
          emit(job.jobId, 'task.phase', {
            phase: 'BATCH_RUNNING',
            progress: Math.round(((job.completed + job.failed) / job.total) * 100),
            message: `批量进度 ${job.completed + job.failed} / ${job.total}`,
          })
        }
      }
    }

  } catch (err) {
    const control = taskRuntime.get(taskId)
    const interruptedByUser = control?.interruptRequested === true
    const msg = interruptedByUser ? '任务已被用户中断' : (err as Error).message
    logger.warn({ taskId, err: msg }, '[bug-analysis] failed')
    logBug(taskId, interruptedByUser ? 'warn' : 'error', `task failed: ${msg}`)
    ctx.status = interruptedByUser ? 'cancelled' : 'failed'
    ctx.error = msg
    ctx.completedAt = new Date().toISOString()
    if (interruptedByUser) {
      emit(taskId, 'task.cancelled', { error: msg, message: msg })
    } else {
      emit(taskId, 'task.failed', { error: msg, message: `分析失败: ${msg}` })
    }

    // 写入失败报告
    try {
      const report = {
        task_id: taskId,
        jira_key: ctx.jiraKey,
        jira_url: ctx.jiraUrl,
        module: ctx.module,
        status: 'failed',
        error: msg,
        started_at: ctx.startedAt,
        completed_at: ctx.completedAt,
        user_description: ctx.userDescription,
        extra_context: ctx.extraContext,
      }
      writeFileSync(reportPath(taskId), JSON.stringify(report, null, 2), 'utf-8')
    } catch { /* swallow */ }

    if (ctx.parentJobId) {
      const job = jobCtx.get(ctx.parentJobId)
      if (job) {
        job.failed += 1
        if (job.completed + job.failed >= job.total) {
          settleJobIfDone(job)
        } else {
          emit(job.jobId, 'task.phase', {
            phase: 'BATCH_RUNNING',
            progress: Math.round(((job.completed + job.failed) / job.total) * 100),
            message: `批量进度 ${job.completed + job.failed} / ${job.total}`,
          })
        }
      }
    }
  } finally {
    // 释放 Agent Pool 中对应的 session（失败/成功都做，幂等）
    sharedBridgeClient.destroy(agentSessionId).catch((e) => {
      logBug(taskId, 'warn', `destroy agent session failed: ${(e as Error).message}`)
    })
    taskRuntime.delete(taskId)
    await appendBugLog(taskId, 'info', '── task end ──')
  }
}

// ─── 工具调用参数摘要 (用于 task.skill_use 消息展示) ────────────────────────

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const obj = args as Record<string, unknown>
  const keys = Object.keys(obj)
  if (keys.length === 0) return ''
  // 抓 1~2 个最关键字段做预览（command/path/url/query/...）
  const prio = ['command', 'cmd', 'shell', 'tool', 'path', 'file', 'file_path', 'url', 'query', 'jql', 'key', 'issue_key']
  const picked: string[] = []
  for (const k of prio) {
    if (k in obj) {
      const v = obj[k]
      if (typeof v === 'string') picked.push(`${k}=${truncateStr(v, 60)}`)
      else if (v != null) picked.push(`${k}=${truncateStr(JSON.stringify(v), 60)}`)
      if (picked.length >= 2) break
    }
  }
  if (picked.length === 0) {
    const first = keys[0]
    const v = obj[first]
    if (typeof v === 'string') picked.push(`${first}=${truncateStr(v, 60)}`)
    else picked.push(`${first}=${truncateStr(JSON.stringify(v), 60)}`)
  }
  return `(${picked.join(', ')})`
}

function truncateStr(s: string, max: number): string {
  if (s.length <= max) return s
  return s.slice(0, max - 1) + '…'
}

// ─── 公开入口：启动单条 Bug 分析 ─────────────────────────────────────────────

export interface StartTaskResult {
  ok: boolean
  taskId?: string
  jiraKey?: string
  error?: string
}

export function startSingleBugAnalysis(input: BugAnalysisInput): StartTaskResult {
  const key = parseIssueKey(input.rawInput)
  if (!key) return { ok: false, error: `无法从输入解析 JIRA Key: ${input.rawInput}` }

  const taskId = genTaskId()
  const jiraBase = (process.env.TAHP_JIRA_BASE_URL || 'http://jira.transsion.com').replace(/\/+$/, '')
  const ctx: BugAnalysisTaskCtx = {
    taskId,
    jiraKey: key,
    jiraUrl: `${jiraBase}/browse/${key}`,
    rawInput: input.rawInput,
    userDescription: input.userDescription,
    extraContext: input.extraContext,
    startedAt: new Date().toISOString(),
    status: 'running',
    corrections: [],
    skillsUsed: [],
  }
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.started', {
    type: 'single',
    jira_key: key,
    jira_url: ctx.jiraUrl,
    message: `智能诊断任务已启动: ${key}`,
  })
  logBug(taskId, 'info', `task.started single ${key}`)

  setImmediate(() => {
    runSingleBugAnalysis(ctx).catch(err => {
      logger.error({ err: (err as Error).message, taskId }, '[bug-analysis] unhandled')
    })
  })

  return { ok: true, taskId, jiraKey: key }
}

// ─── 公开入口：补充信息继续分析 ─────────────────────────────────────────────

export function continueBugAnalysis(prevTaskId: string, input: ContinueAnalysisInput): StartTaskResult {
  const prev = taskCtx.get(prevTaskId)
  if (!prev) {
    // 尝试从报告恢复（场景：服务重启）
    const report = readBugReport(prevTaskId) as any
    if (!report) return { ok: false, error: `找不到原任务 ${prevTaskId}` }
    const newTaskId = genTaskId()
    const ctx: BugAnalysisTaskCtx = {
      taskId: newTaskId,
      jiraKey: report.jira_key,
      jiraUrl: report.jira_url,
      module: report.module as TahpBugModule | undefined,
      userDescription: report.user_description,
      extraContext: report.extra_context,
      startedAt: new Date().toISOString(),
      status: 'running',
      corrections: Array.isArray(report.corrections) ? [...report.corrections] : [],
      skillsUsed: [],
      prevResponse: report.llm_response,
    }
    taskCtx.set(newTaskId, ctx)
    emit(newTaskId, 'task.started', {
      type: 'continue',
      from_task_id: prevTaskId,
      jira_key: ctx.jiraKey,
      jira_url: ctx.jiraUrl,
      message: `补充信息继续分析: ${ctx.jiraKey}（基于报告恢复）`,
    })
    setImmediate(() => {
      runSingleBugAnalysis(ctx, input.additionalInfo).catch(err => {
        logger.error({ err: (err as Error).message, newTaskId }, '[bug-analysis] continue unhandled')
      })
    })
    return { ok: true, taskId: newTaskId, jiraKey: ctx.jiraKey }
  }

  const newTaskId = genTaskId()
  const ctx: BugAnalysisTaskCtx = {
    taskId: newTaskId,
    jiraKey: prev.jiraKey,
    jiraUrl: prev.jiraUrl,
    module: prev.module,
    userDescription: prev.userDescription,
    extraContext: prev.extraContext,
    startedAt: new Date().toISOString(),
    status: 'running',
    corrections: [...prev.corrections],
    skillsUsed: [],
    issue: prev.issue,
    prevResponse: prev.llmResponse || prev.prevResponse,
  }
  taskCtx.set(newTaskId, ctx)
  emit(newTaskId, 'task.started', {
    type: 'continue',
    from_task_id: prevTaskId,
    jira_key: ctx.jiraKey,
    jira_url: ctx.jiraUrl,
    message: `补充信息继续分析: ${ctx.jiraKey}`,
  })
  logBug(newTaskId, 'info', `task.started continue from=${prevTaskId} jira=${ctx.jiraKey}`)

  setImmediate(() => {
    runSingleBugAnalysis(ctx, input.additionalInfo).catch(err => {
      logger.error({ err: (err as Error).message, newTaskId }, '[bug-analysis] continue unhandled')
    })
  })

  return { ok: true, taskId: newTaskId, jiraKey: ctx.jiraKey }
}

// ─── 公开入口：JQL 批量分析 ──────────────────────────────────────────────────

export interface StartBatchResult {
  ok: boolean
  jobId?: string
  total?: number
  tasks?: Array<{ task_id: string; jira_key: string }>
  error?: string
}

const MAX_BATCH_SIZE = 20

export async function startBatchBugAnalysis(jql: string, extraContext?: string, jiraCfg?: JiraConfig): Promise<StartBatchResult> {
  if (!jql?.trim()) return { ok: false, error: '空 JQL' }

  const jobId = genTaskId('task-bugjob')
  const search = await searchJQL(jql, jiraCfg, MAX_BATCH_SIZE)
  if (!search.ok || !search.data) {
    return { ok: false, error: search.error || 'JQL 查询失败' }
  }
  const candidates = search.data.issues
  if (!candidates.length) {
    return { ok: false, error: 'JQL 未匹配到任何 Issue' }
  }

  const job: BugAnalysisJobCtx = {
    jobId,
    type: 'batch',
    jql,
    taskIds: [],
    startedAt: new Date().toISOString(),
    status: 'running',
    total: candidates.length,
    completed: 0,
    failed: 0,
  }
  jobCtx.set(jobId, job)

  const tasks: Array<{ task_id: string; jira_key: string }> = []
  for (const issue of candidates) {
    const tid = genTaskId()
    const ctx: BugAnalysisTaskCtx = {
      taskId: tid,
      parentJobId: jobId,
      jiraKey: issue.key,
      jiraUrl: issue.url,
      startedAt: new Date().toISOString(),
      status: 'pending',
      corrections: [],
      skillsUsed: [],
      extraContext,
    }
    taskCtx.set(tid, ctx)
    job.taskIds.push(tid)
    tasks.push({ task_id: tid, jira_key: issue.key })
  }

  emit(jobId, 'task.started', {
    type: 'batch',
    jql,
    total: candidates.length,
    truncated: search.data.truncated,
    tasks,
    message: `批量 Bug 分析启动：共 ${candidates.length} 单${search.data.truncated ? '（已截断至上限）' : ''}`,
  })
  logBug(jobId, 'info', `batch.started jql=${jql.slice(0, 200)} total=${candidates.length}`)

  // 串行执行（避免 Agent 并发过高，且方便用户在 UI 上跟随观察）。
  // 任一子任务 Agent 失败 → **终止后续任务**（按用户需求，不再继续跑剩下的）。
  // 剩余未跑的任务会被标记为 cancelled，并在事件流里显示原因。
  setImmediate(async () => {
    let aborted = false
    let abortReason = ''
    for (const tid of job.taskIds) {
      const ctx = taskCtx.get(tid)
      if (!ctx) continue
      if (ctx.status === 'cancelled') continue

      if (aborted) {
        ctx.status = 'failed'
        ctx.error = `批量已终止：${abortReason}`
        ctx.completedAt = new Date().toISOString()
        emit(tid, 'task.failed', {
          parent_job_id: jobId,
          error: ctx.error,
          message: `子任务取消（前序任务失败已终止批量）`,
        })
        logBug(tid, 'warn', `child task cancelled (batch aborted): ${abortReason}`)
        job.failed += 1
        continue
      }

      emit(tid, 'task.started', {
        type: 'single',
        parent_job_id: jobId,
        jira_key: ctx.jiraKey,
        jira_url: ctx.jiraUrl,
        message: `子任务启动: ${ctx.jiraKey}`,
      })
      logBug(tid, 'info', `child task.started parent=${jobId}`)

      try {
        await runSingleBugAnalysis(ctx)
        if (ctx.status === 'failed') {
          aborted = true
          abortReason = ctx.error || '子任务执行失败'
          logger.warn({ jobId, tid, reason: abortReason }, '[bug-analysis] batch aborted due to child failure')
          emit(jobId, 'task.message', {
            level: 'warn',
            text: `子任务 ${ctx.jiraKey} 失败，终止批量后续任务：${abortReason}`,
          })
          logBug(jobId, 'warn', `batch aborted by child ${tid}: ${abortReason}`)
        }
        const latest = taskCtx.get(tid)
        if (latest?.status === 'cancelled') {
          logBug(jobId, 'warn', `child task cancelled by user: ${tid}`)
        }
      } catch (err) {
        aborted = true
        abortReason = (err as Error).message
        logger.warn({ err: abortReason, tid }, '[bug-analysis] batch child threw')
      }
    }

    // 最终态修正（runSingleBugAnalysis 内部会维护正常完成路径的 job.status，
    // 但若中途 cancel 了剩余任务，状态可能还未到 terminal state）
    if (job.status === 'running') {
      const allDone = job.completed + job.failed >= job.total
      if (allDone) {
        settleJobIfDone(job, aborted, abortReason)
      }
    }
  })

  return { ok: true, jobId, total: candidates.length, tasks }
}

// ─── Helper: 从内存或 JIRA fetch 出一份完整的 issue 预览（供前端单独预览） ───

export async function previewSingleIssue(
  rawInput: string,
  jiraCfg?: JiraConfig,
): Promise<{ ok: boolean; key?: string; issue?: JiraIssue; error?: string }> {
  const key = parseIssueKey(rawInput)
  if (!key) return { ok: false, error: `无法解析 JIRA Key: ${rawInput}` }
  const r = await fetchIssue(key, jiraCfg)
  if (!r.ok || !r.data) return { ok: false, key, error: r.error || 'JIRA fetch 失败' }
  return { ok: true, key, issue: r.data }
}

// 暴露用于测试 / 路由直接使用
export { genTaskId as _genTaskId }
// 暴露 jira summary helper for batch preview
export { searchJQL as _previewJQL, fetchIssue as _previewIssue }

export async function cancelBugTask(taskId: string): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running'; error?: string }> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (ctx.status === 'completed' || ctx.status === 'failed' || ctx.status === 'cancelled') {
    return { ok: false, error: `任务已结束，当前状态: ${ctx.status}` }
  }

  if (ctx.status === 'pending') {
    ctx.status = 'cancelled'
    ctx.error = '任务已取消（等待中）'
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.cancelled', { error: ctx.error, message: ctx.error })
    logBug(taskId, 'warn', 'task cancelled while pending')
    if (ctx.parentJobId) {
      const job = jobCtx.get(ctx.parentJobId)
      if (job) {
        job.failed += 1
        settleJobIfDone(job)
      }
    }
    return { ok: true, action: 'cancelled_pending' }
  }

  const control = taskRuntime.get(taskId) || { sessionId: `tahp-bug-${taskId}`, interruptRequested: false }
  control.interruptRequested = true
  taskRuntime.set(taskId, control)
  emit(taskId, 'task.message', { level: 'warn', text: '已请求强行中断任务，等待 Agent 停止...' })
  logBug(taskId, 'warn', `task interrupt requested: ${control.sessionId}`)

  // 后台执行中断，避免前端请求阻塞导致“点击无反应”
  setImmediate(() => {
    sharedBridgeClient.interrupt(control.sessionId, '用户手动中断任务').catch((err) => {
      logBug(taskId, 'warn', `task interrupt rpc failed: ${(err as Error).message}`)
    })
  })
  return { ok: true, action: 'interrupted_running' }
}

export type { JiraIssue, JiraIssueSummary }
