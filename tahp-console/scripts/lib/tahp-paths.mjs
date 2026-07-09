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

export function getVenvHermesBin(agentDir) {
  return process.platform === 'win32'
    ? join(agentDir, '.venv', 'Scripts', 'hermes.exe')
    : join(agentDir, '.venv', 'bin', 'hermes')
}

function pythonWorks(cmd) {
  if (!cmd?.trim()) return false
  try {
    const parts = cmd.trim().split(/\s+/).filter(Boolean)
    const exe = parts[0]
    const prefixArgs = parts.slice(1)
    const r = spawnSync(exe, [...prefixArgs, '--version'], { encoding: 'utf-8', windowsHide: true })
    return r.status === 0
  } catch {
    return false
  }
}

/** 供 spawnSync / python -m venv 使用的 [command, ...prefixArgs] */
export function resolvePythonCommand(cmd) {
  const parts = (cmd || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return { command: 'python', prefixArgs: [] }
  return { command: parts[0], prefixArgs: parts.slice(1) }
}

function discoverWindowsPython() {
  const candidates = [
    process.env.TAHP_PYTHON?.trim(),
    'py -3.12',
    'py -3.11',
    'py -3',
    process.env.LOCALAPPDATA
      ? join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python312', 'python.exe')
      : '',
    process.env.LOCALAPPDATA
      ? join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python311', 'python.exe')
      : '',
    'python',
    'python3',
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (pythonWorks(candidate)) return candidate
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

export function getSystemPython() {
  if (process.env.TAHP_PYTHON?.trim() && pythonWorks(process.env.TAHP_PYTHON.trim())) {
    return process.env.TAHP_PYTHON.trim()
  }
  if (process.platform === 'win32') return discoverWindowsPython()
  const fallback = 'python3'
  return pythonWorks(fallback) ? fallback : 'python'
}
