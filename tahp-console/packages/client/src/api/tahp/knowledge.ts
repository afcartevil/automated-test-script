import { tahpGet, tahpPost, tahpPut, tahpRequest } from './client'
import { getBaseUrlValue } from '../client'

// ─── Phase 1 Data Models ──────────────────────────────────────────────────

export interface KnowledgeEntry {
  id?: string
  content: string
  category: string
  module: string
  func_type: string
  keywords: string[]
  confidence_score: number
  source_file?: string
  source_page?: number
  source_section?: string
  source_url?: string
  applicable_versions?: string[]
  created_at?: string
  updated_at?: string
  expires_at?: string
  status?: 'pending_review' | 'approved' | 'rejected' | 'archived'
  is_verified?: boolean
  validation_date?: string
  maintenance_owner?: string
  last_used_in_task?: string
  usage_count?: number
}

export interface SkillDraft {
  id?: string
  skill_id: string
  skill_name: string
  domain_label: string
  module: string
  func_type: string
  content: string
  generated_from_entries: string[]
  generated_at?: string
  generated_by?: string
  status?: 'draft' | 'reviewing' | 'approved' | 'rejected'
  reviewed_by?: string
  reviewed_at?: string
  review_notes?: string
  activated_at?: string
  activated_skill_path?: string
}

export interface KnowledgeStats {
  total_entries: number
  approved_entries: number
  pending_entries: number
  archived_entries: number
  by_module: Record<string, number>
  by_func_type: Record<string, number>
  by_status: Record<string, number>
  total_skill_drafts: number
  draft_skill_drafts: number
  approved_skill_drafts: number
  total_usage_count: number
  average_confidence: number
  total_documents?: number
}

export interface SemanticSearchResult {
  results: (KnowledgeEntry & { search_relevance: number })[]
  total: number
}

// ─── Legacy Interfaces (backward compatibility) ──────────────────────────

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

export interface KbSaveRequest {
  title: string
  content: string
  module: string
  domain?: string
  tags?: string[]
  author?: string
  category?: string
}

// ─── Phase 1 API Functions (New) ──────────────────────────────────────────

// NOTE: tahpGet/tahpPost/tahpPut automatically unwrap the { success, data } envelope
// and return only the inner `data` payload. So return types are the actual data shapes.

/** POST /api/tahp/knowledge/entries — Create a knowledge entry */
export function createKnowledgeEntry(entry: KnowledgeEntry): Promise<KnowledgeEntry> {
  return tahpPost<KnowledgeEntry>('/api/tahp/knowledge/entries', entry)
}

/** GET /api/tahp/knowledge/entries — List knowledge entries with filters */
export function listKnowledgeEntries(query?: {
  module?: string
  func_type?: string
  status?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}): Promise<{ entries: KnowledgeEntry[]; total: number; limit: number; offset: number }> {
  const qs = new URLSearchParams()
  if (query?.module) qs.append('module', query.module)
  if (query?.func_type) qs.append('func_type', query.func_type)
  if (query?.status) qs.append('status', query.status)
  if (query?.sort_by) qs.append('sort_by', query.sort_by)
  if (query?.sort_order) qs.append('sort_order', query.sort_order)
  if (query?.limit) qs.append('limit', String(query.limit))
  if (query?.offset) qs.append('offset', String(query.offset))

  const path = `/api/tahp/knowledge/entries${qs.size ? '?' + qs : ''}`
  return tahpGet<{ entries: KnowledgeEntry[]; total: number; limit: number; offset: number }>(path)
}

/** GET /api/tahp/knowledge/entries/:entryId — Get single knowledge entry */
export function getKnowledgeEntry(entryId: string): Promise<KnowledgeEntry> {
  return tahpGet<KnowledgeEntry>(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}`)
}

/** PUT /api/tahp/knowledge/entries/:entryId — Update knowledge entry */
export function updateKnowledgeEntry(entryId: string, updates: Partial<KnowledgeEntry>): Promise<KnowledgeEntry> {
  return tahpPut<KnowledgeEntry>(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}`, updates)
}

