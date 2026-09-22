import { describe, expect, it } from 'vitest'
import { OTA_UPGRADE_FLASH_CONFIRM } from '../../packages/client/src/components/tahp/self-check/self-check-utils'

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
})
