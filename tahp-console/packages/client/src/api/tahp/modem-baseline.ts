import { getBaseUrlValue } from '../client'
import { tahpDelete, tahpGet, tahpPost, tahpPut } from './client'

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

export type UserWorkspaceProfile = {
  owner: string
  mappedPrefix: string
  remotePrefix: string
  roots: string[]
  updatedAt: string
}

export type RepoProfile = {
  repoId: string
  owner: string
  label: string
  localPath: string
  mappedPrefix: string
  remotePrefix: string
  projectName?: string
  platform?: string
  vendor?: string
  defaultNodeBranch?: string
  defaultTargets?: string[]
  recentBranches?: string[]
  lastUsedAt?: string
  branchTemplateStatus?: 'idle' | 'running' | 'success' | 'failed'
  branchTemplateError?: string
  branchTemplateUpdatedAt?: string
  branches?: {
    trunk?: { nodeBranch: string; trunkBranch: string }
    mp?: Array<{ tos: string; mpNodeBranch: string; mpBranch: string }>
  }
}

export type ScannedRepoCandidate = {
  localPath: string
  repoName: string
  isGitRepo: boolean
}

export type PrecheckItem = {
  key: string
  level: 'ok' | 'warn' | 'error'
  title: string
  detail: string
}

export type PrecheckResult = {
  canStart: boolean
  items: PrecheckItem[]
}

export type ModemPatchOperationType = 'baseline_upgrade' | 'patch' | 'unknown'

export type BranchRule = {
  ruleId: string
  enabled: boolean
  label: string
  operationType?: ModemPatchOperationType
  platform?: string
  vendor?: string
  nodePattern: string
  trunkPattern: string
  mpPattern?: string
  defaultTarget?: 'trunk' | 'mp'
  updatedAt: string
}

export type BranchTemplate = {
  templateId: string
  owner: string
  tos: string
  platform: string
  nodeBranch: string
  trunkBranch: string
  mpBranch: string
  mpNodeBranch: string
  sourceFile?: string
  sourceSheet?: string
  updatedAt: string
}

export type NoticeParseResult = {
  rawText: string
  operationType: ModemPatchOperationType
  platform?: string
  tosVersion?: string
  targetMode?: 'trunk' | 'mp'
  version?: string
  confidence: number
  candidates: { platforms: string[] }
  warnings: string[]
}

export type RecommendationResult = {
  nodeBranch?: string
  targetBranch?: string
  apLabel?: string
  ruleId?: string
  branchSource?: 'template' | 'rule'
  targetMode?: 'trunk' | 'mp'
  warnings: string[]
}

export function getModemBaselineDefaults(): Promise<{ toolRoot: string; config: ModemBaselineConfig }> {
  return tahpGet<{ toolRoot: string; config: ModemBaselineConfig }>('/api/tahp/modem-baseline/defaults')
}

export function getWorkspaceProfile(): Promise<UserWorkspaceProfile | null> {
  return tahpGet<UserWorkspaceProfile | null>('/api/tahp/modem-baseline/workspace-profile')
}

export function saveWorkspaceProfile(input: {
  mappedPrefix: string
  remotePrefix: string
  roots: string[]
}): Promise<UserWorkspaceProfile> {
  return tahpPut<UserWorkspaceProfile>('/api/tahp/modem-baseline/workspace-profile', input)
}

export function listRepoProfiles(): Promise<{ items: RepoProfile[] }> {
  return tahpGet<{ items: RepoProfile[] }>('/api/tahp/modem-baseline/repos')
}

export function createRepoProfile(input: {
  label: string
  localPath: string
  projectName?: string
  platform?: string
  vendor?: string
}): Promise<RepoProfile> {
  return tahpPost<RepoProfile>('/api/tahp/modem-baseline/repos', input)
}

export function updateRepoProfile(
  repoId: string,
  input: {
    label: string
    localPath: string
    platform: string
    branches?: RepoProfile['branches']
  },
): Promise<RepoProfile> {
  return tahpPut<RepoProfile>(`/api/tahp/modem-baseline/repos/${encodeURIComponent(repoId)}`, input)
}

export function deleteRepoProfile(repoId: string): Promise<{ success: true }> {
  return tahpDelete<{ success: true }>(`/api/tahp/modem-baseline/repos/${encodeURIComponent(repoId)}`)
}

export function refreshRepoBranches(repoId: string): Promise<RepoProfile | null> {
  return tahpPost<RepoProfile | null>(`/api/tahp/modem-baseline/repos/${encodeURIComponent(repoId)}/refresh-branches`, {})
}

export function scanRepoProfiles(root: string): Promise<{ root: string; items: ScannedRepoCandidate[]; warnings: string[] }> {
  return tahpPost<{ root: string; items: ScannedRepoCandidate[]; warnings: string[] }>(
    '/api/tahp/modem-baseline/repos/scan',
    { root },
  )
}

export function precheckModemBaseline(
  config: ModemBaselineConfig,
  repoId?: string,
): Promise<PrecheckResult> {
  return tahpPost<PrecheckResult>('/api/tahp/modem-baseline/precheck', { config, repoId })
}

export function listModemPatchRules(): Promise<{ items: BranchRule[] }> {
  return tahpGet<{ items: BranchRule[] }>('/api/tahp/modem-baseline/rules')
}

export function listBranchTemplates(): Promise<{ items: BranchTemplate[] }> {
  return tahpGet<{ items: BranchTemplate[] }>('/api/tahp/modem-baseline/branch-templates')
}

export function importBranchTemplates(filePath: string): Promise<{ sourcePath: string; items: BranchTemplate[] }> {
  return tahpPost<{ sourcePath: string; items: BranchTemplate[] }>(
    '/api/tahp/modem-baseline/branch-templates/import',
    { filePath },
  )
}

export function createModemPatchRule(input: Partial<BranchRule>): Promise<BranchRule> {
  return tahpPost<BranchRule>('/api/tahp/modem-baseline/rules', input)
}

export function updateModemPatchRule(ruleId: string, input: Partial<BranchRule>): Promise<BranchRule> {
  return tahpPut<BranchRule>(`/api/tahp/modem-baseline/rules/${encodeURIComponent(ruleId)}`, input)
}

export function deleteModemPatchRule(ruleId: string): Promise<{ success: true }> {
  return tahpDelete<{ success: true }>(`/api/tahp/modem-baseline/rules/${encodeURIComponent(ruleId)}`)
}

export function parseModemPatchNotice(text: string): Promise<NoticeParseResult> {
  return tahpPost<NoticeParseResult>('/api/tahp/modem-baseline/parse-notice', { text })
}

export function recommendModemPatch(input: {
  noticeText?: string
  repoId?: string
  config: ModemBaselineConfig
}): Promise<RecommendationResult> {
  return tahpPost<RecommendationResult>('/api/tahp/modem-baseline/recommend', input)
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
