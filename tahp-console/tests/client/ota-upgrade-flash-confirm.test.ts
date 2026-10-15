import { describe, expect, it } from 'vitest'
import {
  OTA_UPGRADE_FLASH_CONFIRM,
  hasContinuousOtaPackagePath,
  otaConfirmSteps,
  missingTcardZipHint,
  pickPreferredTcardZip,
  resolveReleaseUpgradeEnabledOnTypeChange,
} from '../../packages/client/src/components/tahp/self-check/self-check-utils'

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


