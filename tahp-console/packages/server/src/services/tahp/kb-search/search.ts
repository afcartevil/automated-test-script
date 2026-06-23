import { readFileSync, existsSync, readdirSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from '../paths'
import { calculateRelevance, phraseOverlapScore } from './bm25'
import { buildSearchBlob } from './blob'
import {
  facetFilter,
  findByEntryId,
  findByJiraKey,
  getIndexRecords,
  tagOverlapScore,
  upsertIndexRecord,
} from './index-store'
import { parseKbQuery } from './query-parser'
import type { KbEntryLike, KbHit, KbSearchQuery } from './types'

const KB_ENTRIES_REL = 'knowledge-base/.kb-data/entries'
const DEFAULT_SNIPPET = Number(process.env.TAHP_KB_SNIPPET_CHARS || 800)
const DEFAULT_MIN_SCORE = Number(process.env.TAHP_KB_SEARCH_MIN_SCORE || 15)

function ensureIndexWarm(): void {
  if (getIndexRecords().length > 0) return
  const entriesDir = join(tahpPaths.knowledgeDir, '.kb-data', 'entries')
  if (!existsSync(entriesDir)) return
  try {
    for (const file of readdirSync(entriesDir)) {
      if (!file.endsWith('.json')) continue
      try {
        const entry = JSON.parse(readFileSync(join(entriesDir, file), 'utf-8')) as KbEntryLike
        if (entry?.id) upsertIndexRecord(entry)
      } catch { /* skip */ }
    }
  } catch { /* ignore */ }
}

function getEntryPath(entryId: string): string {
  return join(tahpPaths.knowledgeDir, '.kb-data', 'entries', `${entryId}.json`)
}

function readEntryFile(entryId: string): KbEntryLike | null {
  const path = getEntryPath(entryId)
  if (!existsSync(path)) return null
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as KbEntryLike
  } catch {
    return null
  }
}

function makeSnippet(content: string, maxLen = DEFAULT_SNIPPET): string {
  return content
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\|/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxLen)
}

function entryTitle(entry: KbEntryLike): string {
  if (entry.source_file) return entry.source_file
  if (entry.symptom_summary) return entry.symptom_summary.slice(0, 80)
  return entry.id
}

function toHit(entry: KbEntryLike, relevance: number): KbHit {
  return {
    id: entry.id,
    source_type: entry.source_type || (entry.source_task_id ? 'bug_distill' : entry.source_document_id ? 'doc_chunk' : 'manual'),
    module: entry.module,
    func_type: entry.func_type,
    title: entryTitle(entry),
    snippet: makeSnippet(entry.content),
    relevance,
    jira_key: entry.jira_key,
    status: entry.status,
    path: `${KB_ENTRIES_REL}/${entry.id}.json`,
    related_skill_ids: entry.related_skill_ids,
  }
}

