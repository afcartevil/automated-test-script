import { describe, expect, it } from 'vitest'
import {
  OTA_UPGRADE_FLASH_CONFIRM,
  OTA_UPGRADE_SOP,
  pickPreferredTcardZip,
  resolveReleaseUpgradeEnabledOnTypeChange,
} from '../../packages/client/src/components/tahp/self-check/self-check-utils'

describe('ota upgrade flash confirm copy', () => {
  it('lists OEM unlock, battery and usbdebug checks with confirm/cancel actions', () => {
    expect(OTA_UPGRADE_FLASH_CONFIRM.title).toBe('开始刷机')
    expect(OTA_UPGRADE_FLASH_CONFIRM.lines).toEqual([
      '1.请确保手机已完成OEM解锁',
      '2.手机电量大于30%',
      '3.AP NV参数的usbdebug标志位已写为1',
    ])
    expect(OTA_UPGRADE_FLASH_CONFIRM.positiveText).toBe('确认')
    expect(OTA_UPGRADE_FLASH_CONFIRM.negativeText).toBe('取消')
  })

  it('points to the official continuous OTA SOP document', () => {
    expect(OTA_UPGRADE_SOP.url).toBe('https://transsioner.feishu.cn/docx/KPDTdp4UhovtfUxHJHocIb0Knjc')
    expect(OTA_UPGRADE_SOP.label).toContain('SOP')
    expect(OTA_UPGRADE_SOP.inlineLabel).toBe('前置操作')
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
  })
})


