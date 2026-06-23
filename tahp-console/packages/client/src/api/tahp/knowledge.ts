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
  status?: 'pending_review' | 'approved' | 'rejected' | 'archived' | 'deleted'
  is_verified?: boolean
  validation_date?: string
  maintenance_owner?: string
  last_used_in_task?: string
  usage_count?: number
}

export interface EvalCase {
  id: string
  title: string
  input: string
  expected_output: string
  judgment_criteria: string
  source: 'ai_generated' | 'human'
  status: 'draft' | 'confirmed'
}

export interface QualityScore {
  total: number
  structure: number
  exclusions: number
  version_range: number
  eval_cases: number
  no_conflict: number
  owner: number
  pass_gate: boolean
  blocking_reasons: string[]
}

export interface ConflictResult {
  conflicting_skill_id: string
  conflicting_skill_name: string
  overlap_type: 'function' | 'version' | 'keyword'
  similarity_score: number
  suggestion: string
}

export interface VersionConstraint {
  android_versions?: string[]
  chipset_platforms?: string[]
  aosp_branches?: string[]
}

export interface SkillSuggestion {
  module: string
  func_type: string
  business_domain: string
  business_domain_label: string
  group_key: string
  entry_count: number
  entry_ids: string[]
  avg_confidence: number
  recommended: boolean
  reason: string
  suggested_skill_name: string
  existing_skill_count: number
  existing_skills: string[]
  has_draft?: boolean
  source_document_ids?: string[]
}

