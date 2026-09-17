import { describe, expect, it } from 'vitest'
import { canOfferBugContinueAnalysis } from '../../packages/client/src/utils/bug-analysis-continue'

describe('canOfferBugContinueAnalysis', () => {
  const ready = {
    taskId: 'task-bug-1',
    status: 'completed',
    running: false,
    pending: false,
    waitingUserInput: false,
    dupJudgeRunning: false,
  }

  it('offers continue for a completed task even if the live session expired', () => {
    expect(canOfferBugContinueAnalysis(ready)).toBe(true)
  })

  it('does not require a live Agent session or recent-task view', () => {
    expect(canOfferBugContinueAnalysis(ready)).toBe(true)
  })

  it('hides continue while the task is busy', () => {
    expect(canOfferBugContinueAnalysis({ ...ready, running: true })).toBe(false)
    expect(canOfferBugContinueAnalysis({ ...ready, pending: true })).toBe(false)
    expect(canOfferBugContinueAnalysis({ ...ready, waitingUserInput: true })).toBe(false)
    expect(canOfferBugContinueAnalysis({ ...ready, dupJudgeRunning: true })).toBe(false)
  })

  it('hides continue for unfinished or missing tasks', () => {
    expect(canOfferBugContinueAnalysis({ ...ready, status: 'failed' })).toBe(false)
    expect(canOfferBugContinueAnalysis({ ...ready, taskId: null })).toBe(false)
  })
})
