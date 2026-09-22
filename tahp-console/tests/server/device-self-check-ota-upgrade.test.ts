import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
  startTest,
} from '../../packages/server/src/services/tahp/device-self-check'

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
    expect(detail[0]?.manualSteps).toContain('device_update')
    expect(detail[0]?.expectedResult).toContain('ro.build.version.release')
  })

  it('rejects start without a full-flash package', async () => {
    initDeviceSelfCheck()
    await expect(startTest('NO_DEVICE', 'ota_upgrade')).rejects.toThrow(/获取外发版本/)
  })
})
