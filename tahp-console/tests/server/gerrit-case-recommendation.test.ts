import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const rerankCasesWithLlmMock = vi.fn()

vi.mock('../../packages/server/src/services/tahp/gerrit-case-recommend-llm', () => ({
  rerankCasesWithLlm: (...args: unknown[]) => rerankCasesWithLlmMock(...args),
}))

import {
  recommendTestCases,
  recommendTestCasesByRules,
  recommendTestCasesWithMeta,
} from '../../packages/server/src/services/tahp/gerrit-case-recommendation'

describe('recommendTestCasesByRules', () => {
  it('recommends cases from must-test USB content', () => {
    const cases = recommendTestCasesByRules([
      '反复插拔 USB 线，验证是否正常触发校准',
    ])
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.every(c => c.reasons.some(r => r.startsWith('必须测试:')))).toBe(true)
    expect(cases.some(c => c.caseName.includes('USB') || c.caseName.includes('充电'))).toBe(true)
  })

  it('returns empty when must-test items are empty', () => {
    expect(recommendTestCasesByRules([])).toEqual([])
  })

  it('recommends tdd cases for SIM must-test text', () => {
    const cases = recommendTestCasesByRules(['验证 SIM 卡与数据连接'])
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.some(c => c.caseKey.startsWith('week/tdd/'))).toBe(true)
  })

  it('recommends from both catalogs for mixed must-test text', () => {
    const cases = recommendTestCasesByRules(['显示异常', 'SIM 识别'])
    const driverCases = cases.filter(c => c.caseKey.startsWith('week/driver/'))
    const tddCases = cases.filter(c => c.caseKey.startsWith('week/tdd/'))
    expect(driverCases.length).toBeGreaterThan(0)
    expect(tddCases.length).toBeGreaterThan(0)
  })

  it('matches markdown P0 lines and SAR sensor scenarios', () => {
    const cases = recommendTestCasesByRules([
      '**SAR 校准基础功能** — USB 正常插入和拔出时，确认是否成功触发校准。',
    ])
    expect(cases.length).toBeGreaterThan(0)
    expect(
      cases.some(c =>
        c.caseName.includes('USB')
        || c.caseName.includes('传感器')
        || c.caseName.includes('SAR'),
      ),
    ).toBe(true)
  })

  it('uses module hints for catalog routing', () => {
    const cases = recommendTestCasesByRules(['验证 USB 插拔稳定性'], ['USB'])
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.some(c => c.caseName.includes('USB') || c.caseKey.includes('driver'))).toBe(true)
  })
})

describe('recommendTestCases hybrid', () => {
  const prevMode = process.env.GERRIT_RECOMMEND_MODE

  beforeEach(() => {
    rerankCasesWithLlmMock.mockReset()
    delete process.env.GERRIT_RECOMMEND_MODE
  })

  afterEach(() => {
    if (prevMode === undefined) delete process.env.GERRIT_RECOMMEND_MODE
    else process.env.GERRIT_RECOMMEND_MODE = prevMode
  })

  it('uses LLM results when rerank returns cases', async () => {
    rerankCasesWithLlmMock.mockResolvedValueOnce([
      {
        caseKey: 'week/driver/14',
        caseName: 'USB功能正常充电',
        moduleLabel: '驱动',
        score: 9,
        reasons: ['P0 要求验证 USB 插拔触发校准'],
      },
    ])

    const { cases, source } = await recommendTestCasesWithMeta([
      'USB 插拔触发 SAR 校准',
    ])

    expect(source).toBe('llm')
    expect(cases).toHaveLength(1)
    expect(cases[0]?.caseKey).toBe('week/driver/14')
    expect(rerankCasesWithLlmMock).toHaveBeenCalled()
  })

  it('returns source in recommend-cases API response', async () => {
    rerankCasesWithLlmMock.mockResolvedValueOnce([
      {
        caseKey: 'week/driver/14',
        caseName: 'USB功能正常充电',
        moduleLabel: '驱动',
        score: 9,
        reasons: ['P0 要求验证 USB 插拔触发校准'],
      },
    ])

    const { cases, source } = await recommendTestCasesWithMeta(['USB 插拔触发 SAR 校准'])
    expect(source).toBe('llm')
    expect(cases[0]?.reasons[0]).not.toMatch(/^必须测试:/)
  })

  it('rule fallback reasons use 必须测试 prefix', async () => {
    rerankCasesWithLlmMock.mockRejectedValueOnce(new Error('Agent Bridge 未运行'))

    const { cases, source } = await recommendTestCasesWithMeta([
      '反复插拔 USB 线，验证是否正常触发校准',
    ])

    expect(source).toBe('rule')
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.every(c => c.reasons.some(r => r.startsWith('必须测试:')))).toBe(true)
  })

  it('falls back to rules when LLM returns empty after filtering', async () => {
    rerankCasesWithLlmMock.mockResolvedValueOnce([])

    const { cases, source } = await recommendTestCasesWithMeta([
      '反复插拔 USB 线，验证是否正常触发校准',
    ])

    expect(source).toBe('rule')
    expect(cases.length).toBeGreaterThan(0)
  })

  it('skips LLM when GERRIT_RECOMMEND_MODE=rule', async () => {
    process.env.GERRIT_RECOMMEND_MODE = 'rule'

    const { cases, source } = await recommendTestCasesWithMeta([
      '验证 SIM 卡与数据连接',
    ])

    expect(source).toBe('rule')
    expect(cases.length).toBeGreaterThan(0)
    expect(rerankCasesWithLlmMock).not.toHaveBeenCalled()
  })

  it('returns empty for empty P0 via recommendTestCases', async () => {
    await expect(recommendTestCases([])).resolves.toEqual([])
  })

  it('returns empty when mode=llm and LLM fails without fallback results', async () => {
    process.env.GERRIT_RECOMMEND_MODE = 'llm'
    rerankCasesWithLlmMock.mockRejectedValueOnce(new Error('timeout'))

    const { cases, source } = await recommendTestCasesWithMeta(['完全不相关的随机描述 xyzabc'])

    expect(source).toBe('rule')
    expect(cases).toEqual([])
  })
})
