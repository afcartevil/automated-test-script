import { describe, expect, it } from 'vitest'
import { routeIntent } from '../../packages/server/src/services/tahp/chat-retrieval/intent-router'
import { searchKb } from '../../packages/server/src/services/tahp/kb-search/search'
import { runRetrieval } from '../../packages/server/src/services/tahp/chat-retrieval/orchestrator'

const QUERY = '插入充电器充电，小板NTC加热至70°C触发端口防烧，但通知栏不显示通知'

describe('port burn deposited case retrieval', () => {
  it('searchKb finds kb-a05dfb15 or related distill entry', async () => {
    const hits = await searchKb({ query: QUERY, include_archived: true, limit: 5, min_score: 5 })
    const ids = hits.map(h => h.id)
    expect(ids.some(id => id === 'kb-a05dfb15' || id === 'kb-1d89adb1')).toBe(true)
  })

  it('runRetrieval returns kb hits for auto mode', async () => {
    const { bundle, routed } = await runRetrieval(QUERY, {})
    expect(bundle.kb_hits.length).toBeGreaterThan(0)
    expect(routed.intent).toBe('historical_case')
  })
})
