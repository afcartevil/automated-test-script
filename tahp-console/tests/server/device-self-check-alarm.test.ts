import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
  resolveStartModules,
  normalizeAlarmToolDir,
  normalizeAlarmSleep,
  normalizeAlarmReboot,
  normalizeAlarmShutdown,
  DEFAULT_ALARM_TOOL_DIR,
  DEFAULT_ALARM_SLEEP,
  DEFAULT_ALARM_REBOOT,
  DEFAULT_ALARM_SHUTDOWN,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check alarm catalog', () => {
  it('loads 休眠唤醒-重启测试 catalog with three mutually exclusive modules', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(item => item.testType === 'alarm')
    expect(group?.label).toBe('休眠唤醒-重启测试')
    expect(group?.modules).toHaveLength(3)
    expect(group?.modules.map(m => m.module)).toEqual(['sleep', 'reboot', 'shutdown'])
    expect(group?.modules.map(m => m.moduleLabel)).toEqual(['休眠唤醒', '重启测试', '关机测试'])
    for (const mod of group?.modules ?? []) {
      expect(mod.cases).toHaveLength(1)
      expect(mod.cases[0]?.automationMode).toBe('full')
    }

    const typeOrder = getAllCaseCatalogs().map(item => item.testType)
    expect(typeOrder.indexOf('ota_upgrade')).toBeLessThan(typeOrder.indexOf('alarm'))
    expect(typeOrder.indexOf('alarm')).toBeLessThan(typeOrder.indexOf('gms'))

    const detail = getCaseCatalogDetail('alarm')
    expect(detail).toHaveLength(3)
    expect(detail.map(item => item.key)).toEqual(['alarm/sleep/1', 'alarm/reboot/1', 'alarm/shutdown/1'])
  })

  it('resolveStartModules: alarm 缺省仅跑 sleep', () => {
    expect(resolveStartModules('alarm')).toEqual(['sleep'])
    expect(resolveStartModules('alarm', null)).toEqual(['sleep'])
    expect(resolveStartModules('alarm', [])).toEqual(['sleep'])
  })

  it('resolveStartModules: alarm 允许单选任一模式', () => {
    expect(resolveStartModules('alarm', ['reboot'])).toEqual(['reboot'])
    expect(resolveStartModules('alarm', ['shutdown'])).toEqual(['shutdown'])
  })

  it('resolveStartModules: alarm 多选或无效模块抛错', () => {
    expect(() => resolveStartModules('alarm', ['sleep', 'reboot'])).toThrow('互斥')
    expect(() => resolveStartModules('alarm', ['sleep', 'shutdown'])).toThrow('互斥')
    expect(() => resolveStartModules('alarm', ['nonexistent'])).toThrow('有效的测试模块')
  })
})

describe('alarm settings normalize', () => {
  it('normalizeAlarmToolDir: 空值回退默认目录', () => {
    expect(normalizeAlarmToolDir(undefined)).toBe(DEFAULT_ALARM_TOOL_DIR)
    expect(normalizeAlarmToolDir('')).toBe(DEFAULT_ALARM_TOOL_DIR)
    expect(normalizeAlarmToolDir('   ')).toBe(DEFAULT_ALARM_TOOL_DIR)
    expect(normalizeAlarmToolDir(' D:\\rd_tool\\alarm_v2.1.029 ')).toBe('D:\\rd_tool\\alarm_v2.1.029')
  })

  it('normalizeAlarmSleep: 缺省/非法值回退，合法值保留并取整', () => {
    expect(normalizeAlarmSleep(undefined)).toEqual(DEFAULT_ALARM_SLEEP)
    expect(normalizeAlarmSleep(null)).toEqual(DEFAULT_ALARM_SLEEP)
    expect(normalizeAlarmSleep({ loops: 0, sleepTimes: -5 })).toEqual(DEFAULT_ALARM_SLEEP)
    expect(normalizeAlarmSleep({ loops: 500, sleepTimes: 120 })).toEqual({ loops: 500, sleepTimes: 120 })
    expect(normalizeAlarmSleep({ loops: 10.6, sleepTimes: 30.4 })).toEqual({ loops: 11, sleepTimes: 30 })
  })

  it('normalizeAlarmReboot: 缺省/非法值回退', () => {
    expect(normalizeAlarmReboot(undefined)).toEqual(DEFAULT_ALARM_REBOOT)
    expect(normalizeAlarmReboot({ loops: Number.NaN })).toEqual(DEFAULT_ALARM_REBOOT)
    expect(normalizeAlarmReboot({ loops: 200, poweronTime: 180 })).toEqual({ loops: 200, poweronTime: 180 })
  })

  it('normalizeAlarmShutdown: 缺省/非法值回退', () => {
    expect(normalizeAlarmShutdown(undefined)).toEqual(DEFAULT_ALARM_SHUTDOWN)
    expect(normalizeAlarmShutdown({ loops: 0 })).toEqual(DEFAULT_ALARM_SHUTDOWN)
    expect(normalizeAlarmShutdown({ loops: 100, poweronTime: 60, shutdownTime: 240 })).toEqual({
      loops: 100,
      poweronTime: 60,
      shutdownTime: 240,
    })
  })
})
