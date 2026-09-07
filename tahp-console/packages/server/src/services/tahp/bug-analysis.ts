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
 *   - 把 Bug 任务投递到 Agent Bridge，监听并转发 tool.started / tool.completed / tool.output / 文本 delta
 *   - 通过 TaskStream 推送 task.* 事件给前端实时显示
 *   - 支持"补充信息继续分析"（同任务、同 Agent 会话续聊）
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
  fetchIssue, searchJQL, searchJQLAll, parseIssueKey,
  type JiraIssue, type JiraIssueSummary, type JiraConfig,
} from './jira'
import {
  failedJobTasks,
  listPersistedBugJobs,
  readPersistedBugJob,
  saveBugJob,
  unfinishedJobTasks,
  type PersistedBugJobTask,
} from './bug-analysis-job-store'
import { logBug, appendBugLog, deleteBugLog, removeDistillRequestsForTask, bugLogPath } from './bug-analysis-logger'
import { buildFullTahpSystemContext, getTahpSkillsRootForPrompt, tahpSkillMdRelativePath } from './context-injector'
import {
  buildRemoteChannelDirective,
  listEnabledRemotePreferredSkillIds,
  readBugAnalysisChannelConfig,
  snapshotRemoteChannelsForReport,
} from './bug-analysis-config'
import {
  buildCodeSourceDirective,
  buildCodeSourceUserBlock,
  codeSourcePreferredSkillIds,
  parseCodeSource,
  restoreCodeSourceFromReport,
  snapshotCodeSourceForReport,
  type CodeSourceRef,
} from './code-source'
import { saveAgentPromptLog } from './prompt-log'
import {
  BUG_UI_PHASE_PROGRESS,
  BugAnalysisEmptyResultError,
  evaluateRunOutcome,
  extractBugAnalysisReportBody,
  findBugStageMarkers,
  formatStageDetailLines,
  truncateForReport,
  type ParsedBugStageMarker,
} from './bug-analysis-stages'
import {
  detectSkillImprove,
  formatSkillImproveSummary,
  mergeLedgerSkillImproves,
  parseSkillImproves,
  skillImprovesNeedUpdate,
  upsertSkillImprove,
  type SkillImproveRecord,
} from './bug-analysis-skill-improve'
import { loadCuratorLedger } from '../hermes/skill-improve-registry'
import { snapshotImprovedSkills, skillImproveSnapshotRoot, readSkillSnapshot } from './bug-analysis-skill-snapshot'
import { scheduleSkillImproveReconcile } from './bug-analysis-skill-reconcile'
import {
  APPROVAL_AUTO_ONCE_MS,
  findUserInputMarkers,
  buildUserInputResumeMessage,
  type ApprovalRequestPayload,
  type ParsedUserInputRequest,
  type UserInputResponseRecord,
} from './bug-analysis-interaction'
import { runJiraOpsAddComment } from './jira-ops-runner'
import { composeDefaultJiraCommentFromReport, preprocessJiraCommentForSubmit } from './compose-jira-comment'
import {
  JIRA_DUP_JUDGE_SKILL_ID,
  buildJiraDupJudgeInstructions,
  buildJiraDupJudgePrompt,
  jiraDupJudgeSessionId,
  resolveJiraBrowseUrl,
} from './jira-dup-judge'
import { hasJiraBasicCredentials, resolveJiraConfig } from './jira-user-config'
import {
  buildSilentCredentialResumeMessage,
  ensureLoginsightCredentialsForBugAnalysis,
  fillSilentCredentialValues,
  isLlmCredentialUserInput,
  redactUserInputValues,
} from './bug-analysis-credentials'

// ─── Agent Bridge 客户端（单例） ────────────────────────────────────────────
//
// 复用一个 AgentBridgeClient（短连接），交给每个 task 独立的 session_id。
// 任务成功结束后保留 session 供「补充信息继续分析」续聊；失败/中断时 destroy。
// 补充继续严格要求 session 仍存活，不再从历史报告重建会话。
//
// 超时：单条分析可能跑数小时（日志下载 + 多轮工具调用），批量队列更长，
// 因此默认不设 RPC 读超时（0 = 不限时）。代价是 bridge 假死时该轮不会自己醒，
// 需要靠「取消任务」或批量队列的等待预算兜底。要恢复硬超时用
// TAHP_BUG_BRIDGE_TIMEOUT_MS 显式指定毫秒数。
function bugBridgeTimeoutMs(): number {
  const raw = Number(process.env.TAHP_BUG_BRIDGE_TIMEOUT_MS)
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 0
}

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: bugBridgeTimeoutMs() })

// ─── 类型定义 ────────────────────────────────────────────────────────────────

// 历史保留的模块类型：BFF 不再据此判断或加载约束，仅作为 Agent **可能**在最终
// 报告中回填的一个标签（可选）。前端不再让用户选择此字段。
export type TahpBugModule = 'telephony' | 'kernel-driver' | 'power-mgmt' | 'shared'

export type BugAnalysisMode = 'jira_single' | 'jira_batch' | 'local'

export interface BugAnalysisInput {
  rawInput: string                // 用户输入: JIRA key 或 URL
  userDescription?: string        // 用户对 Bug 的补充描述
  extraContext?: string           // 其他附加信息
  codeSource?: string             // 可选 · 指定代码源（本地路径 / OpenGrok 分支 / OpenGrok URL）
}

export interface LocalBugAnalysisInput {
  logPath: string
  problemDescription: string
  codeSource?: string             // 可选 · 同上
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
  /** 用户指定的代码源（可选）；三种分析模式通用 */
  codeSource?: CodeSourceRef
  startedAt: string
  status: 'pending' | 'running' | 'waiting_user_input' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  progress?: number
  issue?: JiraIssue               // （已废弃 BFF JIRA fetch；保留字段防旧报告兼容）
  prevResponse?: string           // 上一轮 Agent 输出
  corrections: string[]           // 历次补充信息
  skillsUsed: string[]
  /** 本任务累计自改进 Skill：实时 tool.started + 结束时 curator ledger 合并 */
  skillsImproved?: SkillImproveRecord[]
  llmResponse?: string
  completedAt?: string
  error?: string
  /** Agent fetch_jira 阶段 TAHP_STAGE 字段快照 */
  jiraSnapshot?: Record<string, string>
  analysisMode?: BugAnalysisMode
  localLogPath?: string
  /** 分析完成后的 jira-dup-judge 置重状态（不影响分析终态） */
  dupJudgeStatus?: 'running' | 'completed' | 'failed'
}

export interface BugAnalysisJobCtx {
  jobId: string
  type: 'single' | 'batch'
  jql?: string
  extraContext?: string
  /** 批量任务的指定代码源原始输入，复制给每个子任务 */
  codeSource?: string
  /** 续跑 / 重跑失败项时指向来源 job */
  resumedFrom?: string
  /** 每单分析完成后自动回写 Jira comment，并尝试 jira-dup-judge 置重 */
  autoPostCommentAndDup?: boolean
  taskIds: string[]               // 关联的子任务
  startedAt: string
  /** interrupted：从落盘恢复出来的、上次进程没跑完的队列 */
  status: 'running' | 'completed' | 'failed' | 'interrupted'
  total: number
  completed: number
  failed: number
}

interface TaskRuntimeControl {
  sessionId: string
  interruptRequested: boolean
  userInputPause?: ParsedUserInputRequest
}

interface PendingApprovalEntry {
  timer: ReturnType<typeof setTimeout>
  resolved: boolean
  payload: ApprovalRequestPayload
}

interface PendingUserInputEntry {
  request: ParsedUserInputRequest
  expiresAt: number
  timeoutTimer?: ReturnType<typeof setTimeout>
}

// ─── 内存状态 ────────────────────────────────────────────────────────────────
const taskCtx = new Map<string, BugAnalysisTaskCtx>()
const jobCtx = new Map<string, BugAnalysisJobCtx>()
const taskRuntime = new Map<string, TaskRuntimeControl>()
const pendingApprovalsByTask = new Map<string, Map<string, PendingApprovalEntry>>()
const pendingUserInputByTask = new Map<string, PendingUserInputEntry>()
const seenUserInputRequestIds = new Map<string, Set<string>>()
const dupJudgeRuntime = new Map<string, TaskRuntimeControl>()

const MAX_KEEP = 200

function isTerminalTaskStatus(status: BugAnalysisTaskCtx['status']): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

/**
 * 回收内存里的历史任务。
 *
 * 只裁剪已终态的任务：批量队列会一次性建好上百个 pending 子任务，
 * 若按插入序无条件裁剪，会把本批还没跑的单子删掉 —— 队列静默丢单，
 * 且 job 的 completed+failed 永远凑不满 total，批量永远结不了。
 */
