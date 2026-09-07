/**
 * TAHP — AI Bug 分析 API 客户端.
 *
 * 所有响应统一 ApiEnvelope，由 tahpRequest 解包.
 */
import { tahpGet, tahpPost, tahpPut, tahpDelete } from './client'

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

export type BugAnalysisMode = 'jira_single' | 'jira_batch' | 'local'

/** 「指定代码源」判型结果（后端 services/tahp/code-source.ts 判型后回显） */
export type CodeSourceKind = 'local_path' | 'opengrok_branch' | 'opengrok_url' | 'unknown'

export interface CodeSourceSnapshot {
  raw: string
  kind: CodeSourceKind
  path?: string
  exists?: boolean
  branch?: string
  file_path?: string
  start_line?: number
  branch_known?: boolean
}

export interface CodeSourceOptions {
  branches: string[]
  default_branch: string
}

export interface SkillImproveRecord {
  name: string
  actions: string[]
  snapshot_dir?: string
  snapshot_source?: 'runtime' | 'backfill'
}

export interface BugAnalysisStartResp {
  task_id: string
  jira_key?: string
  type: 'single' | 'continue' | 'local'
  analysis_mode?: BugAnalysisMode
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
  status: 'pending' | 'running' | 'waiting_user_input' | 'completed' | 'failed' | 'cancelled'
  analysis_mode?: BugAnalysisMode
  local_log_path?: string
  phase?: string
  progress?: number
  started_at: string
  completed_at?: string
  skills_used?: string[]
  skills_improved?: SkillImproveRecord[]
  title?: string
  error?: string
  user_description?: string
  extra_context?: string
  code_source?: CodeSourceSnapshot
  corrections?: string[]
  llm_response?: string
  issue?: JiraIssueDetail
  /** 分析完成后的 jira-dup-judge 置重状态 */
  dup_judge_status?: 'running' | 'completed' | 'failed'
}

export interface BugJob {
  job_id: string
  type: 'batch'
  jql?: string
  module?: TahpBugModule
  /** 续跑 / 重跑失败项时指向来源 job */
  resumed_from?: string
  task_ids: string[]
  tasks?: BugTask[]
  started_at: string
  /** interrupted：服务重启前没跑完的队列，可点「继续未完成」 */
  status: 'running' | 'completed' | 'failed' | 'interrupted'
  total: number
  completed: number
  failed: number
  /** 本批开启了「结论后回写备注并尝试置重」 */
  auto_post_comment_and_dup?: boolean
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
  /** Jira 命中数超过本次返回条数（被 cap 截断） */
  truncated: boolean
  /** 服务端全量枚举上限（TAHP_JQL_MAX_ISSUES） */
  cap?: number
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
  code_source?: CodeSourceSnapshot
  corrections?: string[]
  skills_used?: string[]
  skills_improved?: SkillImproveRecord[]
  tool_call_count?: number
  llm_response?: string
  /** Step 5 八节报告正文（不含 Agent 过程输出） */
  report_body?: string
  analysis_mode?: BugAnalysisMode
  local_log_path?: string
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
  skills_improved?: SkillImproveRecord[]
  correction_of?: string
}

// ─── 启动接口 ─────────────────────────────────────────────────────────────

export function startSingle(payload: {
  input: string
  user_description?: string
  extra_context?: string
  code_source?: string
}, jiraConfig?: JiraUserConfig): Promise<BugAnalysisStartResp> {
  return tahpPost<BugAnalysisStartResp>('/api/tahp/bug-analysis/single', payload, { headers: jiraHeaders(jiraConfig) })
}

export function startBatch(payload: {
  jql: string
  extra_context?: string
  code_source?: string
  auto_post_comment_and_dup?: boolean
}, jiraConfig?: JiraUserConfig): Promise<BugBatchStartResp> {
  return tahpPost<BugBatchStartResp>('/api/tahp/bug-analysis/batch', payload, { headers: jiraHeaders(jiraConfig) })
}

export function startLocal(payload: {
  log_path: string
  problem_description: string
  code_source?: string
}): Promise<BugAnalysisStartResp> {
  return tahpPost<BugAnalysisStartResp>('/api/tahp/bug-analysis/local', payload)
}

/** OpenGrok 分支清单（后端维护，前端只做下拉与提示） */
export function getCodeSourceOptions(): Promise<CodeSourceOptions> {
  return tahpGet<CodeSourceOptions>('/api/tahp/bug-analysis/code-source-options')
}

export function postJiraComment(
  taskId: string,
  comment: string,
  jiraConfig?: JiraUserConfig,
  opts?: { tryMarkDuplicate?: boolean },
): Promise<{ comment_id?: string; dup_judge_started?: boolean }> {
  return tahpPost(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/jira-comment`, {
    comment,
    try_mark_duplicate: opts?.tryMarkDuplicate === true,
  }, { headers: jiraHeaders(jiraConfig) })
}

export function continueAnalysis(taskId: string, payload: {
  additional_info: string
}): Promise<BugAnalysisStartResp> {
  return tahpPost<BugAnalysisStartResp>(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/continue`, payload)
}

export interface DistillResult {
  recorded: boolean
  deposited: boolean
  dedup_action?: 'created' | 'updated' | 'unchanged'
  entry: { id: string; module: string; func_type: string } | null
  message: string
}

