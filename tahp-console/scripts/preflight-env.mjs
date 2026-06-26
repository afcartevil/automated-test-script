#!/usr/bin/env node
/**
 * 启动前环境预检：Node.js + Python 是否已安装且版本满足要求。
 * 供 run_adapter.bat / npm run preflight 在 npm install 之前调用。
 *
 * 版本要求与工程一致：
 *   - Node.js >= 22.5（packages/server 使用 node:sqlite）
 *   - Python >= 3.11（hermes-agent-main）
 */
import { spawnSync } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import { getConsoleRoot, getSystemPython, resolvePythonCommand } from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = getConsoleRoot(__dirname)

/** @type {[number, number, number]} */
const MIN_NODE = [22, 5, 0]
/** @type {[number, number, number]} */
const MIN_PYTHON = [3, 11, 0]

function loadDotEnv(root) {
  const envPath = join(root, '.env')
  if (!existsSync(envPath)) return
  const lines = readFileSync(envPath, 'utf-8').split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq <= 0) continue
    const key = trimmed.slice(0, eq).trim()
    let val = trimmed.slice(eq + 1).trim()
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1)
    }
    if (process.env[key] === undefined) process.env[key] = val
  }
}

/** @param {string} versionStr @returns {[number, number, number] | null} */
function parseVersion(versionStr) {
  const m = String(versionStr).trim().match(/(\d+)\.(\d+)(?:\.(\d+))?/)
  if (!m) return null
  return [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3] || '0', 10)]
}

/** @param {[number, number, number]} a @param {[number, number, number]} b */
function versionGte(a, b) {
  for (let i = 0; i < 3; i++) {
    if (a[i] > b[i]) return true
    if (a[i] < b[i]) return false
  }
  return true
}

function formatMin(ver) {
  return ver[2] ? `${ver[0]}.${ver[1]}.${ver[2]}` : `${ver[0]}.${ver[1]}`
}

function fail(msg, hints = []) {
  console.error(`  ✗ ${msg}`)
  for (const hint of hints) console.error(`    ${hint}`)
  console.error('')
  console.error('[EasyAdapter] 环境检查未通过，已中止启动。请按上述提示修复后重试。')
  process.exit(1)
}

function pass(msg) {
  console.log(`  ✓ ${msg}`)
}

loadDotEnv(consoleRoot)

console.log('EasyAdapter 运行环境检查')
console.log('─'.repeat(40))

// --- Node.js ---
const nodeVer = parseVersion(process.versions.node)
if (!nodeVer || !versionGte(nodeVer, MIN_NODE)) {
  fail(
    `Node.js ${process.version} 过低，需要 >= ${formatMin(MIN_NODE)}（内置 SQLite 依赖 node:sqlite）`,
    [
      '下载: https://nodejs.org/',
      '安装后请关闭并重新打开终端，再双击 run_adapter.bat',
    ],
  )
}
pass(`Node.js ${process.version}`)

// --- Python ---
const pythonSpec = getSystemPython()
const { command: pyCmd, prefixArgs: pyPrefix } = resolvePythonCommand(pythonSpec)
const pyRun = spawnSync(pyCmd, [...pyPrefix, '--version'], { encoding: 'utf-8', windowsHide: true })
if (pyRun.status !== 0) {
  fail(
    '未找到可用的 Python',
    [
      `需要 Python >= ${formatMin(MIN_PYTHON)}（hermes-agent 要求）`,
      'Windows 可从 https://www.python.org/downloads/ 安装 3.12',
      '或在 tahp-console\\.env 中设置: TAHP_PYTHON=C:\\Path\\To\\Python312\\python.exe',
    ],
  )
}

const pyText = (pyRun.stdout || pyRun.stderr || '').trim()
const pyVer = parseVersion(pyText)
if (!pyVer || !versionGte(pyVer, MIN_PYTHON)) {
  fail(
    `${pyText || pythonSpec} 版本过低，需要 Python >= ${formatMin(MIN_PYTHON)}`,
    [
      '请安装 Python 3.11–3.13 后重试',
      '或在 tahp-console\\.env 中设置 TAHP_PYTHON 指向符合要求的 python.exe',
    ],
  )
}
pass(`${pyText} (${pythonSpec})`)

if (pyVer[0] >= 3 && pyVer[1] >= 14) {
  console.warn('  ⚠ 当前为 Python 3.14+，hermes-agent 官方测试以 3.11–3.13 为主；若后续安装失败请改用 3.12')
}

console.log('─'.repeat(40))
console.log('')