function pruneOldTasks() {
  if (taskCtx.size <= MAX_KEEP) return
  let over = taskCtx.size - MAX_KEEP
  for (const [id, ctx] of taskCtx) {
    if (over <= 0) break
    if (!isTerminalTaskStatus(ctx.status)) continue
    taskCtx.delete(id)
    over -= 1
  }
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

function persistJob(job: BugAnalysisJobCtx): void {
  if (job.type !== 'batch') return
  saveBugJob(tahpPaths.reportsDir, {
    job_id: job.jobId,
    type: 'batch',
    jql: job.jql,
    extra_context: job.extraContext,
    code_source: job.codeSource,
    resumed_from: job.resumedFrom,
    auto_post_comment_and_dup: job.autoPostCommentAndDup,
    started_at: job.startedAt,
    updated_at: new Date().toISOString(),
    status: job.status,
    total: job.total,
    completed: job.completed,
    failed: job.failed,
    tasks: job.taskIds.map((tid) => {
      const t = taskCtx.get(tid)
      return {
        task_id: tid,
        jira_key: t?.jiraKey || '',
        jira_url: t?.jiraUrl || '',
        status: t?.status || 'unknown',
        error: t?.error,
      }
    }),
  })
}

function settleJobIfDone(job: BugAnalysisJobCtx): void {
  if (job.status !== 'running') return
  if (job.completed + job.failed < job.total) return
  job.status = job.completed === 0 ? 'failed' : 'completed'
  persistJob(job)
  emit(job.jobId, 'task.completed', {
    status: job.status,
    type: 'batch',
    total: job.total,
    completed: job.completed,
    failed: job.failed,
    message: `批量 Bug 分析完成：成功 ${job.completed} / 失败 ${job.failed}`,
  })
}

/** 推批量进度；凑满 total 时改为结算。 */
function emitJobProgress(job: BugAnalysisJobCtx): void {
  if (job.completed + job.failed >= job.total) {
    settleJobIfDone(job)
    return
  }
  persistJob(job)
  emit(job.jobId, 'task.phase', {
    phase: 'BATCH_RUNNING',
    progress: Math.round(((job.completed + job.failed) / job.total) * 100),
    completed: job.completed,
    failed: job.failed,
    total: job.total,
    message: `批量进度 ${job.completed + job.failed} / ${job.total}`,
  })
}

function accountJobChildSuccess(ctx: BugAnalysisTaskCtx): void {
  if (!ctx.parentJobId) return
  const job = jobCtx.get(ctx.parentJobId)
  if (!job) return
  job.completed += 1
  emitJobProgress(job)
}

function accountJobChildFailure(ctx: BugAnalysisTaskCtx): void {
  if (!ctx.parentJobId) return
  const job = jobCtx.get(ctx.parentJobId)
  if (!job) return
  job.failed += 1
  emitJobProgress(job)
}

function writeBugFailureReport(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
  msg: string,
  opts: { failureReason?: string; toolCallCount?: number } = {},
): void {
  try {
    const report = {
      task_id: taskId,
      jira_key: ctx.jiraKey,
      jira_url: ctx.jiraUrl,
      module: ctx.module,
      status: 'failed',
      error: msg,
      failure_reason: opts.failureReason,
      started_at: ctx.startedAt,
      completed_at: ctx.completedAt,
      user_description: ctx.userDescription,
      extra_context: ctx.extraContext,
      code_source: snapshotCodeSourceForReport(ctx.codeSource),
      skills_used: ctx.skillsUsed,
      skills_improved: ctx.skillsImproved || [],
      tool_call_count: opts.toolCallCount,
      llm_response: truncateForReport(ctx.llmResponse || ''),
    }
    writeFileSync(reportPath(taskId), JSON.stringify(report, null, 2), 'utf-8')
  } catch { /* swallow */ }
}

/**
 * 把一个仍处于非终态的任务直接判失败。
 *
 * 用于批量队列兜底：子任务停在 waiting_user_input 超过队列预算，或
 * runSingleBugAnalysis 在内部 catch 之外抛错。不这么兜的话，
 * job 的 completed+failed 永远凑不满 total，整条队列会永久停在「执行中」。
 */
function forceFailTask(taskId: string, reason: string): void {
  const ctx = taskCtx.get(taskId)
  if (!ctx || isTerminalTaskStatus(ctx.status)) return

  const pending = pendingUserInputByTask.get(taskId)
  if (pending?.timeoutTimer) clearTimeout(pending.timeoutTimer)
  pendingUserInputByTask.delete(taskId)

  ctx.status = 'failed'
  ctx.error = reason
  ctx.completedAt = new Date().toISOString()
  taskCtx.set(taskId, ctx)

  logBug(taskId, 'warn', `task force-failed: ${reason}`)
  emit(taskId, 'task.failed', {
    error: reason,
    message: reason,
    skills_improved: ctx.skillsImproved || [],
  })
  writeBugFailureReport(taskId, ctx, reason)

  const control = taskRuntime.get(taskId)
  if (control) {
    sharedBridgeClient.destroy(control.sessionId).catch(() => {})
    taskRuntime.delete(taskId)
  }

  accountJobChildFailure(ctx)
}

// ─── 状态查询 (供 route 使用) ────────────────────────────────────────────────

export function getBugTask(taskId: string): BugAnalysisTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export function listBugTasks(): BugAnalysisTaskCtx[] {
  ensureJobsRestored()
  return Array.from(taskCtx.values()).sort((a, b) => b.startedAt.localeCompare(a.startedAt))
}

/**
 * 从落盘记录恢复批量队列（进程重启后）。
 *
 * 恢复出来的 job 只用于「看进度 + 续跑」，不会自动重启执行：
 * 上次进程里跑着的 Agent 会话已经随进程消失，非终态子任务没有可信结论，
 * 需要用户显式点续跑（resumeBugJob 会用新的子任务重跑这些单子）。
 */
let jobsRestored = false

function ensureJobsRestored(): void {
  if (jobsRestored) return
  jobsRestored = true
  try {
    for (const persisted of listPersistedBugJobs(tahpPaths.reportsDir)) {
      if (jobCtx.has(persisted.job_id)) continue
      const tasks = persisted.tasks || []
      jobCtx.set(persisted.job_id, {
        jobId: persisted.job_id,
        type: 'batch',
        jql: persisted.jql,
        extraContext: persisted.extra_context,
        codeSource: persisted.code_source,
        resumedFrom: persisted.resumed_from,
        autoPostCommentAndDup: persisted.auto_post_comment_and_dup,
        taskIds: tasks.map(t => t.task_id),
        startedAt: persisted.started_at,
        status: persisted.status === 'running' ? 'interrupted' : persisted.status,
        total: persisted.total,
        completed: persisted.completed,
        failed: persisted.failed,
      })
      for (const t of tasks) {
        if (!t.task_id || taskCtx.has(t.task_id)) continue
        const restoredStatus = isTerminalTaskStatus(t.status as BugAnalysisTaskCtx['status'])
          ? (t.status as BugAnalysisTaskCtx['status'])
          : 'cancelled'
        taskCtx.set(t.task_id, {
          taskId: t.task_id,
          parentJobId: persisted.job_id,
          jiraKey: t.jira_key,
          jiraUrl: t.jira_url,
          startedAt: persisted.started_at,
          // 上次跑着的子任务进程已消失：落到 cancelled，避免 UI 显示成「执行中」
          status: restoredStatus,
          phase: restoredStatus === 'completed'
            ? 'COMPLETED'
            : restoredStatus === 'failed'
              ? 'FAILED'
              : restoredStatus === 'cancelled'
                ? 'CANCELLED'
                : undefined,
          error: t.error || (isTerminalTaskStatus(t.status as BugAnalysisTaskCtx['status'])
            ? undefined
            : '服务重启中断，未完成'),
          corrections: [],
          skillsUsed: [],
          skillsImproved: [],
        })
      }
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[bug-analysis] restore persisted jobs failed')
  }
}

export function getBugJob(jobId: string): BugAnalysisJobCtx | undefined {
  ensureJobsRestored()
  return jobCtx.get(jobId)
}

export function listBugJobs(): BugAnalysisJobCtx[] {
  ensureJobsRestored()
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

export function readBugSkillSnapshot(taskId: string, skillName: string) {
  return readSkillSnapshot(tahpPaths.reportsDir, taskId, skillName)
}

export function listBugReports(): unknown[] {
  const d = reportDir()
  if (!existsSync(d)) return []
  // 复用 sync API；批量场景这里数量不大，直接 fs readdirSync
  const fs = require('fs') as typeof import('fs')
  const files = fs.readdirSync(d).filter((f: string) => f.endsWith('.json'))
  const entries = loadCuratorLedger()
  const summaries: any[] = []
  for (const f of files) {
    try {
      const json = JSON.parse(fs.readFileSync(join(d, f), 'utf-8'))
      const taskId = String(json.task_id || f.replace(/\.json$/, ''))
      const existing = parseSkillImproves(json.skills_improved)
      const merged = mergeLedgerSkillImproves(existing, taskId, entries)
      if (skillImprovesNeedUpdate(existing, merged)) {
        json.skills_improved = merged
        try {
          fs.writeFileSync(join(d, f), JSON.stringify(json, null, 2), 'utf-8')
        } catch { /* overlay still returned below */ }
        void reconcileSkillImproveForTask(taskId)
      }
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
        skills_improved: merged,
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
    const snapDir = skillImproveSnapshotRoot(tahpPaths.reportsDir, taskId)
    if (existsSync(snapDir)) {
      rmSync(snapDir, { recursive: true, force: true })
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
    const agentSessionId = `tahp-bug-${taskId}`
    sharedBridgeClient.destroy(agentSessionId).catch(() => {})
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
  onToolOutput?: (text: string) => void
  onReasoning?: (text: string) => void
  onApprovalRequested?: (payload: ApprovalRequestPayload) => void
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
  for (const entry of bucket.values()) {
    clearTimeout(entry.timer)
  }
  pendingApprovalsByTask.delete(taskId)
}

function registerApprovalRequest(taskId: string, payload: ApprovalRequestPayload) {
  const bucket = getOrCreateApprovalBucket(taskId)
  if (bucket.has(payload.approval_id)) return

  // 智能诊断不弹确认窗：后台立即同意一次。适配调试 / Skill 配置仍走各自审批。
  const preview = (payload.command || payload.description || '').slice(0, 120)
  logBug(taskId, 'info', `approval.auto_once: ${payload.approval_id} cmd=${preview}`)
  emitBugActivity(taskId, `已自动同意命令（后台）：${preview || payload.approval_id}`)

  const dummyTimer = setTimeout(() => { /* resolved immediately via resolveBugApproval */ }, 0)
  bucket.set(payload.approval_id, { timer: dummyTimer, resolved: false, payload })
  void resolveBugApproval(taskId, payload.approval_id, 'once', 'auto')
}

async function resolveBugApproval(
  taskId: string,
  approvalId: string,
  choice: string,
  source: 'user' | 'auto',
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
  } catch (err) {
    logBug(taskId, 'warn', `approval.respond failed: ${(err as Error).message}`)
    return { ok: false, error: (err as Error).message }
  }

  emit(taskId, 'task.approval_resolved', {
    approval_id: approvalId,
    choice,
    source,
    message: source === 'auto'
      ? `危险命令已由智能诊断后台自动同意一次（${choice}）`
      : `危险命令审批：${choice}`,
  })
  logBug(taskId, 'info', `approval.resolved: ${approvalId} choice=${choice} source=${source}`)
  return { ok: true }
}

export async function respondBugApproval(
  taskId: string,
  approvalId: string,
  choice: string,
): Promise<{ ok: boolean; error?: string }> {
  const allowed = new Set(['once', 'session', 'always', 'deny'])
  const normalized = allowed.has(choice) ? choice : 'deny'
  return resolveBugApproval(taskId, approvalId, normalized, 'user')
}

function getSeenUserInputIds(taskId: string): Set<string> {
  let set = seenUserInputRequestIds.get(taskId)
  if (!set) {
    set = new Set()
    seenUserInputRequestIds.set(taskId, set)
  }
  return set
}

function persistPartialUserInput(taskId: string, record: UserInputResponseRecord) {
  const existing = readBugReport(taskId) as Record<string, unknown> | null
  const prev = Array.isArray(existing?.user_input_responses)
    ? [...existing!.user_input_responses as UserInputResponseRecord[]]
    : []
  prev.push(record)
  const merged = {
    ...(existing || {}),
    task_id: taskId,
    user_input_responses: prev,
  }
  try {
    writeFileSync(reportPath(taskId), JSON.stringify(merged, null, 2), 'utf-8')
  } catch (err) {
    logBug(taskId, 'warn', `user input partial persist failed: ${(err as Error).message}`)
  }
}

function requestUserInputPause(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
  request: ParsedUserInputRequest,
  sessionId: string,
) {
  const seen = getSeenUserInputIds(taskId)
  if (seen.has(request.requestId)) return
  seen.add(request.requestId)

  const expiresAt = Date.now() + request.timeoutSec * 1000
  const control = taskRuntime.get(taskId) || { sessionId, interruptRequested: false }
  control.userInputPause = request
  taskRuntime.set(taskId, control)

  if (isLlmCredentialUserInput(request)) {
    // 不弹窗、不改 waiting_user_input；中断本轮后静默复用 Console Provider Key
    pendingUserInputByTask.set(taskId, { request, expiresAt })
    emitBugActivity(taskId, '检测到 LLM/LogInsight 凭据请求，已静默复用 Console Provider 并写入工程/Hermes Skill 副本')
    try {
      const seed = ensureLoginsightCredentialsForBugAnalysis()
      logBug(taskId, 'info', `user_input.silent_llm: ${request.requestId} seeded=${seed.seededKey} roots=${seed.writtenRoots.length}`)
    } catch (err) {
      logBug(taskId, 'warn', `silent loginsight seed failed: ${(err as Error).message}`)
    }
    setImmediate(() => {
      sharedBridgeClient.interrupt(sessionId, `静默复用 Console LLM 凭据: ${request.title}`).catch((err) => {
        logBug(taskId, 'warn', `interrupt for silent credential reuse failed: ${(err as Error).message}`)
      })
    })
    return
  }

  const timeoutTimer = setTimeout(() => {
    void autoSubmitEmptyUserInput(taskId, request.requestId)
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
    message_hint: '请在弹窗中按格式填写配置；超时后将以空值继续（可在弹窗内查看倒计时）',
  })
  logBug(taskId, 'info', `user_input.requested: ${request.requestId} fields=${request.fields.map(f => f.name).join(',')}`)

  setImmediate(() => {
    sharedBridgeClient.interrupt(sessionId, `等待用户配置输入: ${request.title}`).catch((err) => {
      logBug(taskId, 'warn', `interrupt for user input failed: ${(err as Error).message}`)
    })
  })
}

async function autoSubmitEmptyUserInput(taskId: string, requestId: string) {
  const pending = pendingUserInputByTask.get(taskId)
  if (!pending || pending.request.requestId !== requestId) return
  const emptyValues: Record<string, string> = {}
  for (const f of pending.request.fields) {
    emptyValues[f.name] = f.default || ''
  }
  await submitBugUserInput(taskId, requestId, emptyValues, 'auto_timeout')
}

export async function submitBugUserInput(
  taskId: string,
  requestId: string,
  values: Record<string, string>,
  source: 'user' | 'auto_timeout' | 'silent_reuse' = 'user',
): Promise<{ ok: boolean; error?: string }> {
  const pending = pendingUserInputByTask.get(taskId)
  if (!pending || pending.request.requestId !== requestId) {
    return { ok: false, error: '配置请求不存在或已过期' }
  }

  if (source !== 'silent_reuse') {
    for (const field of pending.request.fields) {
      if (field.required && !String(values[field.name] ?? '').trim()) {
        return { ok: false, error: `请填写必填项：${field.label}` }
      }
    }
  }

  if (pending.timeoutTimer) clearTimeout(pending.timeoutTimer)
  const request = pending.request
  pendingUserInputByTask.delete(taskId)

  const persistValues = isLlmCredentialUserInput(request)
    ? redactUserInputValues(request, values)
    : { ...values }
  const record: UserInputResponseRecord = {
    request_id: requestId,
    title: request.title,
    persist_key: request.persistKey,
    values: persistValues,
    submitted_at: new Date().toISOString(),
  }
  persistPartialUserInput(taskId, record)

  emit(taskId, 'task.user_input_submitted', {
    request_id: requestId,
    values: persistValues,
    source,
    message: source === 'auto_timeout'
      ? '配置输入超时，已以默认值/空值继续'
      : source === 'silent_reuse'
        ? '已静默复用 Console Provider 凭据，继续分析'
        : '用户已提交配置',
  })
  logBug(taskId, 'info', `user_input.submitted: ${requestId} source=${source}`)

  let ctx = taskCtx.get(taskId)
  if (!ctx) {
    const report = readBugReport(taskId) as Record<string, unknown> | null
    if (report) ctx = restoreCtxFromReport(taskId, report)
  }
  if (!ctx) return { ok: false, error: `找不到任务 ${taskId}` }

  const control = taskRuntime.get(taskId)
  if (control) control.userInputPause = undefined

  ctx.status = 'running'
  ctx.phase = 'ANALYZING'
  ctx.error = undefined
  taskCtx.set(taskId, ctx)

  const filled = source === 'silent_reuse' ? fillSilentCredentialValues(request) : null
  setImmediate(() => {
    runSingleBugAnalysis(ctx!, undefined, {
      mode: 'user_input_resume',
      userInputRequest: request,
      userInputValues: persistValues,
      silentCredentialResume: source === 'silent_reuse' || isLlmCredentialUserInput(request),
      silentCredentialSeeded: !!filled?.seeded,
    }).catch((err) => {
      logger.error({ err: (err as Error).message, taskId }, '[bug-analysis] user input resume unhandled')
    })
  })

  return { ok: true }
}

function scheduleSilentLlmCredentialResume(taskId: string): void {
  const pending = pendingUserInputByTask.get(taskId)
  if (!pending || !isLlmCredentialUserInput(pending.request)) return
  setImmediate(() => {
    const filled = fillSilentCredentialValues(pending.request)
    void submitBugUserInput(
      taskId,
      pending.request.requestId,
      filled?.values || {},
      'silent_reuse',
    )
  })
}

async function runAgentChat(
  sessionId: string,
  userMessage: string,
  cb: AgentRunCallbacks,
  options?: {
    instructions?: string
    conversationHistory?: unknown[]
  },
): Promise<{ fullResponse: string; runId: string; interrupted?: boolean }> {
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
      options?.conversationHistory,
      options?.instructions,
      'default',
    )
  } catch (err) {
    throw new Error(`Agent 启动失败: ${(err as Error).message}`)
  }

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''

  let lastChunk: AgentBridgeOutput | null = null
  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 50 })) {
    lastChunk = chunk

    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'tool.started') {
        const toolName = (ev.tool_name as string) || 'unknown-tool'
        cb.onToolStarted(toolName, ev.args, ev.tool_call_id)
      } else if (evType === 'tool.completed') {
        const toolName = (ev.tool_name as string) || 'unknown-tool'
        cb.onToolCompleted(toolName, ev.is_error === true, ev.tool_call_id)
      } else if (evType === 'tool.output' && cb.onToolOutput) {
        const text = formatLogDownloadProgressActivity(String(ev.text || ''))
        if (text) cb.onToolOutput(text)
      } else if ((evType === 'reasoning.delta' || evType === 'thinking.delta') && cb.onReasoning) {
        cb.onReasoning(String(ev.text || ''))
      } else if (evType === 'approval.requested' && cb.onApprovalRequested) {
        cb.onApprovalRequested({
          approval_id: String(ev.approval_id || ''),
          command: String(ev.command || ''),
          description: String(ev.description || ''),
          choices: Array.isArray(ev.choices) ? ev.choices.map(String) : ['once', 'session', 'deny'],
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
        throw new Error(chunk.error || 'Agent 运行出错')
      }
      if (chunk.status === 'interrupted') {
        // 用户配置输入暂停会主动 interrupt，由调用方根据 userInputPause 处理
        return { fullResponse, runId: started.run_id, interrupted: true }
      }
      break
    }
  }

  if (!lastChunk || !lastChunk.done) {
    throw new Error('Agent 流式输出意外终止（无终止 chunk）')
  }

  return { fullResponse, runId: started.run_id, interrupted: false }
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

function emitBugActivity(taskId: string, message: string, level: 'info' | 'warn' | 'error' = 'info'): void {
  logBug(taskId, level, message)
  emit(taskId, 'task.message', { level: 'activity', text: message })
}

/** Hermes terminal last-line for jira-ops log download (`\\r` progress). */
export function formatLogDownloadProgressActivity(text: string): string | null {
  const line = String(text || '').replace(/\s+/g, ' ').trim()
  if (!line) return null
  if (!/下载进度|开始流式下载|下载中|解压|获取share_token|合并分块|检测服务器能力|线程分块下载|\[文件]|\[文件夹]|下载完成|下载失败/.test(line)) {
    return null
  }
  return line.slice(0, 200)
}

function emitPrepPhase(taskId: string, ctx: BugAnalysisTaskCtx, phase: 'PREPARING' | 'CONNECTING_AGENT', message: string) {
  const progress = phase === 'PREPARING' ? 5 : 10
  ctx.phase = phase
  ctx.progress = progress
  emit(taskId, 'task.phase', { phase, progress, message })
  emitBugActivity(taskId, `阶段：${phase === 'PREPARING' ? '准备 Agent' : '连接 Agent Bridge'} — ${message}`)
}

function applyParsedStageMarker(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
  marker: ParsedBugStageMarker,
  options?: { continueMode?: boolean },
) {
  const isContinueSkip = options?.continueMode
    && (marker.markerId === 'fetch_jira' || marker.markerId === 'download_logs')
  if (isContinueSkip) return

  if (marker.markerId === 'fetch_jira') {
    ctx.jiraSnapshot = { ...(ctx.jiraSnapshot || {}), ...marker.fields }
    if (marker.fields.issue_summary) ctx.title = marker.fields.issue_summary
  }

  // 本地模式：Step 1～2 为 BFF 预置跳过标记，勿将 phase 回退到 JIRA 拉取/下载
  const isLocalSkipMarker = ctx.analysisMode === 'local'
    && (marker.markerId === 'fetch_jira' || marker.markerId === 'download_logs')

  if (!isLocalSkipMarker) {
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
  }
  const message = marker.fields.message || ''
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
  options?: { continueMode?: boolean },
) {
  const markers = findBugStageMarkers(fullText, state.lastIndex)
  for (const marker of markers) {
    state.lastIndex = Math.max(state.lastIndex, marker.startIndex + marker.rawBlock.length)
    applyParsedStageMarker(taskId, ctx, marker, options)
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

export const AGENT_INSTRUCTIONS_BASE = `你是 TAHP（TECNO AI Harness Platform）"智能诊断专家"，运行在传音 Android 底软集成部的 Agent 环境中。

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
1. **先检查系统提示词中的「远程分析渠道」硬规则**：若有 enabled 渠道且适用，须先尝试远程分析；远程成功时可跳过本步（输出 \`download_logs\` 并说明原因）。
2. 远程失败 / 渠道全关 / 本地回退时：继续遵循已 Read 的 \`jira-ops\` SKILL.md。
3. 从 Step 1 的 Issue 信息与 JIRA 附件中，下载/提取日志包（含描述中的 http(s) / UNC 日志链接）。
4. **日志下载硬规则**（FRBOX/SGBOX / \`prepare-logs\` / \`download-logs\` / \`download-box\`）：
   - 必须跑 \`python scripts/api_jira.py prepare-logs\`（或分步 download-logs），**禁止**用浏览器工具下载分享链接。
   - 必须等到 \`api_jira.py\` **进程退出并给出 JSON**。禁止用固定墙钟（如 300s）中断仍在增长的下载。只有脚本返回失败（HTTP 中断 / 连接重置 / 分享令牌失败 / 长时间无数据）才停止等待。文件体积仍在增大时视为进行中。
5. 完成后**立即**输出阶段标记 \`download_logs\`；若确无日志可下载，\`logs_downloaded: false\` 并说明原因，仍可 \`success\` 进入下一步。

## Step 3 — 匹配分析 Skill
1. 若远程渠道已成功产出报告：\`matched_skills\` 填远程 skillId，再进入整理 9 节报告（可与 Step 4～5 合并输出标记）。
2. 否则结合 JIRA **标题 + 描述 + 评论** 与已下载日志类型，在工程 Skill 根目录 \`__TAHP_SKILLS_REL_ROOT__\` 下**自主匹配** 1～3 个最相关的分析 Skill（参考系统提示词末尾「已扫描到的 Skills」索引，禁止编造 skillId）。
3. 对每个匹配到的 skillId，**必须 Read** \`__TAHP_SKILLS_REL_ROOT__/<skillId>/SKILL.md\` 全文。
4. 完成后**立即**输出阶段标记 \`match_skills\`，在 \`matched_skills\` 中列出匹配到的 skillId（逗号分隔）；若未匹配到，\`skills_matched: false\` 并说明原因。

## Step 4 — 大模型分析
1. 依据 Step 1～3 的 JIRA 信息、日志与已 Read 的 Skill SOP，执行根因分析。
2. 若系统提示词中有「**指定代码源**」段落：须先按该段落完成源码取证，再下根因结论；报告中的代码引用只能来自该代码源，并写明路径/分支与行号。
3. 开始分析时输出 \`analyze\` 标记（\`status: running\`）；分析结论就绪后输出 \`analyze\`（\`status: success\`）。

## Step 5 — 生成分析报告
1. 输出完整 **9 节** Markdown 报告（结构见下文，**第 9 节 Jira 备注必填**）。
2. 报告正文开始输出前，先输出 \`generate_report\`（\`status: running\`）；报告全部写完后再输出 \`generate_report\`（\`status: success\`，\`report_ready: true\`）。

# 结构化阶段标记（每步完成后必须输出，供 BFF 解析更新 UI）

**在进入下一步之前**，必须输出一段标记块（可输出在分析报告正文之前，勿嵌入 9 节报告中间）：

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

# 9 节分析报告（Step 5 正文，每节 H2 标题，不要省略）

### 1. 摘要 / TL;DR
### 2. 复现路径
### 3. 关键日志识别
### 4. 根因定位（最关键）
### 5. 影响范围
### 6. 修复建议
### 7. 验证方案
### 8. 风险与遗留问题
### 9. Jira 备注（结论 / 依据 / 建议）

**第 9 节为「分析结论回到 Jira comment」的唯一数据源**，须在分析阶段一次性写好（与前面章节同步输出，勿留占位符）。格式固定如下，勿用 Markdown 表格、架构图、Jira 单号：

\`\`\`
【分析结论】
（1~3 句中文：问题现象 + 你的分析判断，开发者一读即懂）

【结论依据】
1. （精简定位依据；若为异常/日志，本条下方完整粘贴堆栈，须含 at / Caused by 等行，勿只写异常类名）
2. ...

【建议】
1. （可执行修复或验证步骤）
2. ...
\`\`\`

要求：
- **分析结论**：综合全文判断，不是代码路径或「根因层：Framework —」类标签
- **结论依据**：2~4 条，根因细节写在这里；日志必须完整堆栈
- **建议**：1~3 条，与第 6 节修复建议一致但面向 Jira 读者精简表述
- 禁止输出「请根据报告补充」类占位文字

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
- 可用 skill_manage 改进领域分析 Skill；入口契约 Skill（jira-ops / bugfix-analysis / loginsight-remote-cli）请谨慎改。自改进不必写进 9 节报告，BFF 会按工具调用在结果页单独展示

# 人机协同：结构化用户配置输入（需要用户填写路径/凭证等时）

**禁止**为 LogInsight / LLM API Key / sw-aimodel 输出 \`TAHP_USER_INPUT\`。Console 已在分析开始时把已配置的 Provider Key 写入：
- 工程副本 \`skills/.claude/skills/loginsight-remote-cli/.loginsight_cli.json\`
- Hermes 运行时副本 \`%LOCALAPPDATA%/hermes/skills/loginsight-remote-cli/.loginsight_cli.json\`（Agent \`cd\` 的通常是这一份）

\`doctor\` 若 \`local_llm_api_key\` 仍为 false：视为远程渠道失败并回退本地分析，**不要弹窗、不要再要 Key**。

当需要用户在本机提供**无法由 Agent 自行推断**的配置（如日志保存目录、下载路径）时：

1. **先输出**以下标记块（字段按实际场景填写），**然后停止本轮输出**，等待用户提交：
\`\`\`
=== TAHP_USER_INPUT ===
request_id: <唯一 ID，如 log-dir-001>
title: <弹窗标题>
message: <向用户说明为何需要这些配置>
timeout_sec: 300
persist_key: <可选，持久化键名，如 jira_log_output_dir>
field.<name>.label: <字段显示名>
field.<name>.type: text|textarea|password|number
field.<name>.required: true|false
field.<name>.placeholder: <占位提示>
field.<name>.hint: <可选说明>
=== END_TAHP_USER_INPUT ===
\`\`\`

2. 用户提交后，BFF 会以「用户已提交配置」消息继续对话；请据此**持久化配置**并继续后续分析步骤。
3. 同一 \`request_id\` 不要重复请求。
`

const AGENT_INSTRUCTIONS_LOCAL = `你是 TAHP「智能诊断专家」，当前为 **本地日志分析模式**（无 JIRA 工单）。

# 执行原则
1. **不要**拉取 JIRA、不要从 JIRA 下载日志。
2. 用户已提供**本地日志路径**与**问题描述**。
3. BFF 已预置跳过 Step 1～2（JIRA / 日志下载）；你须从 **Step 3 匹配 Skill** 开始，再进入分析与报告。

# 强制执行步骤

## Step 1 — 拉取 JIRA 信息（跳过）
立即输出 \`fetch_jira\` 标记：\`status: success\`，\`message: 本地日志模式跳过 JIRA 拉取\`，\`jira_key: LOCAL\`。

## Step 2 — 下载 JIRA 日志（跳过，使用用户路径）
立即输出 \`download_logs\` 标记：\`status: success\`，\`logs_downloaded: true\`，\`log_paths\` 填用户给出的本地日志路径。

## Step 3 — 匹配分析 Skill（必做）
结合**问题描述**与日志类型/路径，在 \`__TAHP_SKILLS_REL_ROOT__\` 下匹配 1～3 个分析 Skill；**Read 匹配到的 SKILL.md 全文**后输出 \`match_skills\` 标记（\`matched_skills\`、\`skills_matched\` 等字段须填写）。

## Step 4 — 大模型分析
依据已匹配 Skill 的方法论分析本地日志，输出 \`analyze\` 标记。
若系统提示词中有「**指定代码源**」段落：须先按该段落完成源码取证，再下根因结论；代码引用只能来自该代码源并写明路径/分支与行号。

## Step 5 — 生成分析报告
输出完整 **9 节** Markdown 报告（结构同标准模式，**第 9 节 Jira 备注必填**），输出 \`generate_report\` 标记。

# 结构化阶段标记、9 节报告、TOOLS_INVOKED、红线
与标准智能诊断相同（见标准指令）；\`stage_id\` 须完整输出。

# 红线
- 不要编造日志中不存在的行或符号
- 日志路径不存在时显式报错并停止
- **禁止**跳过 Step 3 直接分析（须先完成 Skill 目录匹配与 Read）
`

function emitLocalPreflightStages(taskId: string, ctx: BugAnalysisTaskCtx) {
  const logPath = ctx.localLogPath || ''
  // 本地模式 UI 快进到「大模型分析」；Agent 仍会在 Step 3 真实执行 Skill 匹配
  ctx.phase = 'ANALYZING'
  ctx.progress = BUG_UI_PHASE_PROGRESS.ANALYZING
  ctx.title = ctx.title || '本地日志分析'
  emit(taskId, 'task.stage_detail', {
    stage_id: 'fetch_jira',
    phase: 'FETCH_JIRA_INFO',
    step_id: 'fetch-jira',
    status: 'success',
    message: '本地日志模式已跳过 JIRA 拉取',
    fields: { status: 'success', message: '本地模式跳过', jira_key: ctx.jiraKey },
    detail_lines: ['说明: 本地日志模式已跳过 JIRA 拉取'],
  })
  emit(taskId, 'task.stage_detail', {
    stage_id: 'download_logs',
    phase: 'DOWNLOAD_JIRA_LOGS',
    step_id: 'download-logs',
    status: 'success',
    message: '使用用户提供的本地日志路径',
    fields: { status: 'success', logs_downloaded: 'true', log_paths: logPath },
    detail_lines: [`日志路径: ${logPath}`],
  })
  emit(taskId, 'task.phase', {
    phase: 'ANALYZING',
    progress: BUG_UI_PHASE_PROGRESS.ANALYZING,
    message: '本地日志模式：匹配 Skill 并分析本地日志',
  })
}

/** 补充继续：沿用首轮 Step 1～3 结果，UI 直接进入分析阶段 */
function emitContinuePreflightStages(taskId: string, ctx: BugAnalysisTaskCtx) {
  const report = readBugReport(taskId) as Record<string, unknown> | null
  const snap = ctx.jiraSnapshot || (report?.jira as Record<string, string> | undefined) || {}
  const skills = ctx.skillsUsed?.length
    ? ctx.skillsUsed
    : (Array.isArray(report?.skills_used) ? [...report.skills_used as string[]] : [])
  const isLocal = ctx.analysisMode === 'local' || ctx.jiraKey.startsWith('LOCAL-')
  const round = ctx.corrections.length
  const priorSkillsHint = skills.length ? `首轮已匹配: ${skills.join(', ')}` : '首轮 Skill 见对话记录'

  if (isLocal) {
    const logPath = ctx.localLogPath || String(snap.log_paths || '')
    emit(taskId, 'task.stage_detail', {
      stage_id: 'fetch_jira',
      phase: 'FETCH_JIRA_INFO',
      step_id: 'fetch-jira',
      status: 'success',
      message: '续聊：沿用本地日志模式跳过 JIRA 拉取',
      fields: { status: 'success', jira_key: ctx.jiraKey },
      detail_lines: ['说明: 补充继续不重新拉取 JIRA'],
    })
    emit(taskId, 'task.stage_detail', {
      stage_id: 'download_logs',
      phase: 'DOWNLOAD_JIRA_LOGS',
      step_id: 'download-logs',
      status: 'success',
      message: '续聊：沿用首轮本地日志路径',
      fields: { status: 'success', logs_downloaded: 'true', log_paths: logPath },
      detail_lines: logPath ? [`日志路径: ${logPath}`] : ['沿用首轮日志路径'],
    })
  } else {
    emit(taskId, 'task.stage_detail', {
      stage_id: 'fetch_jira',
      phase: 'FETCH_JIRA_INFO',
      step_id: 'fetch-jira',
      status: 'success',
      message: '续聊：沿用首轮已拉取的 JIRA 信息',
      fields: {
        status: 'success',
        jira_key: ctx.jiraKey,
        issue_summary: snap.issue_summary || ctx.title || ctx.jiraKey,
      },
      detail_lines: ['说明: 补充继续不重新拉取 JIRA'],
    })
    emit(taskId, 'task.stage_detail', {
      stage_id: 'download_logs',
      phase: 'DOWNLOAD_JIRA_LOGS',
      step_id: 'download-logs',
      status: 'success',
      message: '续聊：沿用首轮已下载的日志',
      fields: { status: 'success', logs_downloaded: 'true', log_paths: snap.log_paths || '' },
      detail_lines: ['说明: 补充继续不重新下载日志'],
    })
  }

  emit(taskId, 'task.stage_detail', {
    stage_id: 'match_skills',
    phase: 'MATCH_SKILLS',
    step_id: 'match-skills',
    status: 'running',
    message: '根据补充信息重新评估 Skill 匹配...',
    fields: {
      status: 'running',
      matched_skills: skills.join(', '),
      match_note: priorSkillsHint,
    },
    detail_lines: [priorSkillsHint, '可沿用首轮 Skill，也可根据补充信息调整匹配'],
  })

  ctx.phase = 'MATCH_SKILLS'
  ctx.progress = BUG_UI_PHASE_PROGRESS.MATCH_SKILLS
  emit(taskId, 'task.phase', {
    phase: 'MATCH_SKILLS',
    progress: BUG_UI_PHASE_PROGRESS.MATCH_SKILLS,
    message: `补充分析（第 ${round} 轮）：匹配 Skill...`,
  })
}

function buildLocalAgentUserMessage(ctx: BugAnalysisTaskCtx): string {
  const blocks: string[] = [
    '# 本地日志分析任务',
    `- 本地日志路径: **${ctx.localLogPath}**`,
    `- 问题描述: ${ctx.userDescription || ''}`,
  ]
  blocks.push(...buildCodeSourceUserBlock(ctx.codeSource))
  blocks.push(
    '',
    '请先输出 fetch_jira 与 download_logs 阶段标记（本地模式跳过，log_paths 使用上述路径），',
    '然后结合问题描述在 Skills 目录匹配 1～3 个分析 Skill 并 Read 全文，输出 match_skills 标记，',
    '再分析本地日志并输出 analyze / generate_report 标记，生成完整 9 节报告。',
  )
  return blocks.join('\n')
}

function buildBugAnalysisInstructions(userMessage: string, ctx: BugAnalysisTaskCtx): string {
  // 指定代码源三种模式通用（与远程渠道不同，本地日志模式也注入）
  const codeSourceDirective = buildCodeSourceDirective(ctx.codeSource)
  const codeSourceSkillIds = codeSourcePreferredSkillIds(ctx.codeSource)

  if (ctx.analysisMode === 'local') {
    const skillsRel = getTahpSkillsRootForPrompt()
    const base = AGENT_INSTRUCTIONS_LOCAL.replace(/__TAHP_SKILLS_REL_ROOT__/g, skillsRel)
    // 本地模式：不注入远程渠道，不优先远程 Skill
    const tahpCtx = buildFullTahpSystemContext(userMessage, {
      scenario: 'bug_analysis',
      preferredSkillIds: codeSourceSkillIds,
    })
    return [base, codeSourceDirective, tahpCtx].filter(p => p.trim().length > 0).join('\n\n')
  }
  const skillsRel = getTahpSkillsRootForPrompt()
  const jiraOpsSkill = tahpSkillMdRelativePath('jira-ops')
  const base = AGENT_INSTRUCTIONS_BASE
    .replace(/__TAHP_SKILLS_REL_ROOT__/g, skillsRel)
    .replace(/__JIRA_OPS_SKILL__/g, jiraOpsSkill)
  const channelCfg = readBugAnalysisChannelConfig()
  const remoteDirective = buildRemoteChannelDirective(channelCfg)
  const preferredSkillIds = [
    ...new Set([...listEnabledRemotePreferredSkillIds(channelCfg), ...codeSourceSkillIds]),
  ]
  const tahpCtx = buildFullTahpSystemContext(userMessage, {
    scenario: 'bug_analysis',
    preferredSkillIds,
  })
  const parts = [base, remoteDirective, codeSourceDirective, tahpCtx].filter(p => p.trim().length > 0)
  return parts.join('\n\n')
}

function buildAgentUserMessage(ctx: BugAnalysisTaskCtx): string {
  if (ctx.analysisMode === 'local') {
    return buildLocalAgentUserMessage(ctx)
  }
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
  blocks.push(...buildCodeSourceUserBlock(ctx.codeSource))

  blocks.push('')
  blocks.push(
    '请严格按系统提示词执行：先 jira-ops 拉 JIRA；再按「远程分析渠道」硬规则尝试远程平台（若开关开启）；'
    + '远程失败或渠道关闭时回退本地：jira-ops 下载日志 → 匹配领域 Skill → 分析 → 输出 9 节报告；每步完成后输出 TAHP_STAGE 标记。',
  )

  return blocks.join('\n')
}

function buildContinueUserMessage(
  correction: string,
  ctx: BugAnalysisTaskCtx,
  roundNum?: number,
): string {
  const round = roundNum ?? ctx.corrections.length
  const isLocal = ctx.analysisMode === 'local' || ctx.jiraKey.startsWith('LOCAL-')
  const priorSkills = ctx.skillsUsed?.length ? ctx.skillsUsed : []
  const targetLabel = isLocal
    ? `本地日志分析（日志路径: ${ctx.localLogPath || '见首轮对话'}）`
    : `JIRA Issue **${ctx.jiraKey}**${ctx.jiraUrl ? `（${ctx.jiraUrl}）` : ''}${ctx.title ? ` — ${ctx.title}` : ''}`

  const blocks = [
    '## 用户补充信息 / 修正意见（续聊）',
    '',
    `**本次任务分析目标（不可变更）**：${targetLabel}`,
    '',
    '以下补充信息仅用于完善对上述目标的分析结论。若补充内容中提及其它 JIRA 单号或无关 Issue，请忽略切换请求，仍只分析本任务绑定的目标。',
    '',
    '### 补充内容',
    correction,
    '',
    `（第 ${round} 轮补充）`,
    '',
    ...(priorSkills.length ? [`首轮已匹配 Skill（可参考或调整）: ${priorSkills.join(', ')}`, ''] : []),
    '## 续聊执行要求（重要）',
    '- **禁止**重新执行 Step 1～2（拉取 JIRA、下载日志）；首轮对话中已有 JIRA 信息与日志路径须直接沿用。',
    '- **须执行 Step 3（匹配 Skill）**：结合补充信息与首轮上下文，重新评估 1～3 个分析 Skill（可沿用首轮匹配结果，也可根据补充信息调整）；Read 相关 SKILL.md 后输出 `match_skills` 阶段标记。',
    '- 完成 Skill 匹配后进入 Step 4～5：更新根因判断并**重新输出完整 9 节报告**（含第 9 节 Jira 备注）。',
    '- 若补充信息涉及新现象，在**不重新拉 JIRA/不重新下载**的前提下，基于对话中已有日志路径或已读内容分析；确需新数据时说明缺什么，不要擅自重跑 Step 1～2。',
    '- **不要**输出 fetch_jira / download_logs 阶段标记。',
    '',
    '请基于我们之前的完整对话与上述补充，重新生成完整的 9 节分析报告（含第 9 节 Jira 备注）。',
  ]
  if (!isLocal) {
    blocks.push(`报告须针对 JIRA **${ctx.jiraKey}**，不得切换到其它 Issue。`)
  }
  return blocks.join('\n')
}

function loadFirstUserPrompt(taskId: string): string | null {
  const p = join(promptDirFor(taskId), 'user-prompt.md')
  if (!existsSync(p)) return null
  try {
    return readFileSync(p, 'utf-8')
  } catch {
    return null
  }
}

interface ConversationRound {
  user: string
  assistant: string
}

async function bridgeSessionAlive(sessionId: string): Promise<boolean> {
  try {
    await sharedBridgeClient.getHistory(sessionId)
    return true
  } catch {
    return false
  }
}

function bugAgentSessionId(taskId: string): string {
  return `tahp-bug-${taskId}`
}

export interface BugTaskContinueStatus {
  can_continue: boolean
  reason?: string
  agent_session_id?: string
}

/** 检测任务是否可在当前 Agent Bridge 会话中「补充信息继续分析」 */
export async function getBugTaskContinueStatus(taskId: string): Promise<BugTaskContinueStatus> {
  const agentSessionId = bugAgentSessionId(taskId)
  let ctx = taskCtx.get(taskId)
  const report = readBugReport(taskId) as Record<string, unknown> | null

  if (!ctx && report) {
    ctx = restoreCtxFromReport(taskId, report)
  }
  if (!ctx && !report) {
    return { can_continue: false, reason: '找不到任务' }
  }

  const status = ctx?.status || String(report?.status || '')
  if (status === 'running' || status === 'pending' || status === 'waiting_user_input') {
    return { can_continue: false, reason: '任务正在运行中', agent_session_id: agentSessionId }
  }
  if (ctx?.dupJudgeStatus === 'running' || dupJudgeRuntime.has(taskId)) {
    return { can_continue: false, reason: '正在尝试置重，请稍后再补充分析', agent_session_id: agentSessionId }
  }
  if (status !== 'completed') {
    return { can_continue: false, reason: '仅已完成的分析任务可补充继续', agent_session_id: agentSessionId }
  }

  const alive = await bridgeSessionAlive(agentSessionId)
  if (!alive) {
    return {
      can_continue: false,
      reason: 'Agent 会话已断开（服务重启或跨机器），无法在同一会话中补充分析。请重新发起分析。',
      agent_session_id: agentSessionId,
    }
  }

  return { can_continue: true, agent_session_id: agentSessionId }
}

function buildConversationHistoryFromReport(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
): Array<{ role: string; content: string }> {
  const report = readBugReport(taskId) as Record<string, unknown> | null
  const history: Array<{ role: string; content: string }> = []
  const rounds = report?.conversation_rounds as ConversationRound[] | undefined

  if (Array.isArray(rounds) && rounds.length > 0) {
    for (const round of rounds) {
      if (round.user) history.push({ role: 'user', content: round.user })
      if (round.assistant) history.push({ role: 'assistant', content: round.assistant })
    }
    return history
  }

  const firstUser = loadFirstUserPrompt(taskId) || buildAgentUserMessage(ctx)
  history.push({ role: 'user', content: firstUser })
  if (report?.llm_response) {
    history.push({ role: 'assistant', content: String(report.llm_response) })
  }

  const pastCorrections = ctx.corrections.slice(0, -1)
  for (let i = 0; i < pastCorrections.length; i += 1) {
    history.push({ role: 'user', content: buildContinueUserMessage(pastCorrections[i], ctx, i + 1) })
  }

  return history
}

function restoreReportStatus(raw: unknown): BugAnalysisTaskCtx['status'] {
  const s = String(raw || '')
  if (
    s === 'pending' || s === 'running' || s === 'waiting_user_input'
    || s === 'completed' || s === 'failed' || s === 'cancelled'
  ) return s
  return 'completed'
}

function restoreCtxFromReport(taskId: string, report: Record<string, unknown>): BugAnalysisTaskCtx {
  const status = restoreReportStatus(report.status)
  return {
    taskId,
    jiraKey: String(report.jira_key || ''),
    jiraUrl: String(report.jira_url || ''),
    module: report.module as TahpBugModule | undefined,
    title: typeof report.title === 'string' ? report.title : undefined,
    rawInput: typeof report.jira_key === 'string' ? report.jira_key : undefined,
    userDescription: typeof report.user_description === 'string' ? report.user_description : undefined,
    extraContext: typeof report.extra_context === 'string' ? report.extra_context : undefined,
    codeSource: restoreCodeSourceFromReport(report.code_source),
    startedAt: String(report.started_at || new Date().toISOString()),
    status,
    phase: typeof report.phase === 'string' ? report.phase : (status === 'completed' ? 'COMPLETED' : undefined),
    progress: typeof report.progress === 'number' ? report.progress : (status === 'completed' ? 100 : 0),
    corrections: Array.isArray(report.corrections) ? [...report.corrections as string[]] : [],
    skillsUsed: Array.isArray(report.skills_used) ? [...report.skills_used as string[]] : [],
    skillsImproved: parseSkillImproves(report.skills_improved),
    prevResponse: typeof report.llm_response === 'string' ? report.llm_response : undefined,
    llmResponse: typeof report.llm_response === 'string' ? report.llm_response : undefined,
    completedAt: typeof report.completed_at === 'string' ? report.completed_at : undefined,
    jiraSnapshot: (report.jira as Record<string, string> | undefined),
    analysisMode: report.analysis_mode as BugAnalysisMode | undefined,
    localLogPath: typeof report.local_log_path === 'string' ? report.local_log_path : undefined,
  }
}

interface RunBugAnalysisOptions {
  mode?: 'initial' | 'continue' | 'user_input_resume'
  userInputRequest?: ParsedUserInputRequest
  userInputValues?: Record<string, string>
  silentCredentialResume?: boolean
  silentCredentialSeeded?: boolean
}

/** 任务结束落盘前：ledger 补齐自改进 Skill，再快照。实时 detectSkillImprove 只负责活动流。 */
async function settleSkillImproves(taskId: string, ctx: BugAnalysisTaskCtx): Promise<void> {
  try {
    ctx.skillsImproved = mergeLedgerSkillImproves(
      ctx.skillsImproved || [],
      taskId,
      loadCuratorLedger(),
    )
  } catch (e) {
    logBug(taskId, 'warn', `skill ledger merge failed: ${(e as Error).message}`)
  }
  if (!(ctx.skillsImproved || []).length) return
  try {
    ctx.skillsImproved = await snapshotImprovedSkills({
      reportsDir: tahpPaths.reportsDir,
      taskId,
      records: ctx.skillsImproved || [],
      source: 'runtime',
    })
  } catch (e) {
    logBug(taskId, 'warn', `skill snapshot failed: ${(e as Error).message}`)
  }
}

function persistSkillsImprovedOnExistingReport(taskId: string, records: SkillImproveRecord[]): void {
  if (!records.length) return
  const existing = readBugReport(taskId) as Record<string, unknown> | null
  if (!existing) return
  existing.skills_improved = records
  try {
    writeFileSync(reportPath(taskId), JSON.stringify(existing, null, 2), 'utf-8')
  } catch (e) {
    logBug(taskId, 'warn', `skill improve report patch failed: ${(e as Error).message}`)
  }
}

const skillImproveReconcileInflight = new Map<string, Promise<SkillImproveRecord[]>>()

/** 结束后补扫 ledger；报告已落盘、curator 后到也能补徽章和快照。 */
export function reconcileSkillImproveForTask(taskId: string): Promise<SkillImproveRecord[]> {
  const tid = String(taskId || '').trim()
  if (!tid) return Promise.resolve([])
  const running = skillImproveReconcileInflight.get(tid)
  if (running) return running
  const work = runSkillImproveReconcile(tid).finally(() => {
    skillImproveReconcileInflight.delete(tid)
  })
  skillImproveReconcileInflight.set(tid, work)
  return work
}

async function runSkillImproveReconcile(taskId: string): Promise<SkillImproveRecord[]> {
  const live = taskCtx.get(taskId)
  const report = readBugReport(taskId) as Record<string, unknown> | null
  const existing = live?.skillsImproved || parseSkillImproves(report?.skills_improved)
  let merged = existing
  try {
    merged = mergeLedgerSkillImproves(existing, taskId, loadCuratorLedger())
  } catch (e) {
    logBug(taskId, 'warn', `skill ledger reconcile failed: ${(e as Error).message}`)
    return existing
  }
  if (!skillImprovesNeedUpdate(existing, merged)) return existing
  let records = merged
  if (records.length) {
    try {
      records = await snapshotImprovedSkills({
        reportsDir: tahpPaths.reportsDir,
        taskId,
        records,
        source: 'runtime',
      })
    } catch (e) {
      logBug(taskId, 'warn', `skill snapshot failed: ${(e as Error).message}`)
    }
  }
  if (live) live.skillsImproved = records
  persistSkillsImprovedOnExistingReport(taskId, records)
  emit(taskId, 'task.skill_use', {
    skills_improved: records,
    message: records.length
      ? `自改进 Skill 已回填：${formatSkillImproveSummary(records)}`
      : undefined,
  })
  logBug(taskId, 'info', `skill improve reconciled: ${records.map(r => r.name).join(',') || 'none'}`)
  return records
}

function scheduleLateSkillImproveReconcile(taskId: string): void {
  scheduleSkillImproveReconcile(taskId, async () => {
    await reconcileSkillImproveForTask(taskId)
  })
}

export function overlaySkillsImproved(taskId: string, existing?: SkillImproveRecord[]): SkillImproveRecord[] {
  try {
    return mergeLedgerSkillImproves(existing || [], taskId, loadCuratorLedger())
  } catch {
    return existing || []
  }
}

// ─── 单条 Bug 分析（核心执行 - Agent 模式） ─────────────────────────────────

async function runSingleBugAnalysis(
  ctx: BugAnalysisTaskCtx,
  correction?: string,
  options: RunBugAnalysisOptions = {},
): Promise<void> {
  const startMs = Date.now()
  const taskId = ctx.taskId
  const isContinue = options.mode === 'continue'
  const isUserInputResume = options.mode === 'user_input_resume'
  if (ctx.status === 'cancelled') return
  ctx.status = 'running'
  ctx.skillsUsed = ctx.skillsUsed || []
  ctx.skillsImproved = ctx.skillsImproved || []
  taskCtx.set(taskId, ctx)
  pruneOldTasks()

  logBug(taskId, 'info', `开始 Bug 分析 (Agent 模式) task=${taskId} jira=${ctx.jiraKey}${isContinue ? ' (continue)' : ''}`)

  const agentSessionId = `tahp-bug-${taskId}`
  taskRuntime.set(taskId, { sessionId: agentSessionId, interruptRequested: false })

  const stageMarkerState = { lastIndex: 0 }
  const userInputMarkerState = { lastIndex: 0 }
  let succeeded = false
  let pausedForUserInput = false
  let toolCallCount = 0

  try {
    if (ctx.analysisMode !== 'local') {
      try {
        const seed = ensureLoginsightCredentialsForBugAnalysis()
        if (seed.writtenRoots.length) {
          emitBugActivity(
            taskId,
            `已写入 LogInsight 凭据到 ${seed.writtenRoots.length} 处 Skill 副本（含 Hermes 运行时）：${seed.writtenRoots.join(' | ')}`,
          )
        } else if (!seed.skipped) {
          emitBugActivity(taskId, `LogInsight 凭据未写入：${seed.reason || 'unknown'}`, 'warn')
        }
      } catch (err) {
        logBug(taskId, 'warn', `loginsight credential seed failed: ${(err as Error).message}`)
      }
    }

    let userMessage: string
    let instructions: string | undefined
    let conversationHistory: unknown[] | undefined

    if (isUserInputResume && options.userInputRequest && options.userInputValues) {
      userMessage = options.silentCredentialResume
        ? buildSilentCredentialResumeMessage(options.userInputRequest, !!options.silentCredentialSeeded)
        : buildUserInputResumeMessage(options.userInputRequest, options.userInputValues)
      const sessionAlive = await bridgeSessionAlive(agentSessionId)
      if (sessionAlive) {
        logBug(taskId, 'info', `user_input_resume: reusing bridge session ${agentSessionId}`)
        instructions = undefined
        conversationHistory = undefined
      } else {
        conversationHistory = buildConversationHistoryFromReport(taskId, ctx)
        instructions = buildBugAnalysisInstructions(userMessage, ctx)
      }
      emit(taskId, 'task.message', {
        level: 'round_divider',
        text: options.silentCredentialResume
          ? `\n\n---\n\n**已静默复用 Console Provider 凭据（${options.userInputRequest.title}）**\n\n`
          : `\n\n---\n\n**用户配置已提交（${options.userInputRequest.title}）**\n\n`,
      })
      saveAgentPromptLog(taskId, 'bug-analysis-user-input', instructions || '(session continue)', userMessage)
    } else if (isContinue && correction) {
      const roundNum = ctx.corrections.length
      emit(taskId, 'task.message', {
        level: 'round_divider',
        text: `\n\n---\n\n**用户补充（第 ${roundNum} 轮）**\n\n${correction}\n\n`,
      })

      userMessage = buildContinueUserMessage(correction, ctx, ctx.corrections.length)
      const sessionAlive = await bridgeSessionAlive(agentSessionId)
      if (!sessionAlive) {
        throw new Error(
          'Agent 会话已断开，无法在同一会话中补充分析。请重新发起分析。',
        )
      }
      logBug(taskId, 'info', `continue: reusing bridge session ${agentSessionId}`)
      instructions = undefined
      conversationHistory = undefined

      ctx.llmResponse = ''
      saveAgentPromptLog(taskId, 'bug-analysis', instructions || '(session continue — no new system prompt)', userMessage)
    } else {
      userMessage = buildAgentUserMessage(ctx)
      instructions = buildBugAnalysisInstructions(userMessage, ctx)
      const promptLog = saveAgentPromptLog(taskId, 'bug-analysis', instructions, userMessage)
      logBug(taskId, 'info', `Agent 提示词已落盘: ${promptLog.promptDir}`)
    }

    emitPrepPhase(taskId, ctx, 'PREPARING', isContinue ? '准备继续 Agent 对话...' : '准备提交给 Agent（提示词已落盘）...')

    emitPrepPhase(taskId, ctx, 'CONNECTING_AGENT', '连接 Agent Bridge...')
    // 本地模式：预置跳过 JIRA 步骤的 UI；续聊：沿用首轮 Step 1～3
    if (ctx.analysisMode === 'local' && !isContinue) {
      emitLocalPreflightStages(taskId, ctx)
    } else if (isContinue) {
      emitContinuePreflightStages(taskId, ctx)
    }
    const manager = getAgentBridgeManager()
    if (!manager.running) {
      throw new Error(
        'Agent Bridge 未运行。智能诊断必须由 Agent 执行（含 Skill 工具链）。' +
        '请检查 hermes CLI 是否已安装、agent-bridge 是否启动（查看服务端日志 [agent-bridge] 行）。',
      )
    }
    logBug(taskId, 'info', `Agent Bridge ready, session=${agentSessionId}`)
    emitBugActivity(taskId, `Agent Bridge 已连接，开始执行分析（session=${agentSessionId}）`)

    if (!isContinue && ctx.analysisMode !== 'local') {
      // JIRA 单条/批量首轮：从 Step 1 开始，由 Agent TAHP_STAGE 驱动进度
      ctx.phase = 'FETCH_JIRA_INFO'
      ctx.progress = BUG_UI_PHASE_PROGRESS.FETCH_JIRA_INFO
      emit(taskId, 'task.phase', {
        phase: 'FETCH_JIRA_INFO',
        progress: BUG_UI_PHASE_PROGRESS.FETCH_JIRA_INFO,
        message: 'Agent 正在拉取 JIRA 信息...',
      })
    }

    let lastSkillHitIdx = 0

    const { fullResponse, interrupted } = await runAgentChat(agentSessionId, userMessage, {
      onText: (delta) => {
        emit(taskId, 'task.message', { level: 'stream', text: delta })

        const fullSoFar = (ctx.llmResponse || '') + delta
        ctx.llmResponse = fullSoFar
        ingestStageMarkersFromText(taskId, ctx, fullSoFar, stageMarkerState, { continueMode: isContinue })

        const inputHits = findUserInputMarkers(fullSoFar, userInputMarkerState.lastIndex)
        for (const hit of inputHits) {
          userInputMarkerState.lastIndex = hit.startIndex + hit.rawBlock.length
          requestUserInputPause(taskId, ctx, hit, agentSessionId)
        }

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
        const improveHit = detectSkillImprove(toolName, args)
        if (improveHit) {
          ctx.skillsImproved = upsertSkillImprove(ctx.skillsImproved || [], improveHit)
          emitBugActivity(taskId, `自改进 Skill：${formatSkillImproveSummary([{ name: improveHit.name, actions: [improveHit.action] }])}`)
        }
        const argPreview = summarizeArgs(args)
        const activity = `正在调用工具 ${toolName}${argPreview ? ` ${argPreview}` : ''}`
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          args: argPreview,
          purpose: `Agent 真实调用工具 ${toolName}`,
          message: `🛠 Agent 调用：${toolName}${argPreview ? ` ${argPreview}` : ''}`,
          ...(improveHit ? { skills_improved: ctx.skillsImproved } : {}),
        })
        emitBugActivity(taskId, activity)
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `✗ 工具失败：${toolName}` : `✓ 工具完成：${toolName}`,
        })
        emitBugActivity(taskId, `${isError ? '工具失败' : '工具完成'}：${toolName}`, isError ? 'warn' : 'info')
      },
      onToolOutput: (text) => {
        emitBugActivity(taskId, text)
      },
      onReasoning: (text) => {
        if (text) emit(taskId, 'task.message', { level: 'reasoning', text })
      },
      onApprovalRequested: (payload) => {
        if (payload.approval_id) registerApprovalRequest(taskId, payload)
      },
    }, { instructions, conversationHistory })

    const runtimeAfterChat = taskRuntime.get(taskId)
    if (runtimeAfterChat?.userInputPause || pendingUserInputByTask.has(taskId)) {
      pausedForUserInput = true
      logBug(taskId, 'info', `task paused for user input: ${runtimeAfterChat?.userInputPause?.requestId || 'pending'}`)
      scheduleSilentLlmCredentialResume(taskId)
      return
    }

    if (interrupted) {
      const control = taskRuntime.get(taskId)
      if (control?.userInputPause) {
        pausedForUserInput = true
        logBug(taskId, 'info', `task paused for user input (interrupt): ${control.userInputPause.requestId}`)
        scheduleSilentLlmCredentialResume(taskId)
        return
      }
      throw new Error('Agent 运行被中断')
    }

    ctx.llmResponse = fullResponse
    const outcome = evaluateRunOutcome(fullResponse, toolCallCount)
    if (!outcome.ok) {
      throw new BugAnalysisEmptyResultError(outcome.message)
    }

    ingestStageMarkersFromText(taskId, ctx, fullResponse, stageMarkerState)

    logBug(taskId, 'info', `Agent run complete (${fullResponse.length} chars, tools=${toolCallCount}, skills_recorded=${ctx.skillsUsed.join(',') || 'none'}, skills_improved=${(ctx.skillsImproved || []).map(s => s.name).join(',') || 'none'})`)

    ctx.phase = 'GENERATING_REPORT'
    ctx.progress = BUG_UI_PHASE_PROGRESS.GENERATING_REPORT
    emit(taskId, 'task.phase', {
      phase: 'GENERATING_REPORT',
      progress: BUG_UI_PHASE_PROGRESS.GENERATING_REPORT,
      message: '生成报告并落盘...',
    })
    emit(taskId, 'task.step', { step_id: 'generate-report', status: 'running', message: '正在落盘 JSON 报告...' })

    ctx.prevResponse = fullResponse

    const completedAt = new Date().toISOString()
    const durationMs = Date.now() - startMs
    ctx.status = 'completed'
    ctx.completedAt = completedAt
    ctx.phase = 'COMPLETED'
    ctx.progress = 100
    emit(taskId, 'task.phase', {
      phase: 'COMPLETED',
      progress: 100,
      message: isContinue ? `补充分析完成（第 ${ctx.corrections.length} 轮）` : 'Bug 分析完成',
    })

    const reportBody = extractBugAnalysisReportBody(fullResponse)
    const existingReport = readBugReport(taskId) as Record<string, unknown> | null
    const prevRounds = (existingReport?.conversation_rounds as ConversationRound[] | undefined) || []
    const conversationRounds: ConversationRound[] = isContinue && correction
      ? [...prevRounds, { user: userMessage, assistant: fullResponse }]
      : [{ user: userMessage, assistant: fullResponse }]

    await settleSkillImproves(taskId, ctx)

    const report = {
      task_id: taskId,
      jira_key: ctx.jiraKey,
      jira_url: ctx.jiraUrl,
      module: ctx.module,
      title: ctx.jiraSnapshot?.issue_summary || ctx.title || ctx.rawInput || ctx.jiraKey,
      status: 'completed',
      execution_mode: 'agent',
      analysis_mode: ctx.analysisMode || 'jira_single',
      local_log_path: ctx.localLogPath,
      agent_session_id: agentSessionId,
      started_at: (existingReport?.started_at as string) || ctx.startedAt,
      completed_at: completedAt,
      duration_ms: durationMs,
      user_description: ctx.userDescription,
      extra_context: ctx.extraContext,
      code_source: snapshotCodeSourceForReport(ctx.codeSource),
      corrections: ctx.corrections,
      conversation_rounds: conversationRounds,
      skills_used: ctx.skillsUsed,
      skills_improved: ctx.skillsImproved || [],
      tool_call_count: toolCallCount,
      llm_response: fullResponse,
      report_body: reportBody,
      jira: buildReportJiraSection(ctx),
      remote_channels: ctx.analysisMode === 'local'
        ? undefined
        : snapshotRemoteChannelsForReport(readBugAnalysisChannelConfig()),
      user_input_responses: (existingReport?.user_input_responses as UserInputResponseRecord[] | undefined) || undefined,
    }
    try {
      writeFileSync(reportPath(taskId), JSON.stringify(report, null, 2), 'utf-8')
      emit(taskId, 'task.step', { step_id: 'generate-report', status: 'completed', message: '报告已落盘' })
      logBug(taskId, 'info', `report written: ${reportPath(taskId)}`)
    } catch (e) {
      logBug(taskId, 'error', `report write failed: ${(e as Error).message}`)
    }

    const sessionAlive = await bridgeSessionAlive(agentSessionId)
    emit(taskId, 'task.completed', {
      status: 'completed',
      jira_key: ctx.jiraKey,
      module: ctx.module,
      duration_ms: durationMs,
      skills_used: ctx.skillsUsed,
      skills_improved: ctx.skillsImproved || [],
      response_length: fullResponse.length,
      continue_round: isContinue ? ctx.corrections.length : undefined,
      can_continue_session: sessionAlive,
      agent_session_id: agentSessionId,
      message: isContinue
        ? `补充分析完成（第 ${ctx.corrections.length} 轮，${ctx.jiraKey}）`
        : `Bug 分析完成（${ctx.jiraKey}），使用 Skill: ${ctx.skillsUsed.join(', ') || '无'}`,
    })

    scheduleLateSkillImproveReconcile(taskId)

    succeeded = true

    // ── 更新父 job 状态 ───────────────────────────────────────────────────
    accountJobChildSuccess(ctx)

  } catch (err) {
    const control = taskRuntime.get(taskId)
    if (control?.userInputPause) {
      pausedForUserInput = true
      logBug(taskId, 'info', `task paused for user input (interrupt): ${control.userInputPause.requestId}`)
      scheduleSilentLlmCredentialResume(taskId)
      return
    }
    const interruptedByUser = control?.interruptRequested === true
    const msg = interruptedByUser ? '任务已被用户中断' : (err as Error).message
    const keepPriorReport = isContinue || isUserInputResume
    const failureReason = err instanceof BugAnalysisEmptyResultError ? err.failureReason : undefined
    logger.warn({ taskId, err: msg }, '[bug-analysis] failed')
    logBug(taskId, interruptedByUser ? 'warn' : 'error', `task failed: ${msg}`)
    ctx.status = interruptedByUser ? 'cancelled' : 'failed'
    ctx.error = msg
    ctx.completedAt = new Date().toISOString()
    await settleSkillImproves(taskId, ctx)
    if (keepPriorReport) {
      if (isContinue && correction) {
        const idx = ctx.corrections.lastIndexOf(correction)
        if (idx >= 0) ctx.corrections.splice(idx, 1)
      }
      ctx.status = 'completed'
      ctx.phase = 'COMPLETED'
      ctx.progress = 100
      persistSkillsImprovedOnExistingReport(taskId, ctx.skillsImproved || [])
      emit(taskId, 'task.continue_failed', { error: msg, message: `补充分析失败: ${msg}` })
      emit(taskId, 'task.phase', {
        phase: 'COMPLETED',
        progress: 100,
        message: '补充分析失败，可再次尝试',
      })
    } else if (interruptedByUser) {
      emit(taskId, 'task.cancelled', { error: msg, message: msg, skills_improved: ctx.skillsImproved || [] })
    } else {
      emit(taskId, 'task.failed', { error: msg, message: `分析失败: ${msg}`, skills_improved: ctx.skillsImproved || [] })
    }

    // 写入失败报告（补充继续 / 用户输入续跑失败时保留原 completed 报告）
    if (!keepPriorReport) {
      writeBugFailureReport(taskId, ctx, msg, { failureReason, toolCallCount })
    }

    scheduleLateSkillImproveReconcile(taskId)

    if (!keepPriorReport) {
      accountJobChildFailure(ctx)
    }
  } finally {
    if (!pausedForUserInput) {
      clearApprovalTimers(taskId)
    }
    if (!succeeded && !pausedForUserInput) {
      sharedBridgeClient.destroy(agentSessionId).catch((e) => {
        logBug(taskId, 'warn', `destroy agent session failed: ${(e as Error).message}`)
      })
      taskRuntime.delete(taskId)
    } else if (pausedForUserInput) {
      const control = taskRuntime.get(taskId)
      if (control) {
        control.interruptRequested = false
        taskRuntime.set(taskId, control)
      }
    } else {
      taskRuntime.delete(taskId)
    }
    if (!pausedForUserInput) {
      await appendBugLog(taskId, 'info', '── task end ──')
    }
  }
}

