import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { searchJQLAll, jqlTotalCap, type JiraConfig } from '../../packages/server/src/services/tahp/jira'

const CFG: JiraConfig = { baseUrl: 'http://jira.test', username: 'u', password: 'p' }

interface PageRequest {
  startAt: number
  maxResults: number
}

/**
 * 假 Jira /search：按 startAt 切片返回，并记录每次请求的分页参数，
 * 用于断言真的翻页了（而不是一枪打完靠 maxResults 撑）。
 */
function stubJiraSearch(totalIssues: number, opts: { failAtStartAt?: number } = {}) {
  const requests: PageRequest[] = []
  const fetchMock = vi.fn(async (_url: string, init: any) => {
    const body = JSON.parse(String(init.body)) as PageRequest & { jql: string }
    requests.push({ startAt: body.startAt, maxResults: body.maxResults })

    if (opts.failAtStartAt !== undefined && body.startAt === opts.failAtStartAt) {
      return { ok: false, status: 500, statusText: 'boom', text: async () => 'boom' } as any
    }

    const slice: unknown[] = []
    for (let i = body.startAt; i < Math.min(body.startAt + body.maxResults, totalIssues); i += 1) {
      slice.push({ key: `FOO-${i + 1}`, fields: { summary: `issue ${i + 1}` } })
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ total: totalIssues, issues: slice }),
    } as any
  })
  vi.stubGlobal('fetch', fetchMock)
  return { requests }
}

describe('searchJQLAll', () => {
  beforeEach(() => {
    delete process.env.TAHP_JQL_MAX_ISSUES
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete process.env.TAHP_JQL_MAX_ISSUES
  })

  it('rejects an empty jql without hitting the network', async () => {
    const { requests } = stubJiraSearch(10)
    const r = await searchJQLAll('   ', CFG)
    expect(r.ok).toBe(false)
    expect(requests).toHaveLength(0)
  })

  it('returns every issue for a single-page result', async () => {
    stubJiraSearch(12)
    const r = await searchJQLAll('project = FOO', CFG)
    expect(r.ok).toBe(true)
    expect(r.data?.issues).toHaveLength(12)
    expect(r.data?.total).toBe(12)
    expect(r.data?.truncated).toBe(false)
  })

  it('pages past the 50-per-request limit to collect the full list', async () => {
    const { requests } = stubJiraSearch(120)
    const r = await searchJQLAll('project = FOO', CFG)
    expect(r.ok).toBe(true)
    expect(r.data?.issues).toHaveLength(120)
    expect(r.data?.truncated).toBe(false)
    expect(requests.map(q => q.startAt)).toEqual([0, 50, 100])
    expect(new Set(requests.map(q => q.maxResults))).toEqual(new Set([50]))
  })

  it('keeps keys unique and in Jira order', async () => {
    stubJiraSearch(60)
    const r = await searchJQLAll('project = FOO', CFG)
    const keys = r.data!.issues.map(i => i.key)
    expect(new Set(keys).size).toBe(keys.length)
    expect(keys[0]).toBe('FOO-1')
    expect(keys.at(-1)).toBe('FOO-60')
  })

  it('stops at the configured cap and flags truncation', async () => {
    process.env.TAHP_JQL_MAX_ISSUES = '30'
    stubJiraSearch(500)
    const r = await searchJQLAll('project = FOO', CFG)
    expect(r.data?.issues).toHaveLength(30)
    expect(r.data?.total).toBe(500)
    expect(r.data?.truncated).toBe(true)
  })

  it('honours an explicit cap argument over the env default', async () => {
    process.env.TAHP_JQL_MAX_ISSUES = '500'
    stubJiraSearch(300)
    const r = await searchJQLAll('project = FOO', CFG, 10)
    expect(r.data?.issues).toHaveLength(10)
    expect(r.data?.truncated).toBe(true)
  })

  it('defaults the cap to 500 and falls back on a bad env value', () => {
    expect(jqlTotalCap()).toBe(500)
    process.env.TAHP_JQL_MAX_ISSUES = 'not-a-number'
    expect(jqlTotalCap()).toBe(500)
    process.env.TAHP_JQL_MAX_ISSUES = '-5'
    expect(jqlTotalCap()).toBe(500)
    process.env.TAHP_JQL_MAX_ISSUES = '80'
    expect(jqlTotalCap()).toBe(80)
  })

  it('fails the whole query when the first page fails', async () => {
    stubJiraSearch(200, { failAtStartAt: 0 })
    const r = await searchJQLAll('project = FOO', CFG)
    expect(r.ok).toBe(false)
    expect(r.error).toContain('500')
  })

  it('keeps the pages it already has when a later page fails', async () => {
    stubJiraSearch(200, { failAtStartAt: 100 })
    const r = await searchJQLAll('project = FOO', CFG)
    expect(r.ok).toBe(true)
    expect(r.data?.issues).toHaveLength(100)
    // 命中数 200 > 已取 100 → 必须告诉调用方清单不完整
    expect(r.data?.truncated).toBe(true)
  })

  it('handles a jql matching nothing', async () => {
    stubJiraSearch(0)
    const r = await searchJQLAll('project = NOPE', CFG)
    expect(r.ok).toBe(true)
    expect(r.data?.issues).toHaveLength(0)
    expect(r.data?.truncated).toBe(false)
  })
})
