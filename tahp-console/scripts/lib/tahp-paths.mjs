/**
 * TAHP / tahp-console 路径解析（供 setup 与 ensure-hermes-agent 使用）
 */
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

/** tahp-console 根目录 */
export function getConsoleRoot(fromDir = __dirname) {
  return resolve(fromDir, '..', '..')
}

function isTahpProjectRoot(dir) {
  return (
    existsSync(join(dir, 'skills', '.claude', 'skills')) ||
    existsSync(join(dir, 'knowledge-base'))
  )
}

function isDriveRoot(dir) {
  return /^[A-Za-z]:[\\/]?$/.test(resolve(dir))
}

function isValidTahpProjectRoot(dir) {
  const root = resolve(dir)
  if (isDriveRoot(root)) return false
  if (!isTahpProjectRoot(root)) return false
  if (existsSync(join(root, 'tahp-console', 'packages', 'server'))) return true
  if (existsSync(join(root, 'hermes-agent-main', 'run_agent.py'))) return true
  if (existsSync(join(root, 'skills', '.claude', 'skills', 'jira-ops', 'SKILL.md'))) return true
  return false
}

/** TAHP 主仓根（含 skills、knowledge-base、hermes-agent-main） */
export function getTahpProjectRoot(consoleRoot = getConsoleRoot()) {
  const fromEnv = process.env.TAHP_PROJECT_ROOT?.trim()
  if (fromEnv) {
    const resolved = resolve(fromEnv)
    if (isValidTahpProjectRoot(resolved)) return resolved
  }
  const parent = resolve(consoleRoot, '..')
  if (isValidTahpProjectRoot(parent)) return parent

  let dir = process.cwd()
  for (let i = 0; i < 10; i++) {
    if (isValidTahpProjectRoot(dir)) return resolve(dir)
    const up = resolve(dir, '..')
    if (up === dir || isDriveRoot(up)) break
    dir = up
  }

  return parent
}

const BUNDLED_DIR_NAMES = ['hermes-agent-main', 'hermes-agent']

/** 仓库内自带的 hermes-agent 源码目录 */
export function getBundledHermesAgentDir(tahpRoot = getTahpProjectRoot()) {
  for (const name of BUNDLED_DIR_NAMES) {
    const dir = join(tahpRoot, name)
    if (existsSync(join(dir, 'run_agent.py'))) return dir
  }
  return null
}

export function getAgentStateDir(consoleRoot = getConsoleRoot()) {
  return join(consoleRoot, '.tahp')
}

export function getAgentPathsFile(consoleRoot = getConsoleRoot()) {
  return join(getAgentStateDir(consoleRoot), 'agent-paths.json')
}

export function getVenvPython(agentDir) {
  return process.platform === 'win32'
    ? join(agentDir, '.venv', 'Scripts', 'python.exe')
    : join(agentDir, '.venv', 'bin', 'python')
}

/** GKI Patch Tool 根目录（tools/gki-patch-tool） */
export function getGkiPatchToolRoot(tahpRoot = getTahpProjectRoot()) {
  const fromEnv = process.env.GKI_PATCH_TOOL_ROOT?.trim()
  if (fromEnv && existsSync(fromEnv)) return resolve(fromEnv)

  const candidates = [
    join(tahpRoot, 'tools', 'gki-patch-tool'),
    join(getConsoleRoot(), '..', 'tools', 'gki-patch-tool'),
  ]
  for (const candidate of candidates) {
    if (existsSync(join(candidate, 'web_app', 'app.py'))) return resolve(candidate)
  }
  return resolve(candidates[0])
}

export function getVenvHermesBin(agentDir) {
  return process.platform === 'win32'
    ? join(agentDir, '.venv', 'Scripts', 'hermes.exe')
    : join(agentDir, '.venv', 'bin', 'hermes')
}

