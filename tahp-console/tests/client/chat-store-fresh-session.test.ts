// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/hermes/chat', () => ({
  resumeSession: vi.fn(),
  startRunViaSocket: vi.fn(),
  registerSessionHandlers: vi.fn(),
  unregisterSessionHandlers: vi.fn(),
  getChatRunSocket: vi.fn(() => null),
  respondToolApproval: vi.fn(),
}))

vi.mock('@/api/hermes/sessions', () => ({
  fetchSessions: vi.fn(),
  fetchSession: vi.fn(),
  setSessionModel: vi.fn(),
  deleteSession: vi.fn(),
}))

vi.mock('@/api/hermes/profiles', () => ({
  fetchProfiles: vi.fn(async () => [{ name: 'default', active: true }]),
  fetchProfileDetail: vi.fn(),
}))

import { resumeSession } from '@/api/hermes/chat'
import { fetchSessions } from '@/api/hermes/sessions'
import { useChatStore } from '@/stores/hermes/chat'
import { useProfilesStore } from '@/stores/hermes/profiles'

describe('chat store fresh session', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(resumeSession).mockReset()
    vi.mocked(fetchSessions).mockReset()
    vi.mocked(fetchSessions).mockResolvedValue([
      {
        id: 'old-1',
        source: 'cli',
        model: 'm',
        title: '上一场',
        started_at: 1,
        ended_at: null,
        message_count: 12,
        tool_call_count: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read_tokens: 0,
        cache_write_tokens: 0,
        reasoning_tokens: 0,
        billing_provider: null,
        estimated_cost_usd: 0,
        actual_cost_usd: null,
        cost_status: '',
      },
    ])
  })

  it('newChat does not resume a previous session', async () => {
    const profiles = useProfilesStore()
    profiles.profiles = [{ name: 'default', active: true } as never]
    profiles.activeProfileName = 'default'

    const store = useChatStore()
    await store.newChat()

    expect(resumeSession).not.toHaveBeenCalled()
    expect(store.activeSessionId).toBeTruthy()
    expect(store.isLoadingMessages).toBe(false)
    expect(store.activeSession?.messages).toEqual([])
  })

  it('loadSessions({ activate: false }) keeps the new chat and skips resume', async () => {
    const profiles = useProfilesStore()
    profiles.profiles = [{ name: 'default', active: true } as never]
    profiles.activeProfileName = 'default'

    const store = useChatStore()
    await store.newChat()
    const freshId = store.activeSessionId
    vi.mocked(resumeSession).mockClear()

    await store.loadSessions(undefined, { activate: false })

    expect(resumeSession).not.toHaveBeenCalled()
    expect(store.activeSessionId).toBe(freshId)
    expect(store.sessions.some(s => s.id === 'old-1')).toBe(true)
    expect(store.sessions[0]?.id).toBe(freshId)
  })
})
