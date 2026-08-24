/**
 * TAHP AI Bug 分析路由
 *
 * 设计目标：
 *   - 单条 Bug 分析（输入 ID/URL + 用户补充描述）
 *   - JQL 批量 Bug 分析
 *   - JIRA 预览（fetch 单条 / JQL 列表）
 *   - 任务列表 / 任务详情 / 报告 / 日志
 *   - 补充信息继续分析（带上下文重跑）
 *   - 知识沉淀按钮（占位 — 仅记录请求）
 *
 * 所有事件实时性走 Socket.IO /tahp-run 命名空间（同 AI 适配调试，共享 TaskStream）。
 */
import Router from '@koa/router'
import {
  startSingleBugAnalysis,
  continueBugAnalysis,
  startBatchBugAnalysis,
  startLocalLogBugAnalysis,
  postBugAnalysisJiraComment,
  cancelBugTask,
  previewSingleIssue,
  listBugTasks,
  getBugTask,
  getBugTaskContinueStatus,
  listBugJobs,
  getBugJob,
  listBugReports,
  readBugReport,
  readBugSkillSnapshot,
  deleteBugReport,
  respondBugApproval,
  submitBugUserInput,
} from '../../services/tahp/bug-analysis'
import { searchJQL, parseIssueKey, verifyJiraConnectivity } from '../../services/tahp/jira'
import type { JiraConfig } from '../../services/tahp/jira'
import {
  resolveJiraConfig,
  hasJiraBasicCredentials,
  writeJiraUserConfig,
} from '../../services/tahp/jira-user-config'
import {
  readBugAnalysisChannelConfig,
  writeBugAnalysisChannelConfig,
  resolveRemoteSkillPath,
} from '../../services/tahp/bug-analysis-config'
import { readBugLog, recordDistillRequest, listDistillRequests } from '../../services/tahp/bug-analysis-logger'
import { depositDistilledEntry, type DepositDistilledResult } from './knowledge'
import {
  extractJiraFromBugReport,
  prependDistillJiraHeader,
} from '../../services/tahp/distill-jira-header'
import { formatBugReportPlainText } from '../../services/tahp/format-bug-report-plain'
import { logger } from '../../services/logger'

export const tahpBugAnalysisRoutes = new Router({ prefix: '/api/tahp/bug-analysis' })

function readJiraHeaderOverride(ctx: any): Partial<JiraConfig> | null {
  const username = String(ctx.headers['x-tahp-jira-username'] || '').trim()
  const password = String(ctx.headers['x-tahp-jira-password'] || '').trim()
  if (!username || !password) return null
  return { username, password }
}

function resolveJiraConfigFromRequest(ctx: any): JiraConfig {
  return resolveJiraConfig(readJiraHeaderOverride(ctx))
}

function requireJiraUserConfig(ctx: any): JiraConfig | null {
  const cfg = resolveJiraConfigFromRequest(ctx)
  if (hasJiraBasicCredentials(cfg)) return cfg
  ctx.status = 400
  ctx.body = {
    success: false,
    error: '请先在智能诊断页面配置 JIRA 账号密码（将同步到本机 .tahp/jira-user-config.json）',
  }
  return null
}

// ─── 启动单条 Bug 分析 ───────────────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/single
// Body: { input: "X6873OS162-1079" | URL, user_description?, extra_context? }
//
// 注：不再接收 module —— Bug 域识别由 Agent 在拉到 JIRA 后自主完成。
//     旧客户端若仍传 module 字段，会被静默忽略。
tahpBugAnalysisRoutes.post('/single', async (ctx) => {
  if (!requireJiraUserConfig(ctx)) return
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const rawInput = typeof body.input === 'string' ? body.input.trim() : ''
  if (!rawInput) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 input（JIRA ID 或 URL）' }
    return
  }
  const userDescription = typeof body.user_description === 'string' ? body.user_description : undefined
  const extraContext    = typeof body.extra_context === 'string'    ? body.extra_context    : undefined

  const result = startSingleBugAnalysis({ rawInput, userDescription, extraContext })
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = {
    success: true,
    data: {
      task_id: result.taskId,
      jira_key: result.jiraKey,
      type: 'single',
      status: 'running',
    },
  }
})

