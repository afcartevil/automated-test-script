import type { ChatIntent } from './intents'
import type { KbHit, KbSourceType } from '../kb-search/types'

/** 自动模式融合检索：案例 + 文档 + 摘要 */
export const FUSION_KB_SOURCE_TYPES: KbSourceType[] = ['bug_distill', 'doc_chunk', 'doc_summary']

/** 显式历史案例模式：仅沉淀案例 */
export const CASE_ONLY_KB_SOURCE_TYPES: KbSourceType[] = ['bug_distill']

export interface SkillHit {
  skill_id: string
  description: string
  path: string
  relevance: number
  excerpt?: string
}

export interface LarkHit {
  title: string
  url?: string
  doc_type?: string
  excerpt: string
  relevance: number
}

export interface RetrievalBundle {
  intent: ChatIntent
  strategy_label: string
  kb_hits: KbHit[]
  skill_hits: SkillHit[]
  lark_hits: LarkHit[]
  directives: string[]
  latency_ms: number
  /** 目录/列举类查询（如「有哪些案例」） */
  catalog_mode?: boolean
  /** 显式模式（UI 手选 / slash / JIRA 直达）；自动路由为 false */
  explicit_mode?: boolean
}

export interface RetrievalOptions {
  retrieval_mode?: import('./intents').RetrievalMode
  search_lark?: boolean
  preferred_skill_ids?: string[]
  module_hint?: string
  /** 由 orchestrator 注入：slash / UI mode / JIRA 直达时为 true */
  explicit?: boolean
}

export interface RetrievalStrategy {
  execute(query: string, routed: import('./intent-router').RoutedIntent, options: RetrievalOptions): Promise<RetrievalBundle>
}