// ─── 工具调用参数摘要 (用于 task.skill_use 消息展示) ────────────────────────

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const obj = args as Record<string, unknown>
  const keys = Object.keys(obj)
  if (keys.length === 0) return ''
  // 抓 1~2 个最关键字段做预览（command/path/url/query/...）
  const prio = ['command', 'cmd', 'shell', 'tool', 'path', 'file', 'file_path', 'url', 'query', 'jql', 'key', 'issue_key', 'name', 'action']
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
    codeSource: parseCodeSource(input.codeSource),
    analysisMode: 'jira_single',
    startedAt: new Date().toISOString(),
    status: 'running',
    corrections: [],
    skillsUsed: [],
    skillsImproved: [],
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

export function startLocalLogBugAnalysis(input: LocalBugAnalysisInput): StartTaskResult {
  const logPath = input.logPath?.trim()
  const problemDescription = input.problemDescription?.trim()
  if (!logPath) return { ok: false, error: '本地日志路径不能为空' }
  if (!problemDescription) return { ok: false, error: '问题描述不能为空' }

  const taskId = genTaskId()
  const label = logPath.replace(/[/\\]+$/, '').split(/[/\\]/).pop() || 'local'
  const jiraKey = `LOCAL-${label}`.slice(0, 48)

  const ctx: BugAnalysisTaskCtx = {
    taskId,
    jiraKey,
    jiraUrl: '',
    rawInput: logPath,
    userDescription: problemDescription,
    codeSource: parseCodeSource(input.codeSource),
    localLogPath: logPath,
    analysisMode: 'local',
    title: `本地日志: ${label}`,
    startedAt: new Date().toISOString(),
    status: 'running',
    corrections: [],
    skillsUsed: [],
    skillsImproved: [],
  }
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.started', {
    type: 'local',
    analysis_mode: 'local',
    local_log_path: logPath,
    jira_key: jiraKey,
    message: `本地日志分析已启动: ${logPath}`,
  })
  logBug(taskId, 'info', `task.started local log=${logPath}`)

  setImmediate(() => {
    runSingleBugAnalysis(ctx).catch(err => {
      logger.error({ err: (err as Error).message, taskId }, '[bug-analysis] local unhandled')
    })
  })

  return { ok: true, taskId, jiraKey }
}