// ─── 本地日志分析（跳过 JIRA，从匹配 Skill 开始）────────────────────────────
//
// POST /api/tahp/bug-analysis/local
// Body: { log_path, problem_description }
tahpBugAnalysisRoutes.post('/local', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const logPath = typeof body.log_path === 'string' ? body.log_path.trim() : ''
  const problemDescription = typeof body.problem_description === 'string' ? body.problem_description.trim() : ''
  if (!logPath) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 log_path' }
    return
  }
  if (!problemDescription) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 problem_description' }
    return
  }
  const result = startLocalLogBugAnalysis({ logPath, problemDescription })
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = {
    success: true,
    data: {
      task_id: result.taskId,
      jira_key: result.jiraKey,
      type: 'local',
      analysis_mode: 'local',
      status: 'running',
    },
  }
})

// ─── 启动批量 Bug 分析 ───────────────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/batch
// Body: { jql, extra_context? }
tahpBugAnalysisRoutes.post('/batch', async (ctx) => {
  const jiraCfg = requireJiraUserConfig(ctx)
  if (!jiraCfg) return
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const jql = typeof body.jql === 'string' ? body.jql.trim() : ''
  if (!jql) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 jql' }
    return
  }
  const extraContext = typeof body.extra_context === 'string' ? body.extra_context : undefined

  const result = await startBatchBugAnalysis(jql, extraContext, jiraCfg)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = {
    success: true,
    data: {
      job_id: result.jobId,
      type: 'batch',
      total: result.total,
      tasks: result.tasks,
    },
  }
})

// ─── 补充信息继续分析 ────────────────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/:taskId/continue
// Body: { additional_info }
tahpBugAnalysisRoutes.post('/:taskId/continue', async (ctx) => {
  const taskId = ctx.params.taskId
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const additionalInfo = typeof body.additional_info === 'string' ? body.additional_info.trim() : ''
  if (!additionalInfo) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 additional_info（补充信息）' }
    return
  }
  const result = await continueBugAnalysis(taskId, { additionalInfo })
  if (!result.ok) {
    const isConflict = result.error?.includes('运行中')
    ctx.status = isConflict ? 409 : 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = {
    success: true,
    data: {
      task_id: result.taskId,
      jira_key: result.jiraKey,
      type: 'continue',
      status: 'running',
    },
  }
})

// ─── 危险命令审批（场景 A）────────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/:taskId/approval
// Body: { approval_id, choice: once|session|always|deny }
tahpBugAnalysisRoutes.post('/:taskId/approval', async (ctx) => {
  const taskId = ctx.params.taskId
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const approvalId = typeof body.approval_id === 'string' ? body.approval_id.trim() : ''
  const choice = typeof body.choice === 'string' ? body.choice.trim() : ''
  if (!approvalId || !choice) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 approval_id 或 choice' }
    return
  }
  const result = await respondBugApproval(taskId, approvalId, choice)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { approval_id: approvalId, choice } }
})

// ─── 结构化用户配置输入（场景 D）────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/:taskId/user-input
// Body: { request_id, values: Record<string, string> }
tahpBugAnalysisRoutes.post('/:taskId/user-input', async (ctx) => {
  const taskId = ctx.params.taskId
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const requestId = typeof body.request_id === 'string' ? body.request_id.trim() : ''
  const values = body.values && typeof body.values === 'object' ? body.values as Record<string, string> : null
  if (!requestId || !values) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 request_id 或 values' }
    return
  }
  const result = await submitBugUserInput(taskId, requestId, values, 'user')
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { request_id: requestId } }
})

// ─── 分析结论回到 jira comment ───────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/:taskId/jira-comment
// Body: { comment: string }
tahpBugAnalysisRoutes.post('/:taskId/jira-comment', async (ctx) => {
  const jiraCfg = requireJiraUserConfig(ctx)
  if (!jiraCfg) return
  const taskId = ctx.params.taskId
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const comment = typeof body.comment === 'string' ? body.comment.trim() : ''
  if (!comment) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 comment' }
    return
  }
  const result = postBugAnalysisJiraComment(taskId, comment, jiraCfg)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { comment_id: result.comment_id } }
})

