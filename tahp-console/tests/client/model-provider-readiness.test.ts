import { describe, expect, it } from 'vitest'
import type { AvailableModelGroup } from '@/api/hermes/system'
import { isModelProviderConfigured } from '@/utils/model-provider-readiness'

function group(partial: Partial<AvailableModelGroup> & Pick<AvailableModelGroup, 'provider' | 'models'>): AvailableModelGroup {
  return {
    label: partial.provider,
    base_url: '',
    api_key: '',
    ...partial,
  }
}

describe('isModelProviderConfigured', () => {
  it('returns false for empty provider list', () => {
    expect(isModelProviderConfigured([])).toBe(false)
  })

  it('returns false for config-only fallback groups without credentials', () => {
    expect(isModelProviderConfigured([
      group({ provider: 'anthropic', models: ['claude-sonnet-4-20250514'] }),
    ])).toBe(false)
  })

  it('returns true when api_key is configured', () => {
    expect(isModelProviderConfigured([
      group({ provider: 'deepseek', models: ['deepseek-chat'], api_key: 'sk-test', base_url: 'https://api.deepseek.com/v1' }),
    ])).toBe(true)
  })

  it('returns true for builtin oauth providers', () => {
    expect(isModelProviderConfigured([
      group({ provider: 'copilot', models: ['gpt-4.1'], builtin: true, base_url: 'https://api.githubcopilot.com' }),
    ])).toBe(true)
  })

  it('returns true for custom providers with base_url', () => {
    expect(isModelProviderConfigured([
      group({ provider: 'custom:my-proxy', models: ['gpt-4o'], base_url: 'https://proxy.example/v1' }),
    ])).toBe(true)
  })
})
