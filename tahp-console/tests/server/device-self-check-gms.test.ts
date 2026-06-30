import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  getSettings,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check gms catalog', () => {
  it('loads gms test catalog with cts/gts/vts modules', () => {
    initDeviceSelfCheck()

    const gmsGroup = getAllCaseCatalogs().find(group => group.testType === 'gms')
    expect(gmsGroup?.label).toBe('GMS测试')
    expect(gmsGroup?.modules.map(m => m.module)).toEqual(['cts', 'gts', 'vts'])
    expect(gmsGroup?.modules[0]?.cases).toHaveLength(4)
    expect(gmsGroup?.modules[0]?.cases[0]?.caseName).toBe('CTS指纹测试')

    const ctsDetail = getCaseCatalogDetail('gms').filter(item => item.module === 'cts')
    expect(ctsDetail).toHaveLength(4)
    expect(ctsDetail[0]).toMatchObject({
      testType: 'gms',
      module: 'cts',
      moduleLabel: 'CTS',
      caseName: 'CTS指纹测试',
    })
    expect(ctsDetail[0]?.manualSteps).toContain('cts-tradefed run cts --subplan fingerprint-cts-plan')

    expect(getSettings().gmsTradefedPath).toEqual({})
  })
})
