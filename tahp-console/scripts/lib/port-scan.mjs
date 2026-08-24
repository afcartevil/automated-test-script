/**
 * Cross-platform TCP listen-port PID scan (Windows netstat / Unix ss|lsof|netstat).
 * Used by tahp-console CLI and scripts/lib/free-port.mjs.
 */
import { execFileSync } from 'child_process'

const DEFAULT_PORT_SCAN_TIMEOUT_MS = 4000
const DEFAULT_TASKKILL_TIMEOUT_MS = 5000

export function portScanTimeoutMs() {
  const raw = process.env.TAHP_PORT_SCAN_TIMEOUT_MS
  if (!raw) return DEFAULT_PORT_SCAN_TIMEOUT_MS
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_PORT_SCAN_TIMEOUT_MS
}

export function shouldSkipPortScan() {
  const v = process.env.TAHP_SKIP_PORT_SCAN
  return v === '1' || v === 'true' || v === 'TRUE'
}

function uniquePids(pids) {
  return [...new Set(pids.filter(pid => Number.isFinite(pid) && pid > 0))]
}

export function commandExists(command) {
  try {
    if (process.platform === 'win32') execFileSync('where', [command], { stdio: 'ignore', windowsHide: true })
    else execFileSync('sh', ['-c', `command -v "$1" >/dev/null 2>&1`, 'sh', command], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

export function parseUnixNetstatListeningPids(out, port) {
  const pids = []
  for (const line of out.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/)
    if (parts.length < 6) continue
    const proto = parts[0]?.toLowerCase()
    if (!proto?.startsWith('tcp')) continue
    const localAddress = parts[3]
    const state = parts.find(p => p.toUpperCase() === 'LISTEN' || p.toUpperCase() === 'LISTENING')
    if (!state || !localAddress?.endsWith(`:${port}`)) continue
    const pidPart = parts.find(p => /^\d+\//.test(p))
    const pid = pidPart ? parseInt(pidPart.split('/')[0], 10) : NaN
    if (Number.isFinite(pid)) pids.push(pid)
  }
  return pids
}

/** 查询正在监听指定端口的进程 PID 列表 */
export function getListeningPids(port) {
  if (!port || Number.isNaN(Number(port))) return []
  if (shouldSkipPortScan()) return []
  const timeout = portScanTimeoutMs()

  try {
    if (process.platform === 'win32') {
      const out = execFileSync('netstat.exe', ['-ano', '-p', 'tcp'], {
        encoding: 'utf-8',
        timeout,
        killSignal: 'SIGKILL',
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'ignore'],
      })
      return uniquePids(
        out
          .split('\n')
          .map(l => l.trim())
          .filter(l => l.includes('LISTENING'))
          .map(l => l.split(/\s+/))
          .filter(parts => {
            const addr = parts[1] || ''
            return parseInt(addr.split(':').pop(), 10) === port
          })
          .map(parts => parseInt(parts[parts.length - 1], 10)),
      )
    }
  } catch {
    return []
  }

  if (commandExists('ss')) {
    try {
      const out = execFileSync('ss', ['-ltnp', `sport = :${port}`], {
        encoding: 'utf-8',
        timeout,
        killSignal: 'SIGKILL',
        stdio: ['ignore', 'pipe', 'ignore'],
      })
      const pids = uniquePids(
        out.split(/\r?\n/).map(l => l.match(/pid=(\d+)/)?.[1]).map(p => parseInt(p || '', 10)),
      )
      if (pids.length) return pids
    } catch {}
  }
  if (commandExists('lsof')) {
    try {
      const out = execFileSync('lsof', [`-tiTCP:${port}`, '-sTCP:LISTEN'], {
        encoding: 'utf-8',
        timeout,
        killSignal: 'SIGKILL',
        stdio: ['ignore', 'pipe', 'ignore'],
      }).trim()
      const pids = uniquePids(out.split(/\r?\n/).map(p => parseInt(p, 10)))
      if (pids.length) return pids
    } catch {}
  }
  if (commandExists('netstat')) {
    try {
      const out = execFileSync('netstat', ['-anp', 'tcp'], {
        encoding: 'utf-8',
        timeout,
        killSignal: 'SIGKILL',
        stdio: ['ignore', 'pipe', 'ignore'],
      })
      const pids = uniquePids(parseUnixNetstatListeningPids(out, port))
      if (pids.length) return pids
    } catch {}
  }
  return []
}

/**
 * 终止占用端口的进程
 * @param {number} port
 * @param {number[]} [pids]
 * @param {{ quiet?: boolean }} [opts]
 */
export function killListeningPids(port, pids = getListeningPids(port), opts = {}) {
  if (pids.length === 0) return
  if (!opts.quiet) {
    console.log(`  ⚠ 端口 ${port} 被占用 PID: ${pids.join(' ')}，正在终止...`)
  }
  try {
    if (process.platform === 'win32') {
      const args = ['/F']
      for (const pid of pids) {
        args.push('/PID', String(pid))
      }
      execFileSync('taskkill.exe', args, {
        encoding: 'utf-8',
        timeout: DEFAULT_TASKKILL_TIMEOUT_MS,
        killSignal: 'SIGKILL',
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'ignore'],
      })
    } else {
      execFileSync('kill', ['-9', ...pids.map(String)], {
        encoding: 'utf-8',
        timeout: DEFAULT_TASKKILL_TIMEOUT_MS,
        killSignal: 'SIGKILL',
        stdio: ['ignore', 'pipe', 'ignore'],
      })
    }
  } catch {}
}
