/**
 * 代码拉取能力契约（可复用 ExternalCapability，后期可挂适配流水线）。
 */
import type { CapabilityStatus } from '../adapt-pipeline/types'
import type { FailedRepoItem } from './repo-sync-tmux'

export type { FailedRepoItem }

export interface CodePullInput {
  systemRepoInit: string
  vendorRepoInit: string
  /** 可选覆盖 mapped-root；默认 discover */
  mappedRoot?: string
}

export interface CodePullResult {
  mapped_root: string
  run_rel: string
  system_path_win: string
  system_path_linux: string
  vendor_path_win: string
  vendor_path_linux: string
  /** 兼容旧字段：指向 system */
  code_path_win?: string
  code_path_linux?: string
  duration_ms: number
  /** sync 失败时的仓库清单（任务仍算失败） */
  failed_repos?: FailedRepoItem[]
}

export type CodePullRunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface CodePullRunRecord {
  run_id: string
  /** 展示用短名（取自 system/vendor 目录名或时间戳） */
  project_name: string
  system_repo_init?: string
  vendor_repo_init?: string
  status: CodePullRunStatus
  phase?: string
  progress?: number
  message?: string
  error?: string
  mapped_root?: string
  system_path_win?: string
  system_path_linux?: string
  vendor_path_win?: string
  vendor_path_linux?: string
  /** 兼容旧 UI/摘要 */
  code_path_win?: string
  code_path_linux?: string
  capability_run_id?: string
  active_tmux_session?: string
  /** sync 失败仓库清单 */
  failed_repos?: FailedRepoItem[]
  log_tail: string[]
  created_at: string
  updated_at: string
  completed_at?: string
  duration_ms?: number
}

export interface CodePullRunSummary {
  run_id: string
  project_name: string
  status: CodePullRunStatus
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

export type { CapabilityStatus }
