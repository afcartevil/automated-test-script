/**
 * 仓库内 hermes-agent-main 路径解析与环境变量注入。
 * 与 scripts/ensure-hermes-agent.mjs 写入的 .tahp/agent-paths.json 配合使用。
 */
import { existsSync, readFileSync } from 'fs'
import { join, resolve } from 'path'
import { getTahpProjectRoot, isValidTahpProjectRoot } from '../tahp/paths'

const BUNDLED_DIR_NAMES = ['hermes-agent-main', 'hermes-agent'] as const

function deriveConsoleRoot(): string {
  const candidates = [
    resolve(__dirname, '..', '..', '..', '..'), // packages/server/src/services/hermes
    resolve(__dirname, '..', '..', '..'), // dist/server/services/hermes
  ]
  for (const c of candidates) {
    if (existsSync(join(c, 'package.json'))) return c
  }
  return candidates[0]
}

function deriveTahpProjectRoot(consoleRoot: string): string {
  const fromEnv = process.env.TAHP_PROJECT_ROOT?.trim()
  if (fromEnv) {
    const resolved = resolve(fromEnv)
    if (isValidTahpProjectRoot(resolved)) return resolved
  }
  const parent = resolve(consoleRoot, '..')
  if (isValidTahpProjectRoot(parent)) return parent
  return getTahpProjectRoot()
}

export function getConsoleRoot(): string {
  return deriveConsoleRoot()
}

export function getBundledHermesAgentRoot(tahpRoot?: string): string | undefined {
  const root = tahpRoot ?? deriveTahpProjectRoot(deriveConsoleRoot())
  for (const name of BUNDLED_DIR_NAMES) {
    const dir = join(root, name)
    if (existsSync(join(dir, 'run_agent.py'))) return dir
  }
  return undefined
}

function venvPython(agentDir: string): string {
  return process.platform === 'win32'
    ? join(agentDir, '.venv', 'Scripts', 'python.exe')
    : join(agentDir, '.venv', 'bin', 'python')
}

function venvHermesBin(agentDir: string): string {
  return process.platform === 'win32'
    ? join(agentDir, '.venv', 'Scripts', 'hermes.exe')
    : join(agentDir, '.venv', 'bin', 'hermes')
}

interface AgentPathsFile {
  version?: number
  agentRoot?: string
  python?: string
  hermesBin?: string
}

function readAgentPathsFile(): AgentPathsFile | null {
  const file = join(deriveConsoleRoot(), '.tahp', 'agent-paths.json')
  if (!existsSync(file)) return null
  try {
    return JSON.parse(readFileSync(file, 'utf-8')) as AgentPathsFile
  } catch {
    return null
  }
}

function applyPaths(paths: { agentRoot: string; python: string; hermesBin?: string }): void {
  process.env.HERMES_AGENT_ROOT = paths.agentRoot
  process.env.HERMES_AGENT_BRIDGE_PYTHON = paths.python
  if (paths.hermesBin && existsSync(paths.hermesBin)) {
    process.env.HERMES_BIN = paths.hermesBin
  }
}

/**
 * 在 Agent Bridge 启动前注入 bundled agent 环境（幂等）。
 */
export function applyBundledAgentEnv(): { applied: boolean; source?: string } {
  if (process.env.HERMES_AGENT_ROOT?.trim()) {
    return { applied: false, source: 'HERMES_AGENT_ROOT already set' }
  }

  const cached = readAgentPathsFile()
  if (cached?.agentRoot && cached.python && existsSync(cached.python)) {
    applyPaths({
      agentRoot: cached.agentRoot,
      python: cached.python,
      hermesBin: cached.hermesBin,
    })
    return { applied: true, source: '.tahp/agent-paths.json' }
  }

  const bundled = getBundledHermesAgentRoot()
  if (bundled) {
    const py = venvPython(bundled)
    if (existsSync(py)) {
      const bin = venvHermesBin(bundled)
      applyPaths({
        agentRoot: bundled,
        python: py,
        hermesBin: existsSync(bin) ? bin : undefined,
      })
      return { applied: true, source: 'bundled .venv' }
    }
  }

  return { applied: false }
}

/** 供 resolveAgentRoot 优先使用的 bundled 路径 */
export function getBundledAgentRootForBridge(): string | undefined {
  applyBundledAgentEnv()
  return process.env.HERMES_AGENT_ROOT?.trim()
    || getBundledHermesAgentRoot()
}
