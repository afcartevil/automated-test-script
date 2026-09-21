/**
 * BFF 崩溃落盘（同步、不依赖 pino）。
 * JS 钩子抓不到 native crash / taskkill / OOM，需配合 bff-watchdog.mjs。
 */
import {
  mkdirSync,
  writeFileSync,
  readFileSync,
  appendFileSync,
  statSync,
  openSync,
  readSync,
  closeSync,
  existsSync,
} from 'fs'
import { homedir, freemem, totalmem } from 'os'
import { join, resolve } from 'path'
import { spawnSync } from 'child_process'

const MAX_CRASH_LOG = 1024 * 1024
const TAIL_BYTES = 8 * 1024

export const EXPECTED_EXIT_KINDS = new Set(['graceful', 'stop-requested'])

export function resolveConsoleHome(env = process.env) {
  const explicit = env.TAHP_CONSOLE_HOME?.trim()
  if (explicit) return resolve(explicit)
  const fromWebUi = env.HERMES_WEB_UI_HOME?.trim() || env.HERMES_WEBUI_STATE_DIR?.trim()
  if (fromWebUi) return resolve(fromWebUi)
  return join(homedir(), '.tahp-console')
}

export function crashLogPaths(env = process.env) {
  const home = resolveConsoleHome(env)
  const logsDir = join(home, 'logs')
  return {
    home,
    logsDir,
    crashLog: join(logsDir, 'crash.log'),
    latestCrash: join(logsDir, 'latest-crash.json'),
    lastExit: join(logsDir, 'last-exit.json'),
    heartbeat: join(logsDir, 'bff-heartbeat.json'),
    stdoutLog: join(home, 'server.log'),
    pinoLog: join(logsDir, 'server.log'),
  }
}

export function serializeUnknown(err) {
  if (err instanceof Error) {
    return {
      name: err.name,
      message: err.message,
      stack: err.stack || '',
      code: err.code,
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

export function tailFile(filePath, maxBytes = TAIL_BYTES) {
  try {
    const size = statSync(filePath).size
    if (size <= 0) return ''
    const fd = openSync(filePath, 'r')
    try {
      const start = Math.max(0, size - maxBytes)
      const len = size - start
      const buf = Buffer.alloc(len)
      readSync(fd, buf, 0, len, start)
      return buf.toString('utf8')
    } finally {
      closeSync(fd)
    }
  } catch {
    return ''
  }
}

export function readJsonFile(filePath) {
  try {
    return JSON.parse(readFileSync(filePath, 'utf8'))
  } catch {
    return null
  }
}

export function writeLastExit(record, env = process.env) {
  const paths = crashLogPaths(env)
  mkdirSync(paths.logsDir, { recursive: true })
  const body = {
    pid: record.pid,
    kind: record.kind,
    ts: record.ts || new Date().toISOString(),
    signal: record.signal,
    note: record.note,
  }
  writeFileSync(paths.lastExit, `${JSON.stringify(body)}\n`, 'utf8')
  return body
}

export function readLastExit(env = process.env) {
  return readJsonFile(crashLogPaths(env).lastExit)
}

export function isExpectedExit(pid, env = process.env) {
  const last = readLastExit(env)
  if (!last || last.pid !== pid) return false
  return EXPECTED_EXIT_KINDS.has(last.kind)
}

export function alreadyLoggedFatal(pid, env = process.env) {
  const last = readLastExit(env)
  return Boolean(last && last.pid === pid && last.kind === 'fatal')
}

function rotateCrashLogIfNeeded(filePath) {
  try {
    const stat = statSync(filePath)
    if (stat.size <= MAX_CRASH_LOG) return
    const keep = Math.floor(MAX_CRASH_LOG / 2)
    const fd = openSync(filePath, 'r')
    const buf = Buffer.alloc(keep)
    readSync(fd, buf, 0, keep, stat.size - keep)
    closeSync(fd)
    writeFileSync(filePath, buf)
  } catch {
    /* first write */
  }
}

export function appendCrashRecord(record, env = process.env) {
  const paths = crashLogPaths(env)
  mkdirSync(paths.logsDir, { recursive: true })
  rotateCrashLogIfNeeded(paths.crashLog)
  const line = JSON.stringify({
    ts: new Date().toISOString(),
    ...record,
  })
  appendFileSync(paths.crashLog, `${line}\n`, 'utf8')
  try {
    appendFileSync(
      paths.stdoutLog,
      `\n[bff-watchdog] ${new Date().toISOString()} ${record.type || 'crash'} pid=${record.pid ?? ''} 详情: ${paths.crashLog}\n`,
      'utf8',
    )
  } catch {
    /* stdout log may not exist yet */
  }
  return line
}

export function collectHostDiagnostics() {
  const host = {
    freemem: freemem(),
    totalmem: totalmem(),
    freememMb: Math.round(freemem() / 1024 / 1024),
    totalmemMb: Math.round(totalmem() / 1024 / 1024),
  }
  if (process.env.VITEST || process.env.TAHP_CRASH_SKIP_HOST === '1') {
    host.skipped = 'light'
    return host
  }
  try {
    if (process.platform === 'win32') {
      const r = spawnSync(
        'powershell.exe',
        [
          '-NoProfile',
          '-NonInteractive',
          '-Command',
          "(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } | Select-Object Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,2)},@{n='UsedGB';e={[math]::Round($_.Used/1GB,2)}} | ConvertTo-Json -Compress)",
        ],
        { encoding: 'utf8', timeout: 4_000, windowsHide: true },
      )
      if (r.status === 0 && r.stdout?.trim()) {
        try {
          host.disks = JSON.parse(r.stdout.trim())
        } catch {
          host.disksRaw = r.stdout.trim().slice(0, 1000)
        }
      } else if (r.error) {
        host.diskError = r.error.message
      }
    } else {
      const r = spawnSync('df', ['-k', '.'], { encoding: 'utf8', timeout: 3_000 })
      if (r.status === 0) host.df = (r.stdout || '').trim().split(/\r?\n/).slice(0, 4)
    }
  } catch (err) {
    host.diskError = err instanceof Error ? err.message : String(err)
  }
  return host
}

/** Windows Application 日志中与 node 相关的近期条目（尽力而为，超时则跳过） */
export function collectWindowsAppErrors(lookbackMinutes = 20) {
  if (process.platform !== 'win32') return null
  if (process.env.VITEST || process.env.TAHP_CRASH_SKIP_HOST === '1') {
    return { skipped: 'light' }
  }
  try {
    const minutes = Math.max(5, Math.min(120, Number(lookbackMinutes) || 20))
    const script = [
      `$start=(Get-Date).AddMinutes(-${minutes})`,
      `$ev=@()`,
      `try {`,
      `  $ev=@(Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=$start} -MaxEvents 40 -ErrorAction SilentlyContinue |`,
      `    Where-Object { $_.ProviderName -match 'Application Error|Windows Error Reporting|Application Hang' -or $_.Message -match 'node\\.exe|tahp-console' } |`,
      `    Select-Object -First 8 @{n='time';e={$_.TimeCreated.ToString('o')}},Id,ProviderName,@{n='message';e={($_.Message -replace '\\s+',' ').Substring(0,[Math]::Min(400,($_.Message -replace '\\s+',' ').Length))}})`,
      `} catch {}`,
      `($ev | ConvertTo-Json -Compress)`,
    ].join('; ')
    const r = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
      encoding: 'utf8',
      timeout: 5_000,
      windowsHide: true,
    })
    if (r.error) return { error: r.error.message }
    if (r.status !== 0) {
      return { error: (r.stderr || r.stdout || 'powershell failed').toString().slice(0, 500) }
    }
    const raw = (r.stdout || '').trim()
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : [parsed]
    } catch {
      return { raw: raw.slice(0, 1000) }
    }
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) }
  }
}