/** Hermes 0.20.4 `requires-python = ">=3.11,<3.14"`（无 cp314 wheel） */
export const HERMES_PYTHON_MIN = [3, 11, 0]
export const HERMES_PYTHON_MAX_EXCLUSIVE = [3, 14, 0]
export const HERMES_PYTHON_RANGE_LABEL = '3.11–3.13'

/** @param {string} versionStr @returns {[number, number, number] | null} */
export function parseSemverTriple(versionStr) {
  const m = String(versionStr).trim().match(/(\d+)\.(\d+)(?:\.(\d+))?/)
  if (!m) return null
  return [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3] || '0', 10)]
}

/** @param {[number, number, number]} a @param {[number, number, number]} b */
export function versionGte(a, b) {
  for (let i = 0; i < 3; i++) {
    if (a[i] > b[i]) return true
    if (a[i] < b[i]) return false
  }
  return true
}

/** @param {[number, number, number] | null | undefined} ver */
export function isHermesPythonVersion(ver) {
  if (!ver || ver.length < 2) return false
  return versionGte(ver, HERMES_PYTHON_MIN) && !versionGte(ver, HERMES_PYTHON_MAX_EXCLUSIVE)
}

export function hermesPythonInstallHints() {
  return [
    `需要 Python ${HERMES_PYTHON_RANGE_LABEL}（hermes-agent 0.20.4 要求 >=3.11,<3.14；不要使用 3.14）`,
    'Windows 可从 https://www.python.org/downloads/ 安装 3.12',
    '或在 tahp-console\\.env 中设置: TAHP_PYTHON=C:\\Path\\To\\Python312\\python.exe',
  ]
}

/** 供 spawnSync / python -m venv 使用的 [command, ...prefixArgs] */
export function resolvePythonCommand(cmd) {
  const parts = (cmd || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return { command: 'python', prefixArgs: [] }
  return { command: parts[0], prefixArgs: parts.slice(1) }
}

function spawnPython(cmd, args) {
  const { command, prefixArgs } = resolvePythonCommand(cmd)
  return spawnSync(command, [...prefixArgs, ...args], { encoding: 'utf-8', windowsHide: true })
}

function pythonWorks(cmd) {
  if (!cmd?.trim()) return false
  try {
    const r = spawnPython(cmd, ['--version'])
    return r.status === 0
  } catch {
    return false
  }
}

/** @returns {[number, number, number] | null} */
export function getPythonVersion(cmd) {
  if (!cmd?.trim()) return null
  try {
    const r = spawnPython(cmd, ['--version'])
    if (r.status !== 0) return null
    return parseSemverTriple((r.stdout || r.stderr || '').trim())
  } catch {
    return null
  }
}

export function pythonCommandSupportsHermes(cmd) {
  if (!cmd?.trim()) return false
  try {
    const r = spawnPython(cmd, [
      '-c',
      'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)',
    ])
    return r.status === 0
  } catch {
    return false
  }
}

function localPythonExe(tag) {
  if (!process.env.LOCALAPPDATA) return ''
  return join(process.env.LOCALAPPDATA, 'Programs', 'Python', tag, 'python.exe')
}

function discoverWindowsPython() {
  const candidates = [
    'py -3.12',
    'py -3.13',
    'py -3.11',
    'py -3',
    localPythonExe('Python312'),
    localPythonExe('Python313'),
    localPythonExe('Python311'),
    'python',
    'python3',
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (pythonCommandSupportsHermes(candidate)) return candidate
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

export function getSystemPython() {
  if (process.env.TAHP_PYTHON?.trim() && pythonWorks(process.env.TAHP_PYTHON.trim())) {
    return process.env.TAHP_PYTHON.trim()
  }
  if (process.platform === 'win32') return discoverWindowsPython()
  if (pythonCommandSupportsHermes('python3')) return 'python3'
  if (pythonCommandSupportsHermes('python')) return 'python'
  const fallback = 'python3'
  return pythonWorks(fallback) ? fallback : 'python'
}
