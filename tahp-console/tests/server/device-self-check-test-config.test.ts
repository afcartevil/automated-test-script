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

  it('captures monkey duration for monkey tests', () => {
    const cfg = __testingSnapshotTestConfig('monkey', {})
    expect(cfg.monkeyDuration).toBe('30m')
    expect(cfg.autoRetestEnabled).toBeUndefined()
  })

  it('captures smoke USD skip flag', () => {
    const cfg = __testingSnapshotTestConfig('smoke', {})
    expect(cfg.smokeUsdSkipSpdInfo).toBe(true)
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

  it('formats monkey duration for excel meta rows', () => {
    const rows = formatSelfCheckTestConfigMetaRows({ monkeyDuration: '7d' })
    expect(rows).toEqual([['monkey测试时长', '7d']])
  })
})
