import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  __testingSnapshotTestConfig,
  updateSettings,
} from '../../packages/server/src/services/tahp/device-self-check'
import { formatSelfCheckTestConfigMetaRows } from '../../packages/server/src/services/tahp/self-check-reports'

describe('device self-check testConfig snapshot', () => {
  beforeEach(() => {
    updateSettings({
      autoTestEnabled: {},
      autoTestPath: {},
      monkeyDuration: '30m',
      smokeUsdSkipSpdInfo: true,
      gmsTradefedPath: { cts: '/opt/cts-tradefed' },
      autoRetestEnabled: { str4: true },
      autoRetestCount: { str4: 2 },
    })
  })

  afterEach(() => {
    updateSettings({
      autoTestEnabled: {},
      autoTestPath: {},
      monkeyDuration: '7d',
      smokeUsdSkipSpdInfo: false,
    })
  })

  it('captures kernel feature code_dir', () => {
    updateSettings({
      autoTestEnabled: {},
      autoTestPath: {},
      kernelFeatureCodeDir: 'Z:\\alps',
    })
    const cfg = __testingSnapshotTestConfig('kernel_feature', {})
    expect(cfg.kernelFeatureCodeDir).toBe('Z:\\alps')
    expect(formatSelfCheckTestConfigMetaRows(cfg).some(r => r[0] === '内核源码路径 (code_dir)')).toBe(true)
  })

  it('captures monkey duration for monkey tests', () => {
    const cfg = __testingSnapshotTestConfig('monkey', {})
    expect(cfg.monkeyDuration).toBe('30m')
    expect(cfg.autoRetestEnabled).toBeUndefined()
  })

  it('captures smoke USD skip flag', () => {
    const cfg = __testingSnapshotTestConfig('smoke', {})
    expect(cfg.smokeUsdSkipSpdInfo).toBe(true)
  })

  it('captures GMS timeout hours', () => {
    updateSettings({
      autoTestEnabled: {},
      autoTestPath: {},
      gmsTimeoutHours: 10,
      gmsTradefedPath: { cts: '/opt/cts-tradefed' },
    })
    const cfg = __testingSnapshotTestConfig('gms', {})
    expect(cfg.gmsTimeoutHours).toBe(10)
    expect(formatSelfCheckTestConfigMetaRows(cfg).some(r => r[0] === 'GMS 用例超时')).toBe(true)
  })

  it('does not snapshot auto-retest for ota_upgrade', () => {
    const cfg = __testingSnapshotTestConfig('ota_upgrade', {})
    expect(cfg.autoRetestEnabled).toBeUndefined()
    expect(cfg.autoRetestCount).toBeUndefined()
  })

  it('captures auto retest for str4', () => {
    const cfg = __testingSnapshotTestConfig('str4', {})
    expect(cfg.autoRetestEnabled).toBe(true)
    expect(cfg.autoRetestCount).toBe(2)
  })

  it('captures flash and custom case selection', () => {
    const cfg = __testingSnapshotTestConfig('custom', {
      selectedCases: ['smoke/usd/1', 'week/tdd/2'],
      flashOptions: {
        pkgPath: 'D:\\rom\\daily.zip',
        stageVersion: 'STR4A',
      },
    })
    expect(cfg.selectedCases).toEqual(['smoke/usd/1', 'week/tdd/2'])
    expect(cfg.flashBeforeTest?.pkgPath).toBe('D:\\rom\\daily.zip')
    expect(formatSelfCheckTestConfigMetaRows(cfg).some(r => r[0] === 'monkey测试时长')).toBe(false)
    expect(formatSelfCheckTestConfigMetaRows(cfg).some(r => r[0] === '测试前刷机')).toBe(true)
  })

  it('captures T-card zip upgrade', () => {
    const cfg = __testingSnapshotTestConfig('str4', {
      tcardOptions: { zipPath: 'D:\\rom\\ota.zip' },
    })
    expect(cfg.tcardBeforeTest).toEqual({ enabled: true, zipPath: 'D:\\rom\\ota.zip' })
    expect(formatSelfCheckTestConfigMetaRows(cfg).some(r => r[0] === 'T卡升级 ZIP')).toBe(true)
  })

  it('captures sequential T-card zip upgrades', () => {
    const cfg = __testingSnapshotTestConfig('str4', {
      tcardOptions: {
        zipPath: 'D:\\rom\\a15.zip',
        zipPaths: ['D:\\rom\\a15.zip', 'D:\\rom\\a16.zip'],
      },
    })
    expect(cfg.tcardBeforeTest?.zipPaths).toEqual(['D:\\rom\\a15.zip', 'D:\\rom\\a16.zip'])
    expect(formatSelfCheckTestConfigMetaRows(cfg).map((row) => row[0])).toContain('T卡升级 ZIP 2')
  })

  it('formats monkey duration for excel meta rows', () => {
    const rows = formatSelfCheckTestConfigMetaRows({ monkeyDuration: '7d' })
    expect(rows).toEqual([['monkey测试时长', '7d']])
  })
})
