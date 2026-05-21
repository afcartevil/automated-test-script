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
