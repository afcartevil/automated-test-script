import { readFileSync } from 'fs'
import { resolve } from 'path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../packages/server/src/db/hermes/session-store', () => ({
  updateSessionStats: vi.fn(),
}))
vi.mock('../../packages/server/src/services/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn() },
}))
vi.mock('../../packages/server/src/services/hermes/run-chat/bridge-message', () => ({
  flushBridgePendingToDb: vi.fn(),
}))
vi.mock('../../packages/server/src/services/hermes/run-chat/response-stream', () => ({
  flushResponseRunToDb: vi.fn(),
}))
vi.mock('../../packages/server/src/services/hermes/run-chat/compression', () => ({
  replaceState: vi.fn(),
}))
vi.mock('../../packages/server/src/services/hermes/run-chat/usage', () => ({
  calcAndUpdateUsage: vi.fn(async () => {}),
}))

describe('agent bridge interrupt contracts', () => {
  it('uses utf-8 worker pipes and hard_cancel on user interrupt', () => {
    const src = readFileSync(
      resolve('packages/server/src/services/hermes/agent-bridge/hermes_bridge.py'),
      'utf8',
    )
    expect(src).toContain('PYTHONUTF8')
    expect(src).toContain('PYTHONIOENCODING')
    expect(src).toContain('encoding="utf-8"')
    expect(src).toContain('errors="replace"')
    expect(src).toContain('hard_interrupt')
    expect(src).toContain('hard_cancel=_coerce_bool(req.get("hard_cancel"), True)')
    expect(src).toContain('stderr reader exited')
  })

  it('reports abort.completed.synced=false when the worker run is still active', async () => {
    const { handleAbort } = await import('../../packages/server/src/services/hermes/run-chat/abort')
    const emitted: Array<{ event: string; payload: any }> = []
    const nsp = {
      to: () => ({ emit: (event: string, payload: any) => emitted.push({ event, payload }) }),
      adapter: { rooms: new Map() },
    }
    const socket = { connected: false, emit: vi.fn() }
    const sessionMap = new Map([
      ['sess-1', {
        isWorking: true,
        isAborting: false,
        runId: 'run-1',
        source: 'cli',
        profile: 'default',
        queue: [],
        events: [],
      }],
    ])
    const interrupt = vi.fn(async () => ({ ok: true, status: 'interrupted', synced: false }))
    const runQueuedItem = vi.fn()

    await handleAbort(
      nsp as any,
      socket as any,
      'sess-1',
      sessionMap as any,
      { interrupt },
      runQueuedItem,
    )

    expect(interrupt).toHaveBeenCalledWith('sess-1', 'Aborted by user', 'default', true)
    const completed = emitted.find((item) => item.event === 'abort.completed')
    expect(completed?.payload.synced).toBe(false)
    expect(sessionMap.get('sess-1')?.isWorking).toBe(false)
  })
})
