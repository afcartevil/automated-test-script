import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
  startTest,
} from '../../packages/server/src/services/tahp/device-self-check'
import { tcardBaselineVersionError } from '../../packages/server/src/services/tahp/ota-pretest'

describe('device self-check ota_upgrade catalog', () => {
  it('loads continuous OTA upgrade catalog', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(item => item.testType === 'ota_upgrade')
    expect(group?.label).toBe('连续OTA升级')
    expect(group?.modules).toHaveLength(1)
    expect(group?.modules[0]?.module).toBe('ota')
    expect(group?.modules[0]?.moduleLabel).toBe('连续OTA升级')
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('连续OTA升级')
    expect(group?.modules[0]?.cases[0]?.automationMode).toBe('full')

    const typeOrder = getAllCaseCatalogs().map(item => item.testType)
    expect(typeOrder.indexOf('smoke')).toBeLessThan(typeOrder.indexOf('ota_upgrade'))
    expect(typeOrder.indexOf('ota_upgrade')).toBeLessThan(typeOrder.indexOf('gms'))

    const detail = getCaseCatalogDetail('ota_upgrade')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'ota_upgrade',
      module: 'ota',
      moduleLabel: '连续OTA升级',
      caseName: '连续OTA升级',
      automationMode: 'full',
    })
    expect(detail[0]?.preconditions).toContain('获取外发版本')
    expect(detail[0]?.preconditions).not.toContain('SOP')
    expect(detail[0]?.manualSteps).toContain('device_update')
    expect(detail[0]?.expectedResult).toContain('ro.build.version.release')
  })

  it('allows start without a release package when no device is present', async () => {
    initDeviceSelfCheck()
    await expect(startTest('NO_DEVICE', 'ota_upgrade')).resolves.toBeNull()
  })
})

describe('ota_upgrade tcard baseline version gate', () => {
  it('手机当前版本与最低勾选版本的上一档匹配时放行', () => {
    expect(tcardBaselineVersionError('14', 14)).toBeUndefined()
    expect(tcardBaselineVersionError('14.0', 14)).toBeUndefined()
    expect(tcardBaselineVersionError(' 15 ', 15)).toBeUndefined()
  })

  it('版本不匹配时拦截并提示改用 device_update', () => {
    const error = tcardBaselineVersionError('14', 15)
    expect(error).toContain('Android 14')
    expect(error).toContain('Android 15')
    expect(error).toContain('device_update')
  })

  it('读不到版本号时按未知版本拦截', () => {
    expect(tcardBaselineVersionError('', 15)).toContain('未知 Android 版本')
  })
})