export function postBugAnalysisJiraComment(
  taskId: string,
  comment: string,
  jiraCfg: JiraConfig,
): { ok: boolean; error?: string; comment_id?: string } {
  const ctx = taskCtx.get(taskId)
  const report = readBugReport(taskId) as Record<string, unknown> | null
  const reportBody = report
    ? extractBugAnalysisReportBody(String(report.report_body || report.llm_response || ''))
    : ''
  const text = preprocessJiraCommentForSubmit(comment, reportBody)
  if (!text) return { ok: false, error: '评论内容不能为空' }

  const mode = ctx?.analysisMode || (report?.analysis_mode as string)
  if (mode === 'local') {
    return { ok: false, error: '本地日志分析任务不支持备注到 JIRA' }
  }

  const jiraKey = ctx?.jiraKey || String(report?.jira_key || '')
  if (!jiraKey || jiraKey.startsWith('LOCAL-')) {
    return { ok: false, error: '无效 JIRA Key，无法备注' }
  }

  const result = runJiraOpsAddComment(jiraKey, text, jiraCfg)
  if (!result.ok) return { ok: false, error: result.error }
  logBug(taskId, 'info', `jira comment posted: ${jiraKey}`)
  return {
    ok: true,
    comment_id: String(result.data?.comment_id || ''),
  }
}

