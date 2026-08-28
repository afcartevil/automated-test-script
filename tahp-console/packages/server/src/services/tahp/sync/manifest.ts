/**
 * 同步类型定义 — 与中心 easyadapter_bff/src/routes/sync.ts 的契约保持一致。
 * 两仓各存一份，修改时务必同步。见 .cursor/skill-sync/PHASE-2.md。
 */

export interface ManifestFileEntry {
  rel_path: string
  hash: string
  size: number
}

export interface ManifestItem {
  type: 'entry' | 'skill' | 'config'
  id: string
  updated_at: string
  hash: string
  status: string
  bundle_ids?: string[]
  files?: ManifestFileEntry[]
  has_attachments?: boolean
}

export interface SyncManifest {
  generated_at: string
  items: ManifestItem[]
}

export interface PullSkillItem {
  id: string
  rel_path: string
  content: string
  updated_at: string
  /** Phase 2 整包 hash；缺省时回退用 content 比对 */
  hash?: string
  files?: Array<{ rel_path: string; content_b64: string; hash: string }>
  package_url?: string
}

export interface PullDeletedSkill {
  id: string
  deleted_at: string
  submit_id?: string
}

export interface PullPayload {
  generated_at: string
  entries: Array<Record<string, unknown>>
  skills: PullSkillItem[]
  configs: Array<{ key: string; rel_path: string; content: string }>
  /** 中心已审核删除的 Skill（tombstone）；本机应清理对应目录 */
  deleted_skills?: PullDeletedSkill[]
}

export type SubmitKind = 'entry' | 'skill_draft'

export interface SubmitEntryPayload {
  kind: 'entry'
  entry: Record<string, unknown>
}

export interface SubmitDraftPayload {
  kind: 'skill_draft'
  draft: Record<string, unknown>
}

export type SubmitPayload = SubmitEntryPayload | SubmitDraftPayload
