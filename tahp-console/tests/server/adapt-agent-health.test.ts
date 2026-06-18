import { describe, expect, it } from 'vitest'
import {
  detectModelErrorInText,
  detectUnhealthyAgentRun,
  humanizeAgentError,
} from '../../packages/server/src/services/tahp/adapt-agent-health'

describe('adapt-agent-health', () => {
  it('humanizeAgentError maps quota errors', () => {
    const msg = humanizeAgentError('Error: insufficient quota for model gpt-4')
    expect(msg).toContain('额度')
    expect(msg).toContain('模型管理')
  })

  it('detectModelErrorInText finds balance errors', () => {
    expect(detectModelErrorInText('余额不足，请充值')).toContain('额度')
  })

  it('detectUnhealthyAgentRun flags empty fast runs', () => {
    const err = detectUnhealthyAgentRun({
      fullResponse: '',
      toolsUsedCount: 0,
      durationMs: 2100,
    })
    expect(err).toBeTruthy()
    expect(err).toContain('未执行任何工具')
  })

  it('detectUnhealthyAgentRun passes healthy runs', () => {
    const err = detectUnhealthyAgentRun({
      fullResponse: 'x'.repeat(200),
      toolsUsedCount: 5,
      durationMs: 120_000,
    })
    expect(err).toBeUndefined()
  })
})