function patchBugReportFields(taskId: string, patch: Record<string, unknown>): void {
  const existing = readBugReport(taskId) as Record<string, unknown> | null
  if (!existing) return
  try {
    writeFileSync(reportPath(taskId), JSON.stringify({ ...existing, ...patch }, null, 2), 'utf-8')
  } catch (err) {
    logBug(taskId, 'warn', `report patch failed: ${(err as Error).message}`)
  }
}

function emitDupJudgePhase(
  taskId: string,
  ctx: BugAnalysisTaskCtx,
  status: 'running' | 'completed' | 'failed',
  message: string,
): void {
  ctx.dupJudgeStatus = status
  taskCtx.set(taskId, ctx)
  if (status === 'running') {
    ctx.phase = 'MARK_DUPLICATE'
    emit(taskId, 'task.phase', {
      phase: 'MARK_DUPLICATE',
      progress: 100,
      dup_judge_status: 'running',
      message,
    })
    return
  }
  ctx.phase = 'COMPLETED'
  emit(taskId, 'task.phase', {
    phase: 'COMPLETED',
    progress: 100,
    dup_judge_status: status,
    message,
  })
}

/** 分析完成后按 jira-dup-judge 启动独立 Agent 会话（不污染续聊会话）。 */
export async function runJiraDupJudge(taskId: string): Promise<{ ok: boolean; error?: string }> {
  if (dupJudgeRuntime.has(taskId)) {
    return { ok: false, error: '该任务已在尝试置重' }
  }

  let ctx = taskCtx.get(taskId)
  const report = readBugReport(taskId) as Record<string, unknown> | null
  if (!ctx && report) ctx = restoreCtxFromReport(taskId, report)
  if (!ctx) return { ok: false, error: `找不到任务 ${taskId}` }

  const mode = ctx.analysisMode || (report?.analysis_mode as string)
  if (mode === 'local' || ctx.jiraKey.startsWith('LOCAL-')) {
    return { ok: false, error: '本地日志分析任务不支持置重' }
  }
  if (!ctx.jiraKey) return { ok: false, error: '无效 JIRA Key，无法置重' }

  const jiraUrl = resolveJiraBrowseUrl(ctx.jiraUrl, ctx.jiraKey)
  const userMessage = buildJiraDupJudgePrompt(jiraUrl)
  const instructions = buildJiraDupJudgeInstructions(userMessage)
  const sessionId = jiraDupJudgeSessionId(taskId)
  dupJudgeRuntime.set(taskId, { sessionId, interruptRequested: false })

  emitDupJudgePhase(taskId, ctx, 'running', `按 ${JIRA_DUP_JUDGE_SKILL_ID} 尝试置重: ${ctx.jiraKey}`)
  emit(taskId, 'task.message', {
    level: 'round_divider',
    text: `\n\n---\n\n**按 ${JIRA_DUP_JUDGE_SKILL_ID} 尝试置重**\n\n${userMessage}\n\n`,
  })
  emitBugActivity(taskId, `开始置重：${userMessage}`)
  saveAgentPromptLog(taskId, 'bug-analysis-dup-judge', instructions, userMessage)

  ctx.skillsUsed = ctx.skillsUsed || []
  if (!ctx.skillsUsed.includes(JIRA_DUP_JUDGE_SKILL_ID)) {
    ctx.skillsUsed.push(JIRA_DUP_JUDGE_SKILL_ID)
  }

  try {
    const { fullResponse, interrupted } = await runAgentChat(sessionId, userMessage, {
      onText: (delta) => {
        emit(taskId, 'task.message', { level: 'stream', text: delta })
      },
      onToolStarted: (toolName, args, toolCallId) => {
        if (!ctx!.skillsUsed.includes(toolName)) ctx!.skillsUsed.push(toolName)
        const argPreview = summarizeArgs(args)
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          args: argPreview,
          purpose: `jira-dup-judge 调用 ${toolName}`,
          message: `🛠 置重调用：${toolName}${argPreview ? ` ${argPreview}` : ''}`,
        })
        emitBugActivity(taskId, `置重调用工具 ${toolName}${argPreview ? ` ${argPreview}` : ''}`)
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `✗ 置重工具失败：${toolName}` : `✓ 置重工具完成：${toolName}`,
        })
        emitBugActivity(taskId, `${isError ? '置重工具失败' : '置重工具完成'}：${toolName}`, isError ? 'warn' : 'info')
      },
      onToolOutput: (text) => {
        emitBugActivity(taskId, text)
      },
      onReasoning: (text) => {
        if (text) emit(taskId, 'task.message', { level: 'reasoning', text })
      },
      onApprovalRequested: (payload) => {
        if (payload.approval_id) registerApprovalRequest(taskId, payload)
      },
    }, { instructions })

    const interruptedByUser = dupJudgeRuntime.get(taskId)?.interruptRequested === true || interrupted
    if (interruptedByUser) {
      emitDupJudgePhase(taskId, ctx, 'failed', '置重已停止')
      patchBugReportFields(taskId, {
        jira_dup_judge: { status: 'failed', summary: '用户停止置重' },
        skills_used: ctx.skillsUsed,
      })
      logBug(taskId, 'warn', 'jira-dup-judge interrupted')
      return { ok: false, error: '置重已停止' }
    }

    const summary = (fullResponse || '').trim().slice(0, 2000)
    emitDupJudgePhase(taskId, ctx, 'completed', `置重流程结束（${ctx.jiraKey}）`)
    patchBugReportFields(taskId, {
      jira_dup_judge: { status: 'completed', summary },
      skills_used: ctx.skillsUsed,
    })
    logBug(taskId, 'info', `jira-dup-judge finished: ${ctx.jiraKey} chars=${fullResponse.length}`)
    return { ok: true }
  } catch (err) {
    const msg = (err as Error).message
    emitDupJudgePhase(taskId, ctx, 'failed', `置重失败: ${msg}`)
    emitBugActivity(taskId, `置重失败: ${msg}`, 'error')
    patchBugReportFields(taskId, {
      jira_dup_judge: { status: 'failed', summary: msg },
      skills_used: ctx.skillsUsed,
    })
    logBug(taskId, 'warn', `jira-dup-judge failed: ${msg}`)
    return { ok: false, error: msg }
  } finally {
    const runtime = dupJudgeRuntime.get(taskId)
    dupJudgeRuntime.delete(taskId)
    if (runtime) {
      sharedBridgeClient.destroy(runtime.sessionId).catch(() => {})
    }
  }
}

