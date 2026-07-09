import { describe, expect, it } from 'vitest'
import {
  buildTooltip,
  getConsoleHome,
  getTrayPidFile,
  isProcessRunning,
  readPidFile,
  resolveConsoleUrl,
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
    expect(buildTooltip({ running: true, pid: 1234 }, 8650)).toContain('运行中')
    expect(buildTooltip({ running: true, pid: 1234 }, 8650)).toContain('1234')
    expect(buildTooltip({ running: false, pid: null }, 8650)).toContain('已停止')
  })

  it('readPidFile parses integer pid', () => {
    expect(readPidFile('/nonexistent')).toBeNull()
  })
})
