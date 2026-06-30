import { describe, it, expect } from 'vitest'
import {
  buildRecommendPrompt,
  mapLlmRecommendations,
  parseRecommendLlmJson,
} from '../../packages/server/src/services/tahp/gerrit-case-recommend-llm'
import type { CaseCandidate } from '../../packages/server/src/services/tahp/gerrit-case-recommendation'

const candidates: CaseCandidate[] = [
  { caseKey: 'week/driver/14', caseName: 'USB功能正常充电', moduleLabel: '驱动' },
  { caseKey: 'week/driver/7', caseName: '距离传感器能正常使用', moduleLabel: '驱动' },
  { caseKey: 'week/tdd/1', caseName: 'SIM识别', moduleLabel: '通信' },
]

describe('parseRecommendLlmJson', () => {
  it('parses plain JSON', () => {
    const parsed = parseRecommendLlmJson(
      '{"recommendations":[{"caseKey":"week/driver/14","score":0.9,"reason":"USB"}]}',
    )
    expect(parsed?.recommendations).toHaveLength(1)
    expect(parsed?.recommendations[0]?.caseKey).toBe('week/driver/14')
  })

  it('parses fenced JSON', () => {
    const parsed = parseRecommendLlmJson(`\`\`\`json
{"recommendations":[{"caseKey":"week/driver/7","score":8,"reason":"SAR"}]}
\`\`\``)
    expect(parsed?.recommendations[0]?.caseKey).toBe('week/driver/7')
  })

  it('returns null for invalid structure', () => {
    expect(parseRecommendLlmJson('{"items":[]}')).toBeNull()
    expect(parseRecommendLlmJson('not json')).toBeNull()
  })
})

describe('mapLlmRecommendations', () => {
  it('filters unknown caseKey and maps fields', () => {
    const result = mapLlmRecommendations(
      {
        recommendations: [
          { caseKey: 'week/driver/14', score: 0.85, reason: '匹配 USB 校准' },
          { caseKey: 'week/driver/999', score: 1, reason: '编造' },
        ],
      },
      candidates,
      16,
    )

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      caseKey: 'week/driver/14',
      caseName: 'USB功能正常充电',
      moduleLabel: '驱动',
      score: 9,
      reasons: ['匹配 USB 校准'],
    })
  })

  it('deduplicates caseKey', () => {
    const result = mapLlmRecommendations(
      {
        recommendations: [
          { caseKey: 'week/driver/14', score: 1, reason: 'a' },
          { caseKey: 'week/driver/14', score: 1, reason: 'b' },
        ],
      },
      candidates,
      16,
    )
    expect(result).toHaveLength(1)
  })
})

describe('buildRecommendPrompt', () => {
  it('includes all P0 items and candidate case keys', () => {
    const { instructions, userMessage } = buildRecommendPrompt(
      ['USB 插拔触发 SAR 校准', '验证充电电流'],
      ['USB', 'Sensor'],
      candidates,
    )

    expect(instructions).toContain('禁止调用任何工具')
    expect(instructions).toContain('只输出一个 JSON 对象')
    expect(userMessage).toContain('USB 插拔触发 SAR 校准')
    expect(userMessage).toContain('week/driver/14 | USB功能正常充电 | 驱动')
    expect(userMessage).toContain('week/tdd/1 | SIM识别 | 通信')
  })
})
