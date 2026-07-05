import { describe, expect, it } from 'vitest'
import {
  findReusableHistoricalAiCases,
  textCoversP0Item,
  type AiGeneratedCase,
} from '../../packages/server/src/services/tahp/gerrit-ai-generated-cases'

describe('gerrit-ai-generated-cases historical reuse', () => {
  const historical: AiGeneratedCase[] = [
    {
      caseKey: 'ai_generated/generated/1',
      caseIndex: 1,
      caseName: 'USB 插拔 SAR 校准验证',
      moduleLabel: 'AI生成用例',
      coveredP0Items: ['USB 插拔触发 SAR 校准'],
      reason: '覆盖 USB 校准',
      manualSteps: '1. 插拔 USB',
      expectedResult: '触发校准',
    },
    {
      caseKey: 'ai_generated/generated/2',
      caseIndex: 2,
      caseName: '长时间充电稳定性',
      moduleLabel: 'AI生成用例',
      coveredP0Items: ['长时间充电温升'],
      reason: '覆盖充电稳定性',
      manualSteps: '1. 长时间充电',
      expectedResult: '无异常',
    },
  ]

  it('matches historical cases to coverage gaps by token overlap', () => {
    const { reusable, remainingGaps } = findReusableHistoricalAiCases(
      ['USB 插拔触发 SAR 校准', 'SIM 卡识别异常'],
      historical,
    )

    expect(reusable).toHaveLength(1)
    expect(reusable[0]?.caseKey).toBe('ai_generated/generated/1')
    expect(reusable[0]?.reason).toContain('复用历史 AI 用例')
    expect(reusable[0]?.coveredP0Items).toEqual(['USB 插拔触发 SAR 校准'])
    expect(remainingGaps).toEqual(['SIM 卡识别异常'])
  })

  it('returns all gaps when no historical case matches', () => {
    const { reusable, remainingGaps } = findReusableHistoricalAiCases(
      ['完全不相关的场景 xyz'],
      historical,
    )

    expect(reusable).toEqual([])
    expect(remainingGaps).toEqual(['完全不相关的场景 xyz'])
  })

  it('textCoversP0Item supports mixed Chinese and English tokens', () => {
    expect(textCoversP0Item('USB 插拔触发 SAR 校准', 'USB功能正常充电 SAR sensor')).toBe(true)
    expect(textCoversP0Item('完全不相关', 'USB 插拔')).toBe(false)
  })
})