/** DELETE /api/tahp/knowledge/entries/:entryId — Delete (soft delete) knowledge entry */
export function deleteKnowledgeEntry(entryId: string): Promise<{ archived: string }> {
  return tahpRequest<{ archived: string }>(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}`, { method: 'DELETE' })
}

/** POST /api/tahp/knowledge/search/semantic — Semantic search */
export function semanticSearch(query: string, module?: string, limit?: number): Promise<SemanticSearchResult> {
  return tahpPost<SemanticSearchResult>('/api/tahp/knowledge/search/semantic', { query, module, limit })
}

/** POST /api/tahp/knowledge/skill-drafts — Create skill draft */
export function createSkillDraft(draft: {
  skill_id: string
  skill_name: string
  domain_label: string
  module: string
  func_type: string
  content?: string
  entry_ids?: string[]
  generated_by?: string
}): Promise<SkillDraft> {
  return tahpPost<SkillDraft>('/api/tahp/knowledge/skill-drafts', draft)
}

/** GET /api/tahp/knowledge/skill-drafts — List skill drafts */
export function listSkillDrafts(query?: {
  status?: string
  limit?: number
  offset?: number
}): Promise<{ drafts: SkillDraft[]; total: number; limit: number; offset: number }> {
  const qs = new URLSearchParams()
  if (query?.status) qs.append('status', query.status)
  if (query?.limit) qs.append('limit', String(query.limit))
  if (query?.offset) qs.append('offset', String(query.offset))

  const path = `/api/tahp/knowledge/skill-drafts${qs.size ? '?' + qs : ''}`
  return tahpGet<{ drafts: SkillDraft[]; total: number; limit: number; offset: number }>(path)
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/review — Review skill draft */
export function reviewSkillDraft(draftId: string, action: 'approve' | 'reject', reviewedBy?: string, reviewNotes?: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(`/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/review`, {
    action,
    reviewed_by: reviewedBy,
    review_notes: reviewNotes,
  })
}

/** POST /api/tahp/knowledge/entries/:entryId/feedback — Record task feedback */
export function recordFeedback(entryId: string, feedback: {
  task_id?: string
  feedback?: string
  useful?: boolean
  rating?: number
}): Promise<KnowledgeEntry> {
  return tahpPost<KnowledgeEntry>(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}/feedback`, feedback)
}

/** GET /api/tahp/knowledge/stats — Get knowledge base statistics */
export function getKnowledgeStats(): Promise<KnowledgeStats> {
  return tahpGet<KnowledgeStats>('/api/tahp/knowledge/stats')
}

// ─── Legacy API Functions (backward compatibility) ────────────────────────

export function queryKnowledge(req: KnowledgeQueryRequest): Promise<KnowledgeResult> {
  return tahpPost<KnowledgeResult>('/api/tahp/knowledge/query', req)
}

export function saveKnowledgeFromChat(req: KbSaveRequest): Promise<{ id: string; file: string }> {
  return tahpPost<{ id: string; file: string }>('/api/tahp/knowledge/save', req)
}

export function importKnowledgeBatch(entries: KnowledgeEntry[]): Promise<{ imported: number; errors: number }> {
  return tahpPost<{ imported: number; errors: number }>('/api/tahp/knowledge/import', { entries })
}

// ─── Phase 2 API Functions (Document Import + BM25 Search) ───────────────────

export interface ExtractedEntry {
  id: string
  content: string
  category: string
  module: string
  func_type: string
  keywords: string[]
  confidence_score: number
  source_file: string
  source_section?: string
}

export interface ImportJob {
  id: string
  filename: string
  status: 'processing' | 'done' | 'error'
  progress: number
  stage: 'upload' | 'parse' | 'extract' | 'done' | 'error'
  message: string
  entries: ExtractedEntry[]
  created_at: string
  error?: string
}

/**
 * POST /api/tahp/knowledge/import/start — 启动文档导入任务
 * 对 TXT/MD 传 content（文本字符串），对 PDF/DOCX 传 content_base64（base64 字符串）
 */
export function startImportJob(params: {
  filename: string
  content?: string
  content_base64?: string
}): Promise<{ job_id: string }> {
  return tahpPost<{ job_id: string }>('/api/tahp/knowledge/import/start', params)
}

