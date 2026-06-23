/**
 * 知识库管理系统 — Phase 1 + Phase 2
 *
 * ─── Phase 1 Endpoints ───────────────────────────────────────────────────────
 * POST   /api/tahp/knowledge/entries                    — 创建知识条目
 * GET    /api/tahp/knowledge/entries                    — 查询知识库（支持筛选、排序、分页）
 * GET    /api/tahp/knowledge/entries/:entryId           — 获取单个条目
 * PUT    /api/tahp/knowledge/entries/:entryId           — 更新知识条目
 * DELETE /api/tahp/knowledge/entries/:entryId           — 删除知识条目（软删除）
 * POST   /api/tahp/knowledge/search/semantic            — BM25 语义搜索（Phase 2 增强）
 * POST   /api/tahp/knowledge/skill-drafts               — 自动生成 Skill 草稿
 * GET    /api/tahp/knowledge/skill-drafts               — 查询待审核 Skill 草稿
 * POST   /api/tahp/knowledge/skill-drafts/:draftId/review — 审核和激活 Skill 草稿
 * POST   /api/tahp/knowledge/entries/:entryId/feedback   — 任务反哺知识库
 * GET    /api/tahp/knowledge/stats                      — 知识库统计信息
 *
 * ─── Phase 2 Endpoints ───────────────────────────────────────────────────────
 * POST   /api/tahp/knowledge/import/start               — 启动文档导入任务（返回 jobId）
 * GET    /api/tahp/knowledge/import/jobs/:jobId/progress — SSE 实时进度流
 * GET    /api/tahp/knowledge/import/jobs/:jobId         — 获取任务状态
 * POST   /api/tahp/knowledge/import/jobs/:jobId/save    — 保存提取的条目
 *
 * 存储: knowledge-base/.kb-data/entries/, .kb-data/skill-drafts/, .kb-data/documents/
 *
 * ─── Phase 3 Endpoints (Document Layer) ─────────────────────────────────────
 * GET    /api/tahp/knowledge/documents                   — 文档列表
 * GET    /api/tahp/knowledge/documents/:docId            — 获取单份文档（含全文）
 * DELETE /api/tahp/knowledge/documents/:docId            — 删除文档及关联 chunks
 * GET    /api/tahp/knowledge/documents/:docId/chunks     — 该文档的所有 chunk 条目
 *
 * ─── Phase 3 Import Modes ────────────────────────────────────────────────────
 * POST   /api/tahp/knowledge/import/fetch-url            — 网页链接抓取
 * POST   /api/tahp/knowledge/import/scan-folder          — 本地文件夹批量扫描
 */
import Router from '@koa/router'
import { PassThrough } from 'stream'
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, unlinkSync, renameSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { spawnSync } from 'child_process'
import { get as httpGet } from 'http'
import { get as httpsGet } from 'https'
import { tahpPaths } from '../../services/tahp/paths'
import { safeFileStore } from '../../services/safe-file-store'
import { logger } from '../../services/logger'
import { join } from 'path'
import { randomUUID, createHash } from 'crypto'
import { load as yamlLoad, dump as yamlDump } from 'js-yaml'
import { callTahpLLM } from '../../services/tahp/llm-caller'
import { writeAuditLog } from '../../services/tahp/audit-log'

// ── 规范化映射：英文 raw key → 中文 display（一对一，保留细分） ────────────────
const _FUNC_TYPE_MAP: Record<string, string> = {
  'bug_analysis':       'Bug分析',
  'code_adaptation':    '代码适配',
  'version_adaptation': '版本适配',
  'carrier_porting':    '运营商移植',
  'self_check':         'AI自检',
  'ai_self_check':      'AI自检',
  'other':              '其他',
  // 中文 canonical 透传
  'Bug分析': 'Bug分析', '代码适配': '代码适配', '版本适配': '版本适配',
  '运营商移植': '运营商移植', 'AI自检': 'AI自检', '其他': '其他',
  // 兼容旧数据（中文大类 → 透传）
  'AI故障分析': 'AI故障分析', 'AI自动化适配': 'AI自动化适配', 'AI自检工具': 'AI自检工具',
}
/** 大类分组映射（用于 Skill 侧边栏分组） */
const _FUNC_TYPE_CATEGORY_MAP: Record<string, string> = {
  'bug_analysis': 'AI故障分析', 'Bug分析': 'AI故障分析', 'AI故障分析': 'AI故障分析',
  'code_adaptation': 'AI自动化适配', '代码适配': 'AI自动化适配',
  'version_adaptation': 'AI自动化适配', '版本适配': 'AI自动化适配',
  'carrier_porting': 'AI自动化适配', '运营商移植': 'AI自动化适配',
  'AI自动化适配': 'AI自动化适配',
  'self_check': 'AI自检工具', 'ai_self_check': 'AI自检工具', 'AI自检': 'AI自检工具', 'AI自检工具': 'AI自检工具',
  'other': '其他', '其他': '其他',
}
const _MODULE_MAP: Record<string, string> = {
  'telephony': '通信', 'kernel-driver': '驱动', 'kernel_driver': '驱动',
  'kernel': '内核',
  'power-mgmt': '功耗', 'power_mgmt': '功耗', 'shared': '通用', 'common': '通用',
  // 中文 canonical 透传
  '通信': '通信', '驱动': '驱动', '内核': '内核', '功耗': '功耗', '通用': '通用',
}
function normFuncType(v: string) { return _FUNC_TYPE_MAP[v?.trim()] ?? v?.trim() ?? '' }
function normFuncTypeRaw(v: string): string { return v?.trim() ?? '' }
function getFuncTypeCategory(v: string): string { return _FUNC_TYPE_CATEGORY_MAP[v?.trim()] ?? 'AI自动化适配' }
function normModule(v: string)   { return _MODULE_MAP[v?.trim()]    ?? v?.trim() ?? '' }

export const tahpKnowledgeRoutes = new Router()

// ─── Types ────────────────────────────────────────────────────────────────────

type ConversionStatus = 'pending' | 'done' | 'failed' | 'skipped'

interface KnowledgeDocument {
  id: string
  title: string           // inferred from filename or first heading
  filename: string        // original uploaded filename
  content: string         // full extracted plain text（保留用于 BM25 检索）
  content_markdown?: string  // LLM 规范化后的 Markdown 正文（用于阅读渲染）
  conversion_status?: ConversionStatus  // Markdown 转换状态
  conversion_note?: string   // 转换失败/跳过原因
  module: string
  category: string
  chunk_ids: string[]     // IDs of KnowledgeEntry records derived from this doc
  created_at: string
  updated_at: string
  char_count: number
  chunk_count: number
}

export interface KnowledgeEntry {
  id: string
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
  source_document_id?: string  // parent KnowledgeDocument.id
  source_task_id?: string      // 来源诊断任务 ID（智能诊断沉淀）
  applicable_versions?: string[]
  created_at: string
  updated_at: string
  expires_at?: string
  status: 'pending_review' | 'approved' | 'rejected' | 'archived' | 'deleted'
  is_verified: boolean
  validation_date?: string
  maintenance_owner?: string
  last_used_in_task?: string
  usage_count: number
}

interface EvalCase {
  id: string
  title: string
  input: string
  expected_output: string
  judgment_criteria: string
  source: 'ai_generated' | 'human'
  status: 'draft' | 'confirmed'
}

interface QualityScore {
  total: number
  structure: number       // 0-20
  exclusions: number      // 0-15
  version_range: number   // 0-20 (强制项)
  eval_cases: number      // 0-25 (强制项)
  no_conflict: number     // 0-10
  owner: number           // 0-10
  pass_gate: boolean
  blocking_reasons: string[]
}

interface ConflictResult {
  conflicting_skill_id: string
  conflicting_skill_name: string
  overlap_type: 'function' | 'version' | 'keyword'
  similarity_score: number
  suggestion: string
}

interface VersionConstraint {
  android_versions?: string[]
  chipset_platforms?: string[]
  aosp_branches?: string[]
}

interface SkillDraft {
  id: string
  skill_id: string
  skill_name: string
  domain_label: string
  module: string
  func_type: string
  content: string
  generated_from_entries: string[]
  generated_at: string
  generated_by?: string
  status: 'draft' | 'reviewing' | 'approved' | 'rejected' | 'deprecated' | 'archived'
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
  // ─── 优化计划新增字段 ────────────────────────────────
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
  // ─── 生命周期管控新增字段 ────────────────────────────────
  deprecated_at?: string
  deprecated_by?: string
  deprecate_reason?: string
  archived_at?: string
  archived_by?: string
  archived_from_status?: string  // 归档前的原始状态
  updated_at?: string
  review_action?: 'approve' | 'reject'
}

// ─── Phase 2 Types ───────────────────────────────────────────────────────────

interface ExtractedEntry {
  id: string           // temporary client-side preview ID
  content: string
  category: string
  module: string
  func_type: string
  keywords: string[]
  confidence_score: number
  source_file: string
  source_section?: string
}

interface ImportJob {
  id: string
  filename: string
  status: 'processing' | 'done' | 'error'
  progress: number     // 0-100
  stage: 'upload' | 'parse' | 'convert_markdown' | 'extract' | 'done' | 'error'
  message: string
  entries: ExtractedEntry[]
  full_text?: string   // single-file / URL: full extracted text
  markdown?: string    // single-file / URL: LLM 规范化 Markdown
  conversion_status?: ConversionStatus
  conversion_note?: string
  source_url?: string  // URL import mode
  // Batch (folder) mode: one record per file
  batch_docs?: Array<{
    filename: string
    full_text: string
    markdown?: string
    conversion_status?: ConversionStatus
    conversion_note?: string
  }>
  total_files?: number
  processed_files?: number
  created_at: string
  error?: string
}

// ─── In-memory job store (Phase 2) ───────────────────────────────────────────

const importJobs = new Map<string, ImportJob>()
const jobListeners = new Map<string, Array<(data: string) => void>>()

function emitJobEvent(jobId: string, update: Partial<ImportJob>): void {
  const job = importJobs.get(jobId)
  if (!job) return
  Object.assign(job, update)
  // Exclude full_text / markdown from SSE payload (can be megabytes; saved at job save time)
  const { full_text: _ft, markdown: _md, batch_docs, ...rest } = job
  const ssePayload = {
    ...rest,
    // batch_docs: keep only lightweight metadata over the wire
    batch_docs: batch_docs?.map(d => ({
      filename: d.filename,
      conversion_status: d.conversion_status,
      conversion_note: d.conversion_note,
    })),
  }
  const payload = JSON.stringify(ssePayload)
  for (const listener of (jobListeners.get(jobId) || [])) {
    try { listener(payload) } catch { /* ignore */ }
  }
}

// ─── SkillGen SSE job store (优化计划 Phase 3) ──────────────────────────────

interface SkillGenJob {
  id: string
  status: 'running' | 'completed' | 'error' | 'cancelled'
  stage: 'init' | 'duplicate_check' | 'similarity_check' | 'llm_generate' | 'eval_extract' | 'quality_score' | 'done' | 'error'
  progress: number
  message: string
  result?: {
    draft?: SkillDraft
    duplicate_detected?: boolean
    duplicate_drafts?: Array<{
      id: string
      skill_name: string
      status: string
      generated_at: string
      match_type: 'source_document' | 'fingerprint'
      can_merge: boolean
      is_activated: boolean
    }>
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

const skillGenJobs = new Map<string, SkillGenJob>()
const skillGenListeners = new Map<string, Array<(data: string) => void>>()

function emitSkillGenEvent(jobId: string, update: Partial<SkillGenJob>): void {
  const job = skillGenJobs.get(jobId)
  if (!job) return
  Object.assign(job, update)
  const payload = JSON.stringify(job)
  for (const listener of (skillGenListeners.get(jobId) || [])) {
    try { listener(payload) } catch { /* ignore */ }
  }
}

// TTL 清理：每5分钟清除超过30分钟的 job
setInterval(() => {
  const now = Date.now()
  for (const [id, job] of skillGenJobs) {
    const ttl = new Date(job.ttl_expires_at).getTime()
    if (now > ttl) {
      skillGenJobs.delete(id)
      skillGenListeners.delete(id)
    }
  }
}, 5 * 60 * 1000).unref()

// ─── Paths ────────────────────────────────────────────────────────────────────

function getKbDataDir(): string {
  return join(tahpPaths.knowledgeDir, '.kb-data')
}

function getEntriesDir(): string {
  return join(getKbDataDir(), 'entries')
}

function getSkillDraftsDir(): string {
  return join(getKbDataDir(), 'skill-drafts')
}

function getDocumentsDir(): string {
  return join(getKbDataDir(), 'documents')
}

function getEntryPath(entryId: string): string {
  return join(getEntriesDir(), `${entryId}.json`)
}

function getSkillDraftPath(draftId: string): string {
  return join(getSkillDraftsDir(), `${draftId}.json`)
}

function getDocumentPath(docId: string): string {
  return join(getDocumentsDir(), `${docId}.json`)
}

// ─── Utilities ────────────────────────────────────────────────────────────────

async function initDirs(): Promise<void> {
  mkdirSync(getEntriesDir(), { recursive: true })
  mkdirSync(getSkillDraftsDir(), { recursive: true })
  mkdirSync(getDocumentsDir(), { recursive: true })
}

async function readEntry(entryId: string): Promise<KnowledgeEntry | null> {
  try {
    const path = getEntryPath(entryId)
    const data = await safeFileStore.readText(path)
    return JSON.parse(data)
  } catch {
    return null
  }
}

async function writeEntry(entry: KnowledgeEntry): Promise<void> {
  const path = getEntryPath(entry.id)
  await safeFileStore.writeText(path, JSON.stringify(entry, null, 2))
}

async function readSkillDraft(draftId: string): Promise<SkillDraft | null> {
  try {
    const path = getSkillDraftPath(draftId)
    const data = await safeFileStore.readText(path)
    return JSON.parse(data)
  } catch {
    return null
  }
}

async function writeSkillDraft(draft: SkillDraft): Promise<void> {
  const path = getSkillDraftPath(draft.id)
  await safeFileStore.writeText(path, JSON.stringify(draft, null, 2))
}

async function readDocument(docId: string): Promise<KnowledgeDocument | null> {
  try {
    const data = await safeFileStore.readText(getDocumentPath(docId))
    return JSON.parse(data)
  } catch {
    return null
  }
}

async function writeDocument(doc: KnowledgeDocument): Promise<void> {
  await safeFileStore.writeText(getDocumentPath(doc.id), JSON.stringify(doc, null, 2))
}

async function listDocuments(): Promise<KnowledgeDocument[]> {
  await initDirs()
  const dir = getDocumentsDir()
  try {
    const docs: KnowledgeDocument[] = []
    for (const file of readdirSync(dir)) {
      if (!file.endsWith('.json')) continue
      try {
        docs.push(JSON.parse(readFileSync(join(dir, file), 'utf-8')))
      } catch { /* skip corrupted */ }
    }
    return docs.sort((a, b) => b.created_at.localeCompare(a.created_at))
  } catch {
    return []
  }
}

async function listEntries(): Promise<KnowledgeEntry[]> {
  await initDirs()
  const entriesDir = getEntriesDir()
  try {
    const files = readdirSync(entriesDir)
    const entries: KnowledgeEntry[] = []
    for (const file of files) {
      if (!file.endsWith('.json')) continue
      try {
        const data = readFileSync(join(entriesDir, file), 'utf-8')
        entries.push(JSON.parse(data))
      } catch (e) {
        logger.warn({ file, err: (e as Error).message }, '[kb] failed to read entry')
      }
    }
    return entries
  } catch {
    return []
  }
}

async function listSkillDrafts(): Promise<SkillDraft[]> {
  await initDirs()
  const draftsDir = getSkillDraftsDir()
  try {
    const files = readdirSync(draftsDir)
    const drafts: SkillDraft[] = []
    for (const file of files) {
      if (!file.endsWith('.json')) continue
      try {
        const data = readFileSync(join(draftsDir, file), 'utf-8')
        drafts.push(JSON.parse(data))
      } catch (e) {
        logger.warn({ file, err: (e as Error).message }, '[kb] failed to read skill draft')
      }
    }
    return drafts
  } catch {
    return []
  }
}

// ─── BM25 Search Algorithm (Phase 2) ─────────────────────────────────────────

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9一-龥_]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 1)
}

/** BM25 Okapi scoring + keyword bonus + confidence boost */
function calculateRelevance(entry: KnowledgeEntry, queryTerms: string[], avgDocLen = 200): number {
  const k1 = 1.5
  const b  = 0.75
  const docText = entry.content + ' ' + entry.keywords.join(' ')
  const docTokens = tokenize(docText)
  const docLen = docTokens.length
  const freqMap: Record<string, number> = {}
  for (const t of docTokens) freqMap[t] = (freqMap[t] || 0) + 1

  let score = 0
  for (const term of queryTerms) {
    const tf = freqMap[term] || 0
    if (tf === 0) continue
    const num = tf * (k1 + 1)
    const den = tf + k1 * (1 - b + b * docLen / Math.max(avgDocLen, 1))
    score += num / den
  }

  // Keyword exact/partial bonus
  for (const kw of entry.keywords) {
    const kwLow = kw.toLowerCase()
    for (const qt of queryTerms) {
      if (kwLow.includes(qt) || qt.includes(kwLow)) score += 2
    }
  }

  // Confidence boost
  score *= (0.5 + 0.5 * (entry.confidence_score || 0.8))
  return Math.min(100, score * 10)
}

function validateEntry(entry: Partial<KnowledgeEntry>): string[] {
  const errors: string[] = []
  if (!entry.content?.trim()) errors.push('content 不能为空')
  if (!entry.module) errors.push('module 不能为空')
  if (!entry.func_type) errors.push('func_type 不能为空')
  if (!entry.category) errors.push('category 不能为空')
  return errors
}

// ─── Phase 2 Document Parsing Helpers ────────────────────────────────────────

const MODULE_KEYWORDS: Record<string, string[]> = {
  telephony:       ['ril', 'volte', 'ims', '通话', '短信', 'sms', 'call', 'network', '网络', 'sim', 'modem', 'signal', '信号', 'telephony'],
  'kernel-driver': ['kernel', '内核', 'driver', '驱动', 'dts', 'gpio', 'i2c', 'spi', 'uart', 'interrupt', '中断', 'module_init'],
  'power-mgmt':    ['power', '功耗', 'battery', '电池', 'suspend', '休眠', 'wakeup', '唤醒', 'thermal', '温升', 'cpufreq', 'governor'],
  shared:          ['api', '接口', 'code', '代码', 'review', 'git', 'build', '编译', 'common', '通用'],
}

const FUNC_TYPE_KEYWORDS: Record<string, string[]> = {
  bug_analysis:       ['bug', '错误', 'error', 'crash', '崩溃', 'failed', '失败', '问题', 'issue', 'fix', '修复', 'exception'],
  code_adaptation:    ['适配', 'adaptation', 'migration', '迁移', 'port', '移植', 'refactor', '重构', 'porting'],
  version_adaptation: ['version', '版本', 'upgrade', '升级', 'android 1', 'release', 'api level', 'dessert', 'aosp'],
  carrier_porting:    ['carrier', '运营商', 'operator', 'cmcc', 'unicom', 'telecom', 'esim', 'mvno', 'sim'],
  ai_self_check:      ['check', '检查', 'validate', '验证', 'test', '测试', 'review', '审查', 'quality'],
}

function inferModule(content: string): string {
  const lower = content.toLowerCase()
  let best = 'shared', bestScore = 0
  for (const [mod, kws] of Object.entries(MODULE_KEYWORDS)) {
    const s = kws.filter(k => lower.includes(k)).length
    if (s > bestScore) { bestScore = s; best = mod }
  }
  return best
}

function inferFuncType(content: string): string {
  const lower = content.toLowerCase()
  let best = 'bug_analysis', bestScore = 0
  for (const [ft, kws] of Object.entries(FUNC_TYPE_KEYWORDS)) {
    const s = kws.filter(k => lower.includes(k)).length
    if (s > bestScore) { bestScore = s; best = ft }
  }
  return best
}

function inferCategory(content: string): string {
  const lower = content.toLowerCase()
  if (/error|bug|crash|failed|exception|崩溃|错误/.test(lower)) return '错误模式'
  if (/api|interface|function|method|接口/.test(lower))         return 'API规范'
  if (/best practice|最佳实践|recommend|推荐/.test(lower))       return '最佳实践'
  if (/performance|性能|optimize|优化/.test(lower))              return '性能优化'
  if (/how to|guide|指南|集成|integrate/.test(lower))            return '集成指南'
  return '其他'
}

function extractKeywords(content: string): string[] {
  const chinese = (content.match(/[\u4e00-\u9fff]{2,6}/g) || []).slice(0, 5)
  const english = (content.match(/\b[A-Z][a-zA-Z]{2,}\b/g) || []).slice(0, 5)
  return [...new Set([...chinese, ...english])].slice(0, 8)
}

/** 计算条目内容指纹（SHA256剀16位） */
function computeContentFingerprint(entries: KnowledgeEntry[]): string {
  const combined = entries.map(e => e.content).sort().join('\n')
  return createHash('sha256').update(combined, 'utf8').digest('hex').slice(0, 16)
}

