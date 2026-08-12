/**
 * 代码拉取 API
 */
import { tahpGet, tahpPost } from './client'

export interface CodePullRunSummary {
  run_id: string
  project_name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  progress?: number
  message?: string
  system_path_win?: string
  vendor_path_win?: string
  code_path_win?: string
  code_path_linux?: string
  created_at: string
  updated_at: string
  completed_at?: string
}

export interface FailedRepoItem {
  project: string
  reason: string
  kind: 'fetch' | 'checkout' | 'other'
  scope?: string
}

export interface CodePullRunDetail extends CodePullRunSummary {
  error?: string
  mapped_root?: string
  system_repo_init?: string
  vendor_repo_init?: string
  system_path_linux?: string
  vendor_path_linux?: string
  capability_run_id?: string
  failed_repos?: FailedRepoItem[]
  log_tail: string[]
  duration_ms?: number
}

export function probeCodePull(): Promise<{ available: boolean; reason?: string }> {
  return tahpGet('/api/tahp/code-pull/probe')
}

export function startCodePull(input: {
  system_repo_init: string
  vendor_repo_init: string
  mapped_root?: string
}): Promise<{ run_id: string }> {
  return tahpPost('/api/tahp/code-pull/runs', input)
}

export function getCodePullRun(runId: string): Promise<CodePullRunDetail> {
  return tahpGet(`/api/tahp/code-pull/runs/${encodeURIComponent(runId)}`)
}

export function listCodePullRuns(limit = 30): Promise<CodePullRunSummary[]> {
  return tahpGet(`/api/tahp/code-pull/runs?limit=${limit}`)
}

export function cancelCodePull(runId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/code-pull/runs/${encodeURIComponent(runId)}/cancel`)
}
