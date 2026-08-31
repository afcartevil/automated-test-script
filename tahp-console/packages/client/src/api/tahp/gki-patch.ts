import { tahpGet, tahpPost } from './client'

export interface GkiPatchStatus {
  toolRoot: string
  dataDir: string
  port: number
  appUrl: string
  appBaseUrl: string
  dbPath: string
  seedDbPath: string
  running: boolean
  /** 后台正在拉起（进页时应继续等待，而不是报未启动） */
  starting?: boolean
  frontendBuilt: boolean
  settingsPath: string
  integrated?: boolean
  autoStart?: boolean
  llmManagedByEa?: boolean
  llmModel?: string
  llmApiBase?: string
  sshManagedByEa?: boolean
  sshTargetIp?: string
  sshBastionUser?: string
}

export function fetchGkiPatchStatus() {
  return tahpGet<GkiPatchStatus>('/api/tahp/gki-patch/status')
}

export function startGkiPatchServer() {
  return tahpPost<GkiPatchStatus>('/api/tahp/gki-patch/start')
}

export type GkiUpgradeJobSummary = {
  id: string | number
  status: string
  from_tag?: string
  to_tag?: string
  phase?: string
  build_exit_code?: number
  created_at?: string
  completed_at?: string
}

export type GkiAnalysisTaskSummary = {
  id: string
  type?: string
  status?: string
  from_tag?: string
  to_tag?: string
  sha?: string
  created_at?: string
  repo?: string
}

export function listGkiUpgradeJobs(limit = 50): Promise<{ jobs: GkiUpgradeJobSummary[] }> {
  const query = new URLSearchParams({ limit: String(limit) })
  return tahpGet<{ jobs: GkiUpgradeJobSummary[] }>(`/api/tahp/gki-patch/upgrade-jobs?${query.toString()}`)
}

export function listGkiAnalysisTasks(limit = 50): Promise<{ tasks: GkiAnalysisTaskSummary[] }> {
  const query = new URLSearchParams({ limit: String(limit) })
  return tahpGet<{ tasks: GkiAnalysisTaskSummary[] }>(`/api/tahp/gki-patch/analysis-tasks?${query.toString()}`)
}
