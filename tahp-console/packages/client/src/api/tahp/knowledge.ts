import { tahpPost } from './client'

export interface KnowledgeQueryRequest {
  query: string
  module?: string
  cross_module?: boolean
  top_k?: number
}

export interface KnowledgeResult {
  results?: Array<{
    title?: string
    content?: string
    source?: string
    module?: string
    score?: number
    [key: string]: unknown
  }>
  total?: number
  confidence?: number
  [key: string]: unknown
}

export function queryKnowledge(req: KnowledgeQueryRequest): Promise<KnowledgeResult> {
  return tahpPost<KnowledgeResult>('/api/tahp/knowledge/query', req)
}
