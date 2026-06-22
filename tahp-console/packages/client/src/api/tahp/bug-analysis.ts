/**
 * TAHP — AI Bug 分析 API 客户端.
 *
 * 所有响应统一 ApiEnvelope，由 tahpRequest 解包.
 */
import { tahpGet, tahpPost, tahpDelete } from './client'

export interface JiraUserConfig {
  username: string
  password: string
}

function jiraHeaders(jiraConfig?: JiraUserConfig): Record<string, string> {
  if (!jiraConfig) return {}
  return {
    'x-tahp-jira-username': jiraConfig.username,
    'x-tahp-jira-password': jiraConfig.password,
  }
}

/**
 * 历史保留的模块类型：BFF 已不再据此进行任何路由 / 约束加载 / Skill 提示。
 * Agent 在最终报告里**可能**回填一个 module 字符串（也可能不填），仅作为展示标签。
 * 前端不再要求用户选择该字段。
 */
export type TahpBugModule = 'telephony' | 'kernel-driver' | 'power-mgmt' | 'shared'

export interface BugAnalysisStartResp {
  task_id: string
  jira_key?: string
  type: 'single' | 'continue'
  status: 'running'
  from_task_id?: string
}

export interface BugBatchStartResp {
  job_id: string
  type: 'batch'
  total: number
  tasks: Array<{ task_id: string; jira_key: string }>
}

export interface BugTask {
  task_id: string
  parent_job_id?: string
  jira_key: string
  jira_url: string
  module?: TahpBugModule         // 可选 · Agent 回填
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  progress?: number
  started_at: string
  completed_at?: string
  skills_used?: string[]
  title?: string
  error?: string
  user_description?: string
  extra_context?: string
  corrections?: string[]
  llm_response?: string
  issue?: JiraIssueDetail
}

export interface BugJob {
  job_id: string
  type: 'batch'
  jql?: string
  module?: TahpBugModule
  task_ids: string[]
  tasks?: BugTask[]
  started_at: string
  status: 'running' | 'completed' | 'failed'
  total: number
  completed: number
  failed: number
}

export interface JiraAttachment {
  id: string
  filename: string
  mimeType?: string
  size?: number
  url: string
  createdAt?: string
  author?: string
}

export interface JiraComment {
  id: string
  author?: string
  body: string
  createdAt?: string
}

export interface JiraIssueDetail {
  key: string
  url: string
  summary: string
  status?: string
  priority?: string
  severity?: string
  reporter?: string
  assignee?: string
  components?: string[]
  labels?: string[]
  fixVersions?: string[]
  affectedVersions?: string[]
  createdAt?: string
  updatedAt?: string
  description?: string
  attachments: JiraAttachment[]
  comments: JiraComment[]
}

export interface JiraSearchItem {
  key: string
  url: string
  summary: string
  status?: string
  priority?: string
  assignee?: string
  updatedAt?: string
}

export interface JqlPreview {
  total: number
  issues: JiraSearchItem[]
  jql: string
  truncated: boolean
}

export interface BugReport {
  task_id: string
  jira_key: string
  jira_url: string
  module?: TahpBugModule          // 可选 · Agent 回填
  title?: string
  status: 'completed' | 'failed'
  execution_mode?: 'agent' // 当前架构下分析任务恒为 agent；旧报告可能为 undefined
  agent_session_id?: string
  started_at: string
  completed_at?: string
  duration_ms?: number
  user_description?: string
  extra_context?: string
  corrections?: string[]
  skills_used?: string[]
  tool_call_count?: number
  llm_response?: string
  /** Step 5 八节报告正文（不含 Agent 过程输出） */
  report_body?: string
  error?: string
  jira?: Partial<JiraIssueDetail> & {
    commentCount?: number
    attachmentCount?: number
    fetch_ok?: string
    skill_used?: string
    fetchFailed?: boolean
    note?: string
  }
}

