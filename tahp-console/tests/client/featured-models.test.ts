import { describe, expect, it } from 'vitest'
import type { AvailableModelGroup } from '@/api/hermes/system'
import {
  DASHBOARD_MODEL_LIMIT,
  compareVersionParts,
  detectVendorFamily,
  extractVersionParts,
  modelTierRank,
  pickBestModelForFamily,
  selectFeaturedModels,
} from '@/utils/featured-models'

const identityDisplay = (modelId: string) => modelId

function makeGroup(
  provider: string,
  label: string,
  models: string[],
): AvailableModelGroup {
  return {
    provider,
    label,
    base_url: `https://${provider}.example/v1`,
    models,
    api_key: 'sk-test',
  }
}

describe('featured-models', () => {
  it('detects vendor families from model ids and provider hints', () => {
    expect(detectVendorFamily('deepseek-v4-pro', 'custom:proxy')).toBe('deepseek')
    expect(detectVendorFamily('MiniMax-M2.7', 'minimax')).toBe('minimax')
    expect(detectVendorFamily('glm-5.1', 'zai')).toBe('glm')
    expect(detectVendorFamily('moonshotai/kimi-k2.6', 'openrouter')).toBe('kimi')
    expect(detectVendorFamily('qwen3.6-plus', 'alibaba')).toBe('qwen')
    expect(detectVendorFamily('openai/gpt-5.4', 'ai-gateway')).toBe('gpt')
    expect(detectVendorFamily('google/gemini-3.1-pro-preview', 'nous')).toBe('gemini')
    expect(detectVendorFamily('Doubao-Seed-2.1-pro', 'custom:transsion')).toBeNull()
  })

  it('extracts semantic versions so M3 outranks M2.5', () => {
    expect(extractVersionParts('MiniMax-M2.5')).toEqual([2, 5])
    expect(extractVersionParts('MiniMax/MiniMax-M3')).toEqual([3])
    expect(extractVersionParts('MiniMax-M2.7')).toEqual([2, 7])
    expect(extractVersionParts('deepseek-v4-pro')).toEqual([4])
    expect(extractVersionParts('kimi-k2.6')).toEqual([2, 6])
    expect(extractVersionParts('kimi-k2-0905-preview')).toEqual([2])
    expect(compareVersionParts([3], [2, 5])).toBeGreaterThan(0)
    expect(compareVersionParts([2, 7], [2, 5])).toBeGreaterThan(0)
  })

  it('does not treat MiniMax as a lite mini variant', () => {
    expect(modelTierRank('MiniMax-M2.5')).toBe(2)
    expect(modelTierRank('MiniMax/MiniMax-M3')).toBe(2)
    expect(modelTierRank('Doubao-Seed-2.0-mini')).toBe(0)
    expect(modelTierRank('deepseek-v4-flash')).toBe(0)
    expect(modelTierRank('deepseek-v4-pro')).toBe(5)
  })

  it('prefers MiniMax-M3 over older MiniMax-M2.x models', () => {
    const best = pickBestModelForFamily([
      { model: 'MiniMax-M2.5', provider: 'custom:transsion', label: 'sw', order: 0 },
      { model: 'MiniMax/MiniMax-M3', provider: 'custom:transsion', label: 'sw', order: 1 },
      { model: 'MiniMax-M2.7', provider: 'custom:transsion', label: 'sw', order: 2 },
    ])

    expect(best?.model).toBe('MiniMax/MiniMax-M3')
  })

  it('prefers flagship models over lite variants within the same family', () => {
    const best = pickBestModelForFamily([
      { model: 'deepseek-v4-flash', provider: 'deepseek', label: 'DeepSeek', order: 0 },
      { model: 'deepseek-v4-pro', provider: 'deepseek', label: 'DeepSeek', order: 1 },
      { model: 'deepseek-chat', provider: 'deepseek', label: 'DeepSeek', order: 2 },
    ])

    expect(best?.model).toBe('deepseek-v4-pro')
  })

  it('keeps original order when versions and tiers cannot be distinguished', () => {
    const best = pickBestModelForFamily([
      { model: 'custom-alpha', provider: 'custom:x', label: 'X', order: 0 },
      { model: 'custom-beta', provider: 'custom:x', label: 'X', order: 1 },
    ])

    expect(best?.model).toBe('custom-alpha')
  })

  it('selects one flagship model per vendor in priority order', () => {
    const groups: AvailableModelGroup[] = [
      makeGroup('custom:transsion', 'sw-aimodel.transsion-os.com', [
        'Doubao-Seed-2.0-lite',
        'Doubao-Seed-2.0-mini',
        'Doubao-Seed-2.1-pro',
        'deepseek-v4-pro',
        'MiniMax-M2.5',
        'MiniMax/MiniMax-M3',
        'glm-5.1',
        'kimi-k2.6',
        'qwen3.6-plus',
        'gpt-5.4',
        'gemini-3.1-pro-preview',
      ]),
    ]

    const featured = selectFeaturedModels({
      groups,
      selectedModel: '',
      selectedProvider: '',
      displayModelName: identityDisplay,
    })

    expect(featured).toHaveLength(DASHBOARD_MODEL_LIMIT)
    expect(featured.map(item => item.model)).toEqual([
      'deepseek-v4-pro',
      'MiniMax/MiniMax-M3',
      'glm-5.1',
      'kimi-k2.6',
    ])
  })

  it('pins the user-selected model first and deduplicates its vendor family', () => {
    const groups: AvailableModelGroup[] = [
      makeGroup('custom:transsion', 'sw-aimodel.transsion-os.com', [
        'deepseek-v4-pro',
        'MiniMax/MiniMax-M3',
        'glm-5.1',
        'kimi-k2.6',
        'qwen3.6-plus',
        'gpt-5.4',
        'gemini-3.1-pro-preview',
      ]),
    ]

    const featured = selectFeaturedModels({
      groups,
      selectedModel: 'qwen3.6-plus',
      selectedProvider: 'custom:transsion',
      displayModelName: identityDisplay,
    })

    expect(featured[0]).toMatchObject({
      model: 'qwen3.6-plus',
      provider: 'custom:transsion',
    })
    expect(featured.map(item => item.model)).toEqual([
      'qwen3.6-plus',
      'deepseek-v4-pro',
      'MiniMax/MiniMax-M3',
      'glm-5.1',
    ])
  })

  it('pins non-allowlisted selected models first and fills the remaining slots', () => {
    const groups: AvailableModelGroup[] = [
      makeGroup('custom:transsion', 'sw-aimodel.transsion-os.com', [
        'Doubao-Seed-2.1-pro',
        'deepseek-v4-pro',
        'MiniMax/MiniMax-M3',
        'glm-5.1',
        'kimi-k2.6',
      ]),
    ]

    const featured = selectFeaturedModels({
      groups,
      selectedModel: 'Doubao-Seed-2.1-pro',
      selectedProvider: 'custom:transsion',
      displayModelName: identityDisplay,
    })

    expect(featured[0]?.model).toBe('Doubao-Seed-2.1-pro')
    expect(featured.map(item => item.model)).toEqual([
      'Doubao-Seed-2.1-pro',
      'deepseek-v4-pro',
      'MiniMax/MiniMax-M3',
      'glm-5.1',
    ])
  })

  it('shows pinned selection even when it is not in the visible model list', () => {
    const groups: AvailableModelGroup[] = [
      makeGroup('deepseek', 'DeepSeek', ['deepseek-v4-pro']),
      makeGroup('minimax', 'MiniMax', ['MiniMax/MiniMax-M3']),
    ]

    const featured = selectFeaturedModels({
      groups,
      selectedModel: 'custom-hidden-model',
      selectedProvider: 'custom:corp',
      displayModelName: identityDisplay,
    })

    expect(featured[0]).toMatchObject({
      model: 'custom-hidden-model',
      provider: 'custom:corp',
      vendor: 'custom:corp',
    })
  })

  it('returns fewer than four items when not enough candidates exist', () => {
    const groups: AvailableModelGroup[] = [
      makeGroup('deepseek', 'DeepSeek', ['deepseek-v4-pro']),
      makeGroup('minimax', 'MiniMax', ['MiniMax/MiniMax-M3']),
    ]

    const featured = selectFeaturedModels({
      groups,
      selectedModel: '',
      selectedProvider: '',
      displayModelName: identityDisplay,
    })

    expect(featured).toHaveLength(2)
    expect(featured.map(item => item.model)).toEqual(['deepseek-v4-pro', 'MiniMax/MiniMax-M3'])
  })

  it('keeps provider-specific matches when the same model id appears in multiple providers', () => {
    const groups: AvailableModelGroup[] = [
      makeGroup('provider-a', 'Provider A', ['shared-model']),
      makeGroup('provider-b', 'Provider B', ['shared-model']),
    ]

    const featured = selectFeaturedModels({
      groups,
      selectedModel: 'shared-model',
      selectedProvider: 'provider-b',
      displayModelName: identityDisplay,
    })

    expect(featured[0]).toMatchObject({
      model: 'shared-model',
      provider: 'provider-b',
      vendor: 'Provider B',
    })
  })
})
