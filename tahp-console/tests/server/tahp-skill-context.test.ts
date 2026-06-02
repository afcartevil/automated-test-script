import { describe, expect, it } from 'vitest'
import {
  extractPreferredSkillIds,
  buildSkillExecutionDirective,
} from '../../packages/server/src/services/tahp/context-injector'

describe('tahp skill context injector', () => {
  it('extracts preferred skill ids from adapt handoff text', () => {
    const text = [
      '我正在做 TP 适配',
      '**关联 Skills**: vib-adapt-lra-driver, fc-vib-driver, vib-adapt-dts-regulator',
    ].join('\n')
    expect(extractPreferredSkillIds(text)).toEqual([
      'vib-adapt-lra-driver',
      'fc-vib-driver',
      'vib-adapt-dts-regulator',
    ])
  })

  it('buildSkillExecutionDirective lists preferred skill paths', () => {
    const out = buildSkillExecutionDirective({
      preferredSkillIds: ['com-voice-call-dialing'],
      scenario: 'bug_analysis',
    })
    expect(out).toContain('com-voice-call-dialing')
    expect(out).toContain('SKILL.md')
    expect(out).toContain('AI Bug 分析')
  })
})