export function writeLatestCrashSummary(record, env = process.env) {
  const paths = crashLogPaths(env)
  mkdirSync(paths.logsDir, { recursive: true })
  const summary = {
    ts: record.ts || new Date().toISOString(),
    pid: record.pid,
    type: record.type,
    detectedBy: record.detectedBy,
    exitCode: record.exitCode ?? null,
    signal: record.signal ?? null,
    note: record.note,
    heartbeat: record.heartbeat,
    host: record.host,
    winEvents: record.winEvents,
    lastExit: record.lastExit,
    crashLog: paths.crashLog,
    serverLog: paths.stdoutLog,
  }
  writeFileSync(paths.latestCrash, `${JSON.stringify(summary, null, 2)}\n`, 'utf8')
  return summary
}

export function collectExitDiagnostics(pid, extra = {}, env = process.env) {
  const paths = crashLogPaths(env)
  return {
    pid,
    type: extra.type || 'watchdog-exit',
    platform: process.platform,
    node: process.version,
    lastExit: readLastExit(env),
    heartbeat: readJsonFile(paths.heartbeat),
    host: collectHostDiagnostics(),
    winEvents: collectWindowsAppErrors(20),
    pinoTail: tailFile(paths.pinoLog),
    stdoutTail: tailFile(paths.stdoutLog),
    ...extra,
  }
}

export function recordUnexpectedExit(pid, extra = {}, env = process.env) {
  if (isExpectedExit(pid, env) || alreadyLoggedFatal(pid, env)) return null
  const record = collectExitDiagnostics(pid, extra, env)
  if (!record.note) {
    record.note = '进程已消失，但没有 graceful/stop-requested 标记。常见原因：原生崩溃、OOM、taskkill /F、或未捕获的 native addon 异常。JS uncaughtException 不会走到。'
  }
  appendCrashRecord(record, env)
  try {
    writeLatestCrashSummary(record, env)
  } catch { /* ignore */ }
  writeLastExit({ pid, kind: 'fatal', ts: record.ts, note: record.type }, env)
  return record
}
