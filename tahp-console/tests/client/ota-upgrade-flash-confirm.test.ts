import { describe, expect, it } from 'vitest'
import {
  OTA_UPGRADE_FLASH_CONFIRM,
  hasContinuousOtaPackagePath,
  isOtaStartBusyForDevice,
  otaConfirmSteps,
  missingTcardZipHint,
  pickPreferredTcardZip,
  resolveReleaseUpgradeEnabledOnTypeChange,
  resolveReleaseUpgradeQueue,
  tcardBaselineVersionError,
} from '../../packages/client/src/components/tahp/self-check/self-check-utils'
import type { AndroidUpgradeStep } from '../../packages/client/src/api/tahp/device-self-check'

describe('ota upgrade flash confirm copy', () => {
  it('lists automatic pretest flow, battery and usbdebug checks with confirm/cancel actions', () => {
    expect(OTA_UPGRADE_FLASH_CONFIRM.title).toBe('开始连续 OTA')
    expect(OTA_UPGRADE_FLASH_CONFIRM.lines).toEqual([
      '1.勾选 OEM 解锁后：user 版本先刷 UD；能 adb root 的版本不刷机',
      '2.手机电量大于30%',
      '3.只补未完成的 OEM 解锁和 usbdebug 标志位',
    ])
    expect(OTA_UPGRADE_FLASH_CONFIRM.positiveText).toBe('确认')
    expect(OTA_UPGRADE_FLASH_CONFIRM.negativeText).toBe('取消')
  })

  it('blocks only the device that is already starting continuous OTA', () => {
    const busy = ['device-a']
    expect(isOtaStartBusyForDevice('device-a', busy)).toBe(true)
    expect(isOtaStartBusyForDevice('device-b', busy)).toBe(false)
    expect(isOtaStartBusyForDevice('device-b', [])).toBe(false)
  })

  it('requires a resolved package path before continuous OTA can start', () => {
    expect(hasContinuousOtaPackagePath(null)).toBe(false)
    expect(hasContinuousOtaPackagePath({
      steps: [{ selected: true, available: false, needsTransfer: true, packagePath: '' }],
    })).toBe(false)
    expect(hasContinuousOtaPackagePath({
      steps: [{ selected: true, available: true, needsTransfer: false, packagePath: '\\\\cq\\a14.zip' }],
    })).toBe(true)
  })

  it('keeps pretest steps and drops the upgrade when only pretest is selected', () => {
    expect(otaConfirmSteps({
      pretestOnly: true,
      pretestSteps: [
        '检查 adb root：user 版本刷 UD，已 root 则跳过',
        '检查 OEM 解锁，未完成则解锁',
        '检查 usbdebug，不是 1 则写入',
      ],
      upgradeSteps: ['device_update 刷入 Android 14'],
    })).toEqual([
      '检查 adb root：user 版本刷 UD，已 root 则跳过',
      '检查 OEM 解锁，未完成则解锁',
      '检查 usbdebug，不是 1 则写入',
    ])
    expect(otaConfirmSteps({
      pretestOnly: false,
      pretestSteps: ['检查 OEM 解锁，未完成则解锁'],
      upgradeSteps: ['T卡升级到 Android 15'],
    })).toEqual(['检查 OEM 解锁，未完成则解锁', 'T卡升级到 Android 15'])
  })
})

describe('release upgrade checkbox when switching test type', () => {
  it('forces continuous upgrade on while ota_upgrade is selected', () => {
    const next = resolveReleaseUpgradeEnabledOnTypeChange({
      testType: 'ota_upgrade',
      previousTestType: 'week',
      currentEnabled: false,
      enabledBeforeOta: false,
    })
    expect(next.enabled).toBe(true)
    expect(next.enabledBeforeOta).toBe(false)
  })

  it('does not leave continuous upgrade checked after leaving ota_upgrade', () => {
    const entered = resolveReleaseUpgradeEnabledOnTypeChange({
      testType: 'ota_upgrade',
      previousTestType: 'week',
      currentEnabled: false,
      enabledBeforeOta: false,
    })
    const left = resolveReleaseUpgradeEnabledOnTypeChange({
      testType: 'week',
      previousTestType: 'ota_upgrade',
      currentEnabled: entered.enabled,
      enabledBeforeOta: entered.enabledBeforeOta,
    })
    expect(left.enabled).toBe(false)
  })

  it('restores a previously checked continuous upgrade after leaving ota_upgrade', () => {
    const entered = resolveReleaseUpgradeEnabledOnTypeChange({
      testType: 'ota_upgrade',
      previousTestType: 'str4',
      currentEnabled: true,
      enabledBeforeOta: false,
    })
    const left = resolveReleaseUpgradeEnabledOnTypeChange({
      testType: 'str4',
      previousTestType: 'ota_upgrade',
      currentEnabled: entered.enabled,
      enabledBeforeOta: entered.enabledBeforeOta,
    })
    expect(left.enabled).toBe(true)
  })
})

