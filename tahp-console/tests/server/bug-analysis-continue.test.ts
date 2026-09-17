import { describe, expect, it } from 'vitest'
import {
  evaluateBugContinueEligibility,
  resolveBugContinueSessionMode,
} from '../../packages/server/src/services/tahp/bug-analysis-continue'

describe('evaluateBugContinueEligibility', () => {
  it('allows continue on completed tasks even when the Agent session is gone', () => {
    expect(evaluateBugContinueEligibility({
      found: true,
      status: 'completed',
      dupJudgeRunning: false,
    })).toEqual({ can_continue: true })
  })

  it('blocks continue while the task is still running or waiting', () => {
    for (const status of ['running', 'pending', 'waiting_user_input']) {
      expect(evaluateBugContinueEligibility({ found: true, status })).toEqual({
        can_continue: false,
        reason: '任务正在运行中',
      })
    }
  })

  it('blocks continue during duplicate judging', () => {
    expect(evaluateBugContinueEligibility({
      found: true,
      status: 'completed',
      dupJudgeRunning: true,
    })).toEqual({
      can_continue: false,
      reason: '正在尝试置重，请稍后再补充分析',
    })
  })

  it('blocks continue for failed or missing tasks', () => {
    expect(evaluateBugContinueEligibility({ found: true, status: 'failed' })).toEqual({
      can_continue: false,
      reason: '仅已完成的分析任务可补充继续',
    })
    expect(evaluateBugContinueEligibility({ found: true, status: 'cancelled' })).toEqual({
      can_continue: false,
      reason: '仅已完成的分析任务可补充继续',
    })
    expect(evaluateBugContinueEligibility({ found: false })).toEqual({
      can_continue: false,
      reason: '找不到任务',
    })
  })
})

describe('resolveBugContinueSessionMode', () => {
  it('reuses the live Agent session when it is still alive', () => {
    expect(resolveBugContinueSessionMode(true)).toBe('reuse_session')
  })

  it('rebuilds conversation history after idle GC or restart', () => {
    expect(resolveBugContinueSessionMode(false)).toBe('rebuild_history')
  })
})
