#!/usr/bin/env node
/**
 * TAHP Console daemon CLI.
 * Fork: hermes-web-ui v0.5.33 → tahp-console.
 * Differences:
 *   - 状态目录: ~/.tahp-console/
 *   - 默认端口: 8650
 *   - 默认鉴权: 若未设 AUTH_TOKEN/AUTH_DISABLED, 默认走 AUTH_DISABLED=1 (内网团队工具)
 */
import { spawn, execSync, execFileSync } from 'child_process'
import { ensureHermesAgent } from '../scripts/ensure-hermes-agent.mjs'
import { resolve, dirname, join, delimiter } from 'path'
import { fileURLToPath } from 'url'
import { readFileSync, writeFileSync, unlinkSync, mkdirSync, openSync, chmodSync, statSync, existsSync, realpathSync } from 'fs'
import { randomBytes } from 'crypto'
import { homedir } from 'os'

const __dirname = dirname(fileURLToPath(import.meta.url))
const __filename = fileURLToPath(import.meta.url)
const serverEntry = resolve(__dirname, '..', 'dist', 'server', 'index.js')
const pkgDir = resolve(__dirname, '..')
const pkg = JSON.parse(readFileSync(resolve(pkgDir, 'package.json'), 'utf-8'))
const VERSION = pkg.version
const CONSOLE_HOME = process.env.TAHP_CONSOLE_HOME?.trim()
  ? resolve(process.env.TAHP_CONSOLE_HOME.trim())
  : resolve(homedir(), '.tahp-console')
const PID_DIR = CONSOLE_HOME
const PID_FILE = join(PID_DIR, 'server.pid')
const LOG_FILE = join(PID_DIR, 'server.log')
const TOKEN_FILE = join(PID_DIR, '.token')
const DEFAULT_PORT = 8650
const CLI_NAME = 'tahp-console'

// 默认鉴权关闭：内网团队工具，开箱即用。
// 若需开启 token 鉴权：设 AUTH_DISABLED=0 或显式 AUTH_TOKEN=xxx。
function shouldDisableAuthByDefault() {
  if (process.env.AUTH_DISABLED !== undefined) return false
  if (process.env.AUTH_TOKEN) return false
  return true
}

function shouldOpenBrowser() {
  const v = process.env.TAHP_OPEN_BROWSER
  if (v === '0' || v === 'false' || v === 'FALSE') return false
  return true
}

function ensureNativeModules() {
  const prebuildDir = join(pkgDir, 'node_modules', 'node-pty', 'prebuilds', `${process.platform}-${process.arch}`)
  const helper = join(prebuildDir, 'spawn-helper')
  try { chmodSync(helper, 0o755) } catch {}
}

function getToken() {
  try { return readFileSync(TOKEN_FILE, 'utf-8').trim() } catch { return null }
}

function ensureToken() {
  if (process.env.AUTH_DISABLED === '1' || process.env.AUTH_DISABLED === 'true') return null
  if (process.env.AUTH_TOKEN) return process.env.AUTH_TOKEN

  let token = getToken()
  if (!token) {
    mkdirSync(dirname(TOKEN_FILE), { recursive: true })
    token = randomBytes(32).toString('hex')
    writeFileSync(TOKEN_FILE, token + '\n', { mode: 0o600 })
  }
  return token
}

function getWindowsShell() {
  const systemRoot = process.env.SystemRoot || 'C:\\Windows'
  const candidates = [process.env.ComSpec, join(systemRoot, 'System32', 'cmd.exe')].filter(Boolean)
  for (const c of candidates) if (existsSync(c)) return c
  return 'cmd.exe'
}

function getPortFromArgs() {
  if (process.argv[3] && !isNaN(process.argv[3])) return parseInt(process.argv[3])
  if (process.argv.includes('--port')) return parseInt(process.argv[process.argv.indexOf('--port') + 1])
  return null
}

function getPort() {
  const argPort = getPortFromArgs()
  return argPort ?? DEFAULT_PORT
}

