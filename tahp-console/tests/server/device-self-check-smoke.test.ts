import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  getSettings,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check smoke usd catalog', () => {
  it('loads smoke USD catalog and settings', () => {
    initDeviceSelfCheck()

    const smokeGroup = getAllCaseCatalogs().find(group => group.testType === 'smoke')
    expect(smokeGroup?.label).toBe('冒烟测试')
    expect(smokeGroup?.modules).toHaveLength(1)
    expect(smokeGroup?.modules[0]?.module).toBe('usd')
    expect(smokeGroup?.modules[0]?.moduleLabel).toBe('USD冒烟测试')
    expect(smokeGroup?.modules[0]?.cases[0]?.caseName).toBe('USD冒烟测试')

    const detail = getCaseCatalogDetail('smoke')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'smoke',
      module: 'usd',
      moduleLabel: 'USD冒烟测试',
      caseName: 'USD冒烟测试',
      preconditions: '',
      manualSteps: '',
      expectedResult: '',
    })
    expect(getSettings().smokeUsdSkipSpdInfo).toBe(false)
  })
})
