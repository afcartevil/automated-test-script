/**
 * AI 适配调试 — 域表单布局持久化类型
 *
 * 本地 manifest + 可选云端同步（见 cloud-backend.ts）
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

export interface AdaptDomainLayoutRecord {
  schema_version: number
  domain_id: string
  fields: AdaptLayoutFieldDef[]
  /** 关联 Skill 列表，第一项为主控 Skill */
  related_skills?: string[]
  revision: number
  updated_at: string
  source: 'user' | 'cloud' | 'import'
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
}

export interface AdaptLayoutPullResult {
  pulled: boolean
  merged_domains: string[]
  cloud_revision?: string
  error?: string
}
