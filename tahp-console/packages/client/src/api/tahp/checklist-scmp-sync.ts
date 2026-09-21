/**
 * 飞书 checklist × SCMP 市场支持回写 API
 */
import { tahpGet, tahpPost } from './client'

export type ChecklistScmpStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface ChecklistScmpSummary {
  sheet_count: number
  feature_count: number
  supported: number
  unsupported: number
  partial: number
  missing: number
  failed_sheets: string[]
}

export interface ChecklistScmpRun {
  run_id: string
  url: string
  status: ChecklistScmpStatus
  progress: number
  phase: string
  message: string
  title?: string
  project?: string
  tos_version?: string
  sheet_index?: number
  sheet_total?: number
  current_sheet?: string
  log_tail: string[]
  summary?: ChecklistScmpSummary
  error?: string
  log_file?: string
  created_at: string
  updated_at: string
  completed_at?: string
  exit_code?: number | null
}

export interface ChecklistScmpProbeResult {
  available: boolean
  reason?: string
  python?: string
  cli_root?: string
  tones_cli?: string | null
}

export function probeChecklistScmp(): Promise<ChecklistScmpProbeResult> {
  return tahpGet('/api/tahp/checklist-scmp-sync/probe')
}

export function startChecklistScmpSync(url: string): Promise<{ run_id: string }> {
  return tahpPost('/api/tahp/checklist-scmp-sync/runs', { url })
}

export function getChecklistScmpRun(runId: string): Promise<ChecklistScmpRun> {
  return tahpGet(`/api/tahp/checklist-scmp-sync/runs/${encodeURIComponent(runId)}`)
}

export function listChecklistScmpRuns(limit = 20): Promise<{
  active: ChecklistScmpRun | null
  items: ChecklistScmpRun[]
}> {
  return tahpGet(`/api/tahp/checklist-scmp-sync/runs?limit=${limit}`)
}

export function cancelChecklistScmpSync(runId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/checklist-scmp-sync/runs/${encodeURIComponent(runId)}/cancel`)
}