describe('preferred Tcard OTA zip', () => {
  it('picks Tcard_ *_a15.zip for A15 to A16 and ignores incremental packages', () => {
    expect(pickPreferredTcardZip([
      '\\\\cq\\Open\\X6885-16.3.0.140SP17-OP007PF001AZ-16.3.0.145SP08-OP004PF001AZ_20260826235808.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
    ], 15)).toBe('\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip')
  })

  it('does not fall back to unsuffixed Tcard_ zip when the matching _aNN package is absent', () => {
    expect(pickPreferredTcardZip([
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a14.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
    ], 15)).toBe('')
    expect(missingTcardZipHint(15)).toBe('未找到T卡包（需 Tcard_*_a15.zip）')
  })

  it('picks unsuffixed Tcard_*-15 zip for A14 to A15 and ignores _a14', () => {
    expect(pickPreferredTcardZip([
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ_a14.zip',
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ.zip',
      'D:\\Open\\Tcard_X6850-16.3.0.145SP06-OP001PF001AZ.zip',
    ], 14)).toBe('D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ.zip')
    expect(pickPreferredTcardZip([
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ_a14.zip',
    ], 14)).toBe('')
    expect(missingTcardZipHint(14)).toBe('未找到T卡包（需 Tcard_*-15.*.zip）')
  })
})

function makeStep(partial: Partial<AndroidUpgradeStep> & { androidVersion: number }): AndroidUpgradeStep {
  return {
    androidLabel: `Android ${partial.androidVersion}`,
    releaseVersionName: `1.0.0.${partial.androidVersion}`,
    releaseFolder: `X-${partial.androidVersion}`,
    channel: 'USER',
    packagePath: '',
    tcardZips: [],
    cqTargetPath: '',
    needsTransfer: false,
    available: true,
    selected: false,
    ...partial,
  }
}

const FULL_14 = '\\\\cq\\Open\\X6850-14.0.0.100(SP01).zip'
const FULL_15 = '\\\\cq\\Open\\X6850-15.1.2.180SP05-OP001PF001AZ.zip'
const TCARD_15 = '\\\\cq\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ.zip'
const TCARD_16_A15 = '\\\\cq\\Open\\Tcard_X6850-16.3.0.145SP06-OP001PF001AZ_a15.zip'

function makePlanSteps(): AndroidUpgradeStep[] {
  return [
    makeStep({ androidVersion: 14, fullZip: FULL_14, packagePath: FULL_14, selected: true }),
    makeStep({ androidVersion: 15, fullZip: FULL_15, tcardZips: [TCARD_15], selected: true }),
    makeStep({ androidVersion: 16, tcardZips: [TCARD_16_A15], selected: true }),
  ]
}

