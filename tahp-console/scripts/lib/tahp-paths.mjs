/**
 * TAHP / tahp-console 路径解析（供 setup 与 ensure-hermes-agent 使用）
 */
import { existsSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

/** tahp-console 根目录 */
export function getConsoleRoot(fromDir = __dirname) {
  return resolve(fromDir, '..', '..')
}

/** TAHP 主仓根（含 tahp-mcp-server、hermes-agent-main） */
export function getTahpProjectRoot(consoleRoot = getConsoleRoot()) {
  if (process.env.TAHP_PROJECT_ROOT?.trim()) {
    return resolve(process.env.TAHP_PROJECT_ROOT.trim())
  }
  const parent = resolve(consoleRoot, '..')
  if (existsSync(join(parent, 'tahp-mcp-server', 'server.py'))) return parent
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

export function getSystemPython() {
  return process.env.TAHP_PYTHON?.trim()
    || (process.platform === 'win32' ? 'python' : 'python3')
}