// ─── 沉淀为知识库/Skill ──────────────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/:taskId/distill
// Body: { note?, content?, module?, category?, to_knowledge? }
//
// 真正把诊断报告写入知识库（pending_review 条目），返回条目信息供前端继续做
// Skill 关联（调用 /api/tahp/knowledge/skill-association + merge/generate）。
tahpBugAnalysisRoutes.post('/:taskId/distill', async (ctx) => {
  const taskId = ctx.params.taskId
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const report = readBugReport(taskId) as any
  if (!report) {
    ctx.status = 404
    ctx.body = { success: false, error: `找不到任务报告: ${taskId}` }
    return
  }

  const note = typeof body.note === 'string' ? body.note.trim() : ''
  const toKnowledge = body.to_knowledge !== false   // 默认存入知识库

  // 组装条目正文：优先使用前端传入的可编辑 content，否则从报告组装
  let content = typeof body.content === 'string' && body.content.trim()
    ? body.content.trim()
    : ''
  if (!content) {
    const parts: string[] = []
    if (report.title) parts.push(`【${report.title}】`)
    if (report.report_body) parts.push(String(report.report_body))
    else if (report.llm_response) parts.push(String(report.llm_response))
    content = formatBugReportPlainText(parts.join('\n\n').trim())
  } else {
    content = formatBugReportPlainText(content)
  }

  content = prependDistillJiraHeader(content, extractJiraFromBugReport(report as Record<string, unknown>))
  if (note) content += `\n\n【人工补充】\n${note}`

  try {
    let depositResult: DepositDistilledResult | undefined
    if (toKnowledge && content) {
      depositResult = await depositDistilledEntry({
        content,
        module: typeof body.module === 'string' ? body.module : report.module,
        func_type: 'bug_analysis',
        category: typeof body.category === 'string' ? body.category : undefined,
        source_task_id: taskId,
        jira_key: report.jira_key,
      })
    }
    const entry = depositResult?.entry

    await recordDistillRequest({
      task_id: taskId,
      jira_key: report.jira_key,
      module: report.module,
      title: report.title,
      requested_at: new Date().toISOString(),
      note: note || undefined,
      source: 'bug-analysis',
      entry_id: entry?.id,
      result: entry ? 'deposited' : 'recorded',
    })

    const action = depositResult?.action
    let message = '已记录沉淀请求'
    if (entry && action === 'created') {
      message = '已沉淀为知识条目（待审核），可继续关联/生成 Skill'
    } else if (entry && action === 'updated') {
      message = `已更新已有知识条目（${entry.jira_key || entry.id}），未重复创建`
    } else if (entry && action === 'unchanged') {
      message = `知识库中已存在相同案例（${entry.jira_key || entry.id}），未重复创建`
    }

    ctx.body = {
      success: true,
      data: {
        recorded: true,
        deposited: !!entry,
        dedup_action: action,
        entry: entry ? { id: entry.id, module: entry.module, func_type: entry.func_type } : null,
        message,
      },
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[bug-distill] deposit failed')
    try {
      await recordDistillRequest({
        task_id: taskId, jira_key: report.jira_key, module: report.module, title: report.title,
        requested_at: new Date().toISOString(), note: note || undefined,
        source: 'bug-analysis', result: 'failed',
      })
    } catch { /* ignore */ }
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 远程分析渠道开关 ───────────────────────────────────────────────────────
//
// GET /api/tahp/bug-analysis/channel-config
tahpBugAnalysisRoutes.get('/channel-config', async (ctx) => {
  const cfg = readBugAnalysisChannelConfig()
  const bugfix = cfg.remote_channels.bugfix_analysis
  const loginsight = cfg.remote_channels.loginsight_remote
  ctx.body = {
    success: true,
    data: {
      remote_channels: {
        bugfix_analysis: {
          enabled: bugfix.enabled,
          skill_id: bugfix.skill_id,
          skill_path: bugfix.skill_path || '',
          skill_found: resolveRemoteSkillPath(bugfix).found,
        },
        loginsight_remote: {
          enabled: loginsight.enabled,
          skill_id: loginsight.skill_id,
          skill_path: loginsight.skill_path || '',
          skill_found: resolveRemoteSkillPath(loginsight).found,
        },
      },
      updated_at: cfg.updated_at,
    },
  }
})

// PUT /api/tahp/bug-analysis/channel-config
// Body: { bugfix_analysis?: boolean, loginsight_remote?: boolean, bugfix_skill_path?, loginsight_skill_path? }
tahpBugAnalysisRoutes.put('/channel-config', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  try {
    const cfg = writeBugAnalysisChannelConfig({
      bugfix_analysis: typeof body.bugfix_analysis === 'boolean' ? body.bugfix_analysis : undefined,
      loginsight_remote: typeof body.loginsight_remote === 'boolean' ? body.loginsight_remote : undefined,
      bugfix_skill_path: typeof body.bugfix_skill_path === 'string' ? body.bugfix_skill_path : undefined,
      loginsight_skill_path: typeof body.loginsight_skill_path === 'string' ? body.loginsight_skill_path : undefined,
    })
    const bugfix = cfg.remote_channels.bugfix_analysis
    const loginsight = cfg.remote_channels.loginsight_remote
    ctx.body = {
      success: true,
      data: {
        remote_channels: {
          bugfix_analysis: {
            enabled: bugfix.enabled,
            skill_id: bugfix.skill_id,
            skill_path: bugfix.skill_path || '',
            skill_found: resolveRemoteSkillPath(bugfix).found,
          },
          loginsight_remote: {
            enabled: loginsight.enabled,
            skill_id: loginsight.skill_id,
            skill_path: loginsight.skill_path || '',
            skill_found: resolveRemoteSkillPath(loginsight).found,
          },
        },
        updated_at: cfg.updated_at,
      },
    }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 同步页面 JIRA 凭据到服务端（localStorage 镜像）────────────────────────
//
// PUT /api/tahp/bug-analysis/jira-user-config
// Body: { username, password }
tahpBugAnalysisRoutes.put('/jira-user-config', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const username = typeof body.username === 'string' ? body.username.trim() : ''
  const password = typeof body.password === 'string' ? body.password : ''
  if (!username || !password) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 username 或 password' }
    return
  }
  try {
    const record = writeJiraUserConfig({ username, password })
    void import('../../services/tahp/sync/jira-bind').then(({ scheduleBindJiraToCentral }) => {
      scheduleBindJiraToCentral({
        username: record.username,
        password,
        baseUrl: record.base_url,
      })
    }).catch(() => { /* bind 失败不影响本机保存 */ })
    ctx.body = { success: true, data: { username: record.username, updated_at: record.updated_at } }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── JIRA 凭据连通性校验 ─────────────────────────────────────────────────────
//
// POST /api/tahp/bug-analysis/jira-config/verify
// Headers: x-tahp-jira-username / x-tahp-jira-password（可选，缺省则用已同步的页面凭据）
tahpBugAnalysisRoutes.post('/jira-config/verify', async (ctx) => {
  const jiraCfg = resolveJiraConfigFromRequest(ctx)
  if (!hasJiraBasicCredentials(jiraCfg)) {
    ctx.status = 400
    ctx.body = { success: false, error: '请填写 JIRA 用户名和密码' }
    return
  }
  const r = await verifyJiraConnectivity(jiraCfg)
  if (!r.ok) {
    ctx.body = { success: true, data: { ok: false, error: r.error || '无法连接 JIRA' } }
    return
  }
  const who = r.data?.displayName || r.data?.name || jiraCfg.username
  ctx.body = {
    success: true,
    data: {
      ok: true,
      detail: `JIRA 连接正常（${who}）`,
      user: who,
    },
  }
})

// ─── JIRA 配置状态（是否已配置 + 是否连通）─────────────────────────────────
//
// GET /api/tahp/bug-analysis/jira-config/status
tahpBugAnalysisRoutes.get('/jira-config/status', async (ctx) => {
  const jiraCfg = resolveJiraConfigFromRequest(ctx)
  const configured = hasJiraBasicCredentials(jiraCfg)
  if (!configured) {
    ctx.body = { success: true, data: { configured: false, connected: false } }
    return
  }
  const r = await verifyJiraConnectivity(jiraCfg)
  if (!r.ok) {
    ctx.body = { success: true, data: { configured: true, connected: false, error: r.error || '无法连接 JIRA' } }
    return
  }
  const who = r.data?.displayName || r.data?.name || jiraCfg.username
  ctx.body = {
    success: true,
    data: { configured: true, connected: true, detail: `JIRA 连接正常（${who}）`, user: who },
  }
})

// ─── JIRA 预览 (单条) ────────────────────────────────────────────────────────
//
// GET /api/tahp/bug-analysis/jira/:input
tahpBugAnalysisRoutes.get('/jira/:input', async (ctx) => {
  const jiraCfg = requireJiraUserConfig(ctx)
  if (!jiraCfg) return
  const raw = decodeURIComponent(ctx.params.input || '')
  if (!raw) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 input' }
    return
  }
  const r = await previewSingleIssue(raw, jiraCfg)
  if (!r.ok) {
    // 即使失败也返回 200 + ok:false 让前端柔性处理
    ctx.body = { success: false, error: r.error, data: { jira_key: r.key } }
    return
  }
  ctx.body = { success: true, data: r.issue }
})

// ─── JQL 预览（不启动分析，仅列出匹配的 Issue） ──────────────────────────────
//
// POST /api/tahp/bug-analysis/jql-preview
// Body: { jql }
tahpBugAnalysisRoutes.post('/jql-preview', async (ctx) => {
  const jiraCfg = requireJiraUserConfig(ctx)
  if (!jiraCfg) return
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const jql = typeof body.jql === 'string' ? body.jql.trim() : ''
  if (!jql) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 jql' }
    return
  }
  const r = await searchJQL(jql, jiraCfg)
  if (!r.ok || !r.data) {
    ctx.body = { success: false, error: r.error || 'JQL 查询失败' }
    return
  }
  ctx.body = { success: true, data: r.data }
})

// ─── 任务列表（内存态，最近 200 条） ─────────────────────────────────────────

tahpBugAnalysisRoutes.get('/tasks', async (ctx) => {
  const tasks = listBugTasks().map(t => ({
    task_id: t.taskId,
    parent_job_id: t.parentJobId,
    jira_key: t.jiraKey,
    jira_url: t.jiraUrl,
    module: t.module,
    status: t.status,
    phase: t.phase,
    progress: t.progress,
    started_at: t.startedAt,
    completed_at: t.completedAt,
    skills_used: t.skillsUsed,
    skills_improved: t.skillsImproved || [],
    title: t.issue?.summary || t.title,
    error: t.error,
    analysis_mode: t.analysisMode,
    local_log_path: t.localLogPath,
  }))
  ctx.body = { success: true, data: tasks }
})

tahpBugAnalysisRoutes.get('/tasks/:id/continue-status', async (ctx) => {
  const status = await getBugTaskContinueStatus(ctx.params.id)
  ctx.body = { success: true, data: status }
})

tahpBugAnalysisRoutes.get('/tasks/:id', async (ctx) => {
  const t = getBugTask(ctx.params.id)
  if (!t) {
    // 回落到报告查询
    const r = readBugReport(ctx.params.id)
    if (!r) {
      ctx.status = 404
      ctx.body = { success: false, error: `找不到任务: ${ctx.params.id}` }
      return
    }
    ctx.body = { success: true, data: { fromReport: true, ...(r as object) } }
    return
  }
  ctx.body = { success: true, data: {
    task_id: t.taskId,
    parent_job_id: t.parentJobId,
    jira_key: t.jiraKey,
    jira_url: t.jiraUrl,
    module: t.module,
    status: t.status,
    phase: t.phase,
    progress: t.progress,
    started_at: t.startedAt,
    completed_at: t.completedAt,
    user_description: t.userDescription,
    extra_context: t.extraContext,
    corrections: t.corrections,
    skills_used: t.skillsUsed,
    skills_improved: t.skillsImproved || [],
    llm_response: t.llmResponse,
    error: t.error,
    issue: t.issue,
    title: t.issue?.summary || t.title,
    analysis_mode: t.analysisMode,
    local_log_path: t.localLogPath,
  } }
})

// 取消/中断任务：
// - running  -> 中断 Agent 执行
// - pending  -> 取消等待
tahpBugAnalysisRoutes.post('/tasks/:id/cancel', async (ctx) => {
  const r = await cancelBugTask(ctx.params.id)
  if (!r.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: r.error }
    return
  }
  ctx.body = { success: true, data: r }
})

// ─── Job 列表 / 详情 ─────────────────────────────────────────────────────────

tahpBugAnalysisRoutes.get('/jobs', async (ctx) => {
  const jobs = listBugJobs().map(j => ({
    job_id: j.jobId,
    type: j.type,
    jql: j.jql,
    task_ids: j.taskIds,
    started_at: j.startedAt,
    status: j.status,
    total: j.total,
    completed: j.completed,
    failed: j.failed,
  }))
  ctx.body = { success: true, data: jobs }
})

tahpBugAnalysisRoutes.get('/jobs/:id', async (ctx) => {
  const j = getBugJob(ctx.params.id)
  if (!j) {
    ctx.status = 404
    ctx.body = { success: false, error: `找不到 Job: ${ctx.params.id}` }
    return
  }
  ctx.body = { success: true, data: {
    job_id: j.jobId,
    type: j.type,
    jql: j.jql,
    task_ids: j.taskIds,
    tasks: j.taskIds.map(tid => {
      const t = getBugTask(tid)
      if (!t) return { task_id: tid, status: 'unknown' }
      return {
        task_id: t.taskId,
        jira_key: t.jiraKey,
        jira_url: t.jiraUrl,
        status: t.status,
        phase: t.phase,
        progress: t.progress,
        title: t.issue?.summary,
        skills_used: t.skillsUsed,
        skills_improved: t.skillsImproved || [],
        error: t.error,
      }
    }),
    started_at: j.startedAt,
    status: j.status,
    total: j.total,
    completed: j.completed,
    failed: j.failed,
  } }
})

// ─── 报告列表 / 详情 / 日志 ──────────────────────────────────────────────────

tahpBugAnalysisRoutes.get('/reports', async (ctx) => {
  ctx.body = { success: true, data: listBugReports() }
})

tahpBugAnalysisRoutes.get('/reports/:taskId/skill-snapshots/:skillName', async (ctx) => {
  const snap = readBugSkillSnapshot(ctx.params.taskId, ctx.params.skillName)
  if (!snap) {
    ctx.status = 404
    ctx.body = { success: false, error: `找不到 Skill 快照: ${ctx.params.skillName}` }
    return
  }
  ctx.body = { success: true, data: snap }
})

tahpBugAnalysisRoutes.get('/reports/:taskId', async (ctx) => {
  const r = readBugReport(ctx.params.taskId)
  if (!r) {
    ctx.status = 404
    ctx.body = { success: false, error: `找不到报告: ${ctx.params.taskId}` }
    return
  }
  ctx.body = { success: true, data: r }
})

tahpBugAnalysisRoutes.delete('/reports/:taskId', async (ctx) => {
  const r = await deleteBugReport(ctx.params.taskId)
  if (!r.ok) {
    ctx.status = 404
    ctx.body = { success: false, error: r.error }
    return
  }
  ctx.body = { success: true, data: { deleted: true, task_id: ctx.params.taskId } }
})

// 任务排查日志（文本）
tahpBugAnalysisRoutes.get('/logs/:taskId', async (ctx) => {
  const taskId = ctx.params.taskId
  try {
    const text = await readBugLog(taskId)
    ctx.body = { success: true, data: { task_id: taskId, content: text } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// 知识沉淀请求列表（用于后续二阶段实现 / 排查）
tahpBugAnalysisRoutes.get('/distill-queue', async (ctx) => {
  const arr = await listDistillRequests()
  ctx.body = { success: true, data: arr }
})

// 工具：解析输入 → JIRA Key（前端实时校验用）
tahpBugAnalysisRoutes.get('/parse-key', async (ctx) => {
  const input = typeof ctx.query.input === 'string' ? ctx.query.input : ''
  ctx.body = { success: true, data: { jira_key: parseIssueKey(input) } }
})