/** 批量：有结论后自动回写默认 Jira comment，再尝试置重。失败不改变分析终态。 */
export async function autoPostCommentAndDupJudge(taskId: string): Promise<void> {
  const report = readBugReport(taskId) as Record<string, unknown> | null
  const reportBody = report
    ? extractBugAnalysisReportBody(String(report.report_body || report.llm_response || ''))
    : ''
  const comment = composeDefaultJiraCommentFromReport(reportBody)
  const jiraCfg = resolveJiraConfig()

  if (comment && hasJiraBasicCredentials(jiraCfg)) {
    const posted = postBugAnalysisJiraComment(taskId, comment, jiraCfg)
    if (posted.ok) {
      emitBugActivity(taskId, '已自动把分析结论写回 Jira comment')
      patchBugReportFields(taskId, { jira_comment_posted: true })
    } else {
      emitBugActivity(taskId, `自动回写 Jira comment 失败：${posted.error}`, 'warn')
    }
  } else if (comment && !hasJiraBasicCredentials(jiraCfg)) {
    emitBugActivity(taskId, '未配置 JIRA 账号，跳过自动回写 comment，仍尝试置重', 'warn')
  } else {
    emitBugActivity(taskId, '报告无可用 Jira 备注，跳过自动回写 comment，仍尝试置重', 'warn')
  }

  const dup = await runJiraDupJudge(taskId)
  if (!dup.ok && dup.error) {
    emitBugActivity(taskId, `尝试置重未完成：${dup.error}`, 'warn')
  }
}

