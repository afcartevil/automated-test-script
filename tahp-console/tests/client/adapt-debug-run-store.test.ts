// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const listActiveAdaptAgentRunsMock = vi.fn()
const getAdaptAgentRunMock = vi.fn()

vi.mock('@/api/tahp/adapt', () => ({
  listActiveAdaptAgentRuns: (...args: unknown[]) => listActiveAdaptAgentRunsMock(...args),
  getAdaptAgentRun: (...args: unknown[]) => getAdaptAgentRunMock(...args),
}))

import {
  ADAPT_DEBUG_RUN_STORAGE_KEY,
  useAdaptDebugRunStore,
} from '../../packages/client/src/stores/tahp/adapt-debug-run'

describe('useAdaptDebugRunStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    listActiveAdaptAgentRunsMock.mockReset()
    listActiveAdaptAgentRunsMock.mockResolvedValue([])
    getAdaptAgentRunMock.mockReset()
    getAdaptAgentRunMock.mockResolvedValue({ live: null, report: null })
  })

  it('keeps launched task id after a new store instance hydrates from sessionStorage', () => {
    const first = useAdaptDebugRunStore()
    first.runStateByWorkspace['adapt-debug'].launchedTaskId = 'task-keep-1'
    first.runStateByWorkspace['adapt-debug'].taskStatus = 'EXECUTING'
    first.registerActiveRun('task-keep-1', 'comm-framework', 'adapt-debug')
    first.persist()

    setActivePinia(createPinia())
    const second = useAdaptDebugRunStore()
    expect(second.runStateByWorkspace['adapt-debug'].launchedTaskId).toBe('task-keep-1')
    expect(second.runStateByWorkspace['adapt-debug'].taskStatus).toBe('EXECUTING')
    expect(second.activeRunsByKey['adapt-debug:comm-framework']?.taskId).toBe('task-keep-1')
    expect(sessionStorage.getItem(ADAPT_DEBUG_RUN_STORAGE_KEY)).toContain('task-keep-1')
  })

  it('reattaches a live backend task when local state was cleared', async () => {
    listActiveAdaptAgentRunsMock.mockResolvedValue([
      {
        task_id: 'task-live-9',
        workspace_id: 'adapt-debug',
        domain_id: 'comm-framework',
        domain_label: '通信框架',
        status: 'running',
        phase: 'EXECUTING',
        started_at: '2026-09-16T09:00:00.000Z',
      },
    ])
    const tracked: string[] = []
    const store = useAdaptDebugRunStore()
    await store.reattachLiveTasks({
      ensureSocket: () => {},
      trackTask: (id) => { tracked.push(id) },
    })
    expect(store.runStateByWorkspace['adapt-debug'].launchedTaskId).toBe('task-live-9')
    expect(store.runStateByWorkspace['adapt-debug'].taskStatus).toBe('EXECUTING')
    expect(store.activeRunsByKey['adapt-debug:comm-framework']?.taskId).toBe('task-live-9')
    expect(tracked).toContain('task-live-9')
  })

  it('switches to the live task when the stored id is no longer running', async () => {
    const store = useAdaptDebugRunStore()
    store.runStateByWorkspace['adapt-debug'].launchedTaskId = 'task-old'
    store.runStateByWorkspace['adapt-debug'].taskStatus = 'running'
    store.registerActiveRun('task-old', 'comm-framework', 'adapt-debug')
    listActiveAdaptAgentRunsMock.mockResolvedValue([
      {
        task_id: 'task-new',
        workspace_id: 'adapt-debug',
        domain_id: 'modem',
        domain_label: 'Modem',
        status: 'running',
        started_at: '2026-09-16T10:00:00.000Z',
      },
    ])
    await store.reattachLiveTasks({
      ensureSocket: () => {},
      trackTask: () => {},
    })
    expect(store.runStateByWorkspace['adapt-debug'].launchedTaskId).toBe('task-new')
    expect(store.activeRunsByKey['adapt-debug:comm-framework']).toBeUndefined()
    expect(store.activeRunsByKey['adapt-debug:modem']?.taskId).toBe('task-new')
  })

  it('marks a stored task completed when it is no longer in the live list', async () => {
    const store = useAdaptDebugRunStore()
    store.runStateByWorkspace['adapt-debug'].launchedTaskId = 'task-done'
    store.runStateByWorkspace['adapt-debug'].taskStatus = 'EXECUTING'
    getAdaptAgentRunMock.mockResolvedValue({
      live: { status: 'completed', phase: 'COMPLETED' },
      report: { task_id: 'task-done' },
    })
    await store.reattachLiveTasks({
      ensureSocket: () => {},
      trackTask: () => {},
    })
    expect(store.runStateByWorkspace['adapt-debug'].launchedTaskId).toBe('task-done')
    expect(store.runStateByWorkspace['adapt-debug'].taskStatus).toBe('COMPLETED')
  })
})