/** 文档级重复检测：检查是否有草案已来自相同文档或指纹相同 */
async function checkDocumentDuplicate(entries: KnowledgeEntry[], fingerprint: string): Promise<Array<{
  id: string
  skill_name: string
  status: string
  generated_at: string
  match_type: 'source_document' | 'fingerprint'
  can_merge: boolean
  is_activated: boolean
}>> {
  const allDrafts = await listSkillDrafts()
  const sourceDocIds = new Set(
    entries.map(e => e.source_document_id).filter(Boolean) as string[]
  )
  const results: Array<{
    id: string
    skill_name: string
    status: string
    generated_at: string
    match_type: 'source_document' | 'fingerprint'
    can_merge: boolean
    is_activated: boolean
  }> = []

  for (const draft of allDrafts) {
    if (draft.status === 'rejected') continue
    // 已有 force_create 决策则跳过
    const hasForceCreate = (draft.duplicate_decisions || []).some(d => d.decision === 'force_create')
    if (hasForceCreate) continue

    // 第一层：文档源匹配
    const draftDocIds = new Set(draft.source_document_ids || [])
    const docOverlap = [...sourceDocIds].some(id => draftDocIds.has(id))
    if (docOverlap) {
      results.push({
        id: draft.id,
        skill_name: draft.skill_name,
        status: draft.status,
        generated_at: draft.generated_at,
        match_type: 'source_document',
        can_merge: draft.status === 'draft' || draft.status === 'reviewing',
        is_activated: false,
      })
      continue
    }

    // 第二层：内容指纹匹配
    if (draft.content_fingerprint && draft.content_fingerprint === fingerprint) {
      results.push({
        id: draft.id,
        skill_name: draft.skill_name,
        status: draft.status,
        generated_at: draft.generated_at,
        match_type: 'fingerprint',
        can_merge: draft.status === 'draft' || draft.status === 'reviewing',
        is_activated: false,
      })
    }
  }

  // 已激活的 Skill 也检查指纹
  const activatedSkills = getActivatedSkills()
  for (const sk of activatedSkills) {
    const skDocIds = new Set<string>()
    // 尝试从 generatedFromEntries 反查文档ID（屨5条）
    if (sourceDocIds.size > 0 && sk.generatedFromEntries.length > 0) {
      // 这里简化处理：如果 entry_ids 内容重叠则认为来源相同
      const inputEntryIds = new Set(entries.map(e => e.id))
      const overlap = sk.generatedFromEntries.filter(id => inputEntryIds.has(id)).length
      const jaccardSk = inputEntryIds.size > 0 ?
        overlap / Math.max(inputEntryIds.size, sk.generatedFromEntries.length) : 0
      if (jaccardSk > 0.5) {
        results.push({
          id: sk.skillId,
          skill_name: sk.skillId,
          status: 'activated',
          generated_at: '',
          match_type: 'source_document',
          can_merge: false,
          is_activated: true,
        })
      }
    }
    void skDocIds // suppress unused warning
  }

  return results
}

function inferConfidence(content: string): number {
  let s = 0.6
  if (content.length > 200) s += 0.1
  if (content.length > 500) s += 0.1
  if (/```|`/.test(content))                                    s += 0.05
  if (/步骤|1\.|2\.|first|then|step/i.test(content))            s += 0.05
  return Math.min(1, s)
}

function splitIntoSections(text: string): string[] {
  // Try markdown headings first
  if (/^#{1,3}\s+/m.test(text)) {
    const parts = text.split(/(?=^#{1,3}\s+)/m).filter(Boolean)
    if (parts.length > 1) return parts
  }
  // Paragraph-break splitting with aggressive merging of short fragments.
  // MIN_SECTION = 200 prevents tiny lines (common in PDF-extracted text) from
  // becoming standalone entries.
  const MIN_SECTION = 200
  const paragraphs = text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
  const merged: string[] = []
  let buf = ''
  for (const p of paragraphs) {
    if (buf) {
      buf += '\n\n' + p
      if (buf.length >= MIN_SECTION) {
        merged.push(buf); buf = ''
      }
    } else if (p.length < MIN_SECTION) {
      buf = p
    } else {
      merged.push(p)
    }
  }
  if (buf.trim()) merged.push(buf)
  return merged
}

function extractEntriesFromText(text: string, filename: string): ExtractedEntry[] {
  const sections = splitIntoSections(text)
  // No hard cap — the Document layer preserves full text for human reading.
  // Chunks here are purely for AI retrieval; more chunks = better coverage.
  return sections
    .map(s => s.trim())
    .filter(s => s.length >= 100) // minimum meaningful content per chunk
    .map(content => ({
      id: `ext-${randomUUID().slice(0, 8)}`,
      content,
      category: inferCategory(content),
      module:   inferModule(content),
      func_type: inferFuncType(content),
      keywords: extractKeywords(content),
      confidence_score: inferConfidence(content),
      source_file: filename,
    }))
}

// ─── Markdown 规范化（导入即转 Markdown） ─────────────────────────────────────
//
// 把从 PDF / DOCX / 网页中粗抽取的纯文本，用 LLM 清洗/重排成结构清晰的 Markdown，
// 严格保留原文信息（不概括、不删减、不编造）。失败/超大时降级为原文本。

const MD_SEGMENT_SIZE = 6000          // 单段送入 LLM 的最大字符数
const MD_MAX_SEGMENTS = 15            // 超过则跳过（避免过量 LLM 调用），可手动重试
const MD_MAX_TOKENS = 8192

const MARKDOWN_SYSTEM_PROMPT = `你是文档格式整理助手。把用户给出的、从 PDF/DOCX/网页中粗略抽取的纯文本整理成结构清晰、可读性强的 Markdown。

要求：
1. 严格保留原文的全部信息与措辞，禁止概括、删减、扩写或编造内容。
2. 识别并还原结构：标题层级（#/##/###）、有序与无序列表、表格、代码块、引用块。
3. 修复粗抽取常见问题：把被错误换行打断的句子拼回完整段落；去除重复的页眉页脚；删除孤立的页码行。
4. 不要输出任何前言、说明、结语或"以下是整理结果"之类的话术。
5. 直接输出整理后的 Markdown 正文本身。`

interface MarkdownConversion {
  markdown: string
  status: ConversionStatus
  note?: string
}

/** 按段落边界把长文本切成不超过 segSize 的片段 */
function splitForMarkdown(text: string, segSize: number): string[] {
  const paras = text.split(/\n{2,}/)
  const segs: string[] = []
  let buf = ''
  for (const p of paras) {
    if (buf && buf.length + p.length + 2 > segSize) {
      segs.push(buf)
      buf = p
    } else {
      buf = buf ? buf + '\n\n' + p : p
    }
  }
  if (buf.trim()) segs.push(buf)
  return segs.length ? segs : [text]
}

/**
 * 把粗抽取文本规范化为 Markdown。失败/过大时返回原文本并标记 failed/skipped。
 */
async function normalizeToMarkdown(rawText: string, filename: string): Promise<MarkdownConversion> {
  const text = (rawText || '').trim()
  if (!text) return { markdown: '', status: 'skipped', note: '空内容' }

  const segs = splitForMarkdown(text, MD_SEGMENT_SIZE)
  if (segs.length > MD_MAX_SEGMENTS) {
    return {
      markdown: rawText,
      status: 'skipped',
      note: `文档较大（${text.length} 字符 / ${segs.length} 段），已跳过自动 Markdown 转换，可在文档阅读器手动重试`,
    }
  }

  try {
    const parts: string[] = []
    for (let i = 0; i < segs.length; i++) {
      const userContent = segs.length > 1
        ? `【文档：${filename}｜第 ${i + 1}/${segs.length} 段，仅整理本段，不要补全上下文】\n\n${segs[i]}`
        : segs[i]
      const md = await callTahpLLM(MARKDOWN_SYSTEM_PROMPT, userContent, { maxTokens: MD_MAX_TOKENS })
      parts.push((md || '').trim())
    }
    const markdown = parts.join('\n\n').trim()
    if (!markdown) return { markdown: rawText, status: 'failed', note: 'LLM 返回空内容' }
    return { markdown, status: 'done' }
  } catch (err) {
    logger.warn({ filename, err: (err as Error).message }, '[kb] markdown 规范化失败，降级为原文本')
    return { markdown: rawText, status: 'failed', note: (err as Error).message }
  }
}

/** Pure-JS fallback: extract visible text from a PDF binary using stream markers */
function extractTextFromPdfBinary(buffer: Buffer): string {
  const content = buffer.toString('latin1')
  const lines: string[] = []

  // Find all BT...ET blocks (Begin Text / End Text in PDF)
  const btEtRegex = /BT[\s\S]*?ET/g
  let match
  while ((match = btEtRegex.exec(content)) !== null) {
    const block = match[0]
    // "(text) Tj" — single string operators
    const tjMatches = block.match(/\(([^)]*)\)\s*Tj/g) || []
    for (const m of tjMatches) {
      const text = m.replace(/\(([^)]*)\)\s*Tj/, '$1')
      lines.push(decodePdfString(text))
    }
    // "[(text)(text)] TJ" — array operators
    const tjArrMatches = block.match(/\[([^\]]*)\]\s*TJ/g) || []
    for (const m of tjArrMatches) {
      const inner = m.replace(/^\[/, '').replace(/\]\s*TJ$/, '')
      const parts = inner.match(/\(([^)]*)\)/g) || []
      for (const p of parts) lines.push(decodePdfString(p.slice(1, -1)))
    }
  }

  // Also try extracting text between parentheses in stream objects (works for some PDFs)
  if (lines.length === 0) {
    const streamRegex = /stream\r?\n([\s\S]*?)\r?\nendstream/g
    while ((match = streamRegex.exec(content)) !== null) {
      const stream = match[1]
      const parts = stream.match(/\(([^)]{2,})\)/g) || []
      for (const p of parts) {
        const text = decodePdfString(p.slice(1, -1))
        if (text.length > 2 && /[a-zA-Z一-龥]/.test(text)) lines.push(text)
      }
    }
  }

  return lines.filter(l => l.trim().length > 0).join('\n')
}

function decodePdfString(s: string): string {
  return s
    .replace(/\\([0-7]{1,3})/g, (_, oct) => String.fromCharCode(parseInt(oct, 8)))
    .replace(/\\n/g, '\n').replace(/\\r/g, '\r').replace(/\\t/g, '\t')
    .replace(/\\\\/g, '\\').replace(/\\[()]/g, m => m[1])
}

/** Strip HTML tags and common entities, returning readable plain text */
function htmlToText(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<head[\s\S]*?<\/head>/gi, '')
    .replace(/<nav[\s\S]*?<\/nav>/gi, '')
    .replace(/<footer[\s\S]*?<\/footer>/gi, '')
    .replace(/<(br|p|div|li|tr|h[1-6])[^>]*>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCharCode(parseInt(h, 16)))
    .replace(/&#([0-9]+);/g, (_, d) => String.fromCharCode(parseInt(d, 10)))
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/** Fetch a URL and return its text content (HTML is auto-stripped), follows redirects */
function fetchUrlText(url: string, maxRedirects = 5): Promise<string> {
  return new Promise((resolve, reject) => {
    let parsed: URL
    try { parsed = new URL(url) } catch { reject(new Error('无效的 URL')); return }

    const getter = parsed.protocol === 'https:' ? httpsGet : httpGet
    const req = getter(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; TAHP-KnowledgeBot/1.0)', 'Accept': 'text/html,text/plain' },
    }, (res) => {
      // Follow redirects
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        if (maxRedirects <= 0) { reject(new Error('重定向次数过多')); return }
        const next = res.headers.location.startsWith('http') ? res.headers.location : `${parsed.origin}${res.headers.location}`
        resolve(fetchUrlText(next, maxRedirects - 1))
        res.resume()
        return
      }
      if (res.statusCode && res.statusCode >= 400) {
        reject(new Error(`HTTP ${res.statusCode}`)); res.resume(); return
      }
      const chunks: Buffer[] = []
      res.on('data', (c: Buffer) => chunks.push(c))
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf-8')
        const ct = res.headers['content-type'] || ''
        resolve(ct.includes('text/html') ? htmlToText(body) : body)
      })
      res.on('error', reject)
    })
    req.on('error', reject)
    req.setTimeout(20000, () => { req.destroy(); reject(new Error('请求超时（20s）')) })
  })
}

type ProgressFn = (progress: number, message: string) => void

/**
 * 检测乱码/字体编码错误的文本（PDF CID 字体映射失败产生的）。
 * 如果超过 35% 的非空白字符落在已知合法 Unicode 范围之外，则认为是乱码。
 * 阈值从 25% 提高到 35%，避免把混有少量特殊符号的正常中文误判。
 */
function isGarbledText(text: string): boolean {
  if (text.length < 10) return true
  let bad = 0
  let total = 0
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i)
    if (c === 9 || c === 10 || c === 13 || c === 32) continue // whitespace OK
    total++
    const ok =
      (c >= 33 && c <= 126)          || // ASCII printable
      (c >= 0x0080 && c <= 0x024F)   || // Latin-1 Supplement + Latin Extended-A/B
      (c >= 0x0300 && c <= 0x036F)   || // Combining Diacritical Marks
      (c >= 0x2000 && c <= 0x206F)   || // General Punctuation
      (c >= 0x2100 && c <= 0x214F)   || // Letterlike Symbols (℃ 等)
      (c >= 0x2600 && c <= 0x27BF)   || // Misc Symbols + Dingbats
      (c >= 0x3000 && c <= 0x303F)   || // CJK Symbols & Punctuation
      (c >= 0x3040 && c <= 0x30FF)   || // Hiragana + Katakana
      (c >= 0x3400 && c <= 0x4DBF)   || // CJK Extension A（扩展汉字）
      (c >= 0x4E00 && c <= 0x9FFF)   || // CJK Unified Ideographs（常用汉字）
      (c >= 0xA000 && c <= 0xA4CF)   || // Yi Syllables
      (c >= 0xF900 && c <= 0xFAFF)   || // CJK Compatibility Ideographs
      (c >= 0xFB00 && c <= 0xFDFF)   || // Alphabetic Presentation Forms
      (c >= 0xFE30 && c <= 0xFE4F)   || // CJK Compatibility Forms
      (c >= 0xFF00 && c <= 0xFFEF)      // Halfwidth/Fullwidth Forms
    if (!ok) bad++
  }
  if (total === 0) return true
  return bad / total > 0.35 // 阈值 35%
}

/**
 * 尝试用 pdf-parse (pdf.js 引擎) 提取 PDF 文本。
 * 支持 ToUnicode CMap，可以正确处理 CID 嵌入字体的中文 PDF。
 * 如果包未安装，会自动执行 npm install 安装，完全透明，无需用户干预。
 * 安装失败或解析失败则返回 null，降级到下一个 Tier。
 */
async function tryPdfParse(buffer: Buffer, onProgress?: ProgressFn): Promise<string | null> {
  type PdfParseResult = { text: string; numpages: number }
  type PdfParseFn = (buf: Buffer, opts?: Record<string, unknown>) => Promise<PdfParseResult>

  // 尝试直接 require（已安装时走这条路）
  const tryRequire = (): PdfParseFn | null => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      return require('pdf-parse') as PdfParseFn
    } catch {
      return null
    }
  }

  let pdfParseFn = tryRequire()

  // 包未安装 → 自动 npm install，和 pdfminer 的自动安装逻辑对称
  if (!pdfParseFn) {
    logger.info('[kb] pdf-parse not installed, attempting auto npm install...')
    onProgress?.(46, '首次使用，正在自动安装 PDF 解析引擎（pdf-parse），请稍候...')

    // 在 tahp-console 根目录（process.cwd()）下执行 npm install
    // Windows 需要 shell: true 才能找到 npm.cmd
    const installDir = process.cwd()
    const r = spawnSync('npm', ['install', 'pdf-parse', '--prefer-offline'], {
      encoding: 'utf-8',
      timeout: 120000,
      cwd: installDir,
      shell: true, // Windows npm.cmd 兼容
    })

    if (r.status === 0) {
      logger.info('[kb] pdf-parse installed successfully via npm')
      onProgress?.(47, '安装完成，正在解析 PDF...')
      pdfParseFn = tryRequire()
    } else {
      logger.warn(`[kb] npm install pdf-parse failed (cwd=${installDir}): ${(r.stderr || r.error?.message || '').slice(0, 300)}`)
    }
  }

  if (!pdfParseFn) return null

  try {
    const result = await pdfParseFn(buffer, { max: 0 }) // max: 0 = 解析全部页面
    return (result.text || '').trim() || null
  } catch (e: unknown) {
    logger.debug(`[kb] pdf-parse parse error: ${(e as Error).message?.slice(0, 200)}`)
    return null
  }
}

/** All Python executables to try, in priority order (Windows + Unix) */
const PYTHON_CMDS = ['python3', 'python', 'py']
const PDFMINER_SCRIPT = 'import sys; from pdfminer.high_level import extract_text; print(extract_text(sys.argv[1]))'

async function extractPdfText(buffer: Buffer, _filename: string, onProgress?: ProgressFn): Promise<string> {
  const tmpPath = join(tmpdir(), `kb-${randomUUID().slice(0, 8)}.pdf`)
  try {
    writeFileSync(tmpPath, buffer)

    // Tier 1: try pdfminer with every Python variant (python3 / python / py)
    for (const py of PYTHON_CMDS) {
      const r = spawnSync(py, ['-c', PDFMINER_SCRIPT, tmpPath], { encoding: 'utf-8', timeout: 30000 })
      if (r.status === 0 && r.stdout?.trim()) return r.stdout
    }
    // Tier 1b: try PyPDF2 / pdftotext as bonus paths (may work without pdfminer)
    for (const [cmd, args] of [
      ['python3', ['-c', 'import sys, PyPDF2; r=PyPDF2.PdfReader(sys.argv[1]); print("\\n".join([p.extract_text() or "" for p in r.pages]))', tmpPath]],
      ['python',  ['-c', 'import sys, PyPDF2; r=PyPDF2.PdfReader(sys.argv[1]); print("\\n".join([p.extract_text() or "" for p in r.pages]))', tmpPath]],
      ['py',      ['-c', 'import sys, PyPDF2; r=PyPDF2.PdfReader(sys.argv[1]); print("\\n".join([p.extract_text() or "" for p in r.pages]))', tmpPath]],
      ['pdftotext', [tmpPath, '-']],
    ] as [string, string[]][]) {
      const r = spawnSync(cmd, args, { encoding: 'utf-8', timeout: 30000 })
      if (r.status === 0 && r.stdout?.trim()) return r.stdout
    }

    // Tier 2: auto-install pdfminer.six via every pip variant and retry
    logger.info('[kb] pdfminer.six not found, attempting auto-install...')
    onProgress?.(40, '首次使用 PDF 导入，正在自动安装解析工具（pdfminer.six），请稍候约30秒...')

    // Build pip commands: direct pip executables + python -m pip style
    const pipCmds: [string, string[]][] = [
      ['pip3',     ['install', 'pdfminer.six', '--quiet']],
      ['pip',      ['install', 'pdfminer.six', '--quiet']],
      ['python3',  ['-m', 'pip', 'install', 'pdfminer.six', '--quiet']],
      ['python',   ['-m', 'pip', 'install', 'pdfminer.six', '--quiet']],
      ['py',       ['-m', 'pip', 'install', 'pdfminer.six', '--quiet']],
      // fallback with --user in case of permission issues
      ['pip3',     ['install', 'pdfminer.six', '--quiet', '--user']],
      ['pip',      ['install', 'pdfminer.six', '--quiet', '--user']],
      ['python3',  ['-m', 'pip', 'install', 'pdfminer.six', '--quiet', '--user']],
      ['python',   ['-m', 'pip', 'install', 'pdfminer.six', '--quiet', '--user']],
      ['py',       ['-m', 'pip', 'install', 'pdfminer.six', '--quiet', '--user']],
    ]
    for (const [pipCmd, pipArgs] of pipCmds) {
      const install = spawnSync(pipCmd, pipArgs, { encoding: 'utf-8', timeout: 90000 })
      if (install.status === 0) {
        onProgress?.(50, '安装完成，正在解析 PDF...')
        for (const py of PYTHON_CMDS) {
          const r = spawnSync(py, ['-c', PDFMINER_SCRIPT, tmpPath], { encoding: 'utf-8', timeout: 30000 })
          if (r.status === 0 && r.stdout?.trim()) {
            logger.info(`[kb] pdfminer.six installed successfully via ${pipCmd}`)
            return r.stdout
          }
        }
      } else {
        logger.debug(`[kb] ${pipCmd} ${pipArgs.join(' ')} failed: ${install.stderr?.slice(0, 200) || install.error?.message || 'exit ' + install.status}`)
      }
    }

    // Tier 3: pdf-parse (pdf.js 引擎，支持 ToUnicode CMap，可正确处理中文 CID 字体)
    logger.info('[kb] trying pdf-parse as Tier 3 extractor...')
    onProgress?.(45, '尝试使用 pdf-parse 解析 PDF...')
    const pdfParseText = await tryPdfParse(buffer, onProgress)
    if (pdfParseText && pdfParseText.length >= 50 && !isGarbledText(pdfParseText)) {
      logger.info('[kb] pdf-parse extracted text successfully')
      return pdfParseText
    }
    if (pdfParseText && pdfParseText.length >= 50) {
      // pdf-parse 提取到了内容但检测到乱码 — 保守起见仍然返回（用户选择）
      logger.warn('[kb] pdf-parse returned possibly garbled text, returning anyway')
      return pdfParseText
    }

    // Tier 4: pure-JS 二进制提取（最后备选，仅适用于非加密的纯文本 PDF）
    logger.warn('[kb] pdf-parse unavailable/empty, falling back to pure-JS binary extraction')
    onProgress?.(48, '尝试纯 JS 方式解析 PDF...')
    const fallback = extractTextFromPdfBinary(buffer)
    if (fallback.trim().length >= 50 && !isGarbledText(fallback)) return fallback

    // 所有 Tier 均失败
    throw new Error(
      '无法正确解析此 PDF（可能使用了嵌入字体或加密）。\n\n' +
      '建议解决方案：\n' +
      '① 运行 npm install 后重启服务（已内置 pdf-parse 解析引擎）\n' +
      '② 或安装 Python 后运行：py -m pip install pdfminer.six\n' +
      '③ 或将 PDF 另存为 TXT/Markdown 格式后再导入'
    )
  } finally {
    try { unlinkSync(tmpPath) } catch { /* ignore */ }
  }
}

