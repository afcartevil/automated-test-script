import { getBaseUrlValue } from '../client'
import { tahpGet, tahpPost } from './client'

export type ModemBaselineConfig = {
  NODE_BRANCH: string
  target_BRANCH: string
  AP_lable: string
  DESCRIPTION?: string
  JIRAID: string
  work_dir: string
  mapped_prefix?: string
  remote_prefix?: string
}

export type ModemBaselineStatus = 'running' | 'success' | 'failed' | 'conflict'
export type ModemBaselinePhase = 'precheck' | 'merge' | 'conflict' | 'resume' | 'archive'

export type ModemBaselineRunMeta = {
  runId: string
  status: ModemBaselineStatus
  mode: 'stop_after_merge'
  phase?: ModemBaselinePhase
  createdAt: string
  startedAt?: string
  finishedAt?: string
  config: ModemBaselineConfig
  remoteWorkDir?: string
  logPath?: string
  reportPath?: string
  conflictFiles?: string[]
  error?: string
}

export function getModemBaselineDefaults(): Promise<{ toolRoot: string; config: ModemBaselineConfig }> {
  return tahpGet<{ toolRoot: string; config: ModemBaselineConfig }>('/api/tahp/modem-baseline/defaults')
}

export function listModemBaselineRuns(): Promise<ModemBaselineRunMeta[]> {
  return tahpGet<ModemBaselineRunMeta[]>('/api/tahp/modem-baseline/runs')
}

export function getModemBaselineRun(runId: string): Promise<ModemBaselineRunMeta> {
  return tahpGet<ModemBaselineRunMeta>(`/api/tahp/modem-baseline/runs/${encodeURIComponent(runId)}`)
}

export function getModemBaselineLog(runId: string): Promise<{ content: string }> {
  return tahpGet<{ content: string }>(`/api/tahp/modem-baseline/runs/${encodeURIComponent(runId)}/log`)
}

export function createModemBaselineRun(config: ModemBaselineConfig): Promise<{ runId: string; status: ModemBaselineStatus }> {
  return tahpPost<{ runId: string; status: ModemBaselineStatus }>('/api/tahp/modem-baseline/runs', { config })
}

export function continueModemBaselineRun(runId: string): Promise<{ runId: string; status: ModemBaselineStatus }> {
  return tahpPost<{ runId: string; status: ModemBaselineStatus }>(
    `/api/tahp/modem-baseline/runs/${encodeURIComponent(runId)}/continue`,
  )
}

export function refreshModemBaselineConflicts(runId: string, autoStageResolved = true): Promise<{ files: string[]; staged: number }> {
  return tahpPost<{ files: string[]; staged: number }>(
    `/api/tahp/modem-baseline/runs/${encodeURIComponent(runId)}/refresh-conflicts`,
    { autoStageResolved },
  )
}

export function openModemBaselineConflictFile(runId: string, file: string): Promise<{ success: true }> {
  return tahpPost<{ success: true }>(
    `/api/tahp/modem-baseline/runs/${encodeURIComponent(runId)}/open-conflict-file`,
    { file },
  )
}

export function subscribeModemBaselineEvents(runId: string): EventSource {
  const base = getBaseUrlValue()
  return new EventSource(`${base}/api/tahp/modem-baseline/runs/${encodeURIComponent(runId)}/events`)
}