function commandExists(command) {
  try {
    if (process.platform === 'win32') execFileSync('where', [command], { stdio: 'ignore', windowsHide: true })
    else execFileSync('sh', ['-c', `command -v "$1" >/dev/null 2>&1`, 'sh', command], { stdio: 'ignore' })
    return true
  } catch { return false }
}

function parseUnixNetstatListeningPids(out, port) {
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

function getListeningPids(port) {
  if (!port || isNaN(port)) return []
  const uniquePids = (pids) => [...new Set(pids.filter(pid => Number.isFinite(pid)))]

  try {
    if (process.platform === 'win32') {
      const out = execSync('netstat -aon -p tcp', { encoding: 'utf-8' })
      return uniquePids(out.split('\n')
        .map(l => l.trim())
        .filter(l => l.includes('LISTENING'))
        .map(l => l.split(/\s+/))
        .filter(parts => {
          const addr = parts[1] || ''
          return parseInt(addr.split(':').pop(), 10) === port
        })
        .map(parts => parseInt(parts[parts.length - 1], 10)))
    }
  } catch { return [] }

  if (commandExists('ss')) {
    try {
      const out = execFileSync('ss', ['-ltnp', `sport = :${port}`], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] })
      const pids = uniquePids(out.split(/\r?\n/).map(l => l.match(/pid=(\d+)/)?.[1]).map(p => parseInt(p || '', 10)))
      if (pids.length) return pids
    } catch {}
  }
  if (commandExists('lsof')) {
    try {
      const out = execFileSync('lsof', [`-tiTCP:${port}`, '-sTCP:LISTEN'], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
      const pids = uniquePids(out.split(/\r?\n/).map(p => parseInt(p, 10)))
      if (pids.length) return pids
    } catch {}
  }
  if (commandExists('netstat')) {
    try {
      const out = execFileSync('netstat', ['-anp', 'tcp'], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] })
      const pids = uniquePids(parseUnixNetstatListeningPids(out, port))
      if (pids.length) return pids
    } catch {}
  }
  return []
}

function killListeningPids(port, pids = getListeningPids(port)) {
  if (pids.length === 0) return
  console.log(`  ⚠ 端口 ${port} 被占用 PID: ${pids.join(' ')}，正在终止...`)
  try {
    if (process.platform === 'win32') execSync(`taskkill /F /PID ${pids.join(' /PID ')}`, { encoding: 'utf-8' })
    else execSync(`kill -9 ${pids.join(' ')}`, { encoding: 'utf-8' })
  } catch {}
}

function recoverPidFromPort() {
  const port = getPortFromArgs() ?? DEFAULT_PORT
  for (const pid of getListeningPids(port)) {
    if (isRunning(pid)) {
      mkdirSync(PID_DIR, { recursive: true })
      writePid(pid)
      return pid
    }
  }
  return null
}

function readPidFile() {
  try {
    const pid = parseInt(readFileSync(PID_FILE, 'utf-8').trim())
    return Number.isFinite(pid) ? pid : null
  } catch {}
  return null
}

function getPid() {
  const pid = readPidFile()
  if (pid) {
    if (isRunning(pid)) return pid
    removePid()
  }
  return recoverPidFromPort()
}

function isRunning(pid) {
  try { process.kill(pid, 0); return true }
  catch (err) { return err?.code === 'EPERM' }
}

function writePid(pid) { writeFileSync(PID_FILE, String(pid)) }
function removePid() { try { unlinkSync(PID_FILE) } catch {} }

