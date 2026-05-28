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
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, unlinkSync } from 'fs'
import { tmpdir } from 'os'
import { spawnSync } from 'child_process'
import { get as httpGet } from 'http'
import { get as httpsGet } from 'https'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'
import { tahpPaths } from '../../services/tahp/paths'
import { safeFileStore } from '../../services/safe-file-store'
import { logger } from '../../services/logger'
import { join } from 'path'
import { randomUUID } from 'crypto'
import { load as yamlLoad, dump as yamlDump } from 'js-yaml'

export const tahpKnowledgeRoutes = new Router()

// ─── Types ────────────────────────────────────────────────────────────────────

interface KnowledgeDocument {
  id: string
  title: string           // inferred from filename or first heading
  filename: string        // original uploaded filename
  content: string         // full extracted plain text
  module: string
  category: string
  chunk_ids: string[]     // IDs of KnowledgeEntry records derived from this doc
  created_at: string
  updated_at: string
  char_count: number
  chunk_count: number
}

interface KnowledgeEntry {
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
  applicable_versions?: string[]
  created_at: string
  updated_at: string
  expires_at?: string
  status: 'pending_review' | 'approved' | 'rejected' | 'archived'
  is_verified: boolean
  validation_date?: string
  maintenance_owner?: string
  last_used_in_task?: string
  usage_count: number
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
  status: 'draft' | 'reviewing' | 'approved' | 'rejected'
  reviewed_by?: string
  reviewed_at?: string
  review_notes?: string
  activated_at?: string
  activated_skill_path?: string
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
  stage: 'upload' | 'parse' | 'extract' | 'done' | 'error'
  message: string
  entries: ExtractedEntry[]
  full_text?: string   // single-file / URL: full extracted text
  source_url?: string  // URL import mode
  // Batch (folder) mode: one record per file
  batch_docs?: Array<{ filename: string; full_text: string }>
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
  // Exclude full_text from SSE payload (can be megabytes; saved at job save time)
  const { full_text: _ft, ...ssePayload } = job
  const payload = JSON.stringify(ssePayload)
  for (const listener of (jobListeners.get(jobId) || [])) {
    try { listener(payload) } catch { /* ignore */ }
  }
}

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
  const chinese = (content.match(/[一-龥]{2,6}/g) || []).slice(0, 5)
  const english = (content.match(/\b[A-Z][a-zA-Z]{2,}\b/g) || []).slice(0, 5)
  return [...new Set([...chinese, ...english])].slice(0, 8)
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

    // 筛选活跃条目
    entries = entries.filter(e => e.status !== 'archived' && e.status !== 'rejected')

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

// GET /api/tahp/knowledge/skill-drafts — 查询待审核 Skill 草稿
tahpKnowledgeRoutes.get('/api/tahp/knowledge/skill-drafts', async (ctx) => {
  try {
    await initDirs()
    const { status = 'draft', limit = '20', offset = '0' } = ctx.query

    let drafts = await listSkillDrafts()

    // 筛选状态
    if (status) drafts = drafts.filter(d => d.status === status)

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

    const updated: SkillDraft = {
      ...draft,
      status: action === 'approve' ? 'approved' : 'rejected',
      reviewed_by: reviewed_by ? String(reviewed_by) : undefined,
      reviewed_at: new Date().toISOString(),
      review_notes: review_notes ? String(review_notes) : undefined,
    }

    // 如果批准，尝试激活（写入到 skills/.claude/skills/<skillId>/）
    if (action === 'approve') {
      try {
        const skillsRoot = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
        const skillDir = join(skillsRoot, updated.skill_id)
        mkdirSync(skillDir, { recursive: true })

        const frontmatter = [
          `tahp_adapt_skill: true`,
          `name: ${updated.skill_id}`,
          `domain_label: "${updated.domain_label}"`,
          `domain_id: "${updated.skill_id}"`,
          `module: ${updated.module}`,
          `func_type: ${updated.func_type}`,
          `status: active`,
          `generated_from_knowledge: true`,
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
    ctx.body = { success: true, data: updated }
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

        emitJobEvent(jobId, { stage: 'extract', progress: 60, message: '正在智能提取知识条目...' })
        await new Promise(r => setTimeout(r, 200))

        const entries = extractEntriesFromText(textContent, filename)

        emitJobEvent(jobId, {
          stage: 'done', progress: 100,
          message: `解析完成，提取 ${entries.length} 条知识条目`,
          status: 'done', entries,
          full_text: textContent,   // preserve for KnowledgeDocument creation on save
        })
        logger.info({ jobId, filename, count: entries.length }, '[kb] import job done')
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

      emitJobEvent(jobId, { stage: 'extract', progress: 60, message: '正在提取知识条目...' })
      await new Promise(r => setTimeout(r, 100))
      const entries = extractEntriesFromText(textContent, url)

      emitJobEvent(jobId, {
        stage: 'done', status: 'done', progress: 100,
        message: `抓取完成，提取 ${entries.length} 条知识条目`,
        entries, full_text: textContent,
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
      const batchDocs: Array<{ filename: string; full_text: string }> = []

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
            batchDocs.push({ filename, full_text: textContent })
            allEntries.push(...extractEntriesFromText(textContent, filename))
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

// POST /api/tahp/knowledge/query — 查询知识库（旧接口）
tahpKnowledgeRoutes.post('/api/tahp/knowledge/query', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const query = body.query
  if (typeof query !== 'string' || !query.trim()) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 query' }
    return
  }
  const args: Record<string, unknown> = { query }
  if (body.module) args.module = body.module
  if (body.cross_module !== undefined) args.cross_module = body.cross_module
  if (body.top_k !== undefined) args.top_k = body.top_k
  try {
    const raw = await getMcpBridge().callTool('tahp_query_knowledge', args)
    const r = raw as any
    const unwrapped = r?.content?.[0]?.text ? JSON.parse(r.content[0].text || '') : raw
    ctx.body = { success: true, data: unwrapped }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
