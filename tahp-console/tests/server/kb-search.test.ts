import { describe, expect, it, beforeEach } from 'vitest'
import { parseJiraKey, parseKbQuery, tokenizeQuery } from '../../packages/server/src/services/tahp/kb-search/query-parser'
import { buildSearchBlob, buildTags, inferSourceType } from '../../packages/server/src/services/tahp/kb-search/blob'
import { calculateRelevance, tokenize } from '../../packages/server/src/services/tahp/kb-search/bm25'
import {
  entryToIndexRecord,
  facetFilter,
  invalidateKbSearchIndex,
} from '../../packages/server/src/services/tahp/kb-search/index-store'
import { searchKb } from '../../packages/server/src/services/tahp/kb-search/search'
import type { KbEntryLike, KbIndexRecord } from '../../packages/server/src/services/tahp/kb-search/types'

describe('kb-search query-parser', () => {
  it('parseJiraKey extracts TOS163-37004', () => {
    expect(parseJiraKey('查一下 TOS163-37004 历史')).toBe('TOS163-37004')
  })

  it('parseKbQuery extracts entry id and module hint', () => {
    const p = parseKbQuery('VozWiFi Movistar 通话问题')
    expect(p.module_hint).toBe('telephony')
    expect(tokenizeQuery('VozWiFi')).toContain('vozwifi')
  })
})

describe('kb-search blob', () => {
  const sample: KbEntryLike = {
    id: 'kb-test0001',
    content: '## 1. 摘要 / TL;DR\n\nVozWiFi Movistar 通话界面不显示。',
    category: '错误模式',
    module: 'telephony',
    func_type: 'bug_analysis',
    keywords: ['VozWiFi'],
    status: 'archived',
    source_task_id: 'task-1',
    tags: ['Movistar', 'VozWiFi'],
    jira_key: 'TOS163-37004',
  }

  it('buildSearchBlob includes tags and TL;DR', () => {
    const blob = buildSearchBlob(sample)
    expect(blob).toContain('VozWiFi')
    expect(blob).toContain('Movistar')
    expect(blob).toContain('TOS163-37004')
  })

  it('inferSourceType from source_task_id', () => {
    expect(inferSourceType(sample)).toBe('bug_distill')
  })

  it('buildTags merges keywords and jira', () => {
    const tags = buildTags(sample)
    expect(tags).toContain('TOS163-37004')
    expect(tags).toContain('VozWiFi')
  })
})

describe('kb-search bm25', () => {
  it('tokenize splits long Chinese into ngrams', () => {
    const t = tokenize('插入充电器充电小板NTC加热至70度触发端口防烧')
    expect(t).toContain('端口')
    expect(t).toContain('防烧')
    expect(t.some(x => x.includes('端口') && x.includes('防烧')) || t.includes('端口防烧')).toBe(true)
  })

  it('does not hard-filter shared module when query mentions 充电', async () => {
    const hits = await searchKb({
      query: '插入充电器充电，小板NTC加热至70°C触发端口防烧，但通知栏不显示通知',
      include_archived: true,
      limit: 5,
      min_score: 5,
    })
    expect(hits.length).toBeGreaterThan(0)
    expect(hits.some(h => h.module === 'shared')).toBe(true)
  })

  it('ranks matching entry higher', () => {
    const entry: KbEntryLike = {
      id: 'kb-a',
      content: 'VozWiFi Movistar Colombia',
      category: '错误模式',
      module: 'telephony',
      func_type: 'bug_analysis',
      keywords: ['VozWiFi'],
      status: 'approved',
      tags: ['VozWiFi'],
      search_blob: 'VozWiFi Movistar Colombia',
    }
    const score = calculateRelevance(entry, tokenize('vozwifi movistar'))
    expect(score).toBeGreaterThan(0)
  })
})

describe('kb-search facetFilter', () => {
  const records: KbIndexRecord[] = [
    {
      id: 'kb-1',
      source_type: 'bug_distill',
      module: 'telephony',
      func_type: 'bug_analysis',
      category: '错误模式',
      status: 'archived',
      tags: ['VozWiFi'],
      keywords: [],
      tokens: ['vozwifi'],
      blob_len: 100,
      updated_at: '2026-01-01',
    },
    {
      id: 'kb-2',
      source_type: 'doc_chunk',
      module: 'power-mgmt',
      func_type: 'other',
      category: '其他',
      status: 'approved',
      tags: [],
      keywords: [],
      tokens: ['hbm'],
      blob_len: 50,
      updated_at: '2026-01-01',
    },
  ]

  it('filters by module and source_type', () => {
    const out = facetFilter(records, {
      module: 'telephony',
      source_types: ['bug_distill'],
      include_archived: true,
    })
    expect(out).toHaveLength(1)
    expect(out[0].id).toBe('kb-1')
  })

  it('entryToIndexRecord sets jira_key', () => {
    const rec = entryToIndexRecord({
      id: 'kb-x',
      content: 'test',
      category: '错误模式',
      module: 'telephony',
      func_type: 'bug_analysis',
      status: 'pending_review',
      jira_key: 'TOS163-99',
      source_task_id: 't1',
    })
    expect(rec.jira_key).toBe('TOS163-99')
    expect(rec.source_type).toBe('bug_distill')
  })
})

beforeEach(() => {
  invalidateKbSearchIndex()
})
