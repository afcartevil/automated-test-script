import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../hermes/hermes-cli', () => ({
  getVersion: vi.fn().mockResolvedValue('Hermes Agent 1.8.2\n'),
}))

vi.mock('../hermes/agent-bridge', () => ({
  getAgentBridgeManager: vi.fn(() => ({ running: true })),
}))

vi.mock('fs', async () => {
  const actual = await vi.importActual<typeof import('fs')>('fs')
  return {
    ...actual,
    existsSync: vi.fn((p: string) => {
      if (String(p).includes('skills')) return true
      if (String(p).includes('knowledge-base')) return true
      if (String(p).includes('hermes-agent-main')) return true
      return actual.existsSync(p)
    }),
    readdirSync: vi.fn((p: string) => {
      if (String(p).includes('skills')) return [{ isDirectory: () => true, name: 'tp-adapt-bringup' }]
      if (String(p).includes('entries')) return ['kb-1.json']
      return actual.readdirSync(p)
    }),
  }
})

vi.mock('child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('child_process')>()
  return {
    ...actual,
    spawnSync: vi.fn(() => ({ status: 0, stdout: 'Python 3.11.0', stderr: '' })),
  }
})

import { runSelfCheck } from '../../packages/server/src/services/tahp/self-check'

describe('runSelfCheck', () => {
  beforeEach(() => {
    vi.stubEnv('ANTHROPIC_API_KEY', 'test-key')
  })

  it('returns structured self-check result', async () => {
    const result = await runSelfCheck()
    expect(result.score).toBeGreaterThan(0)
    expect(result.categories.length).toBeGreaterThanOrEqual(4)
    expect(result.total).toBe(result.pass + result.warn + result.fail)
    expect(result.history.length).toBeGreaterThan(0)
    for (const cat of result.categories) {
      expect(cat.title).toBeTruthy()
      expect(cat.items.length).toBeGreaterThan(0)
      for (const item of cat.items) {
        expect(['ok', 'warn', 'err']).toContain(item.state)
      }
    }
  })
})
