/**
 * 射频校准 MetaCLI API
 */
import { tahpGet, tahpPost } from './client'

export type RfCalibMetaMode = 'backup' | 'restore'

export type RfCalibMetaConnectionStrategy =
  | 'preloader_boot'
  | 'meta_port'
  | 'adb_reboot_meta'

export interface RfCalibMetaRunSummary {
  run_id: string
  label: string
  mode: RfCalibMetaMode
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  progress?: number
  message?: string
  cal_file_path?: string
  items_ini_path?: string
  output_cal_path?: string
  created_at: string
  updated_at: string
  completed_at?: string
}

export interface RfCalibMetaRunDetail extends RfCalibMetaRunSummary {
  error?: string
  meta_root?: string
  init_file_path?: string
  com_port?: string
  log_tail: string[]
  duration_ms?: number
  exit_code?: number | null
}

export interface RfCalibMetaProbeResult {
  available: boolean
  reason?: string
  needs_config?: boolean
  meta_root?: string
  meta_cli?: string
  platform?: string
  adb_devices?: string[]
  mtk_com_ports?: Array<{ port: string; name: string }>
  suggested_com_port?: string
  suggested_items_ini?: string
  connection_hint?: string
}

export function probeRfCalibMeta(): Promise<RfCalibMetaProbeResult> {
  return tahpGet('/api/tahp/rf-calib-meta/probe')
}

export function startRfCalibMeta(input: {
  mode: RfCalibMetaMode
  cal_file_path?: string
  items_ini_path: string
  output_cal_path?: string
  com_port?: string
  label?: string
  connection_strategy?: RfCalibMetaConnectionStrategy
}): Promise<{ run_id: string }> {
  return tahpPost('/api/tahp/rf-calib-meta/runs', input)
}

export function getRfCalibMetaRun(runId: string): Promise<RfCalibMetaRunDetail> {
  return tahpGet(`/api/tahp/rf-calib-meta/runs/${encodeURIComponent(runId)}`)
}

export function listRfCalibMetaRuns(limit = 30): Promise<RfCalibMetaRunSummary[]> {
  return tahpGet(`/api/tahp/rf-calib-meta/runs?limit=${limit}`)
}

export function cancelRfCalibMeta(runId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/rf-calib-meta/runs/${encodeURIComponent(runId)}/cancel`)
}

export interface PickCalFileResult {
  canceled: boolean
  path?: string
  error?: string
}

export function pickRfCalibCalFile(): Promise<PickCalFileResult> {
  return tahpPost<PickCalFileResult>('/api/tahp/rf-calib-meta/pick-cal-file', {})
}
