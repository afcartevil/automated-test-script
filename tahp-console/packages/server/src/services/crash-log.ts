/**
 * BFF 进程内崩溃落盘：writeFileSync，不依赖 pino 刷新。
 * native crash / SIGKILL 仍需 scripts/lib/bff-watchdog.mjs。
 */
import { appendFileSync, mkdirSync, writeFileSync } from 'fs'
import { join } from 'path'
import { getTahpConsoleHome } from '../config'
import { logger } from './logger'

const HEARTBEAT_MS = 15_000

let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let installed = false

function logsDir(): string {
  return join(getTahpConsoleHome(), 'logs')
}

function writeJson(fileName: string, body: unknown): void {
  mkdirSync(logsDir(), { recursive: true })
  writeFileSync(join(logsDir(), fileName), `${JSON.stringify(body)}\n`, 'utf8')
}

export function serializeUnknown(err: unknown): { name?: string; message: string; stack?: string; code?: unknown } {
  if (err instanceof Error) {
    return {
      name: err.name,
      message: err.message,
      stack: err.stack || '',
      code: (err as NodeJS.ErrnoException).code,
    }
  }
  if (err == null) return { message: String(err) }
  if (typeof err === 'string') return { message: err }
  try {
    return { message: JSON.stringify(err) }
  } catch {
    return { message: String(err) }
  }
}

export function forceStdioBlocking(): void {
  for (const stream of [process.stdout, process.stderr]) {
    try {
      const handle = (stream as NodeJS.WriteStream & { _handle?: { setBlocking?: (v: boolean) => void } })._handle
      if (handle && typeof handle.setBlocking === 'function' && !stream.isTTY) {
        handle.setBlocking(true)
      }
    } catch {
      /* ignore */
    }
  }
}

export function writeHeartbeat(): void {
  writeJson('bff-heartbeat.json', {
    pid: process.pid,
    ts: new Date().toISOString(),
    uptimeSec: Math.round(process.uptime()),
    rss: process.memoryUsage().rss,
  })
}

export function markBffExit(
  kind: 'running' | 'graceful' | 'stop-requested' | 'fatal',
  extra?: { signal?: string; note?: string },
): void {
  writeJson('last-exit.json', {
    pid: process.pid,
    kind,
    ts: new Date().toISOString(),
    signal: extra?.signal,
    note: extra?.note,
  })
}

export function appendCrashLine(record: Record<string, unknown>): void {
  mkdirSync(logsDir(), { recursive: true })
  const line = JSON.stringify({ ts: new Date().toISOString(), ...record })
  appendFileSync(join(logsDir(), 'crash.log'), `${line}\n`, 'utf8')
}

export function recordFatal(type: string, err: unknown, extra?: Record<string, unknown>): void {
  appendCrashLine({
    type,
    pid: process.pid,
    ppid: process.ppid,
    platform: process.platform,
    node: process.version,
    error: serializeUnknown(err),
    ...extra,
  })
  if (type !== 'unhandledRejection') {
    markBffExit('fatal', { note: type })
  }
}

export function installBffDiagnostics(): void {
  if (installed) return
  installed = true
  forceStdioBlocking()
  markBffExit('running')
  writeHeartbeat()
  heartbeatTimer = setInterval(() => {
    try { writeHeartbeat() } catch { /* ignore */ }
  }, HEARTBEAT_MS)
  heartbeatTimer.unref()

  process.on('uncaughtException', (err) => {
    try { recordFatal('uncaughtException', err) } catch { /* last resort */ }
    try { logger.fatal({ err }, 'Uncaught exception') } catch { /* ignore */ }
    console.error('FATAL: Uncaught exception')
    console.error(err)
    process.exit(1)
  })

  process.on('unhandledRejection', (reason) => {
    try { recordFatal('unhandledRejection', reason) } catch { /* ignore */ }
    try { logger.error({ err: reason }, 'Unhandled rejection') } catch { /* ignore */ }
    console.error('Unhandled rejection')
    console.error(reason)
  })
}

export function stopBffHeartbeat(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}