describe('resolveReleaseUpgradeQueue', () => {
  it('全勾选：计划最低版本为基线，device_update 刷整包后 T卡链（原行为，策略被忽略）', () => {
    const result = resolveReleaseUpgradeQueue(makePlanSteps(), 'tcard')
    expect(result.ok).toBe(true)
    expect(result.flashPath).toBe(FULL_14)
    expect(result.tcardPaths).toEqual([TCARD_15, TCARD_16_A15])
    expect(result.expectFromAndroid).toBeUndefined()
    expect(result.assignments.map(a => a.packagePath)).toEqual([FULL_14, TCARD_15, TCARD_16_A15])
  })

  it('未勾最低版本 + 默认T卡升级：基线走T卡、不刷机，expectFromAndroid 取计划上一档', () => {
    const steps = makePlanSteps()
    steps[0]!.selected = false
    const result = resolveReleaseUpgradeQueue(steps, 'tcard')
    expect(result.ok).toBe(true)
    expect(result.flashPath).toBe('')
    expect(result.tcardPaths).toEqual([TCARD_15, TCARD_16_A15])
    expect(result.expectFromAndroid).toBe(14)
    expect(result.assignments.map(a => a.packagePath)).toEqual([TCARD_15, TCARD_16_A15])
  })

  it('未勾最低版本 + 手动 device_update：基线上移刷整包（原流程）', () => {
    const steps = makePlanSteps()
    steps[0]!.selected = false
    const result = resolveReleaseUpgradeQueue(steps, 'device_update')
    expect(result.ok).toBe(true)
    expect(result.flashPath).toBe(FULL_15)
    expect(result.tcardPaths).toEqual([TCARD_16_A15])
    expect(result.expectFromAndroid).toBeUndefined()
  })

  it('仅勾最高版本：T卡基线要求手机为其计划上一档', () => {
    const steps = makePlanSteps()
    steps[0]!.selected = false
    steps[1]!.selected = false
    const result = resolveReleaseUpgradeQueue(steps, 'tcard')
    expect(result.ok).toBe(true)
    expect(result.flashPath).toBe('')
    expect(result.tcardPaths).toEqual([TCARD_16_A15])
    expect(result.expectFromAndroid).toBe(15)
  })

  it('T卡基线缺包：降级基线步并报对应上一档的T卡包提示', () => {
    const steps = makePlanSteps()
    steps[0]!.selected = false
    steps[1]!.tcardZips = ['\\\\cq\\Open\\Tcard_X6850-16.3.0.145SP06_a15.zip']
    const result = resolveReleaseUpgradeQueue(steps, 'tcard')
    expect(result.ok).toBe(false)
    expect(result.downgrade?.step.androidVersion).toBe(15)
    expect(result.downgrade?.previousAndroid).toBe(14)
    expect(result.error).toContain('Tcard_*-15.*')
  })

  it('链中后续版本缺包：降级该步并保持通用报错', () => {
    const steps = makePlanSteps()
    steps[2]!.tcardZips = ['\\\\cq\\Open\\Tcard_X6850-16.3.0.145SP06_a14.zip']
    const result = resolveReleaseUpgradeQueue(steps, 'device_update')
    expect(result.ok).toBe(false)
    expect(result.downgrade?.step.androidVersion).toBe(16)
    expect(result.downgrade?.previousAndroid).toBe(15)
    expect(result.error).toContain('device_update 整包')
  })

  it('基线无整包且选手动 device_update：报错缺整包', () => {
    const steps = makePlanSteps()
    steps[0]!.selected = false
    steps[1]!.fullZip = undefined
    const result = resolveReleaseUpgradeQueue(steps, 'device_update')
    expect(result.ok).toBe(false)
    expect(result.error).toContain('device_update 整包')
  })

  it('空勾选与基线待回传：直接失败', () => {
    expect(resolveReleaseUpgradeQueue(makePlanSteps().map(s => ({ ...s, selected: false })), 'tcard').error)
      .toContain('至少选择一个')
    const steps = makePlanSteps()
    steps[0]!.needsTransfer = true
    expect(resolveReleaseUpgradeQueue(steps, 'tcard').error).toContain('传回重庆')
  })
})

describe('tcardBaselineVersionError', () => {
  it('手机当前版本与基线上一档匹配时放行', () => {
    expect(tcardBaselineVersionError('14', 14)).toBeUndefined()
    expect(tcardBaselineVersionError('14.0', 14)).toBeUndefined()
    expect(tcardBaselineVersionError(' 15 ', 15)).toBeUndefined()
  })

  it('版本不匹配时提示改用 device_update 或调整勾选', () => {
    const error = tcardBaselineVersionError('13', 14)
    expect(error).toContain('Android 13')
    expect(error).toContain('Android 14')
    expect(error).toContain('device_update')
  })

  it('读不到版本号时按未知版本拦截', () => {
    expect(tcardBaselineVersionError('', 14)).toContain('未知 Android 版本')
  })
})


