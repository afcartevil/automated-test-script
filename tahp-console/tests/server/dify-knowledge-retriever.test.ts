import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

describe('dify-knowledge-retriever', () => {
  let tmpHome: string
  let prevHome: string | undefined
  let prevKey: string | undefined
  let prevEnabled: string | undefined

  beforeEach(() => {
    vi.resetModules()
    tmpHome = mkdtempSync(join(tmpdir(), 'tahp-dify-'))
    prevHome = process.env.TAHP_CONSOLE_HOME
    prevKey = process.env.TAHP_DIFY_API_KEY
    prevEnabled = process.env.TAHP_DIFY_SEARCH_ENABLED
    process.env.TAHP_CONSOLE_HOME = tmpHome
    delete process.env.TAHP_DIFY_API_KEY
    delete process.env.TAHP_DIFY_SEARCH_ENABLED
  })

  afterEach(() => {
    if (prevHome === undefined) delete process.env.TAHP_CONSOLE_HOME
    else process.env.TAHP_CONSOLE_HOME = prevHome
    if (prevKey === undefined) delete process.env.TAHP_DIFY_API_KEY
    else process.env.TAHP_DIFY_API_KEY = prevKey
    if (prevEnabled === undefined) delete process.env.TAHP_DIFY_SEARCH_ENABLED
    else process.env.TAHP_DIFY_SEARCH_ENABLED = prevEnabled
    try { rmSync(tmpHome, { recursive: true, force: true }) } catch { /* ignore */ }
  })

  it('difyEnabled is false when explicitly disabled', async () => {
    process.env.TAHP_DIFY_SEARCH_ENABLED = '0'
    const { difyEnabled } = await import('../../packages/server/src/services/tahp/dify-knowledge-retriever')
    expect(difyEnabled()).toBe(false)
  })

  it('resolveDifyApiKey bootstraps when store empty', async () => {
    const { resolveDifyApiKey, difyEnabled } = await import(
      '../../packages/server/src/services/tahp/dify-knowledge-retriever'
    )
    const key = resolveDifyApiKey()
    expect(key.startsWith('app-')).toBe(true)
    expect(difyEnabled()).toBe(true)
  })

  it('resolveKbTag prefers user choice then module hint', async () => {
    const { resolveKbTag } = await import('../../packages/server/src/services/tahp/dify-knowledge-retriever')
    expect(resolveKbTag('蜂窝通信')).toBe('蜂窝通信')
    expect(resolveKbTag(undefined, 'telephony')).toBe('蜂窝通信')
    expect(resolveKbTag(undefined, 'unknown')).toBe('全局搜索')
  })

  it('parseDifySseLines extracts JSON events', async () => {
    const { parseDifySseLines } = await import('../../packages/server/src/services/tahp/dify-knowledge-retriever')
    const sample = [
      'data: {"event":"agent_message","answer":"你"}',
      '',
      'data: {"event":"message_end","metadata":{"retriever_resources":[{"document_name":"doc.pdf","dataset_name":"底软通信领域公共知识库","content":"hello","score":0.9}]}}',
      '',
    ].join('\n')
    const { events, rest } = parseDifySseLines(sample)
    expect(events).toHaveLength(2)
    expect(events[0].answer).toBe('你')
    expect(rest).toBe('')
  })

  it('mapResourcesToHits maps retriever_resources', async () => {
    const { mapResourcesToHits } = await import('../../packages/server/src/services/tahp/dify-knowledge-retriever')
    const hits = mapResourcesToHits([
      {
        document_name: '测试文档.pdf',
        dataset_name: '底软通信领域公共知识库',
        content: '片段内容',
        score: 0.88,
      },
    ], '全局搜索')
    expect(hits).toHaveLength(1)
    expect(hits[0].title).toBe('测试文档.pdf')
    expect(hits[0].score).toBe(88)
    expect(hits[0].kb_tag).toBe('全局搜索')
  })

  it('searchDifyKnowledge returns empty when disabled', async () => {
    process.env.TAHP_DIFY_SEARCH_ENABLED = '0'
    const { searchDifyKnowledge } = await import(
      '../../packages/server/src/services/tahp/dify-knowledge-retriever'
    )
    expect(await searchDifyKnowledge('test')).toEqual([])
  })
})
