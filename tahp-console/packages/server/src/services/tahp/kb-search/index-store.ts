import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from '../paths'
import { buildSearchBlob, buildTags, inferJiraKey, inferSourceType } from './blob'
import { tokenize } from './bm25'
import type { KbEntryLike, KbIndexRecord, KbSearchQuery, KbSourceType } from './types'
import { parseKbQuery } from './query-parser'

const INDEX_REL = 'search-index.json'

function getIndexPath(): string {
  return join(tahpPaths.knowledgeDir, '.kb-data', INDEX_REL)
}

let _cache: KbIndexRecord[] | null = null
let _cacheMtime = 0

function loadIndexFromDisk(): KbIndexRecord[] {
  const path = getIndexPath()
  if (!existsSync(path)) return []
  try {
    const stat = statSync(path)
    if (_cache && stat.mtimeMs === _cacheMtime) return _cache
    const raw = readFileSync(path, 'utf-8')
    const data = JSON.parse(raw) as { records?: KbIndexRecord[] }
    _cache = data.records || []
    _cacheMtime = stat.mtimeMs
    return _cache
  } catch {
    return []
  }
}

function saveIndex(records: KbIndexRecord[]): void {
  const dir = join(tahpPaths.knowledgeDir, '.kb-data')
  mkdirSync(dir, { recursive: true })
  writeFileSync(getIndexPath(), JSON.stringify({ version: 1, records }, null, 2), 'utf-8')
  _cache = records
  _cacheMtime = Date.now()
}

export function invalidateKbSearchIndex(): void {
  _cache = null
  _cacheMtime = 0
}

export function entryToIndexRecord(entry: KbEntryLike): KbIndexRecord {
  const blob = buildSearchBlob(entry)
  const tags = buildTags(entry)
  return {
    id: entry.id,
    source_type: inferSourceType(entry) as KbSourceType,
    module: entry.module || 'shared',
    func_type: entry.func_type || 'other',
    category: entry.category || '其他',
    status: entry.status || 'pending_review',
    jira_key: inferJiraKey(entry),
    source_document_id: entry.source_document_id,
    tags,
    keywords: entry.keywords || [],
    tokens: tokenize(blob + ' ' + tags.join(' ')),
    blob_len: blob.length,
    updated_at: entry.updated_at || entry.created_at || new Date().toISOString(),
  }
}

export function upsertIndexRecord(entry: KbEntryLike): void {
  if (entry.status === 'deleted' || entry.status === 'rejected') {
    removeIndexRecord(entry.id)
    return
  }
  const records = loadIndexFromDisk()
  const rec = entryToIndexRecord(entry)
  const idx = records.findIndex(r => r.id === entry.id)
  if (idx >= 0) records[idx] = rec
  else records.push(rec)
  saveIndex(records)
}

export function removeIndexRecord(entryId: string): void {
  const records = loadIndexFromDisk().filter(r => r.id !== entryId)
  saveIndex(records)
}

export function facetFilter(
  records: KbIndexRecord[],
  opts: Pick<KbSearchQuery, 'module' | 'func_type' | 'source_types' | 'source_document_ids' | 'include_archived'>,
): KbIndexRecord[] {
  return records.filter(r => {
    if (r.status === 'rejected' || r.status === 'deleted') return false
    if (!opts.include_archived && r.status === 'archived') return false
    if (opts.module && r.module !== opts.module) return false
    if (opts.func_type && r.func_type !== opts.func_type) return false
    if (opts.source_types?.length && !opts.source_types.includes(r.source_type)) return false
    if (opts.source_document_ids?.length) {
      if (!r.source_document_id || !opts.source_document_ids.includes(r.source_document_id)) return false
    }
    return true
  })
}

export function getIndexRecords(): KbIndexRecord[] {
  return loadIndexFromDisk()
}

export function findByJiraKey(jiraKey: string): KbIndexRecord | undefined {
  const key = jiraKey.toUpperCase()
  return loadIndexFromDisk().find(r => r.jira_key?.toUpperCase() === key)
}

export function findByEntryId(entryId: string): KbIndexRecord | undefined {
  return loadIndexFromDisk().find(r => r.id.toLowerCase() === entryId.toLowerCase())
}

export function tagOverlapScore(record: KbIndexRecord, queryTokens: string[]): number {
  if (queryTokens.length === 0) return 0
  const hay = [...record.tags, ...record.keywords, ...record.tokens].map(s => s.toLowerCase())
  let hits = 0
  for (const qt of queryTokens) {
    if (hay.some(h => h.includes(qt) || qt.includes(h))) hits++
  }
  return hits / queryTokens.length
}

export { parseKbQuery }
