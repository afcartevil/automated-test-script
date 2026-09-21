import { describe, it, expect } from 'vitest'
import {
  createFlashProgressState,
  parseFlashLogLine,
  flashPhaseLabel,
  mergeFlashLogLine,
} from '../../packages/client/src/utils/flash-progress'

describe('flash-progress parser', () => {
  it('tracks tahp prepare logs', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, '[刷机] 开始准备刷机环境…')
    expect(s.progress).toBeGreaterThanOrEqual(5)
    expect(s.phase).toBe('准备刷机')
  })

  it('tracks partition flash progress', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, '[DeviceUpdate][SN] --- 开始执行 fastboot 升级')
    parseFlashLogLine(s, '[DeviceUpdate][SN] --- 刷入分区:boot_a 完成, 耗时: 0:00:02')
    expect(s.partitionDone).toBe(1)
    expect(s.progress).toBeGreaterThan(28)
    expect(s.progress).toBeLessThan(50)
    expect(flashPhaseLabel(s)).toContain('boot_a')
  })

  it('tracks super sparse chunks', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, "[DeviceUpdate][SN] --- Sending sparse 'super' 10/45 (131068 KB) OKAY")
    expect(s.superIndex).toBe(10)
    expect(s.superTotal).toBe(45)
    expect(s.progress).toBeGreaterThan(50)
    expect(s.progress).toBeLessThan(70)
  })

  it('tracks zip copy progress from network cache', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, '[刷机] 开始复制 ZIP 到本地（共 10.67 GiB）: D:\\cache\\rom.zip')
    expect(s.phase).toBe('缓存版本包')
    parseFlashLogLine(s, '[刷机] 复制 ZIP 进度: 45% (4.80 GiB/10.67 GiB)')
    expect(s.progress).toBeGreaterThanOrEqual(7)
    expect(flashPhaseLabel(s)).toContain('45%')
    parseFlashLogLine(s, '[刷机] 复制 ZIP 完成: D:\\cache\\rom.zip')
    expect(s.progress).toBeGreaterThanOrEqual(12)
  })

  it('does not jump to post-flash progress during pre-flash boot wait', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, '[DeviceUpdate][SN] --- 开始执行 fastboot 升级')
    parseFlashLogLine(s, '[DeviceUpdate][SN] --- 等待手机:SN 重启')
    parseFlashLogLine(s, '[DeviceUpdate][SN] --- bootani等待5秒后，再次检查！')
    parseFlashLogLine(
      s,
      "[DeviceUpdate] --- 执行命令：['adb', '-s', 'SN', 'shell', 'getprop sys.boot_completed'] 检查手机状态"
    )
    expect(s.progress).toBeLessThan(30)
    expect(s.phase).toBe('设备准备')
  })

  it('marks completion', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, '[DeviceUpdate][SN] --- 手机:SN Fastboot刷机成功, 开始执行跳过OOBE')
    parseFlashLogLine(s, '[刷机] 刷机进程正常结束')
    parseFlashLogLine(s, '[刷机] 刷机完成，开始跳过 OOBE…')
    parseFlashLogLine(s, '[刷机] 已跳过 OOBE')
    expect(s.progress).toBe(100)
    expect(s.flashSucceeded).toBe(true)
    expect(s.phase).toBe('刷机完成')
  })

  it('tracks T-card zip push and reboot wait', () => {
    const s = createFlashProgressState()
    parseFlashLogLine(s, '[T卡升级] 开始推送 ota.zip -> /sdcard/ota.zip')
    expect(s.phase).toBe('推送 ZIP')
    parseFlashLogLine(s, '[T卡升级] [ 40%] /sdcard/ota.zip')
    expect(s.progress).toBeGreaterThanOrEqual(20)
    parseFlashLogLine(s, '[T卡升级] 推送完成')
    expect(s.progress).toBeGreaterThanOrEqual(42)
    parseFlashLogLine(s, '[T卡升级] 刷机完成，开始 T卡升级…')
    expect(s.progress).toBeLessThan(100)
    parseFlashLogLine(s, '[T卡升级] 完成')
    expect(s.progress).toBe(100)
  })

  it('keeps T-card push progress on a single log line', () => {
    const logs = mergeFlashLogLine(
      ['[T卡升级] 开始推送 ota.zip -> /sdcard/ota.zip'],
      '[T卡升级] [  1%] /sdcard/ota.zip',
    )
    expect(logs).toEqual([
      '[T卡升级] 开始推送 ota.zip -> /sdcard/ota.zip',
      '[T卡升级] [  1%] /sdcard/ota.zip',
    ])
    expect(mergeFlashLogLine(logs, '[T卡升级] [ 37%] /sdcard/ota.zip')).toEqual([
      '[T卡升级] 开始推送 ota.zip -> /sdcard/ota.zip',
      '[T卡升级] [ 37%] /sdcard/ota.zip',
    ])
  })
})
