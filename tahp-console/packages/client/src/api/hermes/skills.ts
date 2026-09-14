import { request } from '../client'

export type SkillSource = 'builtin' | 'hub' | 'local' | 'tahp'

export interface SkillInfo {
  name: string
  description: string
  group?: string        // 业务模块（内核/驱动/通信/功耗）
  funcType?: string     // 功能类型（AI故障分析/AI自动化适配/AI自检工具）
  version?: string      // 版本号（来自 frontmatter）
  updatedAt?: number    // 最后更新时间戳（ms），用于“最近更新”排序
  enabled?: boolean
  source?: SkillSource
  modified?: boolean
  patchCount?: number
  useCount?: number
  viewCount?: number
  pinned?: boolean
  status?: string       // 'active' | 'deprecated' | 'archived'
}

export interface SkillCategory {
  name: string
  description: string
  skills: SkillInfo[]
}

export interface SkillListResponse {
  categories: SkillCategory[]
  archived: SkillInfo[]
}

export interface SkillFileEntry {
  path: string
  name: string
  isDir: boolean
}

export interface MemoryData {
  memory: string
  user: string
  soul: string
  memory_mtime: number | null
  user_mtime: number | null
  soul_mtime: number | null
}

export interface SkillsData {
  categories: SkillCategory[]
  archived: SkillInfo[]
}

export interface SkillUsageRow {
  skill: string
  view_count: number
  manage_count: number
  total_count: number
  percentage: number
  last_used_at: number | null
}

export interface SkillUsageDailySkillRow {
  skill: string
  view_count: number
  manage_count: number
  total_count: number
}

export interface SkillUsageDailyRow {
  date: string
  view_count: number
  manage_count: number
  total_count: number
  skills: SkillUsageDailySkillRow[]
}

export interface SkillUsageStats {
  period_days: number
  summary: {
    total_skill_loads: number
    total_skill_edits: number
    total_skill_actions: number
    distinct_skills_used: number
  }
  by_day: SkillUsageDailyRow[]
  top_skills: SkillUsageRow[]
}

export async function fetchSkills(): Promise<SkillsData> {
  const res = await request<SkillListResponse>('/api/hermes/skills')
  return { categories: res.categories, archived: res.archived ?? [] }
}

export type ImprovedSkillStatus = 'agent_only' | 'promoted' | 'at_risk'
export type ImprovedOverwriteRisk = 'none' | 'will_be_overwritten'

export interface ImprovedSkill {
  name: string
  profile_rel_path: string | null
  profile_abs_path: string | null
  actions: string[]
  first_seen_at: string
  last_updated_at: string
  task_ids: string[]
  files: { path: string; sha256: string }[]
  exists_on_disk: boolean
  in_repo: boolean
  overwrite_risk: ImprovedOverwriteRisk
  status: ImprovedSkillStatus
}

export async function fetchImprovedSkills(): Promise<ImprovedSkill[]> {
  const res = await request<{ skills: ImprovedSkill[] }>('/api/hermes/skills/improved')
  return res.skills ?? []
}

