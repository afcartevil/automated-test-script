#!/usr/bin/env node
/**
 * 启动前环境预检：Node.js + Python 是否已安装且版本满足要求。
 * 供 run_adapter.bat / npm run preflight 在 npm install 之前调用。
 *
 * 版本要求与工程一致：
 *   - Node.js >= 22.5（packages/server 使用 node:sqlite）
 *   - Python 3.11–3.13（hermes-agent 0.20.4 requires-python >=3.11,<3.14）
 */
import { spawnSync } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import {
  HERMES_PYTHON_RANGE_LABEL,
  getConsoleRoot,
  getSystemPython,
  hermesPythonInstallHints,
  isHermesPythonVersion,
  parseSemverTriple,
  resolvePythonCommand,
  versionGte,
} from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = getConsoleRoot(__dirname)

/** @type {[number, number, number]} */
const MIN_NODE = [22, 5, 0]

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
const nodeVer = parseSemverTriple(process.versions.node)
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
  fail('未找到可用的 Python', hermesPythonInstallHints())
}

const pyText = (pyRun.stdout || pyRun.stderr || '').trim()
const pyVer = parseSemverTriple(pyText)
if (!isHermesPythonVersion(pyVer)) {
  const why = pyVer && versionGte(pyVer, [3, 14, 0])
    ? `${pyText || pythonSpec} 不受支持，需要 Python ${HERMES_PYTHON_RANGE_LABEL}（不要使用 3.14）`
    : `${pyText || pythonSpec} 版本不在支持范围，需要 Python ${HERMES_PYTHON_RANGE_LABEL}`
  fail(why, hermesPythonInstallHints().slice(1))
}
pass(`${pyText} (${pythonSpec})`)

console.log('─'.repeat(40))
console.log('')
