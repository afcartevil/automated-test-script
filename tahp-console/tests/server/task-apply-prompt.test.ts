import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../packages/server/src/services/tahp/central-user-session', () => ({
  readCentralUserSession: () => ({ token: 'sess' }),
}))

vi.mock('../../packages/server/src/services/tahp/sync/central-client', () => ({
  centralClient: {
    applyCandidates: vi.fn(),
  },
}))

import { centralClient } from '../../packages/server/src/services/tahp/sync/central-client'
import {
  clearApplyPrompt,
  getApplyPrompt,
  listApplyQueue,
  offerApplyPrompt,
  resetApplyQueue,
} from '../../packages/server/src/services/tahp/task-apply-prompt'

const applyCandidates = centralClient.applyCandidates as ReturnType<typeof vi.fn>

function promptData(runId: string, status = 'pass') {
  return {
    run: { run_id: runId, project_code: 'LJ9', campaign_id: 'v1', status, dimension: 'self-check', domain_id: 'tp' },
    packages: [{
      package_id: 'p1',
      title: 'LJ9 · TP',
      domain_label: 'TP',
      pending_items: [{ line_id: 'l1', item_id: 'adapt-p1-tp-0001', title: '息屏' }],
    }],
    campaign_unspecified: false,
  }
}

describe('task-apply-prompt queue', () => {
  afterEach(() => {
    resetApplyQueue()
    applyCandidates.mockReset()
  })

  it('E1 two offers stay queued until dequeue', async () => {
    applyCandidates.mockImplementation(async (_token: string, runId: string) => promptData(runId))
    await offerApplyPrompt('run-a')
    await offerApplyPrompt('run-b')
    expect(listApplyQueue().map(p => p.run.run_id)).toEqual(['run-a', 'run-b'])
    expect(getApplyPrompt()?.run.run_id).toBe('run-a')
  })

  it('E2 offering while head is showing does not drop the third', async () => {
    applyCandidates.mockImplementation(async (_token: string, runId: string) => promptData(runId))
    await offerApplyPrompt('run-a')
    expect(getApplyPrompt()?.run.run_id).toBe('run-a')
    await offerApplyPrompt('run-b')
    await offerApplyPrompt('run-c')
    expect(listApplyQueue().map(p => p.run.run_id)).toEqual(['run-a', 'run-b', 'run-c'])
  })

  it('E3 skip shows the next run', async () => {
    applyCandidates.mockImplementation(async (_token: string, runId: string) => promptData(runId))
    await offerApplyPrompt('run-a')
    await offerApplyPrompt('run-b')
    clearApplyPrompt()
    expect(getApplyPrompt()?.run.run_id).toBe('run-b')
  })

  it('E4 fail run also_pass_default is false', async () => {
    applyCandidates.mockResolvedValueOnce(promptData('run-fail', 'fail'))
    await offerApplyPrompt('run-fail')
    expect(getApplyPrompt()?.also_pass_default).toBe(false)
  })
})
