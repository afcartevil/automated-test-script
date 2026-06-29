import { describe, expect, it, vi } from 'vitest'
import {
  probeProviderConnectivity,
  shouldProbeProviderConnectivity,
} from '@/utils/provider-connectivity'
import { fetchProviderModels } from '@/api/hermes/system'

vi.mock('@/api/hermes/system', () => ({
  fetchProviderModels: vi.fn(),
}))

describe('shouldProbeProviderConnectivity', () => {
  it('always probes custom openai-compatible providers', () => {
    expect(shouldProbeProviderConnectivity('custom', null, 'https://proxy.example/v1')).toBe(true)
  })

  it('skips oauth presets', () => {
    expect(shouldProbeProviderConnectivity('preset', 'copilot', 'https://api.githubcopilot.com')).toBe(false)
  })

  it('skips anthropic-native endpoints', () => {
    expect(shouldProbeProviderConnectivity('preset', 'anthropic', 'https://api.anthropic.com')).toBe(false)
  })

  it('probes openai-compatible presets', () => {
    expect(shouldProbeProviderConnectivity('preset', 'deepseek', 'https://api.deepseek.com')).toBe(true)
  })
})

describe('probeProviderConnectivity', () => {
  it('throws when provider returns empty model list', async () => {
    vi.mocked(fetchProviderModels).mockResolvedValueOnce({ models: [] })
    await expect(
      probeProviderConnectivity('https://api.example.com/v1', 'sk-test'),
    ).rejects.toThrow(/未返回可用模型/)
  })

  it('returns model count when provider responds', async () => {
    vi.mocked(fetchProviderModels).mockResolvedValueOnce({ models: ['gpt-4o'] })
    await expect(
      probeProviderConnectivity('https://api.example.com/v1', 'sk-test'),
    ).resolves.toEqual({ modelCount: 1, models: ['gpt-4o'] })
  })
})