function startDaemon(port) {
  const existing = getPid()
  if (existing && isRunning(existing)) {
    console.log(`  ✗ ${CLI_NAME} 已在运行 (PID: ${existing})`)
    console.log(`    请先执行 "${CLI_NAME} stop"`)
    process.exit(1)
  }
  removePid()

  const occupied = getListeningPids(port)
  if (occupied.length) {
    killListeningPids(port, occupied)
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500)
  }

  if (!existsSync(serverEntry)) {
    console.log(`  ✗ 服务入口不存在: ${serverEntry}`)
    console.log(`    请先执行: npm run build`)
    process.exit(1)
  }

  console.log('')
  const agentReady = ensureHermesAgent({ quiet: false, optional: true })
  if (!agentReady.ok) {
    console.log('  ⚠ Hermes Agent 未就绪，Bridge / Bug 分析 / 适配 Agent 可能不可用')
    console.log('    修复后请重新执行: npm run setup  或  npm run setup:agent')
  }
  console.log('')

  mkdirSync(PID_DIR, { recursive: true })
  ensureNativeModules()

  const authDisabledDefault = shouldDisableAuthByDefault()
  const token = ensureToken()

  const MAX_LOG_SIZE = 3 * 1024 * 1024
  const MAX_LOG_LINES = 2000
  try {
    const stat = statSync(LOG_FILE)
    if (stat.size > MAX_LOG_SIZE) {
      const content = readFileSync(LOG_FILE, 'utf-8')
      const lines = content.split('\n')
      const kept = lines.slice(-MAX_LOG_LINES)
      writeFileSync(LOG_FILE, kept.join('\n'), 'utf-8')
      console.log(`  ↻ 日志轮转 (${(stat.size / 1024 / 1024).toFixed(1)}MB → ${kept.length} 行)`)
    }
  } catch {}

  const logStream = openSync(LOG_FILE, 'a')
  const serverEnv = {
    ...process.env,
    NODE_ENV: 'production',
    PORT: String(port),
  }
  if (authDisabledDefault) serverEnv.AUTH_DISABLED = '1'
  if (token) serverEnv.AUTH_TOKEN = token
  // 兼容 hermes 内部仍用 HERMES_WEB_UI_HOME 的代码
  serverEnv.HERMES_WEB_UI_HOME = CONSOLE_HOME

  if (process.platform === 'win32') {
    const shell = getWindowsShell()
    serverEnv.SHELL = serverEnv.SHELL?.trim() || shell
    serverEnv.ComSpec = serverEnv.ComSpec?.trim() || shell
  }

  const child = spawn(process.execPath, [serverEntry], {
    detached: true,
    stdio: ['ignore', logStream, logStream],
    env: serverEnv,
    windowsHide: true,
  })
  child.on('error', (err) => {
    console.error(`  ✗ 启动失败: ${err.message}`)
    removePid()
    process.exit(1)
  })
  child.unref()
  writePid(child.pid)

  const healthUrl = `http://127.0.0.1:${port}/health`
  const maxWait = 30000
  const interval = 500
  let waited = 0
  console.log(`  ⏳ 正在启动 ${CLI_NAME} (PID: ${child.pid}, 端口: ${port})...`)

  function poll() {
    waited += interval
    if (!isRunning(child.pid)) {
      console.log(`  ✗ ${CLI_NAME} 启动失败`)
      console.log(`    日志: ${LOG_FILE}`)
      removePid()
      process.exit(1)
      return
    }
    fetch(healthUrl).then(res => {
      if (res.ok) {
        const url = token
          ? `http://localhost:${port}/#/?token=${token}`
          : `http://localhost:${port}/#/tahp/dashboard`
        console.log(`  ✓ ${CLI_NAME} 已启动`)
        console.log(`    ${url}`)
        console.log(`    日志: ${LOG_FILE}`)
        if (authDisabledDefault) {
          console.log(`    鉴权: 已关闭 (内网模式，需开启请设 AUTH_DISABLED=0)`)
        }
        if (shouldOpenBrowser()) {
          const cmd = process.platform === 'win32' ? `start "" "${url}"`
            : process.platform === 'darwin' ? `open "${url}"`
              : `xdg-open "${url}"`
          try { execSync(cmd, { stdio: 'ignore' }) } catch {}
        }
      } else if (waited < maxWait) {
        setTimeout(poll, interval)
      } else {
        console.log(`  ⚠ 进程在运行但健康检查 ${maxWait / 1000}s 内未通过`)
        console.log(`    日志: ${LOG_FILE}`)
      }
    }).catch(() => {
      if (waited < maxWait) setTimeout(poll, interval)
      else {
        console.log(`  ⚠ 进程在运行但健康检查 ${maxWait / 1000}s 内未通过`)
        console.log(`    日志: ${LOG_FILE}`)
      }
    })
  }
  setTimeout(poll, interval)
}

