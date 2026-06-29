import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  shouldVerifyProviderConnectivity,
  verifyProviderConnectivity,
} from '../../packages/server/src/services/provider-connectivity'

describe('shouldVerifyProviderConnectivity', () => {
  it('probes custom openai-compatible providers', () => {
    expect(shouldVerifyProviderConnectivity('custom:proxy', 'https://proxy.example/v1')).toBe(true)
  })

  it('skips oauth providers', () => {
    expect(shouldVerifyProviderConnectivity('copilot', 'https://api.githubcopilot.com')).toBe(false)
  })

  it('skips anthropic-native endpoints', () => {
    expect(shouldVerifyProviderConnectivity('anthropic', 'https://api.anthropic.com')).toBe(false)
  })
})

describe('verifyProviderConnectivity', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('throws when provider returns non-ok status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => 'invalid key',
    } as Response)

    await expect(
      verifyProviderConnectivity('https://api.example.com/v1', 'bad-key'),
    ).rejects.toThrow(/探活失败/)
  })

  it('passes when provider returns models', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: [{ id: 'gpt-4o' }] }),
    } as Response)

    await expect(
      verifyProviderConnectivity('https://api.example.com/v1', 'sk-test'),
    ).resolves.toBeUndefined()
  })
})
