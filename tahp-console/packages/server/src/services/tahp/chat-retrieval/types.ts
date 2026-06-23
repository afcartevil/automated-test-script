import type { ChatIntent } from './intents'
import type { KbHit } from '../kb-search/types'

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
}

export interface RetrievalOptions {
  retrieval_mode?: import('./intents').RetrievalMode
  search_lark?: boolean
  preferred_skill_ids?: string[]
  module_hint?: string
}

export interface RetrievalStrategy {
  execute(query: string, routed: import('./intent-router').RoutedIntent, options: RetrievalOptions): Promise<RetrievalBundle>
}
