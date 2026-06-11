import { tahpGet } from './client'

export interface ReportEntry {
  type: 'file' | 'dir'
  name: string
  path: string
  size?: number
  mtime?: number
}

export function listReports(subPath = ''): Promise<ReportEntry[]> {
  const qs = subPath ? `?path=${encodeURIComponent(subPath)}` : ''
  return tahpGet<ReportEntry[]>(`/api/tahp/reports${qs}`)
}

export interface ReportContent { path: string; content: string }
export function readReport(subPath: string): Promise<ReportContent> {
  return tahpGet<ReportContent>(`/api/tahp/reports/content?path=${encodeURIComponent(subPath)}`)
}

// ── 任务报告相关 ──────────────────────────────────────────────────────────

export type AuditCheckStatus = 'pass' | 'fail' | 'warn' | 'na' | 'unknown'

export interface AuditCheckItem {
  key: string
  label: string
  status: AuditCheckStatus
  reason: string
}

export interface AdaptAgentSkillRef {
  skill_id: string
  path: string
  source?: 'configured' | 'read_file' | 'skill_view'
}

export interface AdaptAgentFileChange {
  path: string
  action: string
  tool: string
  at?: string
}

export interface TaskReportSummary {
  task_id: string
  module?: string
  domain?: string
  domain_label?: string
  report_type?: 'adapt_agent' | string
  started_at?: string
  completed_at?: string
  duration_ms?: number
  files_modified: number   // count
  mtime?: number
  path?: string
}

export interface TaskReportDetail {
  task_id: string
  report_type?: 'adapt_agent' | string
  module?: string
  domain?: string
  domain_id?: string
  domain_label?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
  status?: string
  extra_context?: string
  correction_of?: string
  document_content?: string
  files_modified?: string[]
  file_changes?: AdaptAgentFileChange[]
  skills_used?: AdaptAgentSkillRef[]
  related_skills?: string[]
  form_data?: Record<string, string>
  llm_response?: string
  audit_report?: string
  audit_skill?: string
  audit_summary?: AuditCheckItem[]
}

export function listTaskReports(): Promise<TaskReportSummary[]> {
  return tahpGet<TaskReportSummary[]>('/api/tahp/reports/tasks')
}

export function getTaskReport(taskId: string): Promise<TaskReportDetail> {
  return tahpGet<TaskReportDetail>(`/api/tahp/reports/task/${encodeURIComponent(taskId)}`)
}