export function distillToKnowledge(
  taskId: string,
  params?: { note?: string; content?: string; module?: string; category?: string; to_knowledge?: boolean },
): Promise<DistillResult> {
  return tahpPost(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/distill`, params || {})
}

// ─── JIRA 预览 ────────────────────────────────────────────────────────────

export interface JiraConfigVerifyResult {
  ok: boolean
  error?: string
  detail?: string
  user?: string
}

export interface JiraConfigStatus {
  configured: boolean
  connected: boolean
  detail?: string
  error?: string
  user?: string
}

/** 读取服务端已保存的 JIRA 配置状态（是否配置 + 是否连通） */
export function fetchJiraConfigStatus(): Promise<JiraConfigStatus> {
  return tahpGet<JiraConfigStatus>('/api/tahp/bug-analysis/jira-config/status')
}

export function verifyJiraUserConfig(jiraConfig?: JiraUserConfig): Promise<JiraConfigVerifyResult> {
  return tahpPost<JiraConfigVerifyResult>('/api/tahp/bug-analysis/jira-config/verify', {}, {
    headers: jiraConfig ? jiraHeaders(jiraConfig) : {},
  })
}

export function syncJiraUserConfig(jiraConfig: JiraUserConfig): Promise<{ username: string; updated_at?: string }> {
  return tahpPut('/api/tahp/bug-analysis/jira-user-config', jiraConfig)
}

export interface RemoteChannelStatus {
  enabled: boolean
  skill_id: string
  skill_path: string
  skill_found: boolean
}

export interface BugAnalysisChannelConfigResp {
  remote_channels: {
    bugfix_analysis: RemoteChannelStatus
    loginsight_remote: RemoteChannelStatus
  }
  updated_at?: string
}

/** 读取远程分析渠道开关（Bugfix / LogInsight） */
export function fetchChannelConfig(): Promise<BugAnalysisChannelConfigResp> {
  return tahpGet<BugAnalysisChannelConfigResp>('/api/tahp/bug-analysis/channel-config')
}

/** 保存远程分析渠道开关 */
export function saveChannelConfig(payload: {
  bugfix_analysis?: boolean
  loginsight_remote?: boolean
  bugfix_skill_path?: string
  loginsight_skill_path?: string
}): Promise<BugAnalysisChannelConfigResp> {
  return tahpPut<BugAnalysisChannelConfigResp>('/api/tahp/bug-analysis/channel-config', payload)
}

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

export interface BugTaskContinueStatus {
  can_continue: boolean
  reason?: string
  agent_session_id?: string
}

export function getBugTaskContinueStatus(taskId: string): Promise<BugTaskContinueStatus> {
  return tahpGet<BugTaskContinueStatus>(`/api/tahp/bug-analysis/tasks/${encodeURIComponent(taskId)}/continue-status`)
}

export function listBugJobs(): Promise<BugJob[]> {
  return tahpGet<BugJob[]>('/api/tahp/bug-analysis/jobs')
}

export function getBugJob(jobId: string): Promise<BugJob> {
  return tahpGet<BugJob>(`/api/tahp/bug-analysis/jobs/${encodeURIComponent(jobId)}`)
}

/** 续跑：把队列里未完成的单子重新入队为新 job */
export function resumeBugJob(jobId: string): Promise<BugBatchStartResp & { resumed_from: string }> {
  return tahpPost(`/api/tahp/bug-analysis/jobs/${encodeURIComponent(jobId)}/resume`)
}

/** 重跑失败项：把队列里 failed 的单子重新入队为新 job */
export function retryFailedBugJob(jobId: string): Promise<BugBatchStartResp & { resumed_from: string }> {
  return tahpPost(`/api/tahp/bug-analysis/jobs/${encodeURIComponent(jobId)}/retry-failed`)
}

// ─── 报告 / 日志 ──────────────────────────────────────────────────────────

export function listBugReports(): Promise<BugReportSummary[]> {
  return tahpGet<BugReportSummary[]>('/api/tahp/bug-analysis/reports')
}

export function getBugReport(taskId: string): Promise<BugReport> {
  return tahpGet<BugReport>(`/api/tahp/bug-analysis/reports/${encodeURIComponent(taskId)}`)
}

export interface BugSkillSnapshot {
  skill: string
  skill_md: string
  truncated: boolean
  snapshot_source: 'runtime' | 'backfill'
  snapshot_at: string
  files: string[]
}

export function getBugSkillSnapshot(taskId: string, skillName: string): Promise<BugSkillSnapshot> {
  return tahpGet<BugSkillSnapshot>(
    `/api/tahp/bug-analysis/reports/${encodeURIComponent(taskId)}/skill-snapshots/${encodeURIComponent(skillName)}`,
  )
}

export function deleteBugReport(taskId: string): Promise<{ deleted: boolean; task_id: string }> {
  return tahpDelete<{ deleted: boolean; task_id: string }>(
    `/api/tahp/bug-analysis/reports/${encodeURIComponent(taskId)}`,
  )
}

export function getBugLog(taskId: string): Promise<{ task_id: string; content: string }> {
  return tahpGet<{ task_id: string; content: string }>(`/api/tahp/bug-analysis/logs/${encodeURIComponent(taskId)}`)
}

export function cancelBugTask(taskId: string): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running' | 'interrupted_dup_judge' }> {
  return tahpPost(`/api/tahp/bug-analysis/tasks/${encodeURIComponent(taskId)}/cancel`)
}

export function respondBugApproval(
  taskId: string,
  payload: { approval_id: string; choice: string },
): Promise<{ approval_id: string; choice: string }> {
  return tahpPost(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/approval`, payload)
}

export function submitBugUserInput(
  taskId: string,
  payload: { request_id: string; values: Record<string, string> },
): Promise<{ request_id: string }> {
  return tahpPost(`/api/tahp/bug-analysis/${encodeURIComponent(taskId)}/user-input`, payload)
}
