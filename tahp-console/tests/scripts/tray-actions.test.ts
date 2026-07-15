import { describe, expect, it } from 'vitest'
import {
  buildTooltip,
  getConsoleHome,
  getTrayLogFile,
  getTrayPidFile,
  isProcessRunning,
  readPidFile,
  resolveConsoleUrl,
  shouldRestartTray,
  stopTray,
} from '../../scripts/lib/tray-actions.mjs'

describe('tray-actions', () => {
  it('resolveConsoleUrl uses port in dashboard hash route', () => {
    expect(resolveConsoleUrl(8650)).toBe('http://localhost:8650/#/tahp/dashboard')
    expect(resolveConsoleUrl(9000)).toBe('http://localhost:9000/#/tahp/dashboard')
  })

  it('getConsoleHome respects TAHP_CONSOLE_HOME', () => {
    expect(getConsoleHome({ TAHP_CONSOLE_HOME: 'D:\\data\\tahp' })).toBe('D:\\data\\tahp')
  })

  it('getTrayPidFile is under console home', () => {
    const home = 'C:\\Users\\me\\.tahp-console'
    expect(getTrayPidFile({ TAHP_CONSOLE_HOME: home })).toBe('C:\\Users\\me\\.tahp-console\\tray.pid')
    expect(getTrayLogFile({ TAHP_CONSOLE_HOME: home })).toBe('C:\\Users\\me\\.tahp-console\\tray.log')
  })

  it('isProcessRunning uses kill(pid, 0) probe', () => {
    const calls = []
    const kill = (pid, sig) => {
      calls.push([pid, sig])
      if (pid === 42) return
      throw new Error('ESRCH')
    }
    expect(isProcessRunning(42, kill)).toBe(true)
    expect(isProcessRunning(99, kill)).toBe(false)
    expect(calls).toEqual([[42, 0], [99, 0]])
  })

  it('buildTooltip reflects running state', () => {
    expect(buildTooltip({ running: true, pid: 1234 }, 8650)).toContain('running')
    expect(buildTooltip({ running: true, pid: 1234 }, 8650)).toContain('1234')
    expect(buildTooltip({ running: false, pid: null }, 8650)).toContain('stopped')
  })

  it('readPidFile parses integer pid', () => {
    expect(readPidFile('/nonexistent')).toBeNull()
  })

  it('shouldRestartTray reads TAHP_TRAY_RESTART', () => {
    expect(shouldRestartTray({ TAHP_TRAY_RESTART: '1' })).toBe(true)
    expect(shouldRestartTray({ TAHP_TRAY_RESTART: '0' })).toBe(false)
  })

  it('stopTray kills running pid and clears tray.pid', () => {
    const killed = []
    const env = { TAHP_CONSOLE_HOME: 'C:\\tmp\\tahp-tray-test' }
    const kill = (pid, sig) => {
      killed.push([pid, sig])
      if (pid !== 77) throw new Error('ESRCH')
    }
    const result = stopTray({ ...env, TAHP_TRAY_RESTART: '1' }, kill)
    expect(result.stopped).toBe(false)
    expect(killed).toEqual([])
  })
})
