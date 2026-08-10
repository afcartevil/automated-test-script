import { describe, expect, it } from 'vitest'
import { existsSync } from 'fs'
import { join } from 'path'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'
import { normalizePlanTestType, validateTestPlanRules } from '../../packages/server/src/services/tahp/test-planning'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'

describe('device self-check therm catalog', () => {
  it('loads therm scheme catalog next to power types', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'therm')
    expect(group?.label).toBe('温升方案自检')
    expect(group?.modules).toHaveLength(1)
    expect(group?.modules[0]?.module).toBe('scheme')
    expect(group?.modules[0]?.moduleLabel).toBe('温升方案检测')
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('温升方案自检')
    expect(group?.modules[0]?.cases[0]?.automationMode).toBe('full')

    const catalogs = getAllCaseCatalogs()
    const typeOrder = catalogs.map(g => g.testType)
    expect(typeOrder.indexOf('power_feature')).toBeLessThan(typeOrder.indexOf('therm'))

    const detail = getCaseCatalogDetail('therm')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'therm',
      module: 'scheme',
      moduleLabel: '温升方案检测',
      caseName: '温升方案自检',
      key: 'therm/scheme/1',
      automationMode: 'full',
    })
    expect(detail[0]?.preconditions).toContain('ADB')
    expect(detail[0]?.manualSteps.length).toBeGreaterThan(0)
    expect(detail[0]?.expectedResult.length).toBeGreaterThan(0)

    const launcher = join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/tools/tpytest_dzppt_therm/launchers/dzppt/therm/start_therm_cli_python.py',
    )
    expect(existsSync(launcher)).toBe(true)
  })

  it('normalizes plan test type aliases for therm before power', () => {
    expect(normalizePlanTestType('therm')).toBe('therm')
    expect(normalizePlanTestType('温升方案自检')).toBe('therm')
    expect(normalizePlanTestType('tpytest_dzppt_therm')).toBe('therm')
    expect(normalizePlanTestType('功耗自动化测试')).toBe('power')
    expect(validateTestPlanRules([
      { node: 'STR4A', offsetDays: -1, testType: 'therm' },
    ])).toEqual([{ node: 'STR4A', offsetDays: -1, testType: 'therm' }])
  })
})
