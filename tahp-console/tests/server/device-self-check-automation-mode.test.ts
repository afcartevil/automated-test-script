import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
  resolveCaseAutomationMode,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check automationMode', () => {
  it('classifies full / semi / manual cases', () => {
    initDeviceSelfCheck()

    expect(resolveCaseAutomationMode('smoke', 'usd', 1)).toBe('full')
    expect(resolveCaseAutomationMode('str4', 'tdd', 1)).toBe('full')
    expect(resolveCaseAutomationMode('str4', 'driver_component', 9)).toBe('semi')
    expect(resolveCaseAutomationMode('str4', 'tdd', 15)).toBe('manual')
  })

  it('exposes automationMode on catalogs and detail', () => {
    initDeviceSelfCheck()

    const smoke = getAllCaseCatalogs().find(g => g.testType === 'smoke')
    expect(smoke?.modules[0]?.cases[0]?.automationMode).toBe('full')

    const str4Detail = getCaseCatalogDetail('str4')
    const fullCase = str4Detail.find(c => c.module === 'tdd' && c.caseIndex === 1)
    const semiCase = str4Detail.find(c => c.module === 'driver_component' && c.caseIndex === 9)
    const manualCase = str4Detail.find(c => c.module === 'tdd' && c.caseIndex === 15)

    expect(fullCase?.automationMode).toBe('full')
    expect(semiCase?.automationMode).toBe('semi')
    expect(manualCase?.automationMode).toBe('manual')
  })

  it('str4/week tdd has no semi; stub skips are manual', () => {
    initDeviceSelfCheck()

    for (const testType of ['str4', 'week'] as const) {
      const tdd = getCaseCatalogDetail(testType).filter(c => c.module === 'tdd')
      expect(tdd.length).toBeGreaterThan(0)
      expect(tdd.every(c => c.automationMode !== 'semi')).toBe(true)
      expect(tdd.some(c => c.automationMode === 'manual')).toBe(true)
      expect(tdd.some(c => c.automationMode === 'full')).toBe(true)
    }

    // 步骤文案含“人工”等关键词的可执行脚本，通信模块仍应判为全自动
    expect(resolveCaseAutomationMode('str4', 'tdd', 31, {
      manualSteps: '查询话费、人工服务等',
    })).toBe('full')
    expect(resolveCaseAutomationMode('str4', 'tdd', 15)).toBe('manual')
  })
})
