import { tahpGet, tahpPost, tahpPut, tahpRequest } from './client'

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

export interface KnowledgeEntry {
  id?: string
  title: string
  content: string
  module?: string
  tags?: string[]
  source?: string
  created_at?: string
  [key: string]: unknown
}

export interface KnowledgeStats {
  total: number
  by_module: Record<string, number>
  last_updated?: string
}

export function queryKnowledge(req: KnowledgeQueryRequest): Promise<KnowledgeResult> {
  return tahpPost<KnowledgeResult>('/api/tahp/knowledge/query', req)
}

export interface KbSaveRequest {
  title: string
  content: string
  module: string
  domain?: string
  tags?: string[]
  author?: string
  category?: string
}

export function saveKnowledgeFromChat(req: KbSaveRequest): Promise<{ id: string; file: string }> {
  return tahpPost<{ id: string; file: string }>('/api/tahp/knowledge/save', req)
}

export function addKnowledgeEntry(entry: KnowledgeEntry): Promise<{ id: string }> {
  return tahpPost<{ id: string }>('/api/tahp/knowledge/entries', entry)
}

export function updateKnowledgeEntry(id: string, entry: Partial<KnowledgeEntry>): Promise<void> {
  return tahpPut<void>(`/api/tahp/knowledge/entries/${encodeURIComponent(id)}`, entry)
}

export function deleteKnowledgeEntry(id: string): Promise<void> {
  return tahpRequest<void>(`/api/tahp/knowledge/entries/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function listKnowledgeEntries(module?: string): Promise<{ entries: KnowledgeEntry[]; total: number }> {
  const qs = module ? `?module=${encodeURIComponent(module)}` : ''
  return tahpGet<{ entries: KnowledgeEntry[]; total: number }>(`/api/tahp/knowledge/entries${qs}`)
}

export function getKnowledgeStats(): Promise<KnowledgeStats> {
  return tahpGet<KnowledgeStats>('/api/tahp/knowledge/stats')
}

export function importKnowledgeBatch(entries: KnowledgeEntry[]): Promise<{ imported: number; errors: number }> {
  return tahpPost<{ imported: number; errors: number }>('/api/tahp/knowledge/import', { entries })
}
