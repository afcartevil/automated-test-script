/**
 * 同步类型定义 — 与中心 easyadapter_bff/src/routes/sync.ts 的契约保持一致。
 * 两仓各存一份，修改时务必同步。见 .cursor/skill-sync/PHASE-1.md。
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
  /** Phase 1: skill 多为 []；Phase 3 填真实 Bundle */
  bundle_ids?: string[]
  /** Phase 1: skill 仅 SKILL.md；Phase 2 扩展整包 */
  files?: ManifestFileEntry[]
}

export interface SyncManifest {
  generated_at: string
  items: ManifestItem[]
}

export interface PullPayload {
  generated_at: string
  entries: Array<Record<string, unknown>>
  skills: Array<{ id: string; rel_path: string; content: string; updated_at: string }>
  configs: Array<{ key: string; rel_path: string; content: string }>
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
