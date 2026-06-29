import { describe, expect, it, vi, afterEach } from 'vitest'
import { verifyJiraConnectivity } from '../../packages/server/src/services/tahp/jira'

describe('verifyJiraConnectivity', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('rejects empty credentials', async () => {
    const r = await verifyJiraConnectivity({
      baseUrl: 'http://jira.transsion.com',
      username: '',
      password: '',
    })
    expect(r.ok).toBe(false)
    expect(r.error).toMatch(/用户名和密码/)
  })

  it('returns user info when myself succeeds', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ name: 'qing.li3', displayName: 'Qing Li' }),
    } as Response)

    const r = await verifyJiraConnectivity({
      baseUrl: 'http://jira.transsion.com',
      username: 'qing.li3',
      password: 'secret',
    })
    expect(r.ok).toBe(true)
    expect(r.data?.displayName).toBe('Qing Li')
  })

  it('maps 401 to readable auth error', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => 'Login failed',
    } as Response)

    const r = await verifyJiraConnectivity({
      baseUrl: 'http://jira.transsion.com',
      username: 'bad',
      password: 'bad',
    })
    expect(r.ok).toBe(false)
    expect(r.error).toMatch(/401/)
    expect(r.error).toMatch(/用户名或密码/)
  })
})