export interface BugReportSummary {
  task_id: string
  jira_key?: string
  jira_url?: string
  module?: string
  title?: string
  status?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
  skills_used?: string[]
  correction_of?: string
}

// ─── 启动接口 ─────────────────────────────────────────────────────────────

export function startSingle(payload: {
  input: string
  user_description?: string
  extra_context?: string
}, jiraConfig?: JiraUserConfig): Promise<BugAnalysisStartResp> {
  return tahpPost<BugAnalysisStartResp>('/api/tahp/bug-analysis/single', payload, { headers: jiraHeaders(jiraConfig) })
}

export function startBatch(payload: {
  jql: string
  extra_context?: string
}, jiraConfig?: JiraUserConfig): Promise<BugBatchStartResp> {
  return tahpPost<BugBatchStartResp>('/api/tahp/bug-analysis/batch', payload, { headers: jiraHeaders(jiraConfig) })
}

export function continueAnalysis(taskId: string, payload: {
  additional_info: string
}): Promise<BugAnalysisStartResp> {
  return tahpPost<BugAnalysisStartResp>(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/continue`, payload)
}

export function distillToKnowledge(taskId: string, note?: string): Promise<{ recorded: boolean; message: string }> {
  return tahpPost(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/distill`, { note })
}

// ─── JIRA 预览 ────────────────────────────────────────────────────────────

export function previewJira(input: string, jiraConfig?: JiraUserConfig): Promise<JiraIssueDetail> {
  return tahpGet<JiraIssueDetail>(`/api/tahp/bug-analysis/jira/${encodeURIComponent(input)}`, { headers: jiraHeaders(jiraConfig) })
}

export function previewJql(jql: string, jiraConfig?: JiraUserConfig): Promise<JqlPreview> {
  return tahpPost<JqlPreview>('/api/tahp/bug-analysis/jql-preview', { jql }, { headers: jiraHeaders(jiraConfig) })
}

export function parseJiraKey(input: string): Promise<{ jira_key: string | null }> {
  return tahpGet<{ jira_key: string | null }>(`/api/tahp/bug-analysis/parse-key?input=${encodeURIComponent(input)}`)
}

// ─── 任务 / Job 查询 ──────────────────────────────────────────────────────

export function listBugTasks(): Promise<BugTask[]> {
  return tahpGet<BugTask[]>('/api/tahp/bug-analysis/tasks')
}

export function getBugTask(taskId: string): Promise<BugTask> {
  return tahpGet<BugTask>(`/api/tahp/bug-analysis/tasks/${encodeURIComponent(taskId)}`)
}

export function listBugJobs(): Promise<BugJob[]> {
  return tahpGet<BugJob[]>('/api/tahp/bug-analysis/jobs')
}

export function getBugJob(jobId: string): Promise<BugJob> {
  return tahpGet<BugJob>(`/api/tahp/bug-analysis/jobs/${encodeURIComponent(jobId)}`)
}

// ─── 报告 / 日志 ──────────────────────────────────────────────────────────

export function listBugReports(): Promise<BugReportSummary[]> {
  return tahpGet<BugReportSummary[]>('/api/tahp/bug-analysis/reports')
}

export function getBugReport(taskId: string): Promise<BugReport> {
  return tahpGet<BugReport>(`/api/tahp/bug-analysis/reports/${encodeURIComponent(taskId)}`)
}

export function deleteBugReport(taskId: string): Promise<{ deleted: boolean; task_id: string }> {
  return tahpDelete<{ deleted: boolean; task_id: string }>(
    `/api/tahp/bug-analysis/reports/${encodeURIComponent(taskId)}`,
  )
}

export function getBugLog(taskId: string): Promise<{ task_id: string; content: string }> {
  return tahpGet<{ task_id: string; content: string }>(`/api/tahp/bug-analysis/logs/${encodeURIComponent(taskId)}`)
}

export function cancelBugTask(taskId: string): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running' }> {
  return tahpPost(`/api/tahp/bug-analysis/tasks/${encodeURIComponent(taskId)}/cancel`)
}