export async function removeImprovedProfileCopy(name: string): Promise<{ removed: string }> {
  return request<{ removed: string }>(`/api/hermes/skills/improved/${encodeURIComponent(name)}/remove-profile-copy`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export async function fetchSkillUsageStats(days = 7): Promise<SkillUsageStats> {
  const params = new URLSearchParams({ days: String(days) })
  return request<SkillUsageStats>(`/api/hermes/skills/usage/stats?${params}`)
}

export async function fetchSkillContent(skillPath: string): Promise<string> {
  const res = await request<{ content: string }>(`/api/hermes/skills/${skillPath}`)
  return res.content
}

export async function fetchSkillFiles(category: string, skill: string): Promise<SkillFileEntry[]> {
  const res = await request<{ files: SkillFileEntry[] }>(`/api/hermes/skills/${category}/${skill}/files`)
  return res.files
}

export async function fetchMemory(): Promise<MemoryData> {
  return request<MemoryData>('/api/hermes/memory')
}

export async function saveMemory(section: 'memory' | 'user' | 'soul', content: string): Promise<void> {
  await request('/api/hermes/memory', {
    method: 'POST',
    body: JSON.stringify({ section, content }),
  })
}

export async function toggleSkill(name: string, enabled: boolean): Promise<void> {
  await request('/api/hermes/skills/toggle', {
    method: 'PUT',
    body: JSON.stringify({ name, enabled }),
  })
}

export async function pinSkillApi(name: string, pinned: boolean): Promise<void> {
  await request('/api/hermes/skills/pin', {
    method: 'PUT',
    body: JSON.stringify({ name, pinned }),
  })
}

// ── ZIP 批量导入 ──────────────────────────────────────────────────────────────

export interface SkillPreviewItem {
  name: string
  description: string
  zipPrefix: string
  exists: boolean
}

export interface PreviewImportResult {
  skills: SkillPreviewItem[]
}

export interface ImportSkillsResult {
  imported: string[]
  skipped: string[]
  errors: { name: string; error: string }[]
}

/** 将 File 对象读取为 base64 字符串 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // data:application/zip;base64,<data> — 去掉前缀
      const base64 = result.includes(',') ? result.split(',')[1] : result
      resolve(base64)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/** 预览 ZIP 中包含的 skill 列表（不写磁盘） */
export async function previewImport(zipData: string, zipFilename: string): Promise<PreviewImportResult> {
  return request<PreviewImportResult>('/api/hermes/skills/preview-import', {
    method: 'POST',
    body: JSON.stringify({ zipData, zipFilename }),
  })
}

/** 执行导入（写磁盘），overwrite=true 时覆盖已存在的 skill */
export async function importSkills(
  zipData: string,
  zipFilename: string,
  overwrite: boolean,
): Promise<ImportSkillsResult> {
  return request<ImportSkillsResult>('/api/hermes/skills/import', {
    method: 'POST',
    body: JSON.stringify({ zipData, zipFilename, overwrite }),
  })
}

// ── 本地路径扫描导入 ──────────────────────────────────────────────────────────

export interface PathScanItem {
  name: string
  description: string
  sourcePath: string
  category: string   // 相对于扫描根的父路径，空=根级别
  exists: boolean
}

export interface PathScanResult {
  skills: PathScanItem[]
  message?: string
}

/** 扫描本地目录，返回检测到的技能列表（不写磁盘） */
export async function scanPath(sourcePath: string): Promise<PathScanResult> {
  return request<PathScanResult>('/api/hermes/skills/scan-path', {
    method: 'POST',
    body: JSON.stringify({ sourcePath }),
  })
}

/** 从本地路径导入技能（服务器直接拷贝目录，无需传输文件内容） */
export async function importFromPath(
  skills: { name: string; sourcePath: string; category?: string }[],
  overwrite: boolean,
): Promise<ImportSkillsResult> {
  return request<ImportSkillsResult>('/api/hermes/skills/import-from-path', {
    method: 'POST',
    body: JSON.stringify({ skills, overwrite }),
  })
}

export interface BackfillResult {
  updated: string[]
  alreadyOk: number
  unknown: string[]
  message: string
}

/** 一键回填所有已导入 skill 的 funcType / category 字段 */
export async function backfillCategories(): Promise<BackfillResult> {
  return request<BackfillResult>('/api/hermes/skills/backfill-categories', {
    method: 'POST',
  })
}

// ── 变更历史 ──────────────────────────────────────────────────────────────────

export interface SkillCommit {
  hash: string
  shortHash: string
  date: string     // ISO 8601
  author: string
  message: string
}

export interface SkillHistoryResult {
  commits: SkillCommit[]
  message?: string
}

export interface SkillCommitDetail {
  hash: string
  date: string
  author: string
  message: string
  body: string
  diff: string
}

export async function fetchSkillHistory(category: string, skill: string): Promise<SkillHistoryResult> {
  return request<SkillHistoryResult>(`/api/hermes/skills/${category}/${skill}/history`)
}

export async function fetchSkillCommitDetail(category: string, skill: string, hash: string): Promise<SkillCommitDetail> {
  return request<SkillCommitDetail>(`/api/hermes/skills/${category}/${skill}/history/${hash}`)
}

// ── Skill 同步中心（Phase 1）────────────────────────────────────────────────

export type SkillSyncStateName =
  | 'synced'
  | 'behind'
  | 'ahead'
  | 'local_only'
  | 'unknown'
  | 'submitted_pending'
  | 'delete_pending'
  | 'rejected'

export interface SkillSyncStatusItem {
  id: string
  state: SkillSyncStateName
  central_hash?: string
  local_hash?: string
  updated_at?: string
  bundle_ids: string[]
  name?: string
  func_type?: string
  module?: string
  submit_id?: string
  reject_reason?: string
}

export interface SkillSyncGroup {
  id: string
  label: string
  behind_count: number
  skill_ids: string[]
}

export interface SkillSyncStatus {
  configured: boolean
  central_url: string | null
  connected: boolean
  last_pulled_at: string | null
  behind_count: number
  ahead_count?: number
  pending_count?: number
  delete_pending_count?: number
  rejected_count?: number
  skills: SkillSyncStatusItem[]
  groups: SkillSyncGroup[]
  error?: string
}

export interface SkillSyncResult {
  pull: {
    entries: number
    skills: number
    configs: number
    generated_at: string
    skill_ids: string[]
    skipped_synced?: string[]
    skipped_dirty?: string[]
    failed?: Array<{ id: string; error: string }>
    reinjected: string[]
    reinject_error?: string
    requirements_changed?: string[]
  } | null
  reinjected: string[]
  reinject_error?: string
  requirements_changed?: string[]
  status: {
    behind_count: number
    ahead_count?: number
    last_pulled_at: string | null
    connected: boolean
    configured: boolean
  }
}

export interface SkillReinjectResult {
  sourceDir: string
  targetDir: string
  injected: string[]
  updated: string[]
  skipped: string[]
}

export async function fetchSyncStatus(opts?: {
  force?: boolean
  cachedOnly?: boolean
}): Promise<SkillSyncStatus | null> {
  const { tahpGet } = await import('../tahp/client')
  const qs = new URLSearchParams()
  if (opts?.force) qs.set('refresh', '1')
  if (opts?.cachedOnly) qs.set('cached', '1')
  const suffix = qs.toString() ? `?${qs}` : ''
  return tahpGet<SkillSyncStatus | null>(`/api/tahp/skills/sync-status${suffix}`)
}

export async function triggerSync(
  skillIds?: string[],
  opts?: { bundle_id?: string; force?: boolean },
): Promise<SkillSyncResult> {
  const { tahpPost } = await import('../tahp/client')
  const body: { skill_ids?: string[]; bundle_id?: string; force?: boolean } = {}
  if (skillIds?.length) body.skill_ids = skillIds
  if (opts?.bundle_id) body.bundle_id = opts.bundle_id
  if (opts?.force) body.force = true
  return tahpPost<SkillSyncResult>('/api/tahp/skills/sync', Object.keys(body).length ? body : {})
}

export async function reinjectSkills(skillIds?: string[]): Promise<SkillReinjectResult> {
  const { tahpPost } = await import('../tahp/client')
  return tahpPost<SkillReinjectResult>(
    '/api/tahp/skills/reinject',
    skillIds?.length ? { skill_ids: skillIds } : {},
  )
}

export async function publishSkillPackage(skillId: string): Promise<{
  id: string
  hash: string
  file_count: number
  submit_id?: string
  status?: string
}> {
  const { tahpPost } = await import('../tahp/client')
  return tahpPost('/api/tahp/skills/publish-package', { skill_id: skillId })
}

export interface PublishPackagesResult {
  total: number
  ok_count: number
  failed_count: number
  ok: Array<{ id: string; hash: string; file_count: number; submit_id?: string; status?: string }>
  failed: Array<{ id: string; error: string }>
}

export async function publishSkillPackages(skillIds: string[]): Promise<PublishPackagesResult> {
  const { tahpPost } = await import('../tahp/client')
  return tahpPost('/api/tahp/skills/publish-packages', { skill_ids: skillIds })
}

export interface SkillHistoryCommit {
  sha: string
  short_sha: string
  title: string
  author_name: string
  author_email: string
  committed_at: string
  message: string
  web_url?: string
}

/** Phase 3：中心 Git 发布历史（与库浏览本地 hermes history 区分） */
export async function fetchSkillPackageHistory(skillId: string, limit = 50): Promise<{
  id: string
  commits: SkillHistoryCommit[]
}> {
  const { tahpGet } = await import('../tahp/client')
  return tahpGet(`/api/tahp/skills/${encodeURIComponent(skillId)}/history?limit=${limit}`)
}

/** 仅本机删除 Skill 目录（local_only） */
export async function deleteLocalSkill(skillId: string): Promise<{ deleted: string }> {
  const { tahpDelete } = await import('../tahp/client')
  return tahpDelete(`/api/tahp/skills/local/${encodeURIComponent(skillId)}`)
}

/** 向中心申请删除（待审） */
export async function requestSkillDelete(
  skillId: string,
  message?: string,
): Promise<{
  id: string
  submit_id: string
  status: string
  kind: string
  published_hash?: string | null
}> {
  const { tahpPost } = await import('../tahp/client')
  return tahpPost('/api/tahp/skills/request-delete', {
    skill_id: skillId,
    message,
  })
}
