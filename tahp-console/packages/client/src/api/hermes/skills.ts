import { request } from '../client'

export type SkillSource = 'builtin' | 'hub' | 'local' | 'tahp'

export interface SkillInfo {
  name: string
  description: string
  enabled?: boolean
  source?: SkillSource
  modified?: boolean
  patchCount?: number
  useCount?: number
  viewCount?: number
  pinned?: boolean
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
  skills: { name: string; sourcePath: string }[],
  overwrite: boolean,
): Promise<ImportSkillsResult> {
  return request<ImportSkillsResult>('/api/hermes/skills/import-from-path', {
    method: 'POST',
    body: JSON.stringify({ skills, overwrite }),
  })
}
