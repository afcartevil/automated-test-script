import { describe, it, expect } from 'vitest'
import { recommendTestCases } from '../../packages/server/src/services/tahp/gerrit-case-recommendation'

describe('recommendTestCases', () => {
  it('recommends cases from must-test USB content', () => {
    const cases = recommendTestCases([
      '反复插拔 USB 线，验证是否正常触发校准',
    ])
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.every(c => c.reasons.some(r => r.startsWith('必须测试:')))).toBe(true)
    expect(cases.some(c => c.caseName.includes('USB') || c.caseName.includes('充电'))).toBe(true)
  })

  it('returns empty when must-test items are empty', () => {
    expect(recommendTestCases([])).toEqual([])
  })

  it('recommends tdd cases for SIM must-test text', () => {
    const cases = recommendTestCases(['验证 SIM 卡与数据连接'])
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.some(c => c.caseKey.startsWith('week/tdd/'))).toBe(true)
  })

  it('recommends from both catalogs for mixed must-test text', () => {
    const cases = recommendTestCases(['显示异常', 'SIM 识别'])
    const driverCases = cases.filter(c => c.caseKey.startsWith('week/driver/'))
    const tddCases = cases.filter(c => c.caseKey.startsWith('week/tdd/'))
    expect(driverCases.length).toBeGreaterThan(0)
    expect(tddCases.length).toBeGreaterThan(0)
  })
})