// ─── 公开入口：补充信息继续分析 ─────────────────────────────────────────────

export async function continueBugAnalysis(taskId: string, input: ContinueAnalysisInput): Promise<StartTaskResult> {
  const additionalInfo = input.additionalInfo.trim()
  if (!additionalInfo) return { ok: false, error: '补充信息不能为空' }

  if (dupJudgeRuntime.has(taskId)) {
    return { ok: false, error: '正在尝试置重，请稍后再补充分析' }
  }

  const sessionStatus = await getBugTaskContinueStatus(taskId)
  if (!sessionStatus.can_continue) {
    return { ok: false, error: sessionStatus.reason || '当前无法补充继续分析' }
  }

  let ctx = taskCtx.get(taskId)
  const report = readBugReport(taskId) as Record<string, unknown> | null

  if (!ctx && report) {
    ctx = restoreCtxFromReport(taskId, report)
  }

  if (!ctx) {
    return { ok: false, error: `找不到任务 ${taskId}` }
  }

  ctx.corrections = [...ctx.corrections, additionalInfo]
  ctx.status = 'running'
  ctx.phase = 'STARTING'
  ctx.progress = 0
  ctx.error = undefined
  ctx.skillsUsed = [...(ctx.skillsUsed || [])]
  ctx.skillsImproved = [...(ctx.skillsImproved || [])]
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.continue_started', {
    type: 'continue',
    round: ctx.corrections.length,
    additional_info: additionalInfo,
    jira_key: ctx.jiraKey,
    jira_url: ctx.jiraUrl,
    message: `补充信息继续分析（第 ${ctx.corrections.length} 轮）: ${ctx.jiraKey}`,
  })

  // 用户补充说明首轮没达标 —— 评估层据此挑选评测用例候选
  emit(taskId, 'task.correction', {
    round: ctx.corrections.length,
    correction: additionalInfo,
    jira_key: ctx.jiraKey,
    eval_candidate: true,
  })
  logBug(taskId, 'info', `task.continue_started round=${ctx.corrections.length} jira=${ctx.jiraKey}`)

  setImmediate(() => {
    runSingleBugAnalysis(ctx!, additionalInfo, { mode: 'continue' }).catch(err => {
      logger.error({ err: (err as Error).message, taskId }, '[bug-analysis] continue unhandled')
    })
  })

  return { ok: true, taskId, jiraKey: ctx.jiraKey }
}

