/**
 * AI 适配调试 — 域表单布局持久化类型
 *
 * 本地：每工作区一份 manifest.json（layouts 按 domain_id 分条）
 * 同步：按「工作区 × 模块」提交审核 / 拉取已发布版本（见 cloud-backend.ts）
 */
export const ADAPT_LAYOUT_SCHEMA_VERSION = 1

/** 默认工作区：兼容历史单 manifest 路径 */
export const DEFAULT_ADAPT_WORKSPACE = 'adapt-debug' as const

export const ADAPT_WORKSPACE_IDS = ['adapt-debug', 'feature-adapt', 'carrier-config'] as const

export type AdaptWorkspaceId = (typeof ADAPT_WORKSPACE_IDS)[number]

export function isAdaptWorkspaceId(value: string): value is AdaptWorkspaceId {
  return (ADAPT_WORKSPACE_IDS as readonly string[]).includes(value)
}

export type AdaptFieldType = 'text' | 'select' | 'textarea' | 'checklist'

export interface AdaptLayoutFieldDef {
  name: string
  label: string
  type: AdaptFieldType
  placeholder?: string
  required: boolean
  options?: Array<{ label: string; value: string }>
  defaultValue?: string
}

export interface AdaptDomainConfigInput {
  fields?: AdaptLayoutFieldDef[]
  related_skills?: string[]
}

export type AdaptLayoutReviewStatus = 'idle' | 'pending_review' | 'approved' | 'rejected'

export interface AdaptLayoutReviewState {
  status: AdaptLayoutReviewStatus
  submit_id?: string | null
  submitted_by?: string | null
  submitted_at?: string | null
  comment?: string | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  reject_reason?: string | null
}

export interface AdaptDomainLayoutRecord {
  schema_version: number
  domain_id: string
  fields: AdaptLayoutFieldDef[]
  /** 关联 Skill 列表，第一项为主控 Skill */
  related_skills?: string[]
  /** 本机保存次数（与已发布 revision 独立） */
  revision: number
  updated_at: string
  source: 'user' | 'cloud' | 'import'
  /** 本机已知的已发布版本号，提交时作为 base_revision */
  published_revision?: number
  /** 最近一次拉到/对齐的已发布内容指纹，用于判断 local_dirty */
  published_fingerprint?: string
  review?: AdaptLayoutReviewState
}

export interface AdaptLayoutSyncMeta {
  last_local_save?: string
  last_cloud_pull?: string
  last_cloud_push?: string
  cloud_revision?: string
  cloud_sync_enabled: boolean
}

export interface AdaptLayoutManifest {
  schema_version: number
  layouts: Record<string, AdaptDomainLayoutRecord>
  sync: AdaptLayoutSyncMeta
}

export interface AdaptLayoutSaveResult {
  domain_id: string
  revision: number
  updated_at: string
  cloud_pushed: boolean
  cloud_error?: string
  local_dirty?: boolean
}

export interface AdaptLayoutPullResult {
  pulled: boolean
  merged_domains: string[]
  skipped_dirty_domains: string[]
  published_revisions: Record<string, number>
  cloud_revision?: string
  error?: string
}

export interface AdaptLayoutSubmitResult {
  submit_id: string
  workspace_id: string
  domain_id: string
  status: 'pending_review'
  base_revision: number
  submitted_at: string
  submitted_by: string
}

export interface AdaptLayoutReviewQuery {
  workspace_id: string
  domain_id: string
  published_revision: number
  local_dirty: boolean
  review: AdaptLayoutReviewState
}

/** 远程已发布的单模块布局（不含本机 draft 字段） */
export interface AdaptPublishedDomainLayout {
  schema_version: number
  domain_id: string
  fields: AdaptLayoutFieldDef[]
  related_skills: string[]
  revision: number
  updated_at: string
  updated_by?: string
}

export interface AdaptPublishedWorkspaceLayouts {
  workspace_id: string
  layouts: Record<string, AdaptPublishedDomainLayout>
  reviews?: Record<string, AdaptLayoutReviewState>
}
