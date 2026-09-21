import { mkdtempSync, writeFileSync, mkdirSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  alreadyLoggedFatal,
  appendCrashRecord,
  collectExitDiagnostics,
  crashLogPaths,
  isExpectedExit,
  recordUnexpectedExit,
  serializeUnknown,
  tailFile,
  writeLastExit,
} from '../../scripts/lib/crash-log.mjs'

describe('crash-log', () => {
  const dirs: string[] = []

  function envFor() {
    const home = mkdtempSync(join(tmpdir(), 'tahp-crash-'))
    dirs.push(home)
    mkdirSync(join(home, 'logs'), { recursive: true })
    return { TAHP_CONSOLE_HOME: home }
  }

  afterEach(() => {
    for (const dir of dirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('serializeUnknown keeps Error stack', () => {
    const err = new Error('boom')
    const out = serializeUnknown(err)
    expect(out.message).toBe('boom')
    expect(out.stack).toContain('boom')
    expect(serializeUnknown('x')).toEqual({ message: 'x' })
  })

  it('writeLastExit + isExpectedExit matches pid and kind', () => {
    const env = envFor()
    writeLastExit({ pid: 42, kind: 'graceful' }, env)
    expect(isExpectedExit(42, env)).toBe(true)
    expect(isExpectedExit(43, env)).toBe(false)
    writeLastExit({ pid: 42, kind: 'running' }, env)
    expect(isExpectedExit(42, env)).toBe(false)
    writeLastExit({ pid: 42, kind: 'stop-requested' }, env)
    expect(isExpectedExit(42, env)).toBe(true)
  })

  it('recordUnexpectedExit writes crash.log, latest-crash.json, and skips expected pid', () => {
    const env = envFor()
    const paths = crashLogPaths(env)
    writeFileSync(paths.pinoLog, 'last pino line\n')
    writeFileSync(paths.stdoutLog, 'stdout leftover\n')

    writeLastExit({ pid: 9, kind: 'stop-requested' }, env)
    expect(recordUnexpectedExit(9, { type: 'watchdog-exit' }, env)).toBeNull()

    const rec = recordUnexpectedExit(88, { type: 'supervisor-exit', detectedBy: 'test', exitCode: 1, signal: null }, env)
    expect(rec?.pid).toBe(88)
    expect(rec?.exitCode).toBe(1)
    expect(rec?.host?.totalmemMb).toBeGreaterThan(0)
    expect(rec?.pinoTail).toContain('last pino line')
    const crash = readFileSync(paths.crashLog, 'utf8')
    expect(crash).toContain('"type":"supervisor-exit"')
    expect(crash).toContain('"pid":88')
    const latest = JSON.parse(readFileSync(paths.latestCrash, 'utf8'))
    expect(latest.exitCode).toBe(1)
    expect(latest.type).toBe('supervisor-exit')
    expect(alreadyLoggedFatal(88, env)).toBe(true)
    expect(recordUnexpectedExit(88, { type: 'watchdog-exit' }, env)).toBeNull()
  })

  it('appendCrashRecord and tailFile round-trip', () => {
    const env = envFor()
    const paths = crashLogPaths(env)
    appendCrashRecord({ type: 'uncaughtException', pid: 1, error: { message: 'x' } }, env)
    expect(tailFile(paths.crashLog)).toContain('uncaughtException')
    expect(collectExitDiagnostics(1, { type: 'watchdog-exit' }, env).lastExit).toBeNull()
  })
})