const DOCX_SCRIPT = 'import sys, docx; d=docx.Document(sys.argv[1]); print("\\n".join([p.text for p in d.paragraphs if p.text]))'

async function extractDocxText(buffer: Buffer, _filename: string, onProgress?: ProgressFn): Promise<string> {
  const tmpPath = join(tmpdir(), `kb-${randomUUID().slice(0, 8)}.docx`)
  try {
    writeFileSync(tmpPath, buffer)

    // Tier 1: try python-docx with every Python variant
    for (const py of PYTHON_CMDS) {
      const r = spawnSync(py, ['-c', DOCX_SCRIPT, tmpPath], { encoding: 'utf-8', timeout: 30000 })
      if (r.status === 0 && r.stdout?.trim()) return r.stdout
    }

    // Tier 2: auto-install python-docx via every pip variant and retry
    onProgress?.(40, '首次使用 DOCX 导入，正在自动安装解析工具（python-docx），请稍候...')
    const docxPipCmds: [string, string[]][] = [
      ['pip3',    ['install', 'python-docx', '--quiet']],
      ['pip',     ['install', 'python-docx', '--quiet']],
      ['python3', ['-m', 'pip', 'install', 'python-docx', '--quiet']],
      ['python',  ['-m', 'pip', 'install', 'python-docx', '--quiet']],
      ['py',      ['-m', 'pip', 'install', 'python-docx', '--quiet']],
      ['pip3',    ['install', 'python-docx', '--quiet', '--user']],
      ['pip',     ['install', 'python-docx', '--quiet', '--user']],
      ['python3', ['-m', 'pip', 'install', 'python-docx', '--quiet', '--user']],
      ['python',  ['-m', 'pip', 'install', 'python-docx', '--quiet', '--user']],
      ['py',      ['-m', 'pip', 'install', 'python-docx', '--quiet', '--user']],
    ]
    for (const [pipCmd, pipArgs] of docxPipCmds) {
      const install = spawnSync(pipCmd, pipArgs, { encoding: 'utf-8', timeout: 90000 })
      if (install.status === 0) {
        onProgress?.(50, '安装完成，正在解析 DOCX...')
        for (const py of PYTHON_CMDS) {
          const r = spawnSync(py, ['-c', DOCX_SCRIPT, tmpPath], { encoding: 'utf-8', timeout: 30000 })
          if (r.status === 0 && r.stdout?.trim()) return r.stdout
        }
      }
    }

    // Tier 3: DOCX is a zip — extract text from word/document.xml
    logger.warn('[kb] all Python paths exhausted for DOCX, falling back to raw XML extraction')
    onProgress?.(45, '尝试直接解析 DOCX XML...')
    const fallback = extractTextFromDocxBinary(buffer)
    if (fallback.trim().length >= 20) return fallback

    throw new Error(
      '无法解析 DOCX — 请手动安装 python-docx：\n' +
      '  Windows: py -m pip install python-docx\n' +
      '  macOS/Linux: pip3 install python-docx\n' +
      '安装后重新导入。'
    )
  } finally {
    try { unlinkSync(tmpPath) } catch { /* ignore */ }
  }
}

/** Extract text from DOCX (ZIP) by reading word/document.xml directly */
function extractTextFromDocxBinary(buffer: Buffer): string {
  // DOCX is a ZIP. Look for the PK signature and try to find XML text between <w:t> tags.
  // This is a simplified fallback that works without any zip library.
  const str = buffer.toString('utf-8', 0, Math.min(buffer.length, 2_000_000))
  const matches = str.match(/<w:t[^>]*>([^<]+)<\/w:t>/g) || []
  return matches
    .map(m => m.replace(/<w:t[^>]*>/, '').replace(/<\/w:t>/, '').trim())
    .filter(Boolean)
    .join('\n')
}

// ─── Phase 4: Quality Score + Conflict Detection ─────────────────────────────

/** 扫描已激活的 Adapt Skill 列表（从 skills/.claude/skills/ 目录）
 * 自动跳过 frontmatter 中 status: deprecated / archived 的 Skill
 */
