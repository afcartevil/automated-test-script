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

export interface ChecklistScmpJsonlEvent {
  event?: string
  message?: string
  title?: string
  project?: string
  tos_version?: string
  sheet_name?: string
  index?: number
  total?: number
  sheet_count?: number
  path?: string
  ok?: boolean
  summary?: ChecklistScmpSummary
  error?: { message?: string } | string
  [key: string]: unknown
}