// ─── 公开入口：JQL 批量分析 ──────────────────────────────────────────────────

export interface StartBatchResult {
  ok: boolean
  jobId?: string
  total?: number
  tasks?: Array<{ task_id: string; jira_key: string }>
  error?: string
}

/**
 * 队列级等待预算：子任务停在 waiting_user_input 时最多等多久。
 *
 * 人工输入本身有 `timeout_sec`（默认 300s）自动兜底提交空值，之后 Agent 会续跑，
 * 所以这里的预算要覆盖「暂停 → 自动兜底 → 续跑到出结论」的整段。超预算则判该单失败，
 * 队列继续往下走 —— 不允许一次交互挂死整条队列。用 TAHP_BUG_BATCH_TASK_WAIT_MS 覆盖。
 */
const DEFAULT_BATCH_TASK_WAIT_MS = 60 * 60_000

function batchTaskWaitMs(): number {
  const raw = Number(process.env.TAHP_BUG_BATCH_TASK_WAIT_MS)
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : DEFAULT_BATCH_TASK_WAIT_MS
}

function delayMs(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/** 等一个已暂停的子任务走到终态；超出预算则判失败。 */
async function waitForBatchTaskSettled(taskId: string, budgetMs: number): Promise<void> {
  const deadline = Date.now() + budgetMs
  for (;;) {
    const ctx = taskCtx.get(taskId)
    if (!ctx || isTerminalTaskStatus(ctx.status)) return
    if (Date.now() >= deadline) {
      forceFailTask(
        taskId,
        `批量队列等待超时（${Math.round(budgetMs / 60_000)} 分钟未完成，可能卡在人工输入），已判失败并继续后续任务`,
      )
      return
    }
    await delayMs(1000)
  }
}

interface BatchCandidate {
  key: string
  url: string
}

/**
 * 建队列并串行执行。
 *
 * 串行是刻意的：单条子任务就是一次完整 Agent 会话，并发跑会互相抢 Agent Pool 与工具链。
 * 失败**不终止**队列：该单标记失败、写失败报告，队列继续下一单，直到全部走完。
 */
function startBatchQueue(
  candidates: BatchCandidate[],
  opts: { jql?: string; extraContext?: string; codeSource?: string; resumedFrom?: string; autoPostCommentAndDup?: boolean },
): StartBatchResult {
  const jobId = genTaskId('task-bugjob')
  const job: BugAnalysisJobCtx = {
    jobId,
    type: 'batch',
    jql: opts.jql,
    extraContext: opts.extraContext,
    codeSource: opts.codeSource,
    resumedFrom: opts.resumedFrom,
    autoPostCommentAndDup: opts.autoPostCommentAndDup,
    taskIds: [],
    startedAt: new Date().toISOString(),
    status: 'running',
    total: candidates.length,
    completed: 0,
    failed: 0,
  }
  jobCtx.set(jobId, job)

  // 判型只做一次（含路径存在性探测），所有子任务共享这份只读引用
  const codeSourceRef = parseCodeSource(opts.codeSource)

  const tasks: Array<{ task_id: string; jira_key: string }> = []
  for (const candidate of candidates) {
    const tid = genTaskId()
    const ctx: BugAnalysisTaskCtx = {
      taskId: tid,
      parentJobId: jobId,
      jiraKey: candidate.key,
      jiraUrl: candidate.url,
      startedAt: new Date().toISOString(),
      status: 'pending',
      corrections: [],
      skillsUsed: [],
      skillsImproved: [],
      extraContext: opts.extraContext,
      codeSource: codeSourceRef,
    }
    taskCtx.set(tid, ctx)
    job.taskIds.push(tid)
    tasks.push({ task_id: tid, jira_key: candidate.key })
  }
  persistJob(job)

  emit(jobId, 'task.started', {
    type: 'batch',
    jql: opts.jql,
    total: candidates.length,
    resumed_from: opts.resumedFrom,
    tasks,
    message: `批量 Bug 分析启动：共 ${candidates.length} 单（串行，失败自动跳过）`,
  })
  logBug(jobId, 'info', `batch.started total=${candidates.length} jql=${(opts.jql || '').slice(0, 200)}`)

  setImmediate(async () => {
    const budgetMs = batchTaskWaitMs()
    for (const tid of job.taskIds) {
      const ctx = taskCtx.get(tid)
      if (!ctx) {
        // ctx 意外缺失（被清理）：仍要计一次失败，否则 job 凑不满 total 永不结算
        job.failed += 1
        logBug(jobId, 'warn', `child ctx missing, counted as failed: ${tid}`)
        emitJobProgress(job)
        continue
      }
      // 用户在排队期间单独取消 / 已跑过：cancelBugTask 已计过数，跳过即可
      if (isTerminalTaskStatus(ctx.status)) continue

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
      } catch (err) {
        const reason = (err as Error).message
        logger.warn({ err: reason, tid }, '[bug-analysis] batch child threw')
        forceFailTask(tid, `子任务异常终止: ${reason}`)
      }

      // 暂停在人工输入时 runSingleBugAnalysis 会提前 return（此时既未计成功也未计失败），
      // 必须等它真正落地，否则下一单会与它并发，且 job 永远结不了。
      const latest = taskCtx.get(tid)
      if (latest && !isTerminalTaskStatus(latest.status)) {
        await waitForBatchTaskSettled(tid, budgetMs)
      }

      const settled = taskCtx.get(tid)
      if (job.autoPostCommentAndDup && settled?.status === 'completed') {
        try {
          await autoPostCommentAndDupJudge(tid)
        } catch (err) {
          logBug(tid, 'warn', `auto comment/dup failed: ${(err as Error).message}`)
        }
      }
    }

    settleJobIfDone(job)
  })

  return { ok: true, jobId, total: candidates.length, tasks }
}

export async function startBatchBugAnalysis(
  jql: string,
  extraContext?: string,
  jiraCfg?: JiraConfig,
  codeSource?: string,
  autoPostCommentAndDup?: boolean,
): Promise<StartBatchResult> {
  if (!jql?.trim()) return { ok: false, error: '空 JQL' }

  const search = await searchJQLAll(jql, jiraCfg)
  if (!search.ok || !search.data) {
    return { ok: false, error: search.error || 'JQL 查询失败' }
  }
  const candidates = search.data.issues.map(i => ({ key: i.key, url: i.url }))
  if (!candidates.length) {
    return { ok: false, error: 'JQL 未匹配到任何 Issue' }
  }

  const result = startBatchQueue(candidates, { jql, extraContext, codeSource, autoPostCommentAndDup })
  if (result.ok && search.data.truncated) {
    logBug(
      result.jobId!,
      'warn',
      `jql matched ${search.data.total} issues, queued ${candidates.length} (capped by TAHP_JQL_MAX_ISSUES)`,
    )
  }
  return result
}

/** 续跑：把来源 job 中未走到终态的单子重新入队为一个新 job。 */
export function resumeBugJob(jobId: string): StartBatchResult {
  const source = readPersistedBugJob(tahpPaths.reportsDir, jobId)
  if (!source) return { ok: false, error: `找不到批量任务记录: ${jobId}` }
  return requeueJobTasks(source.job_id, unfinishedJobTasks(source), source, '没有未完成的子任务')
}

/** 重跑失败项：把来源 job 中 failed 的单子重新入队为一个新 job。 */
export function retryFailedBugJob(jobId: string): StartBatchResult {
  const source = readPersistedBugJob(tahpPaths.reportsDir, jobId)
  if (!source) return { ok: false, error: `找不到批量任务记录: ${jobId}` }
  return requeueJobTasks(source.job_id, failedJobTasks(source), source, '没有失败的子任务')
}

function requeueJobTasks(
  sourceJobId: string,
  picked: PersistedBugJobTask[],
  source: { jql?: string; extra_context?: string; code_source?: string; auto_post_comment_and_dup?: boolean },
  emptyError: string,
): StartBatchResult {
  const candidates = picked
    .filter(t => t.jira_key)
    .map(t => ({ key: t.jira_key, url: t.jira_url }))
  if (!candidates.length) return { ok: false, error: emptyError }
  return startBatchQueue(candidates, {
    jql: source.jql,
    extraContext: source.extra_context,
    codeSource: source.code_source,
    resumedFrom: sourceJobId,
    autoPostCommentAndDup: source.auto_post_comment_and_dup,
  })
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

export async function cancelBugTask(taskId: string): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running' | 'interrupted_dup_judge'; error?: string }> {
  const ctx = taskCtx.get(taskId)
  const dup = dupJudgeRuntime.get(taskId)
  if (dup) {
    dup.interruptRequested = true
    dupJudgeRuntime.set(taskId, dup)
    try {
      await sharedBridgeClient.interrupt(dup.sessionId, '用户停止置重')
    } catch (err) {
      logBug(taskId, 'warn', `interrupt dup-judge failed: ${(err as Error).message}`)
    }
    logBug(taskId, 'warn', 'jira-dup-judge cancelled by user')
    return { ok: true, action: 'interrupted_dup_judge' }
  }

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
    accountJobChildFailure(ctx)
    return { ok: true, action: 'cancelled_pending' }
  }

  if (ctx.status === 'waiting_user_input') {
    // forceFailTask 会一并写失败报告、销毁会话并更新父 job 计数
    // （批量场景下漏掉计数会让整条队列永远结不了）
    forceFailTask(taskId, '用户取消配置等待')
    return { ok: true, action: 'interrupted_running' }
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
