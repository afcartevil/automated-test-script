import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'

describe('device self-check thermal catalog', () => {
  it('loads thermal scheme catalog next to power types', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'thermal')
    expect(group?.label).toBe('温升方案自检')
    expect(group?.modules).toHaveLength(1)
    expect(group?.modules[0]?.module).toBe('scheme')
    expect(group?.modules[0]?.moduleLabel).toBe('温升方案检测')
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('温升方案自检')
    expect(group?.modules[0]?.cases[0]?.automationMode).toBe('full')

    const catalogs = getAllCaseCatalogs()
    const typeOrder = catalogs.map(g => g.testType)
    expect(typeOrder.indexOf('power_feature')).toBeLessThan(typeOrder.indexOf('thermal'))

    const detail = getCaseCatalogDetail('thermal')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'thermal',
      module: 'scheme',
      moduleLabel: '温升方案检测',
      caseName: '温升方案自检',
      key: 'thermal/scheme/1',
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
    expect(readFileSync(launcher, 'utf-8')).toContain('--log-parent-dir')

    const case1 = join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/cases/thermal/scheme/case1.py',
    )
    const case1Text = readFileSync(case1, 'utf-8')
    expect(case1Text).toContain('thermalLogParentDir')
    expect(case1Text).toContain('--log-parent-dir')
  })
})