function getActivatedSkills(): Array<{ skillId: string; module: string; func_type: string; content: string; keywords: string[]; generatedFromEntries: string[]; status?: string }> {
  const root = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
  if (!existsSync(root)) return []
  const results: Array<{ skillId: string; module: string; func_type: string; content: string; keywords: string[]; generatedFromEntries: string[]; status?: string }> = []
  try {
    for (const entry of readdirSync(root, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.name.startsWith('.')) continue
      const skillMd = join(root, entry.name, 'SKILL.md')
      if (!existsSync(skillMd)) continue
      try {
        const content = readFileSync(skillMd, 'utf-8')
        const fmMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)
        const fmRaw = fmMatch?.[1] || ''
        // 检查 frontmatter status，跳过已废弃/已归档的 Skill
        const statusMatch = fmRaw.match(/^status:\s*['"]?(\w+)['"]?\s*$/m)
        const fmStatus = statusMatch?.[1]?.trim() || ''
        if (fmStatus === 'deprecated' || fmStatus === 'archived') continue
        const modMatch = fmRaw.match(/^module:\s*(.+)$/m)
        const ftMatch  = fmRaw.match(/^func_type:\s*(.+)$/m)
        // 读取生成来源的 entry_ids（生成时写入 frontmatter）
        const genFromMatch = fmRaw.match(/^generated_from_entries:\s*'(.+)'$/m)
        let generatedFromEntries: string[] = []
        try {
          if (genFromMatch?.[1]) generatedFromEntries = JSON.parse(genFromMatch[1])
        } catch { /* ignore */ }
        results.push({
          skillId: entry.name,
          module:    normModule(modMatch?.[1]?.trim() || ''),
          func_type: normFuncType(ftMatch?.[1]?.trim() || ''),
          content,
          keywords: extractKeywords(content),
          generatedFromEntries,
          status: fmStatus || 'active',
        })
      } catch { /* skip */ }
    }
  } catch { /* root not found */ }
  return results
}

/**
 * 计算 Skill 草稿的 7 维质量得分
 */
function calculateQualityScore(draft: SkillDraft, conflicts: ConflictResult[]): QualityScore {
  const content = draft.content || ''
  const blocking_reasons: string[] = []

  // ── 1. 结构完整性 (0-20) ────────────────────────────────────────
  const sections = [
    /##\s+适用场景[\s\S]{30,}/,
    /##\s+核心处理方法[\s\S]{30,}/,
    /##\s+示例[\s\S]{30,}/,
    /##\s+注意事项[\s\S]{10,}/,
  ]
  const sectionScore = sections.filter(r => r.test(content)).length
  const structure = Math.round((sectionScore / sections.length) * 20)

  // ── 2. 不适用情况 (0-15) ────────────────────────────────────────
  const hasExclusions = (draft.exclusion_cases?.length ?? 0) >= 2 ||
    (/##\s+不适用情况[\s\S]*?(?:##|$)/.test(content) && !/待人工确认|待补充|⚠️\s*$/.test(
      (content.match(/##\s+不适用情况([\s\S]*?)(?=##|$)/)?.[1] || '')
    ))
  const exclusions = hasExclusions ? 15 : (
    // 有内容但少于2条给一半分
    ((draft.exclusion_cases?.length ?? 0) === 1) ? 8 : 0
  )

  // ── 3. 版本范围 (0-20) — 强制项 ────────────────────────────────
  const hasVersionRange =
    (draft.version_constraints?.android_versions?.length ?? 0) > 0 ||
    /Android\s+\d{1,2}|API\s+Level\s+\d+/i.test(content)
  const version_range = hasVersionRange ? 20 : 0
  if (!hasVersionRange) blocking_reasons.push('版本范围未填写（必填）')

  // ── 4. eval 用例 (0-25) — 强制项 ────────────────────────────────
  const confirmedEvals = (draft.eval_cases || []).filter(e => e.status === 'confirmed').length
  const totalEvals     = (draft.eval_cases || []).length
  let eval_cases = 0
  if (confirmedEvals >= 2)     eval_cases = 25
  else if (confirmedEvals >= 1) eval_cases = 15
  else if (totalEvals >= 2)    eval_cases = 10  // 有草稿但未确认
  else if (totalEvals >= 1)    eval_cases = 5
  if (totalEvals < 2) blocking_reasons.push('至少需要 2 个 eval 用例（必填）')

  // ── 5. 无冲突 (0-10) ────────────────────────────────────────────
  const highConflicts = conflicts.filter(c => c.similarity_score > 0.7).length
  const no_conflict = highConflicts === 0 ? 10 : highConflicts === 1 ? 5 : 0

  // ── 6. 维护人 (0-10) ────────────────────────────────────────────
  const owner = (draft.maintenance_owner?.trim().length ?? 0) > 0 ? 10 : 0

  const total = structure + exclusions + version_range + eval_cases + no_conflict + owner
  const pass_gate = blocking_reasons.length === 0 && total >= 60

  return { total, structure, exclusions, version_range, eval_cases, no_conflict, owner, pass_gate, blocking_reasons }
}

/**
 * 对比已激活的 Skill，检测与当前草稿的冲突
 */
function detectConflicts(draft: SkillDraft, activatedSkills: ReturnType<typeof getActivatedSkills>): ConflictResult[] {
  const results: ConflictResult[] = []
  const draftTerms = tokenize(draft.content)
  const draftKws   = extractKeywords(draft.content)

  for (const sk of activatedSkills) {
    if (sk.skillId === draft.skill_id) continue // 跳过自身
    const skTerms = tokenize(sk.content)

    // BM25 交叉搜索（简化：看关键词重叠率）
    const kwOverlap = draftKws.filter(k => sk.keywords.includes(k)).length
    const kwSim = draftKws.length > 0 ? kwOverlap / draftKws.length : 0

    // 功能类型匹配 + 相同模块
    const sameFuncModule = sk.module === draft.module && sk.func_type === draft.func_type

    // 内容相似度（共同 token 比率）
    const commonTerms = draftTerms.filter(t => skTerms.includes(t)).length
    const contentSim = draftTerms.length > 0 ? commonTerms / Math.max(draftTerms.length, skTerms.length) : 0

    if (sameFuncModule && contentSim > 0.3) {
      results.push({
        conflicting_skill_id: sk.skillId,
        conflicting_skill_name: sk.skillId,
        overlap_type: 'function',
        similarity_score: contentSim,
        suggestion: contentSim > 0.7 ? '建议合并到现有 Skill 或明确区分使用场景' : '请确认两者的使用场景是否有明确区别',
      })
    } else if (kwSim > 0.6) {
      results.push({
        conflicting_skill_id: sk.skillId,
        conflicting_skill_name: sk.skillId,
        overlap_type: 'keyword',
        similarity_score: kwSim,
        suggestion: '关键词高度重叠，请确认两者处理的问题是否不同',
      })
    }
  }

  return results.sort((a, b) => b.similarity_score - a.similarity_score)
}

/** 解析 LLM 输出中的 EVAL_CASE 块 */
function parseEvalCasesFromLLM(text: string): EvalCase[] {
  const cases: EvalCase[] = []
  const blocks = text.split('EVAL_CASE_START')
  for (const block of blocks.slice(1)) {
    const end = block.indexOf('EVAL_CASE_END')
    if (end < 0) continue
    const inner = block.slice(0, end).trim()
    const get = (key: string): string => {
      const m = inner.match(new RegExp(`^${key}:\\s*([^\\n]+)`, 'm'))
      return m?.[1]?.trim() || ''
    }
    const title = get('title')
    if (!title) continue
    cases.push({
      id: `ec-${randomUUID().slice(0, 8)}`,
      title,
      input: get('input'),
      expected_output: get('expected_output'),
      judgment_criteria: get('judgment_criteria'),
      source: 'ai_generated',
      status: 'draft',
    })
  }
  return cases
}

/** Skill 生成 Prompt */
function buildSkillGenPrompt(
  entries: KnowledgeEntry[],
  module: string,
  funcType: string,
  documents?: KnowledgeDocument[],
): { system: string; user: string } {
  const funcTypeNames: Record<string, string> = {
    bug_analysis: 'Bug 分析', code_adaptation: '代码适配',
    version_adaptation: '版本适配', carrier_porting: '运营商移植', ai_self_check: 'AI 自检',
  }
  const moduleNames: Record<string, string> = {
    telephony: '通信模块', 'kernel-driver': '内核驱动', 'power-mgmt': '功耗管理', shared: '共享模块',
  }

  // ── 构建内容来源文本：优先使用完整文档，fallback 到条目拼接 ──────────────
  let sourceContentText = ''
  let sourceLabel = ''

  if (documents && documents.length > 0) {
    // 使用完整文档内容（每个文档截取前 8000 字符）
    sourceContentText = documents.map((doc, i) => {
      const content = doc.content.length > 8000
        ? doc.content.slice(0, 8000) + `\n\n... (文档截断，原文共 ${doc.char_count} 字符)`
        : doc.content
      return `--- 文档 ${i + 1}: ${doc.title} (${doc.char_count} 字符) ---\n${content}`
    }).join('\n\n')
    const totalChars = documents.reduce((s, d) => s + d.char_count, 0)
    sourceLabel = `${documents.length} 个源文档（共 ${totalChars} 字符）`
  } else {
    // fallback: 使用条目拼接
    sourceContentText = entries.slice(0, 20).map((e, i) =>
      `--- 条目 ${i + 1} ---\n${e.content.slice(0, 800)}`
    ).join('\n\n')
    sourceLabel = `${entries.length} 条知识条目`
  }

  // ── 条目元数据（辅助分类） ────────────────────────────────────────────
  const entriesMeta = entries.slice(0, 20).map((e, i) =>
    `- 条目 ${i + 1}: 关键词=[${e.keywords.slice(0, 5).join(', ')}], 置信度=${e.confidence_score}, 分类=${e.category}`
  ).join('\n')

  const system = `你是 TAHP 平台的 Skill 生成助手，专注于 Android 底软开发领域的知识整合。
你的任务是将源文档内容提炼为结构化、可执行的 Skill 文档，供 AI Agent 在处理开发任务时参考。
请尽量保留源文档中的关键技术细节、代码片段、步骤说明，不要遗漏重要信息。
请使用中文输出。`

  const user = `# 任务：生成 Skill 文档

## 模块：${moduleNames[module] || module}
## 业务类型：${funcTypeNames[funcType] || funcType}
## 数据来源：${sourceLabel}

## 源文档内容（完整）

${sourceContentText}

## 知识条目元数据（辅助分类参考）

${entriesMeta}

---

请按以下模板生成 Skill 文档（直接输出 Markdown 内容，不要额外解释）：
注意：请充分利用源文档中的完整内容，保留关键技术细节、代码示例和处理步骤，不要省略重要信息。

# [基于源文档概括的Skill名称]

## 适用场景
- 适用模块：${moduleNames[module] || module}
- 适用业务类型：${funcTypeNames[funcType] || funcType}
- [列出2-3个典型触发条件，基于源文档提炼]

## ⚠️ 不适用情况（请人工补充）
- [基于源文档推断，至少写2条，并注明"待人工确认"标记]

## 核心处理方法
[将源文档中的关键步骤/方法提炼为有序步骤列表，具体可操作，保留代码片段]

## 示例

### 正例
[从源文档中选取最典型的案例，格式化展示，保留完整技术细节]

### ⚠️ 反例（请人工补充）
[如果源文档有反例则提取，否则写"待人工补充：[描述补充哪类反例]"]

## ⚠️ 版本与平台约束（请确认）
- Android 版本范围：[待确认，如源文档有提及则填入]
- 芯片平台：[待确认]
- AOSP 分支：[待确认]

## 注意事项
[提炼源文档中的注意事项、常见陷阱]

## 维护信息
- 维护人：[待指定]
- 生成来源：${sourceLabel}
- 模板版本：v1.0

---

然后输出 2-3 个 eval 用例（每个用一对标记包裹）：

EVAL_CASE_START
title: [用例标题（10字以内）]
input: [输入场景描述（100字以内）]
expected_output: [期望的Skill输出或处理结果（100字以内）]
judgment_criteria: [pass/fail判定标准（50字以内）]
EVAL_CASE_END
`

  return { system, user }
}

// ─── Routes ────────────────────────────────────────────────────────────────────

// POST /api/tahp/knowledge/entries — 创建知识条目
tahpKnowledgeRoutes.post('/api/tahp/knowledge/entries', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const {
      content, category, module, func_type, keywords = [],
      source_file, source_page, source_section, source_url,
      applicable_versions = [], maintenance_owner,
    } = body

    const errors = validateEntry({ content, category, module, func_type } as any)
    if (errors.length > 0) {
      ctx.status = 400
      ctx.body = { success: false, error: errors.join('; ') }
      return
    }

    const entry: KnowledgeEntry = {
      id: `kb-${randomUUID().slice(0, 8)}`,
      content: String(content),
      category: String(category),
      module: String(module),
      func_type: String(func_type),
      keywords: Array.isArray(keywords) ? keywords.map(String) : [],
      confidence_score: 0.8,
      source_file: source_file ? String(source_file) : undefined,
      source_page: typeof source_page === 'number' ? source_page : undefined,
      source_section: source_section ? String(source_section) : undefined,
      source_url: source_url ? String(source_url) : undefined,
      applicable_versions: Array.isArray(applicable_versions) ? applicable_versions.map(String) : [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      status: 'pending_review',
      is_verified: false,
      maintenance_owner: maintenance_owner ? String(maintenance_owner) : undefined,
      usage_count: 0,
    }

    await writeEntry(entry)
    logger.info({ entryId: entry.id, module }, '[kb] entry created')
    ctx.body = { success: true, data: entry }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to create entry')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

/**
 * 智能诊断「沉淀为知识库」共享入口：从诊断报告创建一条知识条目（pending_review）。
 * 供 bug-analysis 路由调用，避免重复的写盘逻辑。
 */
export async function depositDistilledEntry(params: {
  content: string
  module?: string
  func_type?: string
  category?: string
  keywords?: string[]
  source_task_id?: string
  jira_key?: string
}): Promise<KnowledgeEntry> {
  await initDirs()
  const now = new Date().toISOString()
  const entry: KnowledgeEntry = {
    id: `kb-${randomUUID().slice(0, 8)}`,
    content: params.content,
    category: params.category || '错误模式',
    module: params.module || 'shared',
    func_type: params.func_type || 'bug_analysis',
    keywords: params.keywords?.length ? params.keywords : extractKeywords(params.content),
    confidence_score: 0.8,
    source_file: params.jira_key ? `JIRA ${params.jira_key}` : undefined,
    source_task_id: params.source_task_id,
    created_at: now,
    updated_at: now,
    status: 'pending_review',
    is_verified: false,
    usage_count: 0,
  }
  await writeEntry(entry)
  logger.info({ entryId: entry.id, task: params.source_task_id }, '[kb] distilled entry deposited')
  return entry
}

/** 同一诊断任务已沉淀过时复用条目，避免重复写入知识库 */
export async function findDistilledEntryByTaskId(taskId: string): Promise<KnowledgeEntry | null> {
  if (!taskId) return null
  await initDirs()
  const all = await listEntries()
  const matches = all.filter(e => e.source_task_id === taskId && e.status !== 'archived')
  if (!matches.length) return null
  matches.sort((a, b) => Date.parse(b.updated_at || b.created_at) - Date.parse(a.updated_at || a.created_at))
  return matches[0]
}

// GET /api/tahp/knowledge/entries — 查询知识库
tahpKnowledgeRoutes.get('/api/tahp/knowledge/entries', async (ctx) => {
  try {
    await initDirs()
    const { module, func_type, status, sort_by = 'created_at', sort_order = 'desc', limit = '20', offset = '0' } = ctx.query

    let entries = await listEntries()

    // 筛选
    if (module) entries = entries.filter(e => e.module === module)
    if (func_type) entries = entries.filter(e => e.func_type === func_type)
    if (status) entries = entries.filter(e => e.status === status)

    // 排序
    const sortKey = sort_by as keyof KnowledgeEntry
    entries.sort((a, b) => {
      const aVal = a[sortKey] ?? ''
      const bVal = b[sortKey] ?? ''
      const cmp = String(aVal) > String(bVal) ? 1 : String(aVal) < String(bVal) ? -1 : 0
      return sort_order === 'asc' ? cmp : -cmp
    })

    // 分页
    const pageLimit = Math.min(parseInt(String(limit)) || 20, 100)
    const pageOffset = parseInt(String(offset)) || 0
    const total = entries.length
    const paginated = entries.slice(pageOffset, pageOffset + pageLimit)

    ctx.body = {
      success: true,
      data: {
        entries: paginated,
        total,
        limit: pageLimit,
        offset: pageOffset,
      },
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to list entries')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/entries/:entryId — 获取单个条目
tahpKnowledgeRoutes.get('/api/tahp/knowledge/entries/:entryId', async (ctx) => {
  try {
    const { entryId } = ctx.params
    const entry = await readEntry(entryId)
    if (!entry) {
      ctx.status = 404
      ctx.body = { success: false, error: `条目 ${entryId} 不存在` }
      return
    }
    ctx.body = { success: true, data: entry }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to read entry')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// PUT /api/tahp/knowledge/entries/:entryId — 更新知识条目
tahpKnowledgeRoutes.put('/api/tahp/knowledge/entries/:entryId', async (ctx) => {
  try {
    const { entryId } = ctx.params
    const entry = await readEntry(entryId)
    if (!entry) {
      ctx.status = 404
      ctx.body = { success: false, error: `条目 ${entryId} 不存在` }
      return
    }

    const body = (ctx.request.body || {}) as Record<string, unknown>
    const updates: Partial<KnowledgeEntry> = {}

    // 只允许更新特定字段
    if (body.content !== undefined) updates.content = String(body.content)
    if (body.keywords !== undefined) updates.keywords = Array.isArray(body.keywords) ? body.keywords.map(String) : []
    if (body.confidence_score !== undefined) updates.confidence_score = Number(body.confidence_score)
    if (body.status !== undefined) updates.status = String(body.status) as any
    if (body.maintenance_owner !== undefined) updates.maintenance_owner = body.maintenance_owner ? String(body.maintenance_owner) : undefined
    if (body.validation_date !== undefined) updates.validation_date = body.validation_date ? String(body.validation_date) : undefined
    if (body.is_verified !== undefined) updates.is_verified = Boolean(body.is_verified)

    const updated: KnowledgeEntry = { ...entry, ...updates, updated_at: new Date().toISOString() }
    await writeEntry(updated)
    logger.info({ entryId }, '[kb] entry updated')
    ctx.body = { success: true, data: updated }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to update entry')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// DELETE /api/tahp/knowledge/entries/:entryId — 软删除知识条目
tahpKnowledgeRoutes.delete('/api/tahp/knowledge/entries/:entryId', async (ctx) => {
  try {
    const { entryId } = ctx.params
    const entry = await readEntry(entryId)
    if (!entry) {
      ctx.status = 404
      ctx.body = { success: false, error: `条目 ${entryId} 不存在` }
      return
    }

    // 软删除：标记为 archived
    const updated: KnowledgeEntry = { ...entry, status: 'archived', updated_at: new Date().toISOString() }
    await writeEntry(updated)
    logger.info({ entryId }, '[kb] entry archived')
    ctx.body = { success: true, data: { archived: entryId } }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to delete entry')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/search/semantic — 语义搜索
tahpKnowledgeRoutes.post('/api/tahp/knowledge/search/semantic', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const query = String(body.query || '').trim()
    const { module, limit = '10' } = body

    if (!query) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 query' }
      return
    }

    let entries = await listEntries()

    // 筛选活跃条目（对话/默认搜索排除 archived；传 include_archived=true 可包含已归档沉淀）
    const includeArchived = body.include_archived === true || body.include_archived === 'true'
    entries = entries.filter(e => {
      if (e.status === 'rejected' || e.status === 'deleted') return false
      if (!includeArchived && e.status === 'archived') return false
      return true
    })

    // 按模块筛选
    if (module) entries = entries.filter(e => e.module === module)

    // BM25 搜索
    const queryTerms = tokenize(query)
    const avgDocLen = entries.length > 0
      ? entries.reduce((s, e) => s + tokenize(e.content + ' ' + e.keywords.join(' ')).length, 0) / entries.length
      : 200
    const scored = entries
      .map(e => ({ entry: e, relevance: calculateRelevance(e, queryTerms, avgDocLen) }))
      .filter(({ relevance }) => relevance > 0)
      .sort((a, b) => b.relevance - a.relevance)

    const results = scored.slice(0, Math.min(parseInt(String(limit)) || 10, 100)).map(({ entry, relevance }) => ({
      ...entry,
      search_relevance: relevance,
    }))

    logger.info({ query, found: results.length }, '[kb] semantic search')
    ctx.body = { success: true, data: { results, total: results.length } }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] search failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts — 自动生成 Skill 草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const {
      skill_id, skill_name, domain_label, module, func_type,
      entry_ids = [], content, generated_by,
    } = body

    if (!skill_id || !skill_name || !domain_label || !module || !func_type) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少必填字段: skill_id / skill_name / domain_label / module / func_type' }
      return
    }

    const draft: SkillDraft = {
      id: `sd-${randomUUID().slice(0, 8)}`,
      skill_id: String(skill_id),
      skill_name: String(skill_name),
      domain_label: String(domain_label),
      module: String(module),
      func_type: String(func_type),
      content: content ? String(content) : `# ${skill_name}\n\n待填充的技能说明。`,
      generated_from_entries: Array.isArray(entry_ids) ? entry_ids.map(String) : [],
      generated_at: new Date().toISOString(),
      generated_by: generated_by ? String(generated_by) : undefined,
      status: 'draft',
    }

    await writeSkillDraft(draft)
    logger.info({ draftId: draft.id, skillId: skill_id }, '[kb] skill draft created')
    ctx.body = { success: true, data: draft }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to create skill draft')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/skill-drafts — 查询 Skill 草稿（支持多状态筛选，默认排除 archived）
tahpKnowledgeRoutes.get('/api/tahp/knowledge/skill-drafts', async (ctx) => {
  try {
    await initDirs()
    const { status, include_archived, limit = '20', offset = '0' } = ctx.query

    let drafts = await listSkillDrafts()

    // 状态筛选：支持逗号分隔多值，默认排除 archived
    if (status) {
      const statusList = String(status).split(',').map(s => s.trim()).filter(Boolean)
      if (statusList.length > 0) {
        drafts = drafts.filter(d => statusList.includes(d.status))
      }
    } else if (include_archived !== 'true') {
      drafts = drafts.filter(d => d.status !== 'archived')
    }

    // 分页
    const pageLimit = Math.min(parseInt(String(limit)) || 20, 100)
    const pageOffset = parseInt(String(offset)) || 0
    const total = drafts.length
    const paginated = drafts.slice(pageOffset, pageOffset + pageLimit)

    ctx.body = {
      success: true,
      data: {
        drafts: paginated,
        total,
        limit: pageLimit,
        offset: pageOffset,
      },
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to list skill drafts')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/skill-drafts/:draftId — 获取单个草稿详情
tahpKnowledgeRoutes.get('/api/tahp/knowledge/skill-drafts/:draftId', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404
      ctx.body = { success: false, error: `草稿 ${draftId} 不存在` }
      return
    }
    // 实时计算质量得分
    const activatedSkills = getActivatedSkills()
    const conflicts = draft.conflicts || detectConflicts(draft, activatedSkills)
    const quality_score = calculateQualityScore(draft, conflicts)
    ctx.body = { success: true, data: { ...draft, conflicts, quality_score } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// PUT /api/tahp/knowledge/skill-drafts/:draftId — 更新草稿内容
tahpKnowledgeRoutes.put('/api/tahp/knowledge/skill-drafts/:draftId', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404
      ctx.body = { success: false, error: `草稿 ${draftId} 不存在` }
      return
    }

    const body = (ctx.request.body || {}) as Record<string, unknown>

    // 允许更新的字段
    const updated: SkillDraft = { ...draft }
    if (body.content !== undefined) updated.content = String(body.content)
    if (body.skill_name !== undefined) updated.skill_name = String(body.skill_name)
    if (body.domain_label !== undefined) updated.domain_label = String(body.domain_label)
    if (body.maintenance_owner !== undefined) updated.maintenance_owner = body.maintenance_owner ? String(body.maintenance_owner) : undefined
    if (Array.isArray(body.exclusion_cases)) updated.exclusion_cases = (body.exclusion_cases as string[]).map(String)
    if (body.version_constraints && typeof body.version_constraints === 'object') {
      updated.version_constraints = body.version_constraints as VersionConstraint
    }
    if (Array.isArray(body.eval_cases)) updated.eval_cases = body.eval_cases as EvalCase[]

    // 重新检测冲突 + 重新计算质量得分
    const activatedSkills = getActivatedSkills()
    const conflicts = detectConflicts(updated, activatedSkills)
    updated.conflicts = conflicts
    updated.quality_score = calculateQualityScore(updated, conflicts)

    await writeSkillDraft(updated)
    logger.info({ draftId }, '[kb] skill draft updated')
    ctx.body = { success: true, data: updated }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to update skill draft')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases — 添加/更新 eval 用例
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/eval-cases', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404
      ctx.body = { success: false, error: `草稿 ${draftId} 不存在` }
      return
    }

    const body = (ctx.request.body || {}) as Record<string, unknown>
    const newCase: EvalCase = {
      id: body.id ? String(body.id) : `ec-${randomUUID().slice(0, 8)}`,
      title: String(body.title || ''),
      input: String(body.input || ''),
      expected_output: String(body.expected_output || ''),
      judgment_criteria: String(body.judgment_criteria || ''),
      source: body.source === 'human' ? 'human' : 'ai_generated',
      status: body.status === 'confirmed' ? 'confirmed' : 'draft',
    }

    const cases = draft.eval_cases || []
    const existing = cases.findIndex(c => c.id === newCase.id)
    if (existing >= 0) {
      cases[existing] = newCase
    } else {
      cases.push(newCase)
    }
    draft.eval_cases = cases

    // 重算质量得分
    const activatedSkills = getActivatedSkills()
    const conflicts = draft.conflicts || detectConflicts(draft, activatedSkills)
    draft.quality_score = calculateQualityScore(draft, conflicts)

    await writeSkillDraft(draft)
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases/:caseId/confirm — 确认 eval 用例
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/eval-cases/:caseId/confirm', async (ctx) => {
  try {
    const { draftId, caseId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) { ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return }
    const cases = draft.eval_cases || []
    const ec = cases.find(c => c.id === caseId)
    if (!ec) { ctx.status = 404; ctx.body = { success: false, error: 'eval 用例不存在' }; return }
    ec.status = 'confirmed'
    ec.source = 'human'
    draft.eval_cases = cases
    const activatedSkills = getActivatedSkills()
    const conflicts = draft.conflicts || detectConflicts(draft, activatedSkills)
    draft.quality_score = calculateQualityScore(draft, conflicts)
    await writeSkillDraft(draft)
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases/:caseId/delete — 删除 eval 用例
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/eval-cases/:caseId/delete', async (ctx) => {
  try {
    const { draftId, caseId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) { ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return }
    draft.eval_cases = (draft.eval_cases || []).filter(c => c.id !== caseId)
    const activatedSkills = getActivatedSkills()
    const conflicts = draft.conflicts || detectConflicts(draft, activatedSkills)
    draft.quality_score = calculateQualityScore(draft, conflicts)
    await writeSkillDraft(draft)
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/skill-suggestions — 分组推荐生成 Skill
tahpKnowledgeRoutes.get('/api/tahp/knowledge/skill-suggestions', async (ctx) => {
  try {
    await initDirs()
    const entries = await listEntries()
    const activatedSkills = getActivatedSkills()
    const allDrafts = await listSkillDrafts()

    // 构建已有草稿索引(module::func_type -> true)
    const draftIndex: Record<string, boolean> = {}
    for (const d of allDrafts) {
      if (d.status === 'archived' || d.status === 'deprecated') continue
      draftIndex[`${d.module}::${d.func_type}`] = true
    }

    // 按 module × func_type 分组（只统计非归档条目）
    const groups: Record<string, { entries: KnowledgeEntry[]; module: string; func_type: string }> = {}
    for (const entry of entries) {
      if (entry.status === 'archived' || entry.status === 'rejected') continue
      const key = `${entry.module}::${entry.func_type}`
      if (!groups[key]) groups[key] = { entries: [], module: entry.module, func_type: entry.func_type }
      groups[key].entries.push(entry)
    }

    const MIN_ENTRIES_FOR_SUGGESTION = 3
    const suggestions = Object.entries(groups).map(([_key, g]) => {
      const avgConf = g.entries.reduce((s, e) => s + e.confidence_score, 0) / g.entries.length
      const recommended = g.entries.length >= MIN_ENTRIES_FOR_SUGGESTION

      // 已有的相关 Skill
      const existingSkills = activatedSkills
        .filter(sk => sk.module === g.module && sk.func_type === g.func_type)
        .map(sk => sk.skillId)

      const funcTypeNames: Record<string, string> = {
        bug_analysis: 'Bug 分析', code_adaptation: '代码适配',
        version_adaptation: '版本适配', carrier_porting: '运营商移植', ai_self_check: 'AI 自检',
      }
      const moduleNames: Record<string, string> = {
        telephony: 'Telephony', 'kernel-driver': '内核驱动', 'power-mgmt': '功耗管理', shared: '共享',
      }

      // 收集源文档信息
      const sourceDocIds = [...new Set(g.entries.map(e => e.source_document_id).filter(Boolean) as string[])]

      return {
        module: g.module,
        func_type: g.func_type,
        entry_count: g.entries.length,
        entry_ids: g.entries.map(e => e.id),
        avg_confidence: Math.round(avgConf * 100) / 100,
        recommended,
        reason: recommended
          ? `${g.entries.length} 条相关知识条目，置信度 ${Math.round(avgConf * 100)}%，建议生成 Skill`
          : `仅 ${g.entries.length} 条条目（需至少 ${MIN_ENTRIES_FOR_SUGGESTION} 条才推荐）`,
        suggested_skill_name: `${moduleNames[g.module] || g.module} ${funcTypeNames[g.func_type] || g.func_type} Skill`,
        existing_skill_count: existingSkills.length,
        existing_skills: existingSkills,
        has_draft: !!draftIndex[`${g.module}::${g.func_type}`],
        source_document_ids: sourceDocIds,
      }
    }).sort((a, b) => b.entry_count - a.entry_count)

    const recommendedCount = suggestions.filter(s => s.recommended).length
    ctx.body = { success: true, data: { suggestions, total_groups: suggestions.length, recommended_count: recommendedCount } }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] skill-suggestions failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/check-similarity — 生成前三档相似 Skill 检索
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/check-similarity', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const inputModule   = normModule(String(body.module || ''))
    const inputFuncType = normFuncType(String(body.func_type || ''))
    const skillName     = String(body.skill_name || '')
    const inputEntryIds = new Set<string>(
      Array.isArray(body.entry_ids) ? body.entry_ids.map(String) : []
    )
    const inputKeywords = Array.isArray(body.keywords) ? body.keywords.map(String) : []

    // ── 组装查询内容 token（用于内容相关度匹配，使主题相关的 Skill 也能被检索到） ──
    const queryTextParts: string[] = [skillName, inputKeywords.join(' ')]
    for (const id of inputEntryIds) {
      const e = await readEntry(id)
      if (e) queryTextParts.push(e.content, e.keywords.join(' '))
    }
    const queryTokens = new Set(tokenize(queryTextParts.join(' ')))

    function tokenCosine(a: Set<string>, b: Set<string>): number {
      if (a.size === 0 || b.size === 0) return 0
      let inter = 0
      for (const t of a) if (b.has(t)) inter++
      return inter / Math.sqrt(a.size * b.size)
    }

    // ── Jaccard 相似度（集合交/并） ─────────────────────────────────────────
    function jaccard(a: Set<string>, b: string[]): number {
      if (a.size === 0 || b.length === 0) return 0
      const bSet = new Set(b)
      const intersection = [...a].filter(x => bSet.has(x)).length
      const union = new Set([...a, ...b]).size
      return union === 0 ? 0 : intersection / union
    }

    // ── 候选来源 1：已激活的 TAHP skill ─────────────────────────────────────
    type CandidateItem = {
      id: string           // draftId 或 skillId
      type: 'draft' | 'activated'
      display_name: string
      module: string
      func_type: string
      entryIds: string[]
      description: string
      contentText: string  // 用于内容相关度匹配
      draft?: SkillDraft   // 草稿时提供，用于融合
    }
    const candidates: CandidateItem[] = []

    const activatedSkills = getActivatedSkills()
    for (const sk of activatedSkills) {
      const bodyText = sk.content.replace(/^---[\s\S]*?---\n*/m, '')
      const descMatch = bodyText.match(/^(.{10,100})/m)
      candidates.push({
        id: sk.skillId,
        type: 'activated',
        display_name: sk.skillId,
        module: sk.module,
        func_type: sk.func_type,
        entryIds: sk.generatedFromEntries,
        description: descMatch?.[1]?.replace(/^#+\s*/, '').trim() || '暂无描述',
        contentText: bodyText,
      })
    }

    // ── 候选来源 2：已有的草稿（draft/reviewing 状态） ──────────────────────
    const allDrafts = await listSkillDrafts()
    for (const d of allDrafts) {
      if (d.status === 'rejected') continue
      candidates.push({
        id: d.id,
        type: 'draft',
        display_name: d.skill_name || d.skill_id,
        module: normModule(d.module),
        func_type: normFuncType(d.func_type),
        entryIds: d.generated_from_entries || [],
        description: d.content?.match(/^#[^#\n]+\n+([^\n#]{10,80})/)?.[1]?.trim() || '草稿待完善',
        contentText: (d.content || '') + ' ' + (d.skill_name || ''),
        draft: d,
      })
    }

    // ── 三档分级：EXACT(>70%) / PARTIAL(30~70%) / STRUCTURAL ────────────────
    type SimilarResult = {
      id: string
      type: 'draft' | 'activated'
      display_name: string
      module: string
      func_type: string
      description: string
      jaccard_score: number   // 0-1
      tier: 'exact' | 'partial' | 'structural'
      reasons: string[]
    }

    const results: SimilarResult[] = []
    for (const c of candidates) {
      const reasons: string[] = []
      let jaccardScore = 0

      // ① Entry ID Jaccard（最可靠）
      if (inputEntryIds.size > 0 && c.entryIds.length > 0) {
        jaccardScore = jaccard(inputEntryIds, c.entryIds)
        if (jaccardScore > 0) {
          reasons.push(`来源条目重叠 ${Math.round(jaccardScore * 100)}%`)
        }
      }

      // ② 结构相似（funcType + module 完全相同）
      const structMatch = inputFuncType && c.func_type && inputModule && c.module
        && inputFuncType === c.func_type && inputModule === c.module

      if (structMatch && !reasons.length) {
        reasons.push(`功能类型相同（${inputFuncType}）`, `业务模块相同（${inputModule}）`)
      } else if (structMatch) {
        reasons.push(`功能类型+模块完全匹配`)
      }

      // ③ 名称关键词重叠（兜底）
      if (skillName && c.display_name) {
        const aT = skillName.toLowerCase().split(/[-_\s]+/).filter(Boolean)
        const bT = c.display_name.toLowerCase().split(/[-_\s]+/).filter(Boolean)
        const nameOverlap = aT.filter(t => bT.includes(t)).length
        if (nameOverlap >= 2) reasons.push(`名称关键词重叠 ${nameOverlap} 个`)
      }

      // ④ 内容相关度（SKILL.md / 草稿正文与查询内容的 token 余弦）
      const contentSim = tokenCosine(queryTokens, new Set(tokenize(c.contentText)))
      if (contentSim > 0.08) reasons.push(`内容相关度 ${Math.round(contentSim * 100)}%`)

      if (!reasons.length && !structMatch) continue

      // 分档（entry-id Jaccard 优先，其次内容相关度，再次结构匹配）
      let tier: 'exact' | 'partial' | 'structural'
      if (jaccardScore >= 0.7) {
        tier = 'exact'
      } else if (jaccardScore >= 0.3 || contentSim >= 0.25) {
        tier = 'partial'
      } else if (structMatch || contentSim >= 0.08 || reasons.length > 0) {
        tier = 'structural'
      } else {
        continue
      }

      results.push({
        id: c.id,
        type: c.type,
        display_name: c.display_name,
        module: c.module,
        func_type: c.func_type,
        description: c.description,
        jaccard_score: jaccardScore,
        tier,
        reasons,
      })
    }

    // 按精确度降序：exact > partial > structural，同档按 jaccard 降序
    const tierOrder = { exact: 0, partial: 1, structural: 2 }
    results.sort((a, b) =>
      tierOrder[a.tier] - tierOrder[b.tier] || b.jaccard_score - a.jaccard_score
    )

    ctx.body = {
      success: true,
      similar: results.slice(0, 6),
      has_exact: results.some(r => r.tier === 'exact'),
      has_partial: results.some(r => r.tier === 'partial'),
      total: results.length,
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] check-similarity failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-association — 关联检索：从文档/条目找出相关已有 Skill 并给出 enhance/new 建议
//
// 与 check-similarity 的区别：除了 entry-id / 结构匹配，还会对 SKILL.md 正文做关键词/内容匹配，
// 因此即使新文档没有 entry 重叠，也能检索到主题相关的现有 Skill（如"数据网络分析"）。
//
// Body: { entry_ids?, document_ids?, module?, func_type?, keywords?, text?, skill_name? }
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-association', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const inputModule   = normModule(String(body.module || ''))
    const inputFuncType = normFuncType(String(body.func_type || ''))
    const skillName     = String(body.skill_name || '')
    const freeText      = String(body.text || '')
    const inputKeywords = Array.isArray(body.keywords) ? body.keywords.map(String) : []
    const entryIdList   = Array.isArray(body.entry_ids) ? body.entry_ids.map(String) : []
    const docIdList     = Array.isArray(body.document_ids) ? body.document_ids.map(String) : []
    const inputEntryIds = new Set<string>(entryIdList)
    const inputDocIds   = new Set<string>(docIdList)

    // ── 组装查询 token 集合（条目内容 + 文档标题 + 关键词 + 自由文本 + 名称） ──────
    const queryParts: string[] = [freeText, skillName, inputKeywords.join(' ')]
    for (const id of entryIdList) {
      const e = await readEntry(id)
      if (e) queryParts.push(e.content, e.keywords.join(' '))
    }
    for (const id of docIdList) {
      const d = await readDocument(id)
      if (d) queryParts.push(d.title, (d.content || '').slice(0, 2000))
    }
    const queryTokens = new Set(tokenize(queryParts.join(' ')))

    function tokenCosine(a: Set<string>, b: Set<string>): number {
      if (a.size === 0 || b.size === 0) return 0
      let inter = 0
      for (const t of a) if (b.has(t)) inter++
      return inter / Math.sqrt(a.size * b.size)
    }
    function jaccardIds(a: Set<string>, b: string[]): number {
      if (a.size === 0 || b.length === 0) return 0
      const bSet = new Set(b)
      const inter = [...a].filter(x => bSet.has(x)).length
      const union = new Set([...a, ...b]).size
      return union === 0 ? 0 : inter / union
    }

    type AssocResult = {
      id: string
      type: 'draft' | 'activated'
      display_name: string
      module: string
      func_type: string
      description: string
      association_score: number       // 0-1
      recommendation: 'enhance_existing' | 'create_new'
      can_merge: boolean              // 草稿可直接 merge
      needs_upgrade: boolean          // 已激活 Skill 需走 upgrade-draft
      reasons: string[]
    }
    const results: AssocResult[] = []

    // ── 候选 1：已激活 Skill ───────────────────────────────────────────────
    for (const sk of getActivatedSkills()) {
      const bodyText = sk.content.replace(/^---[\s\S]*?---\n*/m, '')
      const candTokens = new Set(tokenize(bodyText))
      const tokenSim = tokenCosine(queryTokens, candTokens)
      const entryJ = jaccardIds(inputEntryIds, sk.generatedFromEntries)
      const structMatch = !!(inputFuncType && inputModule && inputFuncType === sk.func_type && inputModule === sk.module)
      let score = Math.min(1, 0.45 * tokenSim + 0.35 * entryJ + (structMatch ? 0.2 : 0))
      if (entryJ >= 0.5) score = Math.max(score, 0.8)
      if (score < 0.12 && !structMatch) continue
      const reasons: string[] = []
      if (tokenSim > 0.05) reasons.push(`内容相关度 ${Math.round(tokenSim * 100)}%`)
      if (entryJ > 0) reasons.push(`来源条目重叠 ${Math.round(entryJ * 100)}%`)
      if (structMatch) reasons.push(`模块/类型相同（${inputModule}·${inputFuncType}）`)
      results.push({
        id: sk.skillId, type: 'activated', display_name: sk.skillId,
        module: sk.module, func_type: sk.func_type,
        description: bodyText.match(/^(.{10,100})/m)?.[1]?.replace(/^#+\s*/, '').trim() || '已激活 Skill',
        association_score: score,
        recommendation: score >= 0.5 ? 'enhance_existing' : 'create_new',
        can_merge: false, needs_upgrade: true, reasons,
      })
    }

    // ── 候选 2：草稿（draft / reviewing / approved，排除 rejected/archived） ──
    for (const d of await listSkillDrafts()) {
      if (d.status === 'rejected' || d.status === 'archived') continue
      const candTokens = new Set(tokenize((d.content || '') + ' ' + (d.skill_name || '')))
      const tokenSim = tokenCosine(queryTokens, candTokens)
      const entryJ = jaccardIds(inputEntryIds, d.generated_from_entries || [])
      const docOverlap = (d.source_document_ids || []).some(id => inputDocIds.has(id))
      const dMod = normModule(d.module), dFt = normFuncType(d.func_type)
      const structMatch = !!(inputFuncType && inputModule && inputFuncType === dFt && inputModule === dMod)
      let score = Math.min(1, 0.45 * tokenSim + 0.35 * entryJ + (structMatch ? 0.2 : 0))
      if (docOverlap) score = Math.max(score, 0.85)
      if (entryJ >= 0.5) score = Math.max(score, 0.8)
      if (score < 0.12 && !structMatch && !docOverlap) continue
      const reasons: string[] = []
      if (docOverlap) reasons.push('来源文档相同')
      if (tokenSim > 0.05) reasons.push(`内容相关度 ${Math.round(tokenSim * 100)}%`)
      if (entryJ > 0) reasons.push(`来源条目重叠 ${Math.round(entryJ * 100)}%`)
      if (structMatch) reasons.push(`模块/类型相同（${inputModule}·${inputFuncType}）`)
      const canMerge = d.status === 'draft' || d.status === 'reviewing'
      results.push({
        id: d.id!, type: 'draft', display_name: d.skill_name || d.skill_id,
        module: dMod, func_type: dFt,
        description: d.content?.match(/^#[^#\n]+\n+([^\n#]{10,80})/)?.[1]?.trim() || '草稿待完善',
        association_score: score,
        recommendation: score >= 0.5 ? 'enhance_existing' : 'create_new',
        can_merge: canMerge, needs_upgrade: !canMerge, reasons,
      })
    }

    results.sort((a, b) => b.association_score - a.association_score)
    const top = results.slice(0, 8)
    const bestEnhance = top.find(r => r.recommendation === 'enhance_existing')

    ctx.body = {
      success: true,
      data: {
        associations: top,
        total: results.length,
        // 总体建议：存在高相关 Skill 时建议增强，否则建议新建
        overall_recommendation: bestEnhance ? 'enhance_existing' : 'create_new',
        best_match: bestEnhance || null,
      },
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] skill-association failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/merge — LLM 精准增量融合
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/merge', async (ctx) => {
  try {
    await initDirs()
    const { draftId } = ctx.params as { draftId: string }
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const newEntryIds: string[] = Array.isArray(body.entry_ids) ? body.entry_ids.map(String) : []

    if (!newEntryIds.length) {
      ctx.status = 400; ctx.body = { success: false, error: '缺少 entry_ids' }; return
    }

    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return
    }

    // 加载新条目内容
    const newEntries: KnowledgeEntry[] = []
    for (const id of newEntryIds) {
      const e = await readEntry(id)
      if (e) newEntries.push(e)
    }
    if (!newEntries.length) {
      ctx.status = 400; ctx.body = { success: false, error: '指定的知识条目不存在' }; return
    }

    // 过滤掉已经包含在 draft 中的 entries（避免重复融合）
    const existingIds = new Set(draft.generated_from_entries || [])
    const trulyNewEntries = newEntries.filter(e => !existingIds.has(e.id))
    if (!trulyNewEntries.length) {
      ctx.body = { success: true, data: { draft, merged_count: 0, message: '所有条目已包含在此 Skill 中，无需融合' } }
      return
    }

    // ── LLM 精准增量融合 Prompt ──────────────────────────────────────────────
    const newContent = trulyNewEntries.map((e, i) =>
      `### 新增条目 ${i + 1}（${e.category || ''}）\n${e.content}`
    ).join('\n\n')

    const systemPrompt = `你是一位 Android 底层软件 AI Skill 维护专家，负责将新的知识条目精准融合到已有 Skill 文档中。

融合原则（必须严格遵守）：
1. 【精准增量】只在已有内容缺失的地方补充，禁止重写或改变已有内容的表达
2. 【最小化修改】每处修改需说明原因，不修改已有章节结构
3. 【内容不重复】如果新条目内容与已有内容高度重叠，标注"已覆盖"并跳过
4. 【保留结构】Skill 整体 Markdown 结构、章节标题、格式保持不变
5. 输出格式：完整的更新后 Skill 内容（含所有原有内容 + 精准增补部分）

增补标记规范：
- 新增内容在行末或段末加注 <!-- MERGED -->
- 若某条目内容已覆盖，在注释中写明：<!-- SKIP: 已有相关内容 -->`

    const userPrompt = `当前 Skill 文档（请仔细阅读，理解现有覆盖范围）：
\`\`\`markdown
${draft.content}
\`\`\`

需要融合的新知识条目（共 ${trulyNewEntries.length} 条）：
${newContent}

请按照融合原则，输出完整的更新后 Skill 内容：`

    let mergedContent = draft.content
    let llmError: string | undefined

    try {
      mergedContent = await callTahpLLM(systemPrompt, userPrompt, { maxTokens: 6000 })
      // 清理 LLM 可能输出的 markdown 代码块包装
      mergedContent = mergedContent.replace(/^```markdown\n?/, '').replace(/\n?```$/, '').trim()
    } catch (e: any) {
      llmError = e.message
      logger.warn({ llmError }, '[kb] merge LLM failed, returning original')
    }

    // 更新草稿
    const updatedDraft: SkillDraft = {
      ...draft,
      content: mergedContent,
      generated_from_entries: [
        ...Array.from(existingIds),
        ...trulyNewEntries.map(e => e.id),
      ],
    }
    await writeSkillDraft(updatedDraft)

    ctx.body = {
      success: true,
      data: {
        draft: updatedDraft,
        merged_count: trulyNewEntries.length,
        llm_error: llmError,
        message: llmError
          ? `LLM 融合失败（${llmError}），内容未变更`
          : `已将 ${trulyNewEntries.length} 条新知识精准融合到 Skill`,
      },
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] merge failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 异步 Skill 生成流程（Phase 3 核心） ──────────────────────────────────────────────
async function runSkillGenerationStream(
  jobId: string,
  params: {
    mod: string
    func_type: string
    entry_ids?: string[]
    skill_name?: string
    generated_by?: string
    document_ids?: string[]
  }
): Promise<void> {
  const emit = (update: Partial<SkillGenJob>) => emitSkillGenEvent(jobId, update)
  const { mod, func_type, entry_ids, skill_name, generated_by, document_ids } = params

  // Step 0: 初始化
  emit({ stage: 'init', progress: 5, message: '加载知识条目...' })

  let entriesToUse: KnowledgeEntry[] = []
  if (Array.isArray(entry_ids) && entry_ids.length > 0) {
    for (const id of entry_ids) {
      const e = await readEntry(id)
      if (e) entriesToUse.push(e)
    }
  } else {
    const all = await listEntries()
    entriesToUse = all.filter(e =>
      e.module === mod && e.func_type === func_type && e.status !== 'archived'
    )
  }

  if (entriesToUse.length === 0) {
    emit({ status: 'error', stage: 'error', progress: 0, message: '没有找到可用的知识条目' })
    return
  }

  emit({ stage: 'init', progress: 8, message: `已加载 ${entriesToUse.length} 条知识条目` })

  // ── Step 0.5: 加载源文档（完整内容） ────────────────────────────────
  let sourceDocuments: KnowledgeDocument[] = []
  const docIdSet = new Set<string>()

  // 优先使用前端传入的 document_ids
  if (Array.isArray(document_ids) && document_ids.length > 0) {
    for (const id of document_ids) docIdSet.add(id)
  } else {
    // 从条目的 source_document_id 反查
    for (const e of entriesToUse) {
      if (e.source_document_id) docIdSet.add(e.source_document_id)
    }
  }

  if (docIdSet.size > 0) {
    emit({ stage: 'init', progress: 12, message: `正在加载 ${docIdSet.size} 个源文档...` })
    for (const docId of docIdSet) {
      const doc = await readDocument(docId)
      if (doc) sourceDocuments.push(doc)
    }
    const totalChars = sourceDocuments.reduce((s, d) => s + d.char_count, 0)
    if (sourceDocuments.length > 0) {
      emit({ stage: 'init', progress: 15, message: `已加载 ${sourceDocuments.length} 个源文档，共 ${totalChars} 字符` })
      logger.info({ jobId, docs: sourceDocuments.length, totalChars }, '[kb] loaded source documents for skill generation')
    }
  }

  // Step 1: 文档级重复检测
  emit({ stage: 'duplicate_check', progress: 20, message: '正在检查文档重复...' })
  const fingerprint = computeContentFingerprint(entriesToUse)
  const duplicates = await checkDocumentDuplicate(entriesToUse, fingerprint)

  if (duplicates.length > 0) {
    emit({
      status: 'completed',
      stage: 'done',
      progress: 100,
      message: `检测到 ${duplicates.length} 个重复 Skill，请先检查已有草稿`,
      result: {
        duplicate_detected: true,
        duplicate_drafts: duplicates,
      },
    })
    return
  }

  // Step 2: 内容相似度检索
  emit({ stage: 'similarity_check', progress: 35, message: '检索相似 Skill...' })
  const normMod = normModule(mod)
  const normFt = normFuncType(func_type)
  // 内容 BM25 token 重叠率增强相似度检测
  const inputTerms = tokenize(entriesToUse.map(e => e.content).join(' '))
  const allDraftsForSim = await listSkillDrafts()
  const simResults: Array<{ id: string; type: 'draft' | 'activated'; display_name: string; jaccard_score: number; tier: string; reasons: string[] }> = []
  const activatedForSim = getActivatedSkills()
  for (const sk of activatedForSim) {
    if (normModule(sk.module) !== normMod && sk.module !== mod) continue
    if (normFuncType(sk.func_type) !== normFt && sk.func_type !== func_type) continue
    const skTerms = tokenize(sk.content)
    const commonTerms = inputTerms.filter(t => skTerms.includes(t)).length
    const contentSim = inputTerms.length > 0 ? commonTerms / Math.max(inputTerms.length, skTerms.length) : 0
    if (contentSim > 0.5) {
      simResults.push({ id: sk.skillId, type: 'activated', display_name: sk.skillId, jaccard_score: contentSim, tier: 'partial', reasons: [`内容相似度 ${Math.round(contentSim * 100)}%`] })
    }
  }
  for (const d of allDraftsForSim) {
    if (d.status === 'rejected') continue
    if (normModule(d.module) !== normMod && d.module !== mod) continue
    if (normFuncType(d.func_type) !== normFt && d.func_type !== func_type) continue
    const dTerms = tokenize(d.content)
    const commonTerms = inputTerms.filter(t => dTerms.includes(t)).length
    const contentSim = inputTerms.length > 0 ? commonTerms / Math.max(inputTerms.length, dTerms.length) : 0
    if (contentSim > 0.5) {
      simResults.push({ id: d.id, type: 'draft', display_name: d.skill_name, jaccard_score: contentSim, tier: 'partial', reasons: [`内容相似度 ${Math.round(contentSim * 100)}%`] })
    }
  }

  if (simResults.length > 0) {
    emit({
      status: 'completed',
      stage: 'done',
      progress: 100,
      message: `发现 ${simResults.length} 个相似 Skill，建议融合而非新建`,
      result: { similar_skills: simResults },
    })
    return
  }

  // Step 3-5: LLM 生成
  const sourceInfo = sourceDocuments.length > 0
    ? `${sourceDocuments.length} 个源文档（共 ${sourceDocuments.reduce((s, d) => s + d.char_count, 0)} 字符）`
    : `${entriesToUse.length} 条知识条目`
  emit({ stage: 'llm_generate', progress: 45, message: `正在调用 LLM 生成 Skill 文档（来源: ${sourceInfo}）...` })
  let generatedContent = ''
  let evalCases: EvalCase[] = []
  let llmError: string | undefined
  let llmErrorDetail: string | undefined

  try {
    const { system, user } = buildSkillGenPrompt(entriesToUse, mod, func_type, sourceDocuments.length > 0 ? sourceDocuments : undefined)
    const llmResponse = await callTahpLLM(system, user, { maxTokens: 4096 })
    emit({ stage: 'llm_generate', progress: 65, message: '解析 LLM 输出...' })
    const evalStart = llmResponse.indexOf('EVAL_CASE_START')
    if (evalStart > 0) {
      generatedContent = llmResponse.slice(0, evalStart).trim()
      evalCases = parseEvalCasesFromLLM(llmResponse)
    } else {
      generatedContent = llmResponse.trim()
    }
  } catch (e: unknown) {
    llmError = (e as Error).message
    llmErrorDetail = (e as Error).message
    logger.warn({ llmError }, '[kb] LLM generation failed, using template fallback')
    const funcTypeNames: Record<string, string> = {
      bug_analysis: 'Bug 分析', code_adaptation: '代码适配',
      version_adaptation: '版本适配', carrier_porting: '运营商移植', ai_self_check: 'AI 自检',
    }
    // 增强 fallback：利用条目关键词和文档信息生成更有价值的骨架
    const keywordsSummary = [...new Set(entriesToUse.flatMap(e => e.keywords))].slice(0, 15).join(', ')
    const docInfoLine = sourceDocuments.length > 0
      ? `- 源文档：${sourceDocuments.map(d => `${d.title} (${d.char_count}字符)`).join(', ')}`
      : `- 知识条目：${entriesToUse.length} 条`
    generatedContent = `# ${skill_name || `${mod} ${funcTypeNames[func_type] || func_type} Skill`}\n\n## 适用场景\n- 适用模块：${mod}\n- 适用业务类型：${func_type}\n- 关联关键词：${keywordsSummary}\n${docInfoLine}\n\n## ⚠️ 不适用情况\n- [待人工确认]\n\n## 核心处理方法\n> ⚠️ LLM 生成失败（${llmError}），已使用模板骨架。请基于以下源信息手动完善：\n\n${entriesToUse.slice(0, 8).map((e, i) => `${i + 1}. [${e.category}] ${e.content.slice(0, 200)}`).join('\n')}\n\n## 注意事项\n- 关键词：${keywordsSummary}\n\n## 维护信息\n- 维护人：[待指定]\n- 模板版本：v1.0`
  }

  // Step 6: 解析 eval 用例
  emit({ stage: 'eval_extract', progress: 78, message: '解析 eval 用例...' })

  // Step 7: 质量评分
  emit({ stage: 'quality_score', progress: 90, message: '计算质量评分...' })
  const ts = Date.now().toString(36)
  const skillId = `kb-skill-${mod.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${func_type.replace(/_/g, '-')}-${ts}`
  const activatedSkills = getActivatedSkills()
  const sourceDocIds = [...new Set(entriesToUse.map(e => e.source_document_id).filter(Boolean) as string[])]
  const draft: SkillDraft = {
    id: `sd-${randomUUID().slice(0, 8)}`,
    skill_id: skillId,
    skill_name: skill_name || `${mod} ${func_type} Skill`,
    domain_label: `${mod} — ${func_type}`,
    module: mod,
    func_type: normFt,
    func_type_raw: func_type,
    module_raw: mod,
    category: getFuncTypeCategory(func_type),
    content: generatedContent,
    generated_from_entries: entriesToUse.map(e => e.id),
    generated_at: new Date().toISOString(),
    generated_by: generated_by || undefined,
    status: 'draft',
    eval_cases: evalCases,
    template_version: 'v1.0',
    conflicts: [],
    source_document_ids: sourceDocIds,
    content_fingerprint: fingerprint,
  }
  draft.conflicts = detectConflicts(draft, activatedSkills)
  draft.quality_score = calculateQualityScore(draft, draft.conflicts)

  // Step 8: 持久化
  emit({ stage: 'quality_score', progress: 98, message: '保存 Skill 草稿...' })
  await writeSkillDraft(draft)
  logger.info({ draftId: draft.id, skillId, module: mod, func_type, llmError }, '[kb] skill draft generated via stream')

  // Step 9: 完成
  emit({
    status: 'completed',
    stage: 'done',
    progress: 100,
    message: llmError ? `LLM 调用失败，已使用模板骨架` : 'Skill 生成成功',
    result: { draft, llm_error: llmError, llm_error_detail: llmErrorDetail },
  })
}

// POST /api/tahp/knowledge/skill-drafts/check-duplicate — 文档级重复检测
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/check-duplicate', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const entryIds: string[] = Array.isArray(body.entry_ids) ? body.entry_ids.map(String) : []
    if (!entryIds.length) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 entry_ids' }
      return
    }
    const entries: KnowledgeEntry[] = []
    for (const id of entryIds) {
      const e = await readEntry(id)
      if (e) entries.push(e)
    }
    const fingerprint = computeContentFingerprint(entries)
    const duplicates = await checkDocumentDuplicate(entries, fingerprint)
    ctx.body = {
      success: true,
      data: {
        duplicate_detected: duplicates.length > 0,
        duplicates,
        fingerprint,
      },
    }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/duplicate-decision — 记录用户重复决策
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/duplicate-decision', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { draft_id, decision, target_id } = body
    if (!draft_id || !decision) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 draft_id 或 decision' }
      return
    }
    const draft = await readSkillDraft(String(draft_id))
    if (!draft) {
      ctx.status = 404
      ctx.body = { success: false, error: '草稿不存在' }
      return
    }
    const decisions = draft.duplicate_decisions || []
    decisions.push({
      decision: String(decision) as 'force_create' | 'view_existing' | 'merge' | 'upgrade_draft',
      target_id: target_id ? String(target_id) : undefined,
      decided_at: new Date().toISOString(),
    })
    draft.duplicate_decisions = decisions
    await writeSkillDraft(draft)
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/recommend-merge-target — 智能融合目标推荐
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/recommend-merge-target', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const entryIds: string[] = Array.isArray(body.entry_ids) ? body.entry_ids.map(String) : []
    const inputModule = String(body.module || '')
    const inputFuncType = String(body.func_type || '')

    // 加载条目获取关键词
    const entryKeywords: string[] = []
    for (const id of entryIds) {
      const e = await readEntry(id)
      if (e && e.keywords) entryKeywords.push(...e.keywords)
    }
    const inputKwSet = new Set(entryKeywords)

    type RecommendItem = {
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
    const recommendations: RecommendItem[] = []

    // 扫描草稿
    const allDrafts = await listSkillDrafts()
    for (const d of allDrafts) {
      if (d.status === 'rejected') continue
      if (d.module !== inputModule && normModule(d.module) !== normModule(inputModule)) continue
      if (d.func_type !== inputFuncType &&
        normFuncType(d.func_type) !== normFuncType(inputFuncType) &&
        d.func_type_raw !== inputFuncType) continue
      const draftKws = extractKeywords(d.content)
      const newTopics = [...inputKwSet].filter(k => !draftKws.includes(k))
      const commonTopics = [...inputKwSet].filter(k => draftKws.includes(k))
      const matchScore = (newTopics.length * 0.4 + commonTopics.length * 0.3) / Math.max(inputKwSet.size, 1)
      if (matchScore < 0.1) continue
      recommendations.push({
        target_id: d.id,
        target_name: d.skill_name,
        target_type: 'draft',
        match_score: Math.round(matchScore * 100) / 100,
        new_topics: newTopics.slice(0, 5),
        new_topics_count: newTopics.length,
        common_topics_count: commonTopics.length,
        estimated_quality_delta: Math.min(30, newTopics.length * 3),
        reason: `可补充 ${newTopics.length} 个新知识主题，预估质量分提升 ${Math.min(30, newTopics.length * 3)} 分`,
        can_merge: true,
      })
    }

    // 扫描已激活 Skill
    const activatedSkills = getActivatedSkills()
    for (const sk of activatedSkills) {
      if (normModule(sk.module) !== normModule(inputModule) && sk.module !== inputModule) continue
      if (normFuncType(sk.func_type) !== normFuncType(inputFuncType) && sk.func_type !== inputFuncType) continue
      const draftKws = sk.keywords
      const newTopics = [...inputKwSet].filter(k => !draftKws.includes(k))
      const commonTopics = [...inputKwSet].filter(k => draftKws.includes(k))
      const matchScore = (newTopics.length * 0.4 + commonTopics.length * 0.3) / Math.max(inputKwSet.size, 1)
      if (matchScore < 0.1) continue
      recommendations.push({
        target_id: sk.skillId,
        target_name: sk.skillId,
        target_type: 'activated',
        match_score: Math.round(matchScore * 100) / 100,
        new_topics: newTopics.slice(0, 5),
        new_topics_count: newTopics.length,
        common_topics_count: commonTopics.length,
        estimated_quality_delta: Math.min(20, newTopics.length * 2),
        reason: `已激活的生产 Skill，新建升级草案后融合`,
        can_merge: false,
        upgrade_hint: '将以此 Skill 为基础生成升级草案',
      })
    }

    recommendations.sort((a, b) => b.match_score - a.match_score)
    ctx.body = { success: true, data: { recommendations: recommendations.slice(0, 5) } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/upgrade-draft — 已激活 Skill 生成升级草案
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/upgrade-draft', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { skill_id, entry_ids } = body
    if (!skill_id) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 skill_id' }
      return
    }
    const skillsRoot = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
    const skillDir = join(skillsRoot, String(skill_id))
    const skillMd = join(skillDir, 'SKILL.md')
    if (!existsSync(skillMd)) {
      ctx.status = 404
      ctx.body = { success: false, error: `已激活 Skill ${skill_id} 不存在` }
      return
    }
    const originalContent = readFileSync(skillMd, 'utf-8')
    const bodyPart = originalContent.replace(/^---[\s\S]*?---\n*/, '')
    const ts = Date.now().toString(36)
    const newSkillId = `${skill_id}-upgrade-${ts}`
    const newEntryIds: string[] = Array.isArray(entry_ids) ? entry_ids.map(String) : []
    const upgradeDraft: SkillDraft = {
      id: `sd-${randomUUID().slice(0, 8)}`,
      skill_id: newSkillId,
      skill_name: `${skill_id} (增强版)`,
      domain_label: `upgrade:${skill_id}`,
      module: '',
      func_type: '',
      content: bodyPart.trim(),
      generated_from_entries: newEntryIds,
      generated_at: new Date().toISOString(),
      generated_by: 'upgrade',
      status: 'draft',
      source_document_ids: [],
    }
    await writeSkillDraft(upgradeDraft)
    ctx.body = { success: true, data: { draft: upgradeDraft } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/generate-stream — 启动异步生成任务
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/generate-stream', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { module: mod, func_type, entry_ids, skill_name, generated_by, document_ids } = body
    if (!mod || !func_type) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 module 或 func_type' }
      return
    }
    const jobId = randomUUID()
    const now = new Date()
    const ttl = new Date(now.getTime() + 30 * 60 * 1000)
    const job: SkillGenJob = {
      id: jobId,
      status: 'running',
      stage: 'init',
      progress: 0,
      message: '初始化...',
      created_at: now.toISOString(),
      ttl_expires_at: ttl.toISOString(),
    }
    skillGenJobs.set(jobId, job)
    ctx.body = { success: true, data: { job_id: jobId } }

    // 异步执行生成流程（不阻塞响应）
    runSkillGenerationStream(jobId, {
      mod: String(mod),
      func_type: String(func_type),
      entry_ids: Array.isArray(entry_ids) ? entry_ids.map(String) : undefined,
      skill_name: skill_name ? String(skill_name) : undefined,
      generated_by: generated_by ? String(generated_by) : undefined,
      document_ids: Array.isArray(document_ids) ? document_ids.map(String) : undefined,
    }).catch(err => {
      emitSkillGenEvent(jobId, {
        status: 'error',
        stage: 'error',
        message: `生成失败：${(err as Error).message}`,
      })
    })
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/skill-drafts/generate-stream/:jobId — SSE 订阅生成进度
tahpKnowledgeRoutes.get('/api/tahp/knowledge/skill-drafts/generate-stream/:jobId', async (ctx) => {
  const { jobId } = ctx.params
  const job = skillGenJobs.get(jobId)
  if (!job) {
    ctx.status = 404
    ctx.body = { success: false, error: 'Job 不存在' }
    return
  }
  const stream = new PassThrough()
  ctx.status = 200
  ctx.set('Content-Type', 'text/event-stream; charset=utf-8')
  ctx.set('Cache-Control', 'no-cache')
  ctx.set('Connection', 'keep-alive')
  ctx.body = stream

  const send = (data: string) => {
    try {
      stream.write(`data: ${data}\n\n`)
    } catch { /* ignore */ }
  }

  // 立即发送当前状态
  send(JSON.stringify(job))

  if (job.status === 'completed' || job.status === 'error') {
    stream.end()
    return
  }

  // 注册监听器
  const listeners = skillGenListeners.get(jobId) || []
  listeners.push(send)
  skillGenListeners.set(jobId, listeners)

  // 客户端断开时移除监听器
  ctx.req.on('close', () => {
    const ls = skillGenListeners.get(jobId) || []
    skillGenListeners.set(jobId, ls.filter(l => l !== send))
    try { stream.end() } catch { /* ignore */ }
  })
})

// GET /api/tahp/knowledge/skill-drafts/gen-job/:jobId — 一次性获取任务状态
tahpKnowledgeRoutes.get('/api/tahp/knowledge/skill-drafts/gen-job/:jobId', async (ctx) => {
  const { jobId } = ctx.params
  const job = skillGenJobs.get(jobId)
  if (!job) {
    ctx.status = 404
    ctx.body = { success: false, error: 'Job 不存在或已过期' }
    return
  }
  ctx.body = { success: true, data: job }
})

// POST /api/tahp/knowledge/skill-drafts/generate — LLM 生成 Skill 草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/generate', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { module: mod, func_type, entry_ids, skill_name, generated_by } = body

    if (!mod || !func_type) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 module 或 func_type' }
      return
    }

    // 加载知识条目
    let entriesToUse: KnowledgeEntry[] = []
    if (Array.isArray(entry_ids) && entry_ids.length > 0) {
      for (const id of entry_ids.map(String)) {
        const e = await readEntry(id)
        if (e) entriesToUse.push(e)
      }
    } else {
      // 按 module + func_type 加载
      const all = await listEntries()
      entriesToUse = all.filter(e =>
        e.module === mod && e.func_type === func_type && e.status !== 'archived'
      )
    }

    if (entriesToUse.length === 0) {
      ctx.status = 400
      ctx.body = { success: false, error: '没有找到可用的知识条目' }
      return
    }

    // 调用 LLM 生成
    let generatedContent = ''
    let evalCases: EvalCase[] = []
    let llmError: string | undefined

    try {
      const { system, user } = buildSkillGenPrompt(entriesToUse, String(mod), String(func_type))
      const llmResponse = await callTahpLLM(system, user, { maxTokens: 4096 })

      // 分离 Skill 内容和 eval cases
      const evalStart = llmResponse.indexOf('EVAL_CASE_START')
      if (evalStart > 0) {
        generatedContent = llmResponse.slice(0, evalStart).trim()
        evalCases = parseEvalCasesFromLLM(llmResponse)
      } else {
        generatedContent = llmResponse.trim()
      }
    } catch (e: any) {
      llmError = e.message
      logger.warn({ llmError }, '[kb] LLM generation failed, using template fallback')

      // LLM 失败时使用模板骨架
      const funcTypeNames: Record<string, string> = {
        bug_analysis: 'Bug 分析', code_adaptation: '代码适配',
        version_adaptation: '版本适配', carrier_porting: '运营商移植', ai_self_check: 'AI 自检',
      }
      generatedContent = `# ${skill_name || `${mod} ${funcTypeNames[String(func_type)] || func_type} Skill`}

## 适用场景
- 适用模块：${mod}
- 适用业务类型：${func_type}
- [请基于知识条目补充具体触发条件]

## ⚠️ 不适用情况（请人工补充）
- [待人工确认 1]
- [待人工确认 2]

## 核心处理方法
[基于以下 ${entriesToUse.length} 条知识条目，请整理核心处理步骤]

${entriesToUse.slice(0, 5).map((e, i) => `### 参考条目 ${i + 1}\n${e.content.slice(0, 400)}`).join('\n\n')}

## 示例

### 正例
[请人工补充典型正例]

### ⚠️ 反例（待补充）
[待人工补充]

## ⚠️ 版本与平台约束（待确认）
- Android 版本范围：[待确认]
- 芯片平台：[待确认]

## 注意事项
[请基于知识条目补充注意事项]

## 维护信息
- 维护人：[待指定]
- 生成来源：知识库 ${entriesToUse.length} 条条目
- 模板版本：v1.0`
    }

    // 生成 skill_id（kebab-case）
    const ts = Date.now().toString(36)
    const skillId = `kb-skill-${String(mod).toLowerCase().replace(/[^a-z0-9]/g, '-')}-${String(func_type).replace(/_/g, '-')}-${ts}`

    // 构建草稿
    const activatedSkills = getActivatedSkills()
    const draft: SkillDraft = {
      id: `sd-${randomUUID().slice(0, 8)}`,
      skill_id: skillId,
      skill_name: skill_name ? String(skill_name) : `${mod} ${func_type} Skill`,
      domain_label: `${mod} — ${func_type}`,
      module: String(mod),
      func_type: String(func_type),
      content: generatedContent,
      generated_from_entries: entriesToUse.map(e => e.id),
      generated_at: new Date().toISOString(),
      generated_by: generated_by ? String(generated_by) : undefined,
      status: 'draft',
      eval_cases: evalCases,
      template_version: 'v1.0',
      conflicts: [],
      quality_score: undefined,
    }

    // 检测冲突 + 计算质量得分
    draft.conflicts = detectConflicts(draft, activatedSkills)
    draft.quality_score = calculateQualityScore(draft, draft.conflicts)

    await writeSkillDraft(draft)
    logger.info({ draftId: draft.id, skillId, module: mod, func_type, llmError }, '[kb] skill draft generated')

    ctx.body = {
      success: true,
      data: {
        draft,
        llm_error: llmError,
        message: llmError ? `LLM 调用失败（${llmError}），已使用模板骨架，请人工完善内容` : undefined,
      },
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] skill draft generation failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/review — 审核和激活 Skill 草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/review', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404
      ctx.body = { success: false, error: `草稿 ${draftId} 不存在` }
      return
    }

    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { action, reviewed_by, review_notes } = body

    if (action !== 'approve' && action !== 'reject') {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少或无效的 action (approve / reject)' }
      return
    }

    // ── Phase 4: 审核时计算质量得分（仅警告，不强制阻断） ───────────
    let approveWarning: string | undefined
    if (action === 'approve') {
      const activatedSkills = getActivatedSkills()
      const conflicts = detectConflicts(draft, activatedSkills)
      const score = calculateQualityScore(draft, conflicts)
      if (!score.pass_gate) {
        // 记录警告，写入 review_notes，但不阻止激活
        approveWarning = `质量评分 ${score.total}/100，建议后续完善：${score.blocking_reasons.join('；')}`
      }
    }

    const baseReviewNotes = review_notes ? String(review_notes) : undefined
    const finalReviewNotes = approveWarning
      ? [baseReviewNotes, `[系统警告] ${approveWarning}`].filter(Boolean).join('\n')
      : baseReviewNotes

    const updated: SkillDraft = {
      ...draft,
      status: action === 'approve' ? 'approved' : 'rejected',
      reviewed_by: reviewed_by ? String(reviewed_by) : undefined,
      reviewed_at: new Date().toISOString(),
      review_notes: finalReviewNotes,
    }

    // 如果批准，尝试激活（写入到 skills/.claude/skills/<skillId>/）
    if (action === 'approve') {
      try {
        const skillsRoot = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
        const skillDir = join(skillsRoot, updated.skill_id)
        mkdirSync(skillDir, { recursive: true })

        // normalize 为中文 canonical 值，同时保留 raw 存储
        const normFT  = normFuncType(updated.func_type)
        const normMod = normModule(updated.module)
        const rawFT = updated.func_type_raw || updated.func_type
        const rawMod = updated.module_raw || updated.module
        const category = getFuncTypeCategory(updated.func_type)
        const entryIdsYaml = JSON.stringify(updated.generated_from_entries ?? [])
        const frontmatter = [
          `tahp_adapt_skill: true`,
          `name: ${updated.skill_id}`,
          `domain_label: "${updated.domain_label}"`,
          `domain_id: "${updated.skill_id}"`,
          `module: "${normMod}"`,
          `module_raw: "${rawMod}"`,
          `func_type: "${normFT}"`,
          `func_type_raw: "${rawFT}"`,
          `category: "${category}"`,
          // scanner 读取的字段（camelCase）
          `funcType: "${normFT}"`,
          `group: "${normMod}"`,
          `status: active`,
          `generated_from_knowledge: true`,
          `generated_from_entries: '${entryIdsYaml}'`,
          `created_at: "${new Date().toISOString()}"`,
          `source: knowledge_base`,
        ].join('\n')

        const skillContent = `---\n${frontmatter}\n---\n\n${updated.content}\n`
        await safeFileStore.writeText(join(skillDir, 'SKILL.md'), skillContent)

        updated.activated_at = new Date().toISOString()
        updated.activated_skill_path = `skills/.claude/skills/${updated.skill_id}/SKILL.md`
        logger.info({ skillId: updated.skill_id, draftId }, '[kb] skill activated from draft')
      } catch (e) {
        logger.warn({ draftId, err: (e as Error).message }, '[kb] failed to activate skill, but draft approved')
      }
    }

    await writeSkillDraft(updated)
    ctx.body = { success: true, data: updated, warning: approveWarning }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to review skill draft')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/entries/:entryId/feedback — 任务反哺知识库
tahpKnowledgeRoutes.post('/api/tahp/knowledge/entries/:entryId/feedback', async (ctx) => {
  try {
    const { entryId } = ctx.params
    const entry = await readEntry(entryId)
    if (!entry) {
      ctx.status = 404
      ctx.body = { success: false, error: `条目 ${entryId} 不存在` }
      return
    }

    const body = (ctx.request.body || {}) as Record<string, unknown>
    const {
      task_id, feedback, useful = true, rating,
    } = body

    const updated: KnowledgeEntry = {
      ...entry,
      usage_count: (entry.usage_count || 0) + 1,
      last_used_in_task: task_id ? String(task_id) : undefined,
      updated_at: new Date().toISOString(),
    }

    // 如果评分低，可以标记为需要审查
    if (typeof rating === 'number' && rating < 3) {
      updated.confidence_score = Math.max(0, updated.confidence_score - 0.1)
    } else if (typeof rating === 'number' && rating >= 4) {
      updated.confidence_score = Math.min(1, updated.confidence_score + 0.1)
    }

    await writeEntry(updated)
    logger.info({ entryId, taskId: task_id, useful, rating }, '[kb] entry feedback recorded')
    ctx.body = { success: true, data: updated }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to record feedback')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/stats — 知识库统计
tahpKnowledgeRoutes.get('/api/tahp/knowledge/stats', async (ctx) => {
  try {
    await initDirs()
    const entries = await listEntries()
    const drafts = await listSkillDrafts()
    const docs = await listDocuments()

    const stats = {
      total_entries: entries.length,
      approved_entries: entries.filter(e => e.status === 'approved').length,
      pending_entries: entries.filter(e => e.status === 'pending_review').length,
      archived_entries: entries.filter(e => e.status === 'archived').length,
      by_module: {} as Record<string, number>,
      by_func_type: {} as Record<string, number>,
      by_status: {} as Record<string, number>,
      total_skill_drafts: drafts.length,
      draft_skill_drafts: drafts.filter(d => d.status === 'draft').length,
      approved_skill_drafts: drafts.filter(d => d.status === 'approved').length,
      total_usage_count: entries.reduce((sum, e) => sum + (e.usage_count || 0), 0),
      average_confidence: entries.length > 0 ? entries.reduce((sum, e) => sum + e.confidence_score, 0) / entries.length : 0,
      total_documents: docs.length,
    }

    for (const entry of entries) {
      stats.by_module[entry.module] = (stats.by_module[entry.module] || 0) + 1
      stats.by_func_type[entry.func_type] = (stats.by_func_type[entry.func_type] || 0) + 1
      stats.by_status[entry.status] = (stats.by_status[entry.status] || 0) + 1
    }

    ctx.body = { success: true, data: stats }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to compute stats')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── Phase 2 Import Routes ────────────────────────────────────────────────────

// POST /api/tahp/knowledge/import/start — 启动文档导入任务
tahpKnowledgeRoutes.post('/api/tahp/knowledge/import/start', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { filename, content, content_base64 } = body

    if (!filename || typeof filename !== 'string') {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 filename' }
      return
    }

    const jobId = `job-${randomUUID().slice(0, 8)}`
    const job: ImportJob = {
      id: jobId,
      filename,
      status: 'processing',
      progress: 10,
      stage: 'upload',
      message: '文件已接收，准备解析...',
      entries: [],
      created_at: new Date().toISOString(),
    }
    importJobs.set(jobId, job)
    jobListeners.set(jobId, [])

    // Return jobId immediately
    ctx.body = { success: true, data: { job_id: jobId } }

    // Process asynchronously
    setImmediate(async () => {
      try {
        emitJobEvent(jobId, { stage: 'parse', progress: 30, message: '正在解析文档结构...' })
        await new Promise(r => setTimeout(r, 100)) // let SSE connect

        let textContent = ''
        const ext = filename.split('.').pop()?.toLowerCase() || ''

        const progressFn: ProgressFn = (progress, message) => {
          emitJobEvent(jobId, { progress, message })
        }

        if (content && typeof content === 'string') {
          textContent = content
        } else if (content_base64 && typeof content_base64 === 'string') {
          const buffer = Buffer.from(content_base64, 'base64')
          if (ext === 'pdf') {
            textContent = await extractPdfText(buffer, filename, progressFn)
          } else if (ext === 'docx' || ext === 'doc') {
            textContent = await extractDocxText(buffer, filename, progressFn)
          } else {
            textContent = buffer.toString('utf-8')
          }
        }

        if (!textContent.trim()) {
          emitJobEvent(jobId, {
            status: 'error', stage: 'error', progress: 0,
            message: '文档内容为空或无法解析', error: '无法提取文本内容',
          })
          return
        }

        // 转换为规范 Markdown（失败则降级原文本）
        emitJobEvent(jobId, { stage: 'convert_markdown', progress: 55, message: '正在转换为规范 Markdown...' })
        const conv = await normalizeToMarkdown(textContent, filename)

        emitJobEvent(jobId, { stage: 'extract', progress: 80, message: '正在智能提取知识条目...' })
        await new Promise(r => setTimeout(r, 200))

        // 优先用规范化后的 Markdown 切分 chunk（标题边界更清晰）
        const chunkSource = conv.status === 'done' ? conv.markdown : textContent
        const entries = extractEntriesFromText(chunkSource, filename)

        emitJobEvent(jobId, {
          stage: 'done', progress: 100,
          message: `解析完成，提取 ${entries.length} 条知识条目`,
          status: 'done', entries,
          full_text: textContent,   // preserve for KnowledgeDocument creation on save
          markdown: conv.markdown,
          conversion_status: conv.status,
          conversion_note: conv.note,
        })
        logger.info({ jobId, filename, count: entries.length, conversion: conv.status }, '[kb] import job done')
      } catch (err) {
        const msg = (err as Error).message
        emitJobEvent(jobId, { status: 'error', stage: 'error', progress: 0, message: msg, error: msg })
        logger.error({ jobId, err: msg }, '[kb] import job failed')
      }
    })
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/import/jobs/:jobId/progress — SSE 实时进度流
tahpKnowledgeRoutes.get('/api/tahp/knowledge/import/jobs/:jobId/progress', async (ctx) => {
  const { jobId } = ctx.params
  const job = importJobs.get(jobId)
  if (!job) {
    ctx.status = 404
    ctx.body = { success: false, error: '任务不存在' }
    return
  }

  ctx.set('Content-Type', 'text/event-stream')
  ctx.set('Cache-Control', 'no-cache')
  ctx.set('Connection', 'keep-alive')
  ctx.set('X-Accel-Buffering', 'no')

  const stream = new PassThrough()
  ctx.body = stream

  // Send current state immediately
  stream.write(`data: ${JSON.stringify(job)}\n\n`)

  if (job.status === 'done' || job.status === 'error') {
    stream.end()
    return
  }

  const listener = (data: string) => {
    try {
      stream.write(`data: ${data}\n\n`)
      const j = JSON.parse(data)
      if (j.status === 'done' || j.status === 'error') {
        setTimeout(() => { try { stream.end() } catch { /* ignore */ } }, 200)
      }
    } catch { /* ignore */ }
  }

  const ls = jobListeners.get(jobId) || []
  ls.push(listener)
  jobListeners.set(jobId, ls)

  ctx.req.on('close', () => {
    const current = jobListeners.get(jobId) || []
    const idx = current.indexOf(listener)
    if (idx >= 0) current.splice(idx, 1)
  })
})

// GET /api/tahp/knowledge/import/jobs/:jobId — 获取任务状态
tahpKnowledgeRoutes.get('/api/tahp/knowledge/import/jobs/:jobId', async (ctx) => {
  const { jobId } = ctx.params
  const job = importJobs.get(jobId)
  if (!job) {
    ctx.status = 404
    ctx.body = { success: false, error: '任务不存在' }
    return
  }
  ctx.body = { success: true, data: job }
})

// POST /api/tahp/knowledge/import/jobs/:jobId/save — 保存选中条目到知识库
tahpKnowledgeRoutes.post('/api/tahp/knowledge/import/jobs/:jobId/save', async (ctx) => {
  try {
    const { jobId } = ctx.params
    const job = importJobs.get(jobId)
    if (!job) {
      ctx.status = 404; ctx.body = { success: false, error: '任务不存在' }; return
    }
    if (job.status !== 'done') {
      ctx.status = 400; ctx.body = { success: false, error: '任务尚未完成' }; return
    }

    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const selectedIds = Array.isArray(body.entry_ids) ? (body.entry_ids as string[]) : []
    const toSave = selectedIds.length > 0 ? job.entries.filter(e => selectedIds.includes(e.id)) : job.entries

    const now = new Date().toISOString()
    const saved: KnowledgeEntry[] = []
    const createdDocIds: string[] = []

    // Helper: count most-frequent value
    const mostFrequent = (arr: string[], fallback: string): string => {
      const m: Record<string, number> = {}
      for (const v of arr) m[v] = (m[v] || 0) + 1
      return Object.entries(m).sort((a, b) => b[1] - a[1])[0]?.[0] ?? fallback
    }

    if (job.batch_docs && job.batch_docs.length > 0) {
      // ── Batch (folder) mode: one KnowledgeDocument per source file ──────────
      for (const batchFile of job.batch_docs) {
        const fileChunks = toSave.filter(e => e.source_file === batchFile.filename)
        if (fileChunks.length === 0 && !batchFile.full_text.trim()) continue

        const docId = `doc-${randomUUID().slice(0, 8)}`
        const docTitle = batchFile.filename.replace(/\.[^/.]+$/, '').trim()
        const doc: KnowledgeDocument = {
          id: docId,
          title: docTitle,
          filename: batchFile.filename,
          content: batchFile.full_text,
          content_markdown: batchFile.markdown,
          conversion_status: batchFile.conversion_status,
          conversion_note: batchFile.conversion_note,
          module: mostFrequent(fileChunks.map(e => e.module), 'shared'),
          category: mostFrequent(fileChunks.map(e => e.category), '其他'),
          chunk_ids: [],
          created_at: now, updated_at: now,
          char_count: batchFile.full_text.length,
          chunk_count: fileChunks.length,
        }
        for (const ext of fileChunks) {
          const entry: KnowledgeEntry = {
            id: `kb-${randomUUID().slice(0, 8)}`, content: ext.content, category: ext.category,
            module: ext.module, func_type: ext.func_type, keywords: ext.keywords,
            confidence_score: ext.confidence_score, source_file: ext.source_file,
            source_section: ext.source_section, source_document_id: docId,
            created_at: now, updated_at: now, status: 'pending_review', is_verified: false, usage_count: 0,
          }
          await writeEntry(entry)
          saved.push(entry)
          doc.chunk_ids.push(entry.id)
        }
        doc.chunk_count = doc.chunk_ids.length
        await writeDocument(doc)
        createdDocIds.push(docId)
      }
    } else {
      // ── Single file / URL mode: one KnowledgeDocument for the job ───────────
      const docId = `doc-${randomUUID().slice(0, 8)}`
      const rawTitle = (job.full_text?.match(/^#{1,3}\s+(.+)$/m)?.[1] ?? job.filename)
        .replace(/\.[^/.]+$/, '').trim()
      const doc: KnowledgeDocument = {
        id: docId,
        title: rawTitle,
        filename: job.source_url || job.filename,
        content: job.full_text || '',
        content_markdown: job.markdown,
        conversion_status: job.conversion_status,
        conversion_note: job.conversion_note,
        module: mostFrequent(toSave.map(e => e.module), 'shared'),
        category: mostFrequent(toSave.map(e => e.category), '其他'),
        chunk_ids: [],
        created_at: now, updated_at: now,
        char_count: (job.full_text || '').length,
        chunk_count: toSave.length,
      }
      for (const ext of toSave) {
        const entry: KnowledgeEntry = {
          id: `kb-${randomUUID().slice(0, 8)}`, content: ext.content, category: ext.category,
          module: ext.module, func_type: ext.func_type, keywords: ext.keywords,
          confidence_score: ext.confidence_score, source_file: ext.source_file,
          source_section: ext.source_section, source_document_id: docId,
          created_at: now, updated_at: now, status: 'pending_review', is_verified: false, usage_count: 0,
        }
        await writeEntry(entry)
        saved.push(entry)
        doc.chunk_ids.push(entry.id)
      }
      doc.chunk_count = saved.length
      await writeDocument(doc)
      createdDocIds.push(docId)
    }

    // Clean up job after saving
    importJobs.delete(jobId)
    jobListeners.delete(jobId)

    logger.info({ jobId, docs: createdDocIds.length, saved: saved.length }, '[kb] import saved')
    ctx.body = { success: true, data: { saved: saved.length, doc_ids: createdDocIds, entries: saved } }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] import save failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── Phase 3 Import Mode: URL Fetch ──────────────────────────────────────────

tahpKnowledgeRoutes.post('/api/tahp/knowledge/import/fetch-url', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const { url } = body
  if (!url || typeof url !== 'string') {
    ctx.status = 400; ctx.body = { success: false, error: '缺少 url' }; return
  }
  try { new URL(url) } catch {
    ctx.status = 400; ctx.body = { success: false, error: '无效的 URL 格式' }; return
  }

  const jobId = `job-${randomUUID().slice(0, 8)}`
  const job: ImportJob = {
    id: jobId, filename: url, source_url: url,
    status: 'processing', progress: 10, stage: 'upload',
    message: '正在连接并抓取网页内容...', entries: [],
    created_at: new Date().toISOString(),
  }
  importJobs.set(jobId, job)
  jobListeners.set(jobId, [])
  ctx.body = { success: true, data: { job_id: jobId } }

  setImmediate(async () => {
    try {
      emitJobEvent(jobId, { stage: 'parse', progress: 30, message: '正在解析网页结构...' })
      const textContent = await fetchUrlText(url)

      if (!textContent.trim()) {
        emitJobEvent(jobId, { status: 'error', stage: 'error', progress: 0, message: '无法从该 URL 提取文本内容', error: '内容为空' })
        return
      }

      emitJobEvent(jobId, { stage: 'convert_markdown', progress: 50, message: '正在转换为规范 Markdown...' })
      const conv = await normalizeToMarkdown(textContent, url)

      emitJobEvent(jobId, { stage: 'extract', progress: 80, message: '正在提取知识条目...' })
      await new Promise(r => setTimeout(r, 100))
      const chunkSource = conv.status === 'done' ? conv.markdown : textContent
      const entries = extractEntriesFromText(chunkSource, url)

      emitJobEvent(jobId, {
        stage: 'done', status: 'done', progress: 100,
        message: `抓取完成，提取 ${entries.length} 条知识条目`,
        entries, full_text: textContent,
        markdown: conv.markdown,
        conversion_status: conv.status,
        conversion_note: conv.note,
      })
    } catch (err) {
      const msg = (err as Error).message
      emitJobEvent(jobId, { status: 'error', stage: 'error', progress: 0, message: '抓取失败：' + msg, error: msg })
    }
  })
})

// ─── Phase 3 Import Mode: Folder Scan ────────────────────────────────────────

const FOLDER_SUPPORTED_EXTS = ['.txt', '.md', '.pdf', '.docx', '.doc']

tahpKnowledgeRoutes.post('/api/tahp/knowledge/import/scan-folder', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const { folder_path, recursive } = body
  if (!folder_path || typeof folder_path !== 'string') {
    ctx.status = 400; ctx.body = { success: false, error: '缺少 folder_path' }; return
  }
  if (!existsSync(folder_path)) {
    ctx.status = 400; ctx.body = { success: false, error: `文件夹不存在: ${folder_path}` }; return
  }

  // Collect files from folder (optional single-level recursion)
  let allFiles: string[] = []
  try {
    const scan = (dir: string, depth: number) => {
      for (const item of readdirSync(dir, { withFileTypes: true })) {
        if (item.isDirectory() && recursive && depth < 2) {
          scan(join(dir, item.name), depth + 1)
        } else if (item.isFile() && FOLDER_SUPPORTED_EXTS.some(e => item.name.toLowerCase().endsWith(e))) {
          allFiles.push(join(dir, item.name))
        }
      }
    }
    scan(folder_path, 0)
  } catch (e) {
    ctx.status = 400; ctx.body = { success: false, error: '无法读取文件夹: ' + (e as Error).message }; return
  }

  if (allFiles.length === 0) {
    ctx.status = 400; ctx.body = { success: false, error: '文件夹中没有可导入的文档（支持：txt、md、pdf、docx）' }; return
  }

  const jobId = `job-${randomUUID().slice(0, 8)}`
  const job: ImportJob = {
    id: jobId,
    filename: `[批量] ${folder_path}`,
    status: 'processing', progress: 5, stage: 'upload',
    message: `发现 ${allFiles.length} 份文档，开始批量处理...`,
    entries: [], total_files: allFiles.length, processed_files: 0,
    created_at: new Date().toISOString(),
  }
  importJobs.set(jobId, job)
  jobListeners.set(jobId, [])
  ctx.body = { success: true, data: { job_id: jobId, file_count: allFiles.length } }

  setImmediate(async () => {
    try {
      const allEntries: ExtractedEntry[] = []
      const batchDocs: NonNullable<ImportJob['batch_docs']> = []

      for (let i = 0; i < allFiles.length; i++) {
        const filePath = allFiles[i]
        const filename = filePath.split(/[/\\]/).pop() || filePath
        const ext = filename.split('.').pop()?.toLowerCase() || ''
        const pct = Math.round(10 + (i / allFiles.length) * 75)

        emitJobEvent(jobId, {
          progress: pct, stage: 'parse',
          message: `(${i + 1}/${allFiles.length}) 正在处理: ${filename}`,
          processed_files: i + 1,
        })

        try {
          const buffer = readFileSync(filePath)
          let textContent = ''

          const progressFn: ProgressFn = (_p, m) => emitJobEvent(jobId, { progress: pct, message: m })
          if (ext === 'pdf') {
            textContent = await extractPdfText(buffer, filename, progressFn)
          } else if (ext === 'docx' || ext === 'doc') {
            textContent = await extractDocxText(buffer, filename, progressFn)
          } else {
            textContent = buffer.toString('utf-8')
          }

          if (textContent.trim() && !isGarbledText(textContent)) {
            emitJobEvent(jobId, {
              stage: 'convert_markdown', progress: pct,
              message: `(${i + 1}/${allFiles.length}) 转换 Markdown: ${filename}`,
            })
            const conv = await normalizeToMarkdown(textContent, filename)
            batchDocs.push({
              filename, full_text: textContent,
              markdown: conv.markdown,
              conversion_status: conv.status,
              conversion_note: conv.note,
            })
            const chunkSource = conv.status === 'done' ? conv.markdown : textContent
            allEntries.push(...extractEntriesFromText(chunkSource, filename))
          } else if (textContent.trim()) {
            logger.warn({ filename }, '[kb] skipped garbled/unreadable file in batch')
          }
        } catch (fileErr) {
          logger.warn({ filePath, err: (fileErr as Error).message }, '[kb] skipped file during batch scan')
        }
      }

      emitJobEvent(jobId, {
        stage: 'extract', progress: 92,
        message: `已处理 ${batchDocs.length} 份文档，共提取 ${allEntries.length} 条知识条目...`,
      })
      await new Promise(r => setTimeout(r, 200))

      emitJobEvent(jobId, {
        stage: 'done', status: 'done', progress: 100,
        message: `批量完成：${batchDocs.length}/${allFiles.length} 份文档成功，${allEntries.length} 条知识条目`,
        entries: allEntries, batch_docs: batchDocs,
      })
    } catch (err) {
      const msg = (err as Error).message
      emitJobEvent(jobId, { status: 'error', stage: 'error', progress: 0, message: msg, error: msg })
    }
  })
})

// ─── Phase 3 Document Routes ─────────────────────────────────────────────────

// GET /api/tahp/knowledge/documents — 文档列表（不含全文，减少传输量）
tahpKnowledgeRoutes.get('/api/tahp/knowledge/documents', async (ctx) => {
  try {
    const docs = await listDocuments()
    // Strip full text from list response for performance
    const summaries = docs.map(({ content: _c, ...rest }) => rest)
    ctx.body = { success: true, data: { documents: summaries, total: summaries.length } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/documents/:docId — 获取单份文档（含全文）
tahpKnowledgeRoutes.get('/api/tahp/knowledge/documents/:docId', async (ctx) => {
  try {
    const doc = await readDocument(ctx.params.docId)
    if (!doc) {
      ctx.status = 404; ctx.body = { success: false, error: '文档不存在' }; return
    }
    ctx.body = { success: true, data: doc }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// DELETE /api/tahp/knowledge/documents/:docId — 删除文档及关联 chunks
tahpKnowledgeRoutes.delete('/api/tahp/knowledge/documents/:docId', async (ctx) => {
  try {
    const doc = await readDocument(ctx.params.docId)
    if (!doc) {
      ctx.status = 404; ctx.body = { success: false, error: '文档不存在' }; return
    }
    // Soft-delete all linked chunks
    let chunksDeleted = 0
    for (const chunkId of doc.chunk_ids) {
      const entry = await readEntry(chunkId)
      if (entry) {
        entry.status = 'archived'
        entry.updated_at = new Date().toISOString()
        await writeEntry(entry)
        chunksDeleted++
      }
    }
    // Hard-delete the document record itself
    try { unlinkSync(getDocumentPath(doc.id)) } catch { /* already gone */ }
    logger.info({ docId: doc.id, chunksDeleted }, '[kb] document deleted')
    ctx.body = { success: true, data: { deleted: doc.id, chunks_archived: chunksDeleted } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/documents/:docId/chunks — 该文档的所有 chunk 条目
tahpKnowledgeRoutes.get('/api/tahp/knowledge/documents/:docId/chunks', async (ctx) => {
  try {
    const doc = await readDocument(ctx.params.docId)
    if (!doc) {
      ctx.status = 404; ctx.body = { success: false, error: '文档不存在' }; return
    }
    const chunks: KnowledgeEntry[] = []
    for (const chunkId of doc.chunk_ids) {
      const entry = await readEntry(chunkId)
      if (entry && entry.status !== 'archived') chunks.push(entry)
    }
    ctx.body = { success: true, data: { chunks, total: chunks.length } }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/documents/:docId/reconvert — 手动重试 Markdown 规范化
tahpKnowledgeRoutes.post('/api/tahp/knowledge/documents/:docId/reconvert', async (ctx) => {
  try {
    const doc = await readDocument(ctx.params.docId)
    if (!doc) {
      ctx.status = 404; ctx.body = { success: false, error: '文档不存在' }; return
    }
    if (!doc.content?.trim()) {
      ctx.status = 400; ctx.body = { success: false, error: '文档无原始文本，无法转换' }; return
    }
    const conv = await normalizeToMarkdown(doc.content, doc.filename || doc.title)
    doc.content_markdown = conv.markdown
    doc.conversion_status = conv.status
    doc.conversion_note = conv.note
    doc.updated_at = new Date().toISOString()
    await writeDocument(doc)
    logger.info({ docId: doc.id, conversion: conv.status }, '[kb] document reconvert done')
    ctx.body = {
      success: true,
      data: {
        id: doc.id,
        conversion_status: conv.status,
        conversion_note: conv.note,
        content_markdown: conv.markdown,
      },
    }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 生命周期管控路由 (Lifecycle Management) ────────────────────────────────────

// DELETE /api/tahp/knowledge/skill-drafts/:draftId — 删除草稿（仅 draft/rejected）
tahpKnowledgeRoutes.delete('/api/tahp/knowledge/skill-drafts/:draftId', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return
    }
    if (draft.status !== 'draft' && draft.status !== 'rejected') {
      ctx.status = 409; ctx.body = { success: false, error: `仅 draft/rejected 状态可删除，当前状态: ${draft.status}` }; return
    }
    try { unlinkSync(getSkillDraftPath(draftId)) } catch { /* already gone */ }
    writeAuditLog({
      action: 'skill_draft_deleted',
      actor: 'admin',
      target_type: 'skill_draft',
      target_id: draftId,
      target_name: draft.skill_name,
      details: { status: draft.status, module: draft.module, func_type: draft.func_type },
    })
    ctx.body = { success: true, data: { deleted: draftId } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/deprecate — 废弃已激活 Skill
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/deprecate', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const reason = String(body.reason || '').trim()
    if (!reason) {
      ctx.status = 400; ctx.body = { success: false, error: '废弃原因为必填' }; return
    }
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return
    }
    if (draft.status !== 'approved') {
      ctx.status = 409; ctx.body = { success: false, error: `仅 approved 状态可废弃，当前状态: ${draft.status}` }; return
    }
    // 修改磁盘 SKILL.md 的 frontmatter status
    const skillDir = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills', draft.skill_id)
    const skillMd = join(skillDir, 'SKILL.md')
    if (existsSync(skillMd)) {
      let content = readFileSync(skillMd, 'utf-8')
      const fmMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---(\r?\n|$)/)
      if (fmMatch) {
        let fmLines = fmMatch[1].split(/\r?\n/)
        const statusIdx = fmLines.findIndex(l => l.startsWith('status:'))
        const statusLine = `status: "deprecated"`
        if (statusIdx >= 0) fmLines[statusIdx] = statusLine
        else fmLines.push(statusLine)
        const rest = content.slice(fmMatch[0].length)
        content = `---\n${fmLines.join('\n')}\n---\n${rest}`
        writeFileSync(skillMd, content, 'utf-8')
      }
    }
    // 更新草稿状态
    draft.status = 'deprecated'
    draft.deprecated_at = new Date().toISOString()
    draft.deprecated_by = String(body.deprecated_by || 'admin')
    draft.deprecate_reason = reason
    await writeSkillDraft(draft)
    writeAuditLog({
      action: 'skill_draft_deprecated',
      actor: draft.deprecated_by,
      target_type: 'skill_draft',
      target_id: draftId,
      target_name: draft.skill_name,
      reason,
      details: { skill_id: draft.skill_id, module: draft.module, func_type: draft.func_type },
    })
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/deactivate — 下线(物理移除磁盘文件)
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/deactivate', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const reason = String(body.reason || '').trim()
    if (!reason) {
      ctx.status = 400; ctx.body = { success: false, error: '下线原因为必填' }; return
    }
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return
    }
    if (draft.status !== 'approved' && draft.status !== 'deprecated') {
      ctx.status = 409; ctx.body = { success: false, error: `仅 approved/deprecated 状态可下线，当前状态: ${draft.status}` }; return
    }
    // 移动磁盘文件到 .archive
    const skillsRoot = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
    const srcDir = join(skillsRoot, draft.skill_id)
    const archiveDir = join(skillsRoot, '.archive')
    const destDir = join(archiveDir, draft.skill_id)
    if (existsSync(srcDir)) {
      mkdirSync(archiveDir, { recursive: true })
      if (existsSync(destDir)) rmSync(destDir, { recursive: true, force: true })
      renameSync(srcDir, destDir)
    }
    const originalStatus = draft.status
    draft.status = 'archived'
    draft.archived_at = new Date().toISOString()
    draft.archived_by = String(body.archived_by || 'admin')
    draft.archived_from_status = originalStatus
    draft.deprecate_reason = draft.deprecate_reason || reason
    await writeSkillDraft(draft)
    writeAuditLog({
      action: 'skill_draft_deactivated',
      actor: draft.archived_by,
      target_type: 'skill_draft',
      target_id: draftId,
      target_name: draft.skill_name,
      reason,
      details: { skill_id: draft.skill_id, module: draft.module, func_type: draft.func_type, previous_status: originalStatus },
    })
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/archive — 归档草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/archive', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return
    }
    if (draft.status === 'archived') {
      ctx.status = 409; ctx.body = { success: false, error: '已经是归档状态' }; return
    }
    const originalStatus = draft.status
    draft.status = 'archived'
    draft.archived_at = new Date().toISOString()
    draft.archived_by = 'admin'
    draft.archived_from_status = originalStatus
    await writeSkillDraft(draft)
    writeAuditLog({
      action: 'skill_draft_archived',
      actor: 'admin',
      target_type: 'skill_draft',
      target_id: draftId,
      target_name: draft.skill_name,
      details: { previous_status: originalStatus },
    })
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/:draftId/restore — 恢复归档草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/:draftId/restore', async (ctx) => {
  try {
    const { draftId } = ctx.params
    const draft = await readSkillDraft(draftId)
    if (!draft) {
      ctx.status = 404; ctx.body = { success: false, error: '草稿不存在' }; return
    }
    if (draft.status !== 'archived') {
      ctx.status = 409; ctx.body = { success: false, error: `仅 archived 状态可恢复，当前状态: ${draft.status}` }; return
    }
    const restoreTo = draft.archived_from_status || 'draft'
    draft.status = restoreTo as SkillDraft['status']
    delete draft.archived_at
    delete draft.archived_by
    delete draft.archived_from_status
    // 如果之前下线了磁盘文件，从 .archive 移回
    if (draft.skill_id) {
      const skillsRoot = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
      const archiveSrc = join(skillsRoot, '.archive', draft.skill_id)
      const destDir = join(skillsRoot, draft.skill_id)
      if (existsSync(archiveSrc) && !existsSync(destDir)) {
        renameSync(archiveSrc, destDir)
      }
    }
    await writeSkillDraft(draft)
    writeAuditLog({
      action: 'skill_draft_restored',
      actor: 'admin',
      target_type: 'skill_draft',
      target_id: draftId,
      target_name: draft.skill_name,
      details: { restored_to: restoreTo },
    })
    ctx.body = { success: true, data: draft }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/bulk-cleanup — 批量清理 rejected 草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/bulk-cleanup', async (ctx) => {
  try {
    await initDirs()
    const allDrafts = await listSkillDrafts()
    const rejected = allDrafts.filter(d => d.status === 'rejected')
    let cleaned = 0
    for (const d of rejected) {
      try { unlinkSync(getSkillDraftPath(d.id)); cleaned++ } catch { /* skip */ }
    }
    writeAuditLog({
      action: 'skill_bulk_cleanup',
      actor: 'admin',
      target_type: 'skill_draft',
      target_id: 'bulk',
      details: { cleaned_count: cleaned, draft_ids: rejected.map(d => d.id) },
    })
    ctx.body = { success: true, data: { cleaned } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/bulk-deprecate — 批量废弃已激活 Skill
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/bulk-deprecate', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const draftIds: string[] = Array.isArray(body.draft_ids) ? body.draft_ids.map(String) : []
    const reason = String(body.reason || '').trim()
    if (!draftIds.length) {
      ctx.status = 400; ctx.body = { success: false, error: '缺少 draft_ids' }; return
    }
    if (!reason) {
      ctx.status = 400; ctx.body = { success: false, error: '废弃原因为必填' }; return
    }
    let deprecated = 0
    for (const id of draftIds) {
      const draft = await readSkillDraft(id)
      if (!draft || draft.status !== 'approved') continue
      // 修改 SKILL.md frontmatter
      const skillMd = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills', draft.skill_id, 'SKILL.md')
      if (existsSync(skillMd)) {
        let content = readFileSync(skillMd, 'utf-8')
        const fmMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---(\r?\n|$)/)
        if (fmMatch) {
          let fmLines = fmMatch[1].split(/\r?\n/)
          const statusIdx = fmLines.findIndex(l => l.startsWith('status:'))
          if (statusIdx >= 0) fmLines[statusIdx] = `status: "deprecated"`
          else fmLines.push(`status: "deprecated"`)
          const rest = content.slice(fmMatch[0].length)
          content = `---\n${fmLines.join('\n')}\n---\n${rest}`
          writeFileSync(skillMd, content, 'utf-8')
        }
      }
      draft.status = 'deprecated'
      draft.deprecated_at = new Date().toISOString()
      draft.deprecated_by = 'admin'
      draft.deprecate_reason = reason
      await writeSkillDraft(draft)
      deprecated++
    }
    writeAuditLog({
      action: 'skill_bulk_deprecate',
      actor: 'admin',
      target_type: 'skill_draft',
      target_id: 'bulk',
      reason,
      details: { deprecated_count: deprecated, draft_ids: draftIds },
    })
    ctx.body = { success: true, data: { deprecated } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 知识条目管理增强路由 ──────────────────────────────────────────────────────

// DELETE /api/tahp/knowledge/entries/:entryId/hard — 物理删除条目
tahpKnowledgeRoutes.delete('/api/tahp/knowledge/entries/:entryId/hard', async (ctx) => {
  try {
    const { entryId } = ctx.params
    const entry = await readEntry(entryId)
    if (!entry) {
      ctx.status = 404; ctx.body = { success: false, error: '条目不存在' }; return
    }
    try { unlinkSync(getEntryPath(entryId)) } catch { /* already gone */ }
    writeAuditLog({
      action: 'entry_hard_deleted',
      actor: 'admin',
      target_type: 'knowledge_entry',
      target_id: entryId,
      details: { module: entry.module, func_type: entry.func_type, status: entry.status },
    })
    ctx.body = { success: true, data: { deleted: entryId } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/entries/bulk-archive — 批量归档条目
// 支持 ids: string[] 精确归档，无 ids 时按 module/before 筛选
tahpKnowledgeRoutes.post('/api/tahp/knowledge/entries/bulk-archive', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const ids = Array.isArray(body.ids) ? (body.ids as string[]) : null
    const filterModule = body.module ? String(body.module) : undefined
    const filterBefore = body.before ? String(body.before) : undefined
    const allEntries = await listEntries()
    let archived = 0
    for (const entry of allEntries) {
      if (entry.status === 'archived') continue
      if (ids) {
        if (!ids.includes(entry.id)) continue
      } else {
        if (filterModule && entry.module !== filterModule) continue
        if (filterBefore && entry.created_at >= filterBefore) continue
      }
      entry.status = 'archived'
      entry.updated_at = new Date().toISOString()
      await writeEntry(entry)
      archived++
    }
    writeAuditLog({
      action: 'entry_bulk_archived',
      actor: 'admin',
      target_type: 'knowledge_entry',
      target_id: ids ? ids.join(',') : 'bulk',
      details: { archived_count: archived, ids, filter_module: filterModule, filter_before: filterBefore },
    })
    ctx.body = { success: true, data: { archived } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/entries/bulk-delete — 批量物理删除条目
// 支持 ids: string[] 精确删除，无 ids 时只删除 archived 状态
tahpKnowledgeRoutes.post('/api/tahp/knowledge/entries/bulk-delete', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const ids = Array.isArray(body.ids) ? (body.ids as string[]) : null
    const filterModule = body.module ? String(body.module) : undefined
    const allEntries = await listEntries()
    let deleted = 0
    for (const entry of allEntries) {
      if (ids) {
        if (!ids.includes(entry.id)) continue
      } else {
        if (entry.status !== 'archived') continue
        if (filterModule && entry.module !== filterModule) continue
      }
      try { unlinkSync(getEntryPath(entry.id)); deleted++ } catch { /* skip */ }
    }
    writeAuditLog({
      action: 'entry_bulk_deleted',
      actor: 'admin',
      target_type: 'knowledge_entry',
      target_id: ids ? ids.join(',') : 'bulk',
      details: { deleted_count: deleted, ids, filter_module: filterModule },
    })
    ctx.body = { success: true, data: { deleted } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/stats/enhanced — 增强统计
tahpKnowledgeRoutes.get('/api/tahp/knowledge/stats/enhanced', async (ctx) => {
  try {
    await initDirs()
    const allEntries = await listEntries()
    const allDrafts = await listSkillDrafts()
    const activated = getActivatedSkills()

    // 条目状态分布
    const entryByStatus: Record<string, number> = {}
    for (const e of allEntries) {
      entryByStatus[e.status] = (entryByStatus[e.status] || 0) + 1
    }
    // 草稿状态分布
    const draftByStatus: Record<string, number> = {}
    for (const d of allDrafts) {
      draftByStatus[d.status] = (draftByStatus[d.status] || 0) + 1
    }
    // 过期条目数（expires_at < now）
    const now = new Date().toISOString()
    const expiredEntries = allEntries.filter(e => e.expires_at && e.expires_at < now && e.status !== 'archived').length
    // 废弃 Skill 数
    const deprecatedSkills = allDrafts.filter(d => d.status === 'deprecated').length

    ctx.body = {
      success: true,
      data: {
        entry_by_status: entryByStatus,
        draft_by_status: draftByStatus,
        total_entries: allEntries.length,
        total_drafts: allDrafts.length,
        activated_skills: activated.length,
        expired_entries: expiredEntries,
        deprecated_skills: deprecatedSkills,
      },
    }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/governance — 知识库治理面板（可运营指标 + 钻取数据）
tahpKnowledgeRoutes.get('/api/tahp/knowledge/governance', async (ctx) => {
  try {
    await initDirs()
    const allEntries = await listEntries()
    const allDrafts = await listSkillDrafts()
    const allDocs = await listDocuments()
    const activated = getActivatedSkills()

    const now = Date.now()
    const in30d = now + 30 * 24 * 3600 * 1000
    const live = allEntries.filter(e => e.status !== 'archived' && e.status !== 'deleted' && e.status !== 'rejected')

    const pendingEntries = live.filter(e => e.status === 'pending_review')
    const expiredEntries = live.filter(e => e.expires_at && new Date(e.expires_at).getTime() < now)
    const expiringSoon = live.filter(e => e.expires_at && new Date(e.expires_at).getTime() >= now && new Date(e.expires_at).getTime() < in30d)
    const lowConfidence = live.filter(e => (e.confidence_score ?? 1) < 0.6)
    const zeroUsage = live.filter(e => (e.usage_count || 0) === 0)

    // 热门检索 TopN（按 usage_count）
    const topUsed = [...live]
      .filter(e => (e.usage_count || 0) > 0)
      .sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0))
      .slice(0, 8)
      .map(e => ({
        id: e.id,
        content_preview: e.content.slice(0, 60),
        usage_count: e.usage_count || 0,
        module: e.module,
      }))

    // 文档转换失败/跳过
    const conversionFailed = allDocs.filter(d => d.conversion_status === 'failed')
    const conversionSkipped = allDocs.filter(d => d.conversion_status === 'skipped')

    // Skill 覆盖盲区：同一 module×func_type 有 ≥3 条 live 条目，但无对应已激活 Skill / 草稿
    const coveredKeys = new Set<string>()
    for (const sk of activated) coveredKeys.add(`${normModule(sk.module)}::${normFuncType(sk.func_type)}`)
    for (const d of allDrafts) {
      if (d.status === 'rejected' || d.status === 'archived') continue
      coveredKeys.add(`${normModule(d.module)}::${normFuncType(d.func_type)}`)
    }
    const groupMap = new Map<string, { module: string; func_type: string; entry_ids: string[] }>()
    for (const e of live) {
      const key = `${normModule(e.module)}::${normFuncType(e.func_type)}`
      if (!groupMap.has(key)) groupMap.set(key, { module: e.module, func_type: e.func_type, entry_ids: [] })
      groupMap.get(key)!.entry_ids.push(e.id)
    }
    const blindSpots = [...groupMap.entries()]
      .filter(([key, g]) => g.entry_ids.length >= 3 && !coveredKeys.has(key))
      .map(([, g]) => ({ module: g.module, func_type: g.func_type, entry_count: g.entry_ids.length, entry_ids: g.entry_ids }))
      .sort((a, b) => b.entry_count - a.entry_count)

    const pendingDrafts = allDrafts.filter(d => d.status === 'draft' || d.status === 'reviewing').length
    const deprecatedSkills = allDrafts.filter(d => d.status === 'deprecated').length

    ctx.body = {
      success: true,
      data: {
        totals: {
          entries: allEntries.length,
          live_entries: live.length,
          documents: allDocs.length,
          drafts: allDrafts.length,
          activated_skills: activated.length,
        },
        pending_entries: pendingEntries.length,
        expired_entries: expiredEntries.length,
        expiring_soon: expiringSoon.length,
        low_confidence: lowConfidence.length,
        zero_usage: zeroUsage.length,
        pending_drafts: pendingDrafts,
        deprecated_skills: deprecatedSkills,
        conversion_failed: conversionFailed.length,
        conversion_skipped: conversionSkipped.length,
        top_used: topUsed,
        blind_spots: blindSpots.slice(0, 10),
      },
    }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] governance failed')
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/knowledge/audit-log — 审计日志查询
tahpKnowledgeRoutes.get('/api/tahp/knowledge/audit-log', async (ctx) => {
  try {
    const { limit = '100', action } = ctx.query
    const { readAuditLog } = await import('../../services/tahp/audit-log')
    const entries = readAuditLog(
      Math.min(parseInt(String(limit)) || 100, 500),
      action ? String(action) as any : undefined,
    )
    ctx.body = { success: true, data: { entries, total: entries.length } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── Legacy endpoints (kept for backward compatibility) ─────────────────────

// POST /api/tahp/knowledge/save — 保存知识条目（旧接口）
tahpKnowledgeRoutes.post('/api/tahp/knowledge/save', async (ctx) => {
  try {
    await initDirs()
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const { title, content, module: mod, tags, domain, author, category } = body

    if (typeof title !== 'string' || !title.trim()) {
      ctx.status = 400; ctx.body = { success: false, error: '缺少 title' }; return
    }
    if (typeof content !== 'string' || !content.trim()) {
      ctx.status = 400; ctx.body = { success: false, error: '缺少 content' }; return
    }
    if (typeof mod !== 'string' || !mod.trim()) {
      ctx.status = 400; ctx.body = { success: false, error: '缺少 module' }; return
    }

    const validModules = ['telephony', 'kernel-driver', 'power-mgmt', 'shared']
    const safeModule = validModules.includes(mod) ? mod : 'shared'

    const now = new Date()
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
    const rand4 = String(Math.floor(Math.random() * 9000) + 1000)
    const entryId = `kb-${safeModule}-${dateStr}-${rand4}`

    const docsDir = join(tahpPaths.knowledgeDir, safeModule, 'docs')
    mkdirSync(docsDir, { recursive: true })

    const filePath = join(docsDir, `${entryId}.md`)

    const frontmatter = {
      id:           entryId,
      title:        title.trim(),
      module:       safeModule,
      category:     (typeof category === 'string' && category.trim()) ? category.trim() : 'practice_note',
      type:         'practice_note',
      author:       (typeof author === 'string' && author.trim()) ? author.trim() : 'user',
      domain:       (typeof domain === 'string' && domain.trim()) ? domain.trim() : undefined,
      tags:         Array.isArray(tags) ? tags : (typeof tags === 'string' ? tags.split(',').map((t: string) => t.trim()).filter(Boolean) : [safeModule]),
      confidence:   0.85,
      referenced_by: [],
      source:       'chat_extract',
      created_at:   now.toISOString(),
      updated_at:   now.toISOString(),
    }

    const yamlStr  = yamlDump(frontmatter, { lineWidth: -1 }).trimEnd()
    const fileContent = `---\n${yamlStr}\n---\n\n${content.trim()}\n`

    await safeFileStore.writeText(filePath, fileContent)

    const indexPath = join(tahpPaths.knowledgeDir, safeModule, 'index.yaml')
    let index: any = { entries: { auto: [], cases: [], docs: [] }, module: safeModule, updated: dateStr, version: '1.0' }
    if (existsSync(indexPath)) {
      try { index = yamlLoad(readFileSync(indexPath, 'utf-8')) as any } catch { /* ignore */ }
    }
    if (!index.entries) index.entries = {}
    if (!Array.isArray(index.entries.docs)) index.entries.docs = []
    const alreadyIn = index.entries.docs.some((e: any) => (typeof e === 'string' ? e : e.id) === entryId)
    if (!alreadyIn) {
      index.entries.docs.push({ id: entryId, title: title.trim() })
      index.updated = dateStr
      await safeFileStore.writeText(indexPath, yamlDump(index, { lineWidth: -1 }))
    }

    ctx.body = { success: true, data: { id: entryId, file: `knowledge-base/${safeModule}/docs/${entryId}.md` } }
  } catch (err) {
    logger.error({ err: (err as Error).message }, '[kb] failed to save entry')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 草稿批量操作路由 ─────────────────────────────────────────────────

// POST /api/tahp/knowledge/skill-drafts/bulk-approve — 批量批准草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/bulk-approve', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const ids = Array.isArray(body.draft_ids) ? (body.draft_ids as string[]) : []
    if (!ids.length) { ctx.status = 400; ctx.body = { success: false, error: 'draft_ids is required' }; return }
    let approved = 0
    for (const id of ids) {
      const draft = await readSkillDraft(id)
      if (!draft || (draft.status !== 'draft' && draft.status !== 'reviewing')) continue
      draft.status = 'approved'
      draft.reviewed_by = 'admin'
      draft.reviewed_at = new Date().toISOString()
      draft.review_action = 'approve'
      draft.updated_at = new Date().toISOString()
      await writeSkillDraft(draft)
      approved++
    }
    writeAuditLog({ action: 'skill_bulk_approved', actor: 'admin', target_type: 'skill_draft', target_id: ids.join(','), details: { approved_count: approved } })
    ctx.body = { success: true, data: { approved } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/bulk-reject — 批量拒绝草稿
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/bulk-reject', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const ids = Array.isArray(body.draft_ids) ? (body.draft_ids as string[]) : []
    const reason = body.reason ? String(body.reason) : ''
    if (!ids.length) { ctx.status = 400; ctx.body = { success: false, error: 'draft_ids is required' }; return }
    let rejected = 0
    for (const id of ids) {
      const draft = await readSkillDraft(id)
      if (!draft || (draft.status !== 'draft' && draft.status !== 'reviewing')) continue
      draft.status = 'rejected'
      draft.reviewed_by = 'admin'
      draft.reviewed_at = new Date().toISOString()
      draft.review_action = 'reject'
      draft.review_notes = reason
      draft.updated_at = new Date().toISOString()
      await writeSkillDraft(draft)
      rejected++
    }
    writeAuditLog({ action: 'skill_bulk_rejected', actor: 'admin', target_type: 'skill_draft', target_id: ids.join(','), details: { rejected_count: rejected, reason } })
    ctx.body = { success: true, data: { rejected } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/bulk-delete — 批量删除草稿(仅 draft/rejected)
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/bulk-delete', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const ids = Array.isArray(body.draft_ids) ? (body.draft_ids as string[]) : []
    if (!ids.length) { ctx.status = 400; ctx.body = { success: false, error: 'draft_ids is required' }; return }
    let deleted = 0
    for (const id of ids) {
      const draft = await readSkillDraft(id)
      if (!draft || (draft.status !== 'draft' && draft.status !== 'rejected')) continue
      try { unlinkSync(getSkillDraftPath(id)); deleted++ } catch { /* skip */ }
    }
    writeAuditLog({ action: 'skill_bulk_deleted', actor: 'admin', target_type: 'skill_draft', target_id: ids.join(','), details: { deleted_count: deleted } })
    ctx.body = { success: true, data: { deleted } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/knowledge/skill-drafts/bulk-archive-selected — 批量归档草稿(approved/deprecated)
tahpKnowledgeRoutes.post('/api/tahp/knowledge/skill-drafts/bulk-archive-selected', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const ids = Array.isArray(body.draft_ids) ? (body.draft_ids as string[]) : []
    if (!ids.length) { ctx.status = 400; ctx.body = { success: false, error: 'draft_ids is required' }; return }
    let archived = 0
    for (const id of ids) {
      const draft = await readSkillDraft(id)
      if (!draft || (draft.status !== 'approved' && draft.status !== 'deprecated')) continue
      draft.archived_from_status = draft.status
      draft.status = 'archived'
      draft.archived_at = new Date().toISOString()
      draft.archived_by = 'admin'
      draft.updated_at = new Date().toISOString()
      await writeSkillDraft(draft)
      archived++
    }
    writeAuditLog({ action: 'skill_bulk_archived', actor: 'admin', target_type: 'skill_draft', target_id: ids.join(','), details: { archived_count: archived } })
    ctx.body = { success: true, data: { archived } }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})

// ─── 文档编辑路由 ─────────────────────────────────────────────────────

// PUT /api/tahp/knowledge/documents/:docId — 更新文档元数据
tahpKnowledgeRoutes.put('/api/tahp/knowledge/documents/:docId', async (ctx) => {
  try {
    const { docId } = ctx.params
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const doc = await readDocument(docId)
    if (!doc) { ctx.status = 404; ctx.body = { success: false, error: 'Document not found' }; return }
    if (typeof body.title === 'string' && body.title.trim()) doc.title = body.title.trim()
    if (typeof body.module === 'string' && body.module.trim()) doc.module = body.module.trim()
    doc.updated_at = new Date().toISOString()
    await writeDocument(doc)
    ctx.body = { success: true, data: doc }
  } catch (err) {
    ctx.status = 500; ctx.body = { success: false, error: (err as Error).message }
  }
})
