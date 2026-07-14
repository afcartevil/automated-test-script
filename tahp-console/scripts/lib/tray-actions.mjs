/**
 * EasyAdapter 托盘动作（可单元测试的纯逻辑 + 平台调用）
 */
import { spawn, spawnSync, execSync } from 'child_process'
import { existsSync, readFileSync, unlinkSync, writeFileSync, mkdirSync } from 'fs'
import { homedir } from 'os'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import { getTahpProjectRoot } from './tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..', '..')

export const DEFAULT_PORT = 8650

export function getConsoleHome(env = process.env) {
  if (env.TAHP_CONSOLE_HOME?.trim()) return resolve(env.TAHP_CONSOLE_HOME.trim())
  return resolve(homedir(), '.tahp-console')
}

export function getTrayPidFile(env = process.env) {
  return join(getConsoleHome(env), 'tray.pid')
}

export function getServerPidFile(env = process.env) {
  return join(getConsoleHome(env), 'server.pid')
}

export function getLogFile(env = process.env) {
  return join(getConsoleHome(env), 'server.log')
}

export function getTrayLogFile(env = process.env) {
  return join(getConsoleHome(env), 'tray.log')
}

export function getTrayIconPath() {
  return resolve(consoleRoot, 'scripts', 'win', 'tray', 'easyadapter.ico')
}

export function getTahpConsoleBin() {
  return resolve(consoleRoot, 'bin', 'tahp-console.mjs')
}

export function getRepoRoot() {
  return getTahpProjectRoot(consoleRoot)
}

export function getRunAdapterBat() {
  return join(getRepoRoot(), 'run_adapter.bat')
}

export function resolveConsoleUrl(port = DEFAULT_PORT) {
  const p = Number(port) || DEFAULT_PORT
  return `http://localhost:${p}/#/tahp/dashboard`
}

export function readPidFile(path) {
  try {
    const pid = parseInt(readFileSync(path, 'utf-8').trim(), 10)
    return Number.isFinite(pid) ? pid : null
  } catch {
    return null
  }
}

export function isProcessRunning(pid, killProbe = process.kill) {
  if (!pid || !Number.isFinite(pid)) return false
  try {
    killProbe(pid, 0)
    return true
  } catch (err) {
    return err?.code === 'EPERM'
  }
}

export function readTrayPid(env = process.env) {
  return readPidFile(getTrayPidFile(env))
}

export function writeTrayPid(pid, env = process.env) {
  const dir = getConsoleHome(env)
  mkdirSync(dir, { recursive: true })
  writeFileSync(getTrayPidFile(env), String(pid))
}

export function removeTrayPid(env = process.env) {
  try { unlinkSync(getTrayPidFile(env)) } catch { /* ignore */ }
}

export function stopTray(env = process.env, killProbe = process.kill) {
  const pid = readTrayPid(env)
  if (!pid) {
    removeTrayPid(env)
    return { ok: true, stopped: false }
  }
  let stopped = false
  if (isProcessRunning(pid, killProbe)) {
    try {
      killProbe(pid)
      stopped = true
    } catch { /* ignore */ }
  }
  removeTrayPid(env)
  return { ok: true, stopped }
}

export function shouldRestartTray(env = process.env) {
  const v = env.TAHP_TRAY_RESTART
  return v === '1' || v === 'true' || v === 'TRUE'
}

export function queryServiceStatus(env = process.env) {
  const pid = readPidFile(getServerPidFile(env))
  const running = pid ? isProcessRunning(pid) : false
  return { running, pid: running ? pid : null }
}

export function buildTooltip(status, port = DEFAULT_PORT) {
  if (status.running && status.pid) {
    return `EasyAdapter running :${port} PID ${status.pid}`
  }
  return 'EasyAdapter stopped'
}

export function openConsole(port = DEFAULT_PORT) {
  const url = resolveConsoleUrl(port)
  if (process.platform === 'win32') {
    execSync(`start "" "${url}"`, { stdio: 'ignore' })
    return
  }
  if (process.platform === 'darwin') execSync(`open "${url}"`, { stdio: 'ignore' })
  else execSync(`xdg-open "${url}"`, { stdio: 'ignore' })
}

export function runTahpConsoleCommand(command, args = [], env = process.env) {
  const result = spawnSync(process.execPath, [getTahpConsoleBin(), command, ...args], {
    cwd: consoleRoot,
    encoding: 'utf-8',
    env,
    windowsHide: true,
  })
  return { ok: result.status === 0, status: result.status ?? 1, stdout: result.stdout, stderr: result.stderr }
}

export function restartService(env = process.env) {
  return runTahpConsoleCommand('restart', [], env)
}

export function stopService(env = process.env) {
  return runTahpConsoleCommand('stop', [], env)
}

export function openLog(env = process.env) {
  const logPath = getLogFile(env)
  if (!existsSync(logPath)) {
    return { ok: false, error: `日志文件不存在: ${logPath}` }
  }
  if (process.platform === 'win32') {
    execSync(`start "" notepad "${logPath}"`, { stdio: 'ignore' })
  } else if (process.platform === 'darwin') {
    execSync(`open "${logPath}"`, { stdio: 'ignore' })
  } else {
    execSync(`xdg-open "${logPath}"`, { stdio: 'ignore' })
  }
  return { ok: true }
}

/** 通过 WScript 无闪窗执行 run_adapter.bat（含 git pull + build + start + 托盘） */
export function getRunAdapterHiddenVbs() {
  return resolve(consoleRoot, 'scripts', 'win', 'run-adapter-hidden.vbs')
}

export function spawnFullRestart(env = process.env) {
  const bat = getRunAdapterBat()
  if (!existsSync(bat)) {
    return { ok: false, error: `未找到启动脚本: ${bat}` }
  }
  if (process.platform === 'win32') {
    const vbs = getRunAdapterHiddenVbs()
    if (existsSync(vbs)) {
      const child = spawn('wscript.exe', ['//B', vbs], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      })
      child.unref()
      return { ok: true }
    }
  }
  const child = spawn('cmd.exe', ['/d', '/c', bat], {
    cwd: getRepoRoot(),
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    env: { ...env, TAHP_TRAY: '1', TAHP_SILENT: '1' },
  })
  child.unref()
  return { ok: true }
}

export function isTrayEnabled(env = process.env) {
  const v = env.TAHP_TRAY
  if (v === '0' || v === 'false' || v === 'FALSE') return false
  return true
}

export function getPort(env = process.env) {
  const p = parseInt(env.PORT || String(DEFAULT_PORT), 10)
  return Number.isFinite(p) ? p : DEFAULT_PORT
}
