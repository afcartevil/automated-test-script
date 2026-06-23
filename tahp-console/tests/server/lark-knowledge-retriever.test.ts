import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('child_process', () => ({
  execFile: vi.fn((_cmd, _args, _opts, cb) => {
    if (typeof _opts === 'function') {
      cb = _opts
    }
    cb?.(null, JSON.stringify({ data: { items: [{ title: 'VoWiFi SOP', url: 'https://example.com/doc' }] } }), '')
  }),
}))

describe('lark-knowledge-retriever', () => {
  beforeEach(() => {
    vi.resetModules()
    process.env.TAHP_LARK_SEARCH_ENABLED = '1'
  })

  it('returns empty when disabled', async () => {
    process.env.TAHP_LARK_SEARCH_ENABLED = '0'
    const { searchLarkKnowledge } = await import('../../packages/server/src/services/tahp/lark-knowledge-retriever')
    const hits = await searchLarkKnowledge('test')
    expect(hits).toEqual([])
  })
})