export interface SkillDraft {
  id?: string
  skill_id: string
  skill_name: string
  domain_label: string
  business_domain?: string
  module: string
  func_type: string
  content: string
  generated_from_entries: string[]
  generated_at?: string
  generated_by?: string
  status?: 'draft' | 'reviewing' | 'approved' | 'rejected' | 'deprecated' | 'archived'
  reviewed_by?: string
  reviewed_at?: string
  review_notes?: string
  activated_at?: string
  activated_skill_path?: string
  // ─── Phase 4 新增字段 ──────────────────────────────────────────
  eval_cases?: EvalCase[]
  quality_score?: QualityScore
  conflicts?: ConflictResult[]
  template_version?: string
  maintenance_owner?: string
  exclusion_cases?: string[]
  version_constraints?: VersionConstraint
  // ─── 优化计划新增字段 ───
  source_document_ids?: string[]
  content_fingerprint?: string
  duplicate_decisions?: Array<{
    decision: 'force_create' | 'view_existing' | 'merge' | 'upgrade_draft'
    target_id?: string
    decided_at: string
  }>
  func_type_raw?: string
  module_raw?: string
  category?: string
  // ─── 生命周期管控新增字段 ───
  deprecated_at?: string
  deprecated_by?: string
  deprecate_reason?: string
  archived_at?: string
  archived_by?: string
  archived_from_status?: string
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

export type ConversionStatus = 'pending' | 'done' | 'failed' | 'skipped'

export interface ImportJob {
  id: string
  filename: string
  status: 'processing' | 'done' | 'error'
  progress: number
  stage: 'upload' | 'parse' | 'convert_markdown' | 'extract' | 'done' | 'error'
  message: string
  entries: ExtractedEntry[]
  conversion_status?: ConversionStatus
  conversion_note?: string
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
  content_markdown?: string  // LLM 规范化 Markdown（仅单文档 GET）
  conversion_status?: ConversionStatus
  conversion_note?: string
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

/** POST /api/tahp/knowledge/documents/:docId/reconvert — 手动重试 Markdown 规范化 */
export function reconvertDocument(docId: string): Promise<{
  id: string
  conversion_status: ConversionStatus
  conversion_note?: string
  content_markdown: string
}> {
  return tahpPost<{ id: string; conversion_status: ConversionStatus; conversion_note?: string; content_markdown: string }>(
    `/api/tahp/knowledge/documents/${encodeURIComponent(docId)}/reconvert`,
    {},
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

// ─── Phase 4 API Functions (Skill 工坊) ──────────────────────────────────────

export interface BusinessDomainInfo {
  id: string
  label: string
  modules: string[]
  aliases: string[]
}

/** GET /api/tahp/knowledge/business-domains — 可配置业务子域表 */
export function getBusinessDomains(module?: string): Promise<{
  domains: BusinessDomainInfo[]
  total: number
  config_path: string
}> {
  const qs = module ? `?module=${encodeURIComponent(module)}` : ''
  return tahpGet<{ domains: BusinessDomainInfo[]; total: number; config_path: string }>(
    `/api/tahp/knowledge/business-domains${qs}`,
  )
}

/** GET /api/tahp/knowledge/skill-suggestions — 分组推荐生成 Skill */
export function getSkillSuggestions(): Promise<{
  suggestions: SkillSuggestion[]
  total_groups: number
  recommended_count: number
}> {
  return tahpGet<{ suggestions: SkillSuggestion[]; total_groups: number; recommended_count: number }>(
    '/api/tahp/knowledge/skill-suggestions',
  )
}

/** POST /api/tahp/knowledge/skill-association — 关联检索：找出相关已有 Skill 并给出 enhance/new 建议 */
export interface SkillAssociationItem {
  id: string
  type: 'draft' | 'activated'
  display_name: string
  module: string
  func_type: string
  description: string
  association_score: number
  recommendation: 'enhance_existing' | 'create_new'
  can_merge: boolean
  needs_upgrade: boolean
  reasons: string[]
}
export function skillAssociation(params: {
  entry_ids?: string[]
  document_ids?: string[]
  module?: string
  func_type?: string
  keywords?: string[]
  text?: string
  skill_name?: string
}): Promise<{
  associations: SkillAssociationItem[]
  total: number
  overall_recommendation: 'enhance_existing' | 'create_new'
  best_match: SkillAssociationItem | null
}> {
  return tahpPost('/api/tahp/knowledge/skill-association', params)
}

/** POST /api/tahp/knowledge/skill-drafts/check-similarity — 生成前相似 Skill 检索 */
export interface SimilarSkillItem {
  /** 草稿时为 draft.id，已激活时为 skillId */
  id: string
  /** 来源类型 */
  type: 'draft' | 'activated'
  /** 展示名称 */
  display_name: string
  module: string
  func_type: string
  description: string
  /** Jaccard 相似度 0-1 */
  jaccard_score: number
  /** 三档分级 */
  tier: 'exact' | 'partial' | 'structural'
  reasons: string[]
  /** @deprecated 兼容旧字段，等同于 id */
  skill_id?: string
}
export function checkSkillSimilarity(params: {
  module: string
  func_type: string
  entry_ids?: string[]
  skill_name?: string
  keywords?: string[]
  business_domain?: string
}): Promise<{ similar: SimilarSkillItem[]; has_exact: boolean; has_partial: boolean; total: number }> {
  return tahpPost<{ similar: SimilarSkillItem[]; has_exact: boolean; has_partial: boolean; total: number }>(
    '/api/tahp/knowledge/skill-drafts/check-similarity',
    params,
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/merge — LLM 精准增量融合 */
export function mergeIntoSkill(
  draftId: string,
  entryIds: string[],
): Promise<{ draft: SkillDraft; merged_count: number; message: string; llm_error?: string }> {
  return tahpPost<{ draft: SkillDraft; merged_count: number; message: string; llm_error?: string }>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/merge`,
    { entry_ids: entryIds },
  )
}

/** POST /api/tahp/knowledge/skill-drafts/generate — LLM 生成 Skill 草稿 */
export function generateSkillDraft(params: {
  module: string
  func_type: string
  entry_ids?: string[]
  skill_name?: string
  generated_by?: string
}): Promise<{ draft: SkillDraft; llm_error?: string; message?: string }> {
  return tahpPost<{ draft: SkillDraft; llm_error?: string; message?: string }>(
    '/api/tahp/knowledge/skill-drafts/generate',
    params,
  )
}

/** GET /api/tahp/knowledge/skill-drafts/:draftId — 获取单个草稿详情 */
export function getSkillDraft(draftId: string): Promise<SkillDraft> {
  return tahpGet<SkillDraft>(`/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}`)
}

/** PUT /api/tahp/knowledge/skill-drafts/:draftId — 更新草稿内容 */
export function updateSkillDraft(draftId: string, updates: {
  content?: string
  skill_name?: string
  domain_label?: string
  maintenance_owner?: string
  exclusion_cases?: string[]
  version_constraints?: VersionConstraint
  eval_cases?: EvalCase[]
}): Promise<SkillDraft> {
  return tahpRequest<SkillDraft>(`/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases — 添加/更新 eval 用例 */
export function upsertEvalCase(draftId: string, evalCase: Partial<EvalCase> & { title: string }): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/eval-cases`,
    evalCase,
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases/:caseId/confirm — 确认 eval 用例 */
export function confirmEvalCase(draftId: string, caseId: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/eval-cases/${encodeURIComponent(caseId)}/confirm`,
    {},
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases/:caseId/delete — 删除 eval 用例 */
export function deleteEvalCase(draftId: string, caseId: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/eval-cases/${encodeURIComponent(caseId)}/delete`,
    {},
  )
}

// ─── 优化计划新增 API ───────────────────────────────────────────────────────────────────────────────

export interface DuplicateItem {
  id: string
  skill_name: string
  status: string
  generated_at: string
  match_type: 'source_document' | 'fingerprint'
  can_merge: boolean
  is_activated: boolean
}

export interface RecommendItem {
  target_id: string
  target_name: string
  target_type: 'draft' | 'activated'
  match_score: number
  new_topics: string[]
  new_topics_count: number
  common_topics_count: number
  estimated_quality_delta: number
  reason: string
  can_merge: boolean
  upgrade_hint?: string
}

export interface SkillGenJobResult {
  id: string
  status: 'running' | 'completed' | 'error' | 'cancelled'
  stage: string
  progress: number
  message: string
  result?: {
    draft?: SkillDraft
    duplicate_detected?: boolean
    duplicate_drafts?: DuplicateItem[]
    similar_skills?: Array<{
      id: string
      type: 'draft' | 'activated'
      display_name: string
      jaccard_score: number
      tier: string
      reasons: string[]
    }>
    llm_error?: string
    llm_error_detail?: string
  }
  created_at: string
  ttl_expires_at: string
}

/** POST /api/tahp/knowledge/skill-drafts/check-duplicate — 文档级重复检测 */
export function checkDuplicateDraft(entryIds: string[]): Promise<{
  duplicate_detected: boolean
  duplicates: DuplicateItem[]
  fingerprint: string
}> {
  return tahpPost<{ duplicate_detected: boolean; duplicates: DuplicateItem[]; fingerprint: string }>(
    '/api/tahp/knowledge/skill-drafts/check-duplicate',
    { entry_ids: entryIds },
  )
}

/** POST /api/tahp/knowledge/skill-drafts/duplicate-decision — 记录用户重复决策 */
export function recordDuplicateDecision(
  draftId: string,
  decision: 'force_create' | 'view_existing' | 'merge' | 'upgrade_draft',
  targetId?: string,
): Promise<SkillDraft> {
  return tahpPost<SkillDraft>('/api/tahp/knowledge/skill-drafts/duplicate-decision', {
    draft_id: draftId,
    decision,
    target_id: targetId,
  })
}

/** POST /api/tahp/knowledge/skill-drafts/recommend-merge-target — 融合目标推荐 */
export function recommendMergeTarget(params: {
  entry_ids: string[]
  module: string
  func_type: string
}): Promise<{ recommendations: RecommendItem[] }> {
  return tahpPost<{ recommendations: RecommendItem[] }>(
    '/api/tahp/knowledge/skill-drafts/recommend-merge-target',
    params,
  )
}

/** POST /api/tahp/knowledge/skill-drafts/upgrade-draft — 已激活 Skill 生成升级草案 */
export function createUpgradeDraft(skillId: string, entryIds?: string[]): Promise<{ draft: SkillDraft }> {
  return tahpPost<{ draft: SkillDraft }>('/api/tahp/knowledge/skill-drafts/upgrade-draft', {
    skill_id: skillId,
    entry_ids: entryIds || [],
  })
}

/** POST /api/tahp/knowledge/skill-drafts/generate-stream — 启动异步生成任务 */
export function startGenerateStream(params: {
  module: string
  func_type: string
  entry_ids?: string[]
  skill_name?: string
  generated_by?: string
  document_ids?: string[]
  business_domain?: string
  business_domain_label?: string
}): Promise<{ job_id: string }> {
  return tahpPost<{ job_id: string }>('/api/tahp/knowledge/skill-drafts/generate-stream', params)
}

/** GET /api/tahp/knowledge/skill-drafts/generate-stream/:jobId — SSE 订阅生成进度 */
export function subscribeSkillGenProgress(jobId: string): EventSource {
  const base = getBaseUrlValue()
  return new EventSource(`${base}/api/tahp/knowledge/skill-drafts/generate-stream/${encodeURIComponent(jobId)}`)
}

/** GET /api/tahp/knowledge/skill-drafts/gen-job/:jobId — 一次性获取任务状态 */
export function getSkillGenJob(jobId: string): Promise<SkillGenJobResult> {
  return tahpGet<SkillGenJobResult>(`/api/tahp/knowledge/skill-drafts/gen-job/${encodeURIComponent(jobId)}`)
}

// ─── 生命周期管控 API ────────────────────────────────────────────────────────

/** DELETE /api/tahp/knowledge/skill-drafts/:draftId — 删除草稿(仅 draft/rejected) */
export function deleteSkillDraft(draftId: string): Promise<{ deleted: string }> {
  return tahpRequest<{ deleted: string }>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}`,
    { method: 'DELETE' },
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/deprecate — 废弃已激活 Skill */
export function deprecateSkillDraft(draftId: string, reason: string, deprecatedBy?: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/deprecate`,
    { reason, deprecated_by: deprecatedBy },
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/deactivate — 下线 Skill(物理移除) */
export function deactivateSkill(draftId: string, reason: string, archivedBy?: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/deactivate`,
    { reason, archived_by: archivedBy },
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/archive — 归档草稿 */
export function archiveSkillDraft(draftId: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/archive`,
    {},
  )
}

/** POST /api/tahp/knowledge/skill-drafts/:draftId/restore — 恢复归档草稿 */
export function restoreSkillDraft(draftId: string): Promise<SkillDraft> {
  return tahpPost<SkillDraft>(
    `/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/restore`,
    {},
  )
}

/** POST /api/tahp/knowledge/skill-drafts/bulk-cleanup — 批量清理 rejected 草稿 */
export function bulkCleanupDrafts(): Promise<{ cleaned: number }> {
  return tahpPost<{ cleaned: number }>('/api/tahp/knowledge/skill-drafts/bulk-cleanup', {})
}

/** POST /api/tahp/knowledge/skill-drafts/bulk-deprecate — 批量废弃已激活 Skill */
export function bulkDeprecateSkills(draftIds: string[], reason: string): Promise<{ deprecated: number }> {
  return tahpPost<{ deprecated: number }>('/api/tahp/knowledge/skill-drafts/bulk-deprecate', {
    draft_ids: draftIds,
    reason,
  })
}

/** DELETE /api/tahp/knowledge/entries/:entryId/hard — 物理删除条目 */
export function hardDeleteEntry(entryId: string): Promise<{ deleted: string }> {
  return tahpRequest<{ deleted: string }>(
    `/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}/hard`,
    { method: 'DELETE' },
  )
}

/** POST /api/tahp/knowledge/entries/bulk-archive — 批量归档条目 */
export function bulkArchiveEntries(filter?: { module?: string; before?: string; ids?: string[] }): Promise<{ archived: number }> {
  return tahpPost<{ archived: number }>('/api/tahp/knowledge/entries/bulk-archive', filter || {})
}

/** POST /api/tahp/knowledge/entries/bulk-delete — 批量物理删除条目 */
export function bulkDeleteArchived(filter?: { module?: string; ids?: string[] }): Promise<{ deleted: number }> {
  return tahpPost<{ deleted: number }>('/api/tahp/knowledge/entries/bulk-delete', filter || {})
}

// ─── 增强统计 + 审计日志 ──────────────────────────────────────────────────

export interface EnhancedStats {
  entry_by_status: Record<string, number>
  draft_by_status: Record<string, number>
  total_entries: number
  total_drafts: number
  activated_skills: number
  expired_entries: number
  deprecated_skills: number
}

/** GET /api/tahp/knowledge/stats/enhanced — 增强统计 */
export function getEnhancedStats(): Promise<EnhancedStats> {
  return tahpGet<EnhancedStats>('/api/tahp/knowledge/stats/enhanced')
}

// ─── 治理面板 ────────────────────────────────────────────────────────────────

export interface GovernanceData {
  totals: {
    entries: number
    live_entries: number
    documents: number
    drafts: number
    activated_skills: number
  }
  pending_entries: number
  expired_entries: number
  expiring_soon: number
  low_confidence: number
  zero_usage: number
  pending_drafts: number
  deprecated_skills: number
  conversion_failed: number
  conversion_skipped: number
  top_used: Array<{ id: string; content_preview: string; usage_count: number; module: string }>
  blind_spots: Array<{ module: string; func_type: string; entry_count: number; entry_ids: string[] }>
}

/** GET /api/tahp/knowledge/governance — 知识库治理面板数据 */
export function getGovernance(): Promise<GovernanceData> {
  return tahpGet<GovernanceData>('/api/tahp/knowledge/governance')
}

export interface AuditLogEntry {
  id: string
  timestamp: string
  action: string
  actor: string
  target_type: string
  target_id: string
  target_name?: string
  details?: Record<string, unknown>
  reason?: string
}

/** GET /api/tahp/knowledge/audit-log — 审计日志查询 */
export function getAuditLog(limit?: number, action?: string): Promise<{ entries: AuditLogEntry[]; total: number }> {
  const qs = new URLSearchParams()
  if (limit) qs.append('limit', String(limit))
  if (action) qs.append('action', action)
  return tahpGet<{ entries: AuditLogEntry[]; total: number }>(
    `/api/tahp/knowledge/audit-log${qs.size ? '?' + qs : ''}`,
  )
}

// ─── 草稿批量操作 API ─────────────────────────────────────────────────

/** POST /api/tahp/knowledge/skill-drafts/bulk-approve — 批量批准草稿 */
export function bulkApproveDrafts(draftIds: string[]): Promise<{ approved: number }> {
  return tahpPost<{ approved: number }>('/api/tahp/knowledge/skill-drafts/bulk-approve', { draft_ids: draftIds })
}

/** POST /api/tahp/knowledge/skill-drafts/bulk-reject — 批量拒绝草稿 */
export function bulkRejectDrafts(draftIds: string[], reason?: string): Promise<{ rejected: number }> {
  return tahpPost<{ rejected: number }>('/api/tahp/knowledge/skill-drafts/bulk-reject', { draft_ids: draftIds, reason })
}

/** POST /api/tahp/knowledge/skill-drafts/bulk-delete — 批量删除草稿 */
export function bulkDeleteDrafts(draftIds: string[]): Promise<{ deleted: number }> {
  return tahpPost<{ deleted: number }>('/api/tahp/knowledge/skill-drafts/bulk-delete', { draft_ids: draftIds })
}

/** POST /api/tahp/knowledge/skill-drafts/bulk-archive-selected — 批量归档草稿 */
export function bulkArchiveSelectedDrafts(draftIds: string[]): Promise<{ archived: number }> {
  return tahpPost<{ archived: number }>('/api/tahp/knowledge/skill-drafts/bulk-archive-selected', { draft_ids: draftIds })
}

// ─── 文档编辑 API ───────────────────────────────────────────────────────

/** PUT /api/tahp/knowledge/documents/:docId — 更新文档元数据 */
export function updateDocument(docId: string, data: { title?: string; module?: string }): Promise<KnowledgeDocument> {
  return tahpPut<KnowledgeDocument>(`/api/tahp/knowledge/documents/${encodeURIComponent(docId)}`, data)
}
