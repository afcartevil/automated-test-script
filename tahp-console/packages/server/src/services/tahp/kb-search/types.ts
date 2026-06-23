/** 知识条目来源类型（检索分场景过滤） */
export type KbSourceType = 'bug_distill' | 'doc_chunk' | 'doc_summary' | 'manual'

export interface KbIndexRecord {
  id: string
  source_type: KbSourceType
  module: string
  func_type: string
  category: string
  status: string
  jira_key?: string
  source_document_id?: string
  tags: string[]
  keywords: string[]
  tokens: string[]
  blob_len: number
  updated_at: string
}

export interface KbSearchQuery {
  query: string
  module?: string
  /** 软加权：匹配该 module 的条目加分，不做硬过滤 */
  module_hint?: string
  func_type?: string
  source_types?: KbSourceType[]
  source_document_ids?: string[]
  include_archived?: boolean
  jira_fast_path?: boolean
  limit?: number
  min_score?: number
}

export interface KbHit {
  id: string
  source_type: KbSourceType
  module: string
  func_type: string
  title: string
  snippet: string
  relevance: number
  jira_key?: string
  status: string
  path: string
  related_skill_ids?: string[]
}

/** 最小条目形状（索引与 blob 构建用） */
export interface KbEntryLike {
  id: string
  content: string
  category: string
  module: string
  func_type: string
  keywords?: string[]
  confidence_score?: number
  source_file?: string
  source_document_id?: string
  source_task_id?: string
  status: string
  updated_at?: string
  created_at?: string
  source_type?: KbSourceType
  jira_key?: string
  tags?: string[]
  search_blob?: string
  symptom_summary?: string
  related_skill_ids?: string[]
  applicable_versions?: string[]
}
