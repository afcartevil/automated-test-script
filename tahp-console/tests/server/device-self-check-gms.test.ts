import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  getSettings,
  initDeviceSelfCheck,
  isGmsSupportedOnHost,
  normalizeGmsTimeoutHours,
  updateSettings,
  __testingResolveCaseDisplayName,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check gms catalog', () => {
  it('loads gms test catalog with cts/gts/vts modules', () => {
    initDeviceSelfCheck()

    const gmsGroup = getAllCaseCatalogs().find(group => group.testType === 'gms')
    expect(gmsGroup?.label).toBe('GMS测试')
    expect(gmsGroup?.modules.map(m => m.module)).toEqual(['cts', 'gts', 'vts', 'cts_tele'])
    expect(gmsGroup?.modules[0]?.cases).toHaveLength(4)
    expect(gmsGroup?.modules[0]?.cases[0]?.caseName).toBe('CTS指纹测试')
    expect(gmsGroup?.modules[0]?.cases[3]?.caseName).toBe('CTS安全测试')

    const ctsDetail = getCaseCatalogDetail('gms').filter(item => item.module === 'cts')
    expect(ctsDetail).toHaveLength(4)
    expect(ctsDetail[3]).toMatchObject({
      testType: 'gms',
      module: 'cts',
      moduleLabel: 'CTS',
      caseName: 'CTS安全测试',
    })
    expect(ctsDetail[3]?.manualSteps).toContain('cts-tradefed run security-cts-plan')

    const gtsDetail = getCaseCatalogDetail('gms').filter(item => item.module === 'gts')
    expect(gtsDetail[4]?.caseName).toBe('GTS安全测试')
    expect(gtsDetail[4]?.manualSteps).toContain('gts-tradefed run security-gts-plan')

    const vtsDetail = getCaseCatalogDetail('gms').filter(item => item.module === 'vts')
    expect(vtsDetail[4]?.caseName).toBe('VTS安全测试')
    expect(vtsDetail[4]?.manualSteps).toContain('vts-tradefed run security-vts-plan')

    expect(getSettings().gmsTradefedPath).toEqual({})
    expect(getSettings().gmsTimeoutHours).toBe(8)
    expect(getSettings().gmsHostSupported).toBe(process.platform !== 'win32')
    if (process.platform === 'win32') {
      expect(gmsGroup?.unavailableReason).toContain('Windows 环境不支持 GMS')
    } else {
      expect(gmsGroup?.unavailableReason).toBeUndefined()
    }
  })

  it('resolves GMS report names from case_info 名称 or catalog, not 用例N', () => {
    initDeviceSelfCheck()
    expect(__testingResolveCaseDisplayName('gms', 'cts', 1, { 名称: 'CTS指纹测试' })).toBe('CTS指纹测试')
    expect(__testingResolveCaseDisplayName('gms', 'cts', 4)).toBe('CTS安全测试')
    expect(__testingResolveCaseDisplayName('gms', 'gts', 3)).toBe('GTS通信测试')
  })

  it('clamps GMS timeout hours and marks Windows as unsupported', () => {
    expect(normalizeGmsTimeoutHours(undefined)).toBe(8)
    expect(normalizeGmsTimeoutHours(0)).toBe(8)
    expect(normalizeGmsTimeoutHours(3.6)).toBe(4)
    expect(normalizeGmsTimeoutHours(100)).toBe(72)
    expect(isGmsSupportedOnHost('win32')).toBe(false)
    expect(isGmsSupportedOnHost('linux')).toBe(true)
  })

  it('persists GMS timeout hours in settings', () => {
    initDeviceSelfCheck()
    updateSettings({
      ...getSettings(),
      autoTestEnabled: {},
      autoTestPath: {},
      gmsTimeoutHours: 12,
    })
    expect(getSettings().gmsTimeoutHours).toBe(12)
    updateSettings({
      ...getSettings(),
      autoTestEnabled: {},
      autoTestPath: {},
      gmsTimeoutHours: 8,
    })
  })
})
