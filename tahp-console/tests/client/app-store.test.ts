// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockSystemApi = vi.hoisted(() => ({
  checkHealth: vi.fn(),
  fetchAvailableModels: vi.fn(),
  updateDefaultModel: vi.fn(),
  updateModelAlias: vi.fn(),
  updateModelVisibility: vi.fn(),
  triggerUpdate: vi.fn(),
}))

vi.mock('@/api/hermes/system', () => mockSystemApi)
vi.mock('@/api/client', () => ({ hasApiKey: () => true }))

import { useAppStore } from '@/stores/hermes/app'

describe('App Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('persists desktop sidebar collapsed state to localStorage', () => {
    const store = useAppStore()

    expect(store.sidebarCollapsed).toBe(false)

    store.toggleSidebarCollapsed()
    expect(store.sidebarCollapsed).toBe(true)
    expect(window.localStorage.getItem('hermes_sidebar_collapsed')).toBe('1')

    store.toggleSidebarCollapsed()
    expect(store.sidebarCollapsed).toBe(false)
    expect(window.localStorage.getItem('hermes_sidebar_collapsed')).toBe('0')
  })

  it('loads model visibility and falls back when the configured default is hidden', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: 'deepseek-chat',
      default_provider: 'deepseek',
      groups: [
        {
          provider: 'deepseek',
          label: 'DeepSeek',
          base_url: 'https://api.deepseek.com/v1',
          api_key: 'sk-test',
          models: ['deepseek-reasoner'],
        },
      ],
      allProviders: [],
      model_visibility: {
        deepseek: { mode: 'include', models: ['deepseek-reasoner'] },
      },
    })
    const store = useAppStore()

    await store.loadModels()

    expect(store.modelVisibility).toEqual({
      deepseek: { mode: 'include', models: ['deepseek-reasoner'] },
    })
    expect(store.selectedModel).toBe('deepseek-reasoner')
    expect(store.selectedProvider).toBe('deepseek')
    expect(store.customModels).toEqual({})
    expect(store.isModelVisible('deepseek', 'deepseek-reasoner')).toBe(true)
    expect(store.isModelVisible('deepseek', 'deepseek-chat')).toBe(false)
  })

  it('loads aliases while falling back from a hidden default without rehydrating it as custom', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: 'deepseek-chat',
      default_provider: 'deepseek',
      groups: [
        {
          provider: 'deepseek',
          label: 'DeepSeek',
          base_url: 'https://api.deepseek.com/v1',
          api_key: 'sk-test',
          models: ['deepseek-reasoner'],
          available_models: ['deepseek-chat', 'deepseek-reasoner'],
        },
      ],
      allProviders: [
        {
          provider: 'deepseek',
          label: 'DeepSeek',
          base_url: 'https://api.deepseek.com/v1',
          api_key: 'sk-test',
          models: ['deepseek-chat', 'deepseek-reasoner'],
        },
      ],
      model_aliases: {
        deepseek: { 'deepseek-reasoner': 'Reasoner Alias' },
      },
      model_visibility: {
        deepseek: { mode: 'include', models: ['deepseek-reasoner'] },
      },
    })
    const store = useAppStore()

    await store.loadModels()

    expect(store.modelAliases).toEqual({
      deepseek: { 'deepseek-reasoner': 'Reasoner Alias' },
    })
    expect(store.modelVisibility).toEqual({
      deepseek: { mode: 'include', models: ['deepseek-reasoner'] },
    })
    expect(store.selectedModel).toBe('deepseek-reasoner')
    expect(store.selectedProvider).toBe('deepseek')
    expect(store.displayModelName('deepseek-reasoner', 'deepseek')).toBe('Reasoner Alias')
    expect(store.customModels).toEqual({})
  })

  it('persists model visibility without changing the canonical selected model id', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: 'deepseek-reasoner',
      default_provider: 'deepseek',
      groups: [
        {
          provider: 'deepseek',
          label: 'DeepSeek',
          base_url: 'https://api.deepseek.com/v1',
          api_key: 'sk-test',
          models: ['deepseek-reasoner'],
        },
      ],
      allProviders: [],
      model_visibility: {
        deepseek: { mode: 'include', models: ['deepseek-reasoner'] },
      },
    })
    mockSystemApi.updateModelVisibility.mockResolvedValue({
      success: true,
      model_visibility: {
        deepseek: { mode: 'include', models: ['deepseek-reasoner'] },
      },
    })
    const store = useAppStore()

    await store.setModelVisibility('deepseek', { mode: 'include', models: ['deepseek-reasoner'] })

    expect(mockSystemApi.updateModelVisibility).toHaveBeenCalledWith({
      provider: 'deepseek',
      mode: 'include',
      models: ['deepseek-reasoner'],
    })
    expect(store.selectedModel).toBe('deepseek-reasoner')
    expect(store.selectedProvider).toBe('deepseek')
    expect(mockSystemApi.updateDefaultModel).not.toHaveBeenCalled()
  })

  it('marks the client stale when the served Web UI version changes', async () => {
    mockSystemApi.checkHealth.mockResolvedValue({
      status: 'ok',
      webui_version: '0.5.17',
      webui_latest: '0.5.17',
      webui_update_available: false,
    })
    const store = useAppStore()

    await store.checkConnection()

    expect(store.connected).toBe(true)
    expect(store.serverVersion).toBe('0.5.17')
    expect(store.clientOutdated).toBe(true)
    expect(store.updateAvailable).toBe(false)
  })

  it('does not mark the client stale when the served Web UI version matches this bundle', async () => {
    mockSystemApi.checkHealth.mockResolvedValue({
      status: 'ok',
      webui_version: 'test',
      webui_latest: 'test',
      webui_update_available: false,
    })
    const store = useAppStore()

    await store.checkConnection()

    expect(store.serverVersion).toBe('test')
    expect(store.clientOutdated).toBe(false)
  })

  it('clears the updating state and reports failure when self-update request fails', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSystemApi.triggerUpdate.mockRejectedValue(new Error('install failed'))
    const store = useAppStore()

    const ok = await store.doUpdate()

    expect(ok).toBe(false)
    expect(store.updating).toBe(false)
    expect(consoleError).toHaveBeenCalledWith('Failed to update Hermes Web UI:', expect.any(Error))
    consoleError.mockRestore()
  })

  it('loads model aliases and resolves display names without changing canonical IDs', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: 'deepseek-v4-flash',
      default_provider: 'deepseek',
      groups: [{
        provider: 'deepseek',
        label: 'DeepSeek',
        base_url: 'https://api.deepseek.com/v1',
        models: ['deepseek-v4-flash'],
        api_key: '',
      }],
      allProviders: [],
      model_aliases: {
        deepseek: { 'deepseek-v4-flash': 'Flash Alias' },
      },
    })
    const store = useAppStore()

    await store.loadModels()

    expect(store.selectedModel).toBe('deepseek-v4-flash')
    expect(store.getModelAlias('deepseek-v4-flash', 'deepseek')).toBe('Flash Alias')
    expect(store.displayModelName('deepseek-v4-flash', 'deepseek')).toBe('Flash Alias')
    expect(store.displayModelName('unknown', 'deepseek')).toBe('unknown')
  })

  it('does not refetch available models within the cache window after an empty response', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: '',
      default_provider: '',
      groups: [],
      allProviders: [],
    })
    const store = useAppStore()

    await store.loadModels()
    await store.loadModels()

    expect(mockSystemApi.fetchAvailableModels).toHaveBeenCalledTimes(1)
  })

  it('waits only up to the run timeout for the first available models request', async () => {
    vi.useFakeTimers()
    mockSystemApi.fetchAvailableModels.mockReturnValue(new Promise(() => {}))
    const store = useAppStore()
    let resolved = false

    const waitPromise = store.waitForModelsForRun(15000).then(() => {
      resolved = true
    })

    expect(mockSystemApi.fetchAvailableModels).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(14999)
    expect(resolved).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    await waitPromise
    expect(resolved).toBe(true)
    expect(store.modelGroups).toEqual([])
  })

  it('keeps aliases scoped to their provider when model IDs overlap', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: 'shared-model',
      default_provider: 'provider-a',
      groups: [
        {
          provider: 'provider-a',
          label: 'Provider A',
          base_url: 'https://a.example/v1',
          models: ['shared-model'],
          api_key: '',
        },
        {
          provider: 'provider-b',
          label: 'Provider B',
          base_url: 'https://b.example/v1',
          models: ['shared-model'],
          api_key: '',
        },
      ],
      allProviders: [],
      model_aliases: {
        'provider-a': { 'shared-model': 'A Alias' },
      },
    })
    const store = useAppStore()

    await store.loadModels()

    expect(store.displayModelName('shared-model', 'provider-a')).toBe('A Alias')
    expect(store.displayModelName('shared-model', 'provider-b')).toBe('shared-model')
    expect(store.displayModelName('shared-model')).toBe('A Alias')
  })

  it('rehydrates an active unlisted default model as removable after loading models', async () => {
    mockSystemApi.fetchAvailableModels.mockResolvedValue({
      default: 'manually-supported-id',
      default_provider: 'deepseek',
      groups: [{
        provider: 'deepseek',
        label: 'DeepSeek',
        base_url: 'https://api.deepseek.com/v1',
        models: ['deepseek-v4-flash'],
        api_key: '',
      }],
      allProviders: [],
      model_aliases: {},
    })
    const store = useAppStore()

    await store.loadModels()

    expect(store.selectedModel).toBe('manually-supported-id')
    expect(store.customModels).toEqual({ deepseek: ['manually-supported-id'] })
  })

  it('saves and clears model aliases via the Web UI-only alias API', async () => {
    mockSystemApi.updateModelAlias.mockResolvedValue(undefined)
    const store = useAppStore()

    await store.setModelAlias('deepseek-v4-flash', 'deepseek', '  Flash Alias  ')

    expect(mockSystemApi.updateModelAlias).toHaveBeenCalledWith({
      provider: 'deepseek',
      model: 'deepseek-v4-flash',
      alias: 'Flash Alias',
    })
    expect(store.modelAliases).toEqual({ deepseek: { 'deepseek-v4-flash': 'Flash Alias' } })

    await store.setModelAlias('deepseek-v4-flash', 'deepseek', '')
    expect(store.modelAliases).toEqual({})
  })

  it('removes an unlisted custom model and falls back to a listed model when active', async () => {
    mockSystemApi.updateDefaultModel.mockResolvedValue(undefined)
    const store = useAppStore()
    store.modelGroups = [{
      provider: 'deepseek',
      label: 'DeepSeek',
      base_url: 'https://api.deepseek.com/v1',
      models: ['deepseek-v4-flash'],
      api_key: '',
    }]

    await store.switchModel('test', 'deepseek')
    expect(store.selectedModel).toBe('test')
    expect(store.customModels).toEqual({ deepseek: ['test'] })

    await store.removeCustomModel('test', 'deepseek')
    expect(store.customModels).toEqual({})
    expect(store.selectedModel).toBe('deepseek-v4-flash')
    expect(mockSystemApi.updateDefaultModel).toHaveBeenLastCalledWith({
      default: 'deepseek-v4-flash',
      provider: 'deepseek',
    })
  })

  it('serializes rapid model switches so later clicks wait for earlier writes', async () => {
    let resolveFirst!: () => void
    const firstPending = new Promise<void>(resolve => { resolveFirst = resolve })
    const callOrder: string[] = []

    mockSystemApi.updateDefaultModel
      .mockImplementationOnce(async (payload: { default: string; provider?: string }) => {
        callOrder.push(`start:${payload.default}`)
        await firstPending
        callOrder.push(`end:${payload.default}`)
      })
      .mockImplementationOnce(async (payload: { default: string; provider?: string }) => {
        callOrder.push(`start:${payload.default}`)
        callOrder.push(`end:${payload.default}`)
      })

    const store = useAppStore()
    store.modelGroups = [{
      provider: 'custom:transsion',
      label: 'Transsion',
      base_url: 'https://example.com/v1',
      models: ['deepseek-v4-pro', 'MiniMax/MiniMax-M3', 'glm-5.1'],
      api_key: '',
    }]

    const first = store.switchModel('deepseek-v4-pro', 'custom:transsion')
    const second = store.switchModel('MiniMax/MiniMax-M3', 'custom:transsion')

    await Promise.resolve()
    expect(mockSystemApi.updateDefaultModel).toHaveBeenCalledTimes(1)
    expect(mockSystemApi.updateDefaultModel).toHaveBeenLastCalledWith({
      default: 'deepseek-v4-pro',
      provider: 'custom:transsion',
    })
    expect(store.selectedModel).toBe('')

    resolveFirst()
    await Promise.all([first, second])

    expect(mockSystemApi.updateDefaultModel).toHaveBeenCalledTimes(2)
    expect(callOrder).toEqual([
      'start:deepseek-v4-pro',
      'end:deepseek-v4-pro',
      'start:MiniMax/MiniMax-M3',
      'end:MiniMax/MiniMax-M3',
    ])
    expect(store.selectedModel).toBe('MiniMax/MiniMax-M3')
    expect(store.selectedProvider).toBe('custom:transsion')
  })

  it('keeps later model switches runnable after an earlier switch fails', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSystemApi.updateDefaultModel
      .mockRejectedValueOnce(new Error('write failed'))
      .mockResolvedValueOnce(undefined)

    const store = useAppStore()
    store.modelGroups = [{
      provider: 'custom:transsion',
      label: 'Transsion',
      base_url: 'https://example.com/v1',
      models: ['deepseek-v4-pro', 'glm-5.1'],
      api_key: '',
    }]

    await Promise.all([
      store.switchModel('deepseek-v4-pro', 'custom:transsion'),
      store.switchModel('glm-5.1', 'custom:transsion'),
    ])

    expect(mockSystemApi.updateDefaultModel).toHaveBeenCalledTimes(2)
    expect(mockSystemApi.updateDefaultModel).toHaveBeenNthCalledWith(1, {
      default: 'deepseek-v4-pro',
      provider: 'custom:transsion',
    })
    expect(mockSystemApi.updateDefaultModel).toHaveBeenNthCalledWith(2, {
      default: 'glm-5.1',
      provider: 'custom:transsion',
    })
    expect(store.selectedModel).toBe('glm-5.1')
    expect(store.selectedProvider).toBe('custom:transsion')
    expect(consoleError).toHaveBeenCalledWith('Failed to switch model:', expect.any(Error))
    consoleError.mockRestore()
  })
})
