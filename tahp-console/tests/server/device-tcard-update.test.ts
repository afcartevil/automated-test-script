import { describe, expect, it } from 'vitest'
import {
  consumeAdbOutput,
  centerOfBounds,
  findNodesByResourceId,
  matchZipNode,
  isTcardZipPath,
  matchPackageFileNode,
  parseAdbPushPercent,
  formatAdbPushProgressLine,
  percentFromSizes,
  tcardRemotePath,
  tcardZipQueue,
  isAdbRemoteCreateMissingError,
  isSystemBootCompleted,
} from '../../packages/server/src/services/tahp/device-tcard-update'

const FILE_LIST_XML = `<?xml version='1.0' encoding='UTF-8' ?>
<hierarchy rotation="0">
  <node resource-id="com.transsion.systemupdate:id/ota_local" text="本地升级" bounds="[40,800][1040,920]" />
  <node resource-id="com.transsion.systemupdate:id/file_name" text="other.zip" bounds="[0,200][1080,320]" />
  <node resource-id="com.transsion.systemupdate:id/file_name" text="CM5_OTA_v1000.zip" bounds="[0,320][1080,440]" />
  <node resource-id="com.transsion.systemupdate:id/btn_positive" text="安装" bounds="[200,1600][880,1720]" />
  <node resource-id="com.transsion.systemupdate:id/reboot_now" text="立即重启" bounds="[100,1800][980,1920]" />
</hierarchy>`

describe('tcard update helpers', () => {
  it('only accepts zip paths and maps them to /sdcard', () => {
    expect(isTcardZipPath('D:/rom/ota.zip')).toBe(true)
    expect(isTcardZipPath('D:/rom/scatter.xml')).toBe(false)
    expect(tcardRemotePath('D:/cache/CM5_OTA_v1000.zip')).toBe('/sdcard/CM5_OTA_v1000.zip')
    expect(tcardRemotePath(
      '\\\\10.205.4.40\\sw_version\\CI\\Tcard_X6850-16.3.0.145SP06-OP005PF001AZ_a15.zip',
      '/data/media/0',
    )).toBe('/data/media/0/Tcard_X6850-16.3.0.145SP06-OP005PF001AZ_a15.zip')
    expect(isAdbRemoteCreateMissingError(
      "adb: error: failed to copy '\\\\server\\a.zip' to '/sdcard/a.zip': remote couldn't create file: No such file or directory",
    )).toBe(true)
    expect(isAdbRemoteCreateMissingError('1 file pushed, 0 skipped')).toBe(false)
    expect(isSystemBootCompleted('1')).toBe(true)
    expect(isSystemBootCompleted('1\r\n')).toBe(true)
    expect(isSystemBootCompleted('0')).toBe(false)
    expect(isSystemBootCompleted('')).toBe(false)
    expect(tcardZipQueue({
      zipPath: 'D:/rom/fallback.zip',
      zipPaths: [' D:/rom/a15.zip ', 'D:/rom/a16.zip', 'D:/rom/a15.zip'],
    })).toEqual(['D:/rom/a15.zip', 'D:/rom/a16.zip'])
  })

  it('parses cmd-style adb push progress', () => {
    expect(parseAdbPushPercent('[  7%] /sdcard/ota.zip')).toBe(7)
    expect(parseAdbPushPercent('1 file pushed')).toBeNull()
    expect(formatAdbPushProgressLine(7, '/sdcard/ota.zip')).toBe('[T卡升级] [  7%] /sdcard/ota.zip')
    expect(percentFromSizes(37, 100)).toBe(37)
    expect(percentFromSizes(50, 0)).toBe(0)
  })

  it('splits adb \\r progress frames into separate lines', () => {
    const first = consumeAdbOutput('', '[  1%] /sdcard/ota.zip\r[  2%] /sdcard/ota.zip\r')
    expect(first.lines).toEqual(['[  1%] /sdcard/ota.zip', '[  2%] /sdcard/ota.zip'])
    const second = consumeAdbOutput('[  3%] /sdcard/ota.zip', '\r[  4%] /sdcard/ota.zip')
    expect(second.lines).toEqual(['[  3%] /sdcard/ota.zip'])
    expect(second.rest).toBe('[  4%] /sdcard/ota.zip')
  })

  it('finds system update nodes and matches the package name', () => {
    const local = findNodesByResourceId(FILE_LIST_XML, 'com.transsion.systemupdate:id/ota_local')[0]
    expect(local?.text).toBe('本地升级')
    expect(centerOfBounds(local.bounds)).toEqual({ x: 540, y: 860 })

    const files = findNodesByResourceId(FILE_LIST_XML, 'com.transsion.systemupdate:id/file_name')
    expect(files[0]?.text).toBe('other.zip')
    expect(matchPackageFileNode(files, 'CM5_OTA_v1000.zip')?.text).toBe('CM5_OTA_v1000.zip')
    expect(centerOfBounds(findNodesByResourceId(FILE_LIST_XML, 'com.transsion.systemupdate:id/reboot_now')[0].bounds))
      .toEqual({ x: 540, y: 1860 })
  })

  it('matches zip stem or a non-file_name list item', () => {
    expect(matchPackageFileNode(
      findNodesByResourceId(
        `<node resource-id="com.transsion.systemupdate:id/file_name" text="CM5_OTA_v1000" bounds="[0,0][100,40]" />`,
        'com.transsion.systemupdate:id/file_name',
      ),
      'CM5_OTA_v1000.zip',
    )?.text).toBe('CM5_OTA_v1000')

    const pickerXml = `<node resource-id="com.transsion.systemupdate:id/file_name" text="请选择升级包" bounds="[40,240][1040,360]" />`
    expect(findNodesByResourceId(pickerXml, 'com.transsion.systemupdate:id/file_name')[0]?.text).toBe('请选择升级包')
    expect(matchZipNode(pickerXml, 'CM5_OTA_v1000.zip')).toBeNull()
    expect(matchZipNode(
      `<node resource-id="android:id/title" text="CM5_OTA_v1000.zip" bounds="[0,320][1080,440]" />`,
      'CM5_OTA_v1000.zip',
    )?.text).toBe('CM5_OTA_v1000.zip')
  })
})