function stopDaemon() {
  const pid = getPid()
  if (!pid) {
    console.log(`  ✗ ${CLI_NAME} 未运行`)
    process.exit(1)
  }
  if (!isRunning(pid)) {
    removePid()
    console.log(`  ✓ ${CLI_NAME} 未在运行 (已清理过期 PID)`)
    return
  }
  try {
    try {
      process.kill(pid, 'SIGTERM')
      for (let i = 0; i < 10; i++) {
        if (!isRunning(pid)) break
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500)
      }
    } catch {}
    if (isRunning(pid)) process.kill(pid, 'SIGKILL')
    removePid()
    console.log(`  ✓ ${CLI_NAME} 已停止 (PID: ${pid})`)
  } catch (err) {
    console.log(`  ✗ 停止失败: ${err.message}`)
    process.exit(1)
  }
}

function showStatus() {
  const pid = getPid()
  if (pid && isRunning(pid)) {
    console.log(`  ✓ ${CLI_NAME} 正在运行 (PID: ${pid})`)
    console.log(`    PID 文件: ${PID_FILE}`)
    console.log(`    日志: ${LOG_FILE}`)
  } else {
    if (pid) removePid()
    console.log(`  ✗ ${CLI_NAME} 未运行`)
  }
}

function main() {
  const command = process.argv[2] || 'start'

  if (['-v', '--version', 'version'].includes(command)) {
    console.log(`${CLI_NAME} v${VERSION}`)
    process.exit(0)
  }
  if (['-h', '--help', 'help'].includes(command)) {
    console.log(`
${CLI_NAME} v${VERSION}

用法: ${CLI_NAME} <command> [options]

命令:
  start [port]       启动服务 (默认端口: ${DEFAULT_PORT})
  stop               停止服务
  restart [port]     重启服务
  status             查看服务状态
  version            显示版本号

选项:
  -v, --version      显示版本号
  -h, --help         显示帮助
  --port <port>      指定端口

环境变量:
  TAHP_CONSOLE_HOME  数据目录 (默认 ~/.tahp-console)
  AUTH_DISABLED      设为 0 启用 token 鉴权 (默认已关闭)
  AUTH_TOKEN         显式指定 token
  TAHP_PROJECT_ROOT  TAHP 仓库根目录 (默认上级)
  TAHP_PYTHON        Python 可执行路径 (默认 python)
  TAHP_OPEN_BROWSER  设为 0 时 start 不自动打开浏览器 (run_adapter.bat 使用)
`)
    process.exit(0)
  }

  switch (command) {
    case 'start':
      startDaemon(getPort())
      break
    case 'stop':
      stopDaemon()
      break
    case 'restart':
      stopDaemon()
      setTimeout(() => startDaemon(getPort()), 500)
      break
    case 'status':
      showStatus()
      break
    default: {
      ensureNativeModules()
      ensureHermesAgent({ quiet: false, optional: true })
      const port = !isNaN(command) ? parseInt(command) : DEFAULT_PORT
      const serverEnv = { ...process.env, NODE_ENV: 'production', PORT: String(port) }
      if (shouldDisableAuthByDefault()) serverEnv.AUTH_DISABLED = '1'
      serverEnv.HERMES_WEB_UI_HOME = CONSOLE_HOME
      if (process.platform === 'win32') {
        const shell = getWindowsShell()
        serverEnv.SHELL = serverEnv.SHELL?.trim() || shell
        serverEnv.ComSpec = serverEnv.ComSpec?.trim() || shell
      }
      const child = spawn(process.execPath, [serverEntry], {
        stdio: 'inherit',
        env: serverEnv,
        windowsHide: true,
      })
      child.on('exit', (code) => process.exit(code ?? 1))
      process.on('SIGTERM', () => child.kill('SIGTERM'))
      process.on('SIGINT', () => child.kill('SIGINT'))
    }
  }
}

if (process.argv[1] && realpathSync(resolve(process.argv[1])) === __filename) {
  main()
}

export { commandExists, getListeningPids, parseUnixNetstatListeningPids }