export async function searchKb(options: KbSearchQuery): Promise<KbHit[]> {
  ensureIndexWarm()
  const parsed = parseKbQuery(options.query)
  const limit = Math.min(options.limit ?? 5, 20)
  const minScore = options.min_score ?? DEFAULT_MIN_SCORE
  const jiraFast = options.jira_fast_path !== false

  // JIRA / entry id 直达
  if (jiraFast && parsed.jira_key) {
    const rec = findByJiraKey(parsed.jira_key)
    if (rec) {
      const entry = readEntryFile(rec.id)
      if (entry) return [toHit(entry, 100)]
    }
  }
  if (parsed.entry_id) {
    const rec = findByEntryId(parsed.entry_id)
    if (rec) {
      const entry = readEntryFile(rec.id)
      if (entry) return [toHit(entry, 100)]
    }
  }

  let records = getIndexRecords()
  if (records.length === 0) return []

  records = facetFilter(records, {
    module: options.module,
    func_type: options.func_type,
    source_types: options.source_types,
    source_document_ids: options.source_document_ids,
    include_archived: options.include_archived ?? true,
  })

  const queryTerms = parsed.tokens
  if (queryTerms.length === 0 && !options.query.trim()) return []

  const moduleHint = options.module_hint || parsed.module_hint
  const candidates: Array<{ id: string; score: number }> = []
  for (const rec of records) {
    const tagScore = tagOverlapScore(rec, queryTerms) * 40
    const entry = readEntryFile(rec.id)
    if (!entry) continue
    const blob = buildSearchBlob(entry)
    const bm25 = calculateRelevance({ ...entry, search_blob: blob }, queryTerms)
    const phraseScore = phraseOverlapScore(options.query, blob)
    let sourceBoost = rec.source_type === 'bug_distill' ? 1.15 : rec.source_type === 'doc_summary' ? 1.1 : 1
    if (moduleHint && rec.module === moduleHint) sourceBoost *= 1.2
    const total = (tagScore + bm25 + phraseScore) * sourceBoost
    if (total > 0) candidates.push({ id: rec.id, score: total })
  }

  candidates.sort((a, b) => b.score - a.score)
  const hits: KbHit[] = []
  for (const { id, score } of candidates) {
    if (score < minScore && hits.length > 0) break
    const entry = readEntryFile(id)
    if (!entry) continue
    hits.push(toHit(entry, Math.round(score)))
    if (hits.length >= limit) break
  }
  return hits
}

function domainKeywordScore(blob: string, keywords: string[]): number {
  if (keywords.length === 0) return 0
  const lower = blob.toLowerCase()
  let hits = 0
  for (const kw of keywords) {
    const k = kw.toLowerCase()
    if (k.length >= 2 && lower.includes(k)) hits++
  }
  return (hits / keywords.length) * 65
}

/** 目录列举：放宽阈值、扩展领域词，返回多条 bug_distill 案例 */
export async function searchKbCatalog(options: {
  query: string
  domain_keywords?: string[]
  source_types?: KbSearchQuery['source_types']
  include_archived?: boolean
  limit?: number
  min_score?: number
}): Promise<KbHit[]> {
  ensureIndexWarm()
  const focus = options.query.trim()
  const parsed = parseKbQuery(focus)
  const domainKeywords = options.domain_keywords || []
  const queryTerms = parsed.tokens.filter(t => t.length >= 2)
  const limit = Math.min(options.limit ?? 15, 30)
  const minScore = options.min_score ?? 8

  let records = getIndexRecords()
  if (records.length === 0) return []

  records = facetFilter(records, {
    source_types: options.source_types,
    include_archived: options.include_archived ?? true,
  })

  const candidates: Array<{ id: string; score: number }> = []
  for (const rec of records) {
    const entry = readEntryFile(rec.id)
    if (!entry) continue
    const blob = buildSearchBlob(entry)
    const tagScore = tagOverlapScore(rec, queryTerms) * 35
    const bm25 = calculateRelevance({ ...entry, search_blob: blob }, queryTerms)
    const phraseScore = phraseOverlapScore(focus, blob) * 0.8
    const domainScore = domainKeywordScore(blob, domainKeywords)
    const sourceBoost = rec.source_type === 'bug_distill' ? 1.15 : 1
    const total = (tagScore + bm25 + phraseScore + domainScore) * sourceBoost
    if (total > 0) candidates.push({ id: rec.id, score: total })
  }

  candidates.sort((a, b) => b.score - a.score)
  const hits: KbHit[] = []
  for (const { id, score } of candidates) {
    if (score < minScore && hits.length > 0) break
    const entry = readEntryFile(id)
    if (!entry) continue
    hits.push(toHit(entry, Math.round(score)))
    if (hits.length >= limit) break
  }
  return hits
}

export { invalidateKbSearchIndex, upsertIndexRecord, removeIndexRecord, facetFilter, entryToIndexRecord } from './index-store'
