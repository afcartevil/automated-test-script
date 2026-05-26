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

export interface TaskReportSummary {
  task_id: string
  module?: string
  domain?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
  files_modified: number   // count
  mtime?: number
  path?: string
}

export interface TaskReportDetail {
  task_id: string
  module?: string
  domain?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
  extra_context?: string
  correction_of?: string
  document_content?: string
  files_modified?: string[]
  llm_response?: string
}

export function listTaskReports(): Promise<TaskReportSummary[]> {
  return tahpGet<TaskReportSummary[]>('/api/tahp/reports/tasks')
}

export function getTaskReport(taskId: string): Promise<TaskReportDetail> {
  return tahpGet<TaskReportDetail>(`/api/tahp/reports/task/${encodeURIComponent(taskId)}`)
}
