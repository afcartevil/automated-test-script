import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check power_feature (WBS) catalog', () => {
  it('loads power_feature WBS catalog', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'power_feature')
    expect(group?.label).toBe('功耗特性自检')
    expect(group?.modules).toHaveLength(1)
    expect(group?.modules[0]?.module).toBe('wbs')
    expect(group?.modules[0]?.moduleLabel).toBe('功耗特性检测')
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('功耗特性自检')
    expect(group?.modules[0]?.cases[0]?.automationMode).toBe('full')

    const detail = getCaseCatalogDetail('power_feature')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'power_feature',
      module: 'wbs',
      moduleLabel: '功耗特性检测',
      caseName: '功耗特性自检',
      key: 'power_feature/wbs/1',
      automationMode: 'full',
    })
    expect(detail[0]?.preconditions).toContain('ADB')
    expect(detail[0]?.manualSteps.length).toBeGreaterThan(0)
    expect(detail[0]?.expectedResult.length).toBeGreaterThan(0)
  })
})
