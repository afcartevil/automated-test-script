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
  cancelBugTask,
  previewSingleIssue,
  listBugTasks,
  getBugTask,
  listBugJobs,
  getBugJob,
  listBugReports,
  readBugReport,
  deleteBugReport,
} from '../../services/tahp/bug-analysis'
import { searchJQL, parseIssueKey } from '../../services/tahp/jira'
import type { JiraConfig } from '../../services/tahp/jira'
import { readBugLog, recordDistillRequest, listDistillRequests } from '../../services/tahp/bug-analysis-logger'
import { depositDistilledEntry, type DepositDistilledResult } from './knowledge'
import { logger } from '../../services/logger'

export const tahpBugAnalysisRoutes = new Router({ prefix: '/api/tahp/bug-analysis' })

function readJiraConfigFromHeaders(ctx: any): JiraConfig | null {
  const username = String(ctx.headers['x-tahp-jira-username'] || '').trim()
  const password = String(ctx.headers['x-tahp-jira-password'] || '').trim()
  if (!username || !password) return null
  return {
    baseUrl: (process.env.TAHP_JIRA_BASE_URL || 'http://jira.transsion.com').replace(/\/+$/, ''),
    username,
    password,
  }
}

function requireJiraUserConfig(ctx: any): JiraConfig | null {
  const cfg = readJiraConfigFromHeaders(ctx)
  if (cfg) return cfg
  ctx.status = 400
  ctx.body = {
    success: false,
    error: '请先配置 JIRA 账号密码（TAHP_JIRA_USERNAME + TAHP_JIRA_PASSWORD）',
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
  const result = continueBugAnalysis(taskId, { additionalInfo })
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
    if (report.title) parts.push(`# ${report.title}`)
    if (report.jira_key) parts.push(`> JIRA: ${report.jira_key}`)
    if (report.report_body) parts.push(String(report.report_body))
    else if (report.llm_response) parts.push(String(report.llm_response))
    content = parts.join('\n\n').trim()
  }
  if (note) content += `\n\n---\n**人工补充**：${note}`

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
    title: t.issue?.summary,
    error: t.error,
  }))
  ctx.body = { success: true, data: tasks }
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
    llm_response: t.llmResponse,
    error: t.error,
    issue: t.issue,
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