/** GET /api/tahp/knowledge/import/jobs/:jobId — 一次性获取任务状态 */
export function getImportJob(jobId: string): Promise<ImportJob> {
  return tahpGet<ImportJob>(`/api/tahp/knowledge/import/jobs/${encodeURIComponent(jobId)}`)
}

/**
 * GET /api/tahp/knowledge/import/jobs/:jobId/progress — SSE 进度流
 * 返回原生 EventSource，调用方监听 onmessage / onerror。
 */
export function subscribeImportProgress(jobId: string): EventSource {
  const base = getBaseUrlValue()
  return new EventSource(`${base}/api/tahp/knowledge/import/jobs/${encodeURIComponent(jobId)}/progress`)
}

/**
 * POST /api/tahp/knowledge/import/jobs/:jobId/save — 保存选中条目到知识库
 * 不传 entry_ids 则保存全部。返回新建 doc_id。
 */
export function saveImportedEntries(jobId: string, entryIds?: string[]): Promise<{ saved: number; doc_id: string; entries: KnowledgeEntry[] }> {
  return tahpPost<{ saved: number; doc_id: string; entries: KnowledgeEntry[] }>(
    `/api/tahp/knowledge/import/jobs/${encodeURIComponent(jobId)}/save`,
    entryIds ? { entry_ids: entryIds } : {},
  )
}

// ─── Phase 3 API Functions (Document Layer) ──────────────────────────────────

export interface KnowledgeDocument {
  id: string
  title: string
  filename: string
  content?: string       // only present in single-doc GET, omitted in list
  module: string
  category: string
  chunk_ids: string[]
  created_at: string
  updated_at: string
  char_count: number
  chunk_count: number
}

/** GET /api/tahp/knowledge/documents — 文档列表（不含全文） */
export function listDocuments(): Promise<{ documents: KnowledgeDocument[]; total: number }> {
  return tahpGet<{ documents: KnowledgeDocument[]; total: number }>('/api/tahp/knowledge/documents')
}

/** GET /api/tahp/knowledge/documents/:docId — 单份文档（含全文） */
export function getDocument(docId: string): Promise<KnowledgeDocument> {
  return tahpGet<KnowledgeDocument>(`/api/tahp/knowledge/documents/${encodeURIComponent(docId)}`)
}

/** DELETE /api/tahp/knowledge/documents/:docId — 删除文档及关联 chunks */
export function deleteDocument(docId: string): Promise<{ deleted: string; chunks_archived: number }> {
  return tahpRequest<{ deleted: string; chunks_archived: number }>(
    `/api/tahp/knowledge/documents/${encodeURIComponent(docId)}`,
    { method: 'DELETE' },
  )
}

/** GET /api/tahp/knowledge/documents/:docId/chunks — 该文档的 chunk 条目列表 */
export function getDocumentChunks(docId: string): Promise<{ chunks: KnowledgeEntry[]; total: number }> {
  return tahpGet<{ chunks: KnowledgeEntry[]; total: number }>(
    `/api/tahp/knowledge/documents/${encodeURIComponent(docId)}/chunks`,
  )
}

// ─── Phase 3 API Functions (Folder Scan + URL Fetch) ─────────────────────────

/**
 * POST /api/tahp/knowledge/import/fetch-url — 启动网页链接导入任务
 * 返回 job_id，使用 subscribeImportProgress(job_id) 监听 SSE 进度。
 */
export function startFetchUrl(url: string): Promise<{ job_id: string }> {
  return tahpPost<{ job_id: string }>('/api/tahp/knowledge/import/fetch-url', { url })
}

/**
 * POST /api/tahp/knowledge/import/scan-folder — 启动本地文件夹批量导入任务
 * folder_path: 绝对路径，recursive: 是否递归扫描子目录（默认 false）
 * 返回 job_id + file_count，使用 subscribeImportProgress(job_id) 监听 SSE 进度。
 */
export function startScanFolder(
  folderPath: string,
  recursive?: boolean,
): Promise<{ job_id: string; file_count: number }> {
  return tahpPost<{ job_id: string; file_count: number }>('/api/tahp/knowledge/import/scan-folder', {
    folder_path: folderPath,
    recursive: recursive ?? false,
  })
}
