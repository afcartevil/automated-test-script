import { describe, expect, it } from 'vitest'
import {
  extractCatalogFocus,
  isCatalogQuery,
  resolveDomainKeywords,
} from '../../packages/server/src/services/tahp/chat-retrieval/catalog-query'
import { runRetrieval } from '../../packages/server/src/services/tahp/chat-retrieval/orchestrator'
import { searchKbCatalog } from '../../packages/server/src/services/tahp/kb-search/search'
import { formatRetrievalPrompt } from '../../packages/server/src/services/tahp/chat-retrieval/prompt-formatter'

const QUERY = '通话相关的案例有哪些'

describe('telephony catalog retrieval', () => {
  it('detects catalog query', () => {
    expect(isCatalogQuery(QUERY)).toBe(true)
    expect(extractCatalogFocus(QUERY)).toContain('通话')
  })

  it('resolves telephony domain keywords from 通话', () => {
    const kws = resolveDomainKeywords('通话', 'telephony')
    expect(kws).toContain('通话')
    expect(kws.some(k => /vowifi|telephony|通信/i.test(k))).toBe(true)
  })

  it('searchKbCatalog returns telephony-related bug_distill entries', async () => {
    const focus = extractCatalogFocus(QUERY)
    const domainKeywords = resolveDomainKeywords(focus, 'telephony')
    const hits = await searchKbCatalog({
      query: focus,
      domain_keywords: domainKeywords,
      source_types: ['bug_distill'],
      include_archived: true,
      limit: 15,
      min_score: 5,
    })
    expect(hits.length).toBeGreaterThan(0)
    const jiraKeys = hits.map(h => h.jira_key).filter(Boolean)
    expect(jiraKeys.some(k => k === 'TOS163-37004')).toBe(true)
  })

  it('runRetrieval historical mode uses catalog and no skills', async () => {
    const { bundle, routed } = await runRetrieval(QUERY, { retrieval_mode: 'historical' })
    expect(routed.intent).toBe('historical_case')
    expect(bundle.catalog_mode).toBe(true)
    expect(bundle.skill_hits).toHaveLength(0)
    expect(bundle.kb_hits.length).toBeGreaterThan(0)
    const prompt = formatRetrievalPrompt(bundle)
    expect(prompt).toContain('禁止')
    expect(prompt).toContain('Skill')
    expect(prompt).not.toContain('## 相关 Skill')
  })
})
