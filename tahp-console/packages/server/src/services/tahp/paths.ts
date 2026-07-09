/**
 * TAHP 路径解析 — 集中处理 skills / knowledge-base / reports 等位置。
 *
 * 优先级:
 *   1. 环境变量 TAHP_PROJECT_ROOT（须通过校验）
 *   2. tahp-console 上级目录（含完整 TAHP 仓库标记）
 *   3. 自 cwd 向上探测
 */
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { resolve, join } from 'path'

function isTahpProjectRoot(dir: string): boolean {
  return (
    existsSync(join(dir, 'skills', '.claude', 'skills')) ||
    existsSync(join(dir, 'knowledge-base'))
  )
}

function isDriveRoot(dir: string): boolean {
  return /^[A-Za-z]:[\\/]?$/.test(resolve(dir))
}

function isConsoleRoot(dir: string): boolean {
  return (
    existsSync(join(dir, 'package.json')) &&
    existsSync(join(dir, 'packages', 'server'))
  )
}

/**
 * 强校验：排除盘符根目录上残留的孤立 skills/ 目录（历史误解析产物）。
 */
export function isValidTahpProjectRoot(dir: string): boolean {
  const root = resolve(dir)
  if (isDriveRoot(root)) return false
  if (!isTahpProjectRoot(root)) return false
  if (existsSync(join(root, 'tahp-console', 'packages', 'server'))) return true
  if (existsSync(join(root, 'hermes-agent-main', 'run_agent.py'))) return true
  if (existsSync(join(root, 'skills', '.claude', 'skills', 'jira-ops', 'SKILL.md'))) return true
  return false
}

/** 从当前模块位置推断 tahp-console 根目录（兼容 src / dist 打包） */
function deriveConsoleRoot(): string {
  const candidates = [
    resolve(__dirname, '..', '..'), // dist/server
    resolve(__dirname, '..', '..', '..', '..'), // dist/server/services/tahp
    resolve(__dirname, '..', '..', '..', '..', '..'), // src/services/tahp
    resolve(process.cwd()),
  ]
  for (const c of candidates) {
    if (isConsoleRoot(c)) return c
  }
  return candidates[0]
}

export function deriveTahpProjectRoot(): string {
  const fromEnv = process.env.TAHP_PROJECT_ROOT?.trim()
  if (fromEnv) {
    const resolved = resolve(fromEnv)
    if (isValidTahpProjectRoot(resolved)) return resolved
    console.warn(
      `[tahp-paths] TAHP_PROJECT_ROOT 无效或缺少完整仓库标记，将自动探测: ${resolved}`,
    )
  }

  const consoleRoot = deriveConsoleRoot()
  const parentOfConsole = resolve(consoleRoot, '..')
  if (isValidTahpProjectRoot(parentOfConsole)) return parentOfConsole

  let dir = process.cwd()
  for (let i = 0; i < 10; i++) {
    if (isValidTahpProjectRoot(dir)) return resolve(dir)
    const up = resolve(dir, '..')
    if (up === dir || isDriveRoot(up)) break
    dir = up
  }

  return parentOfConsole
}

/** 每次调用重新解析（避免模块加载时 cwd/env 与运行时不一致） */
export function getTahpProjectRoot(): string {
  return deriveTahpProjectRoot()
}

function pythonWorks(cmd: string): boolean {
  const parts = cmd.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return false
  const [command, ...prefixArgs] = parts
  try {
    const result = spawnSync(command, [...prefixArgs, '--version'], {
      encoding: 'utf-8',
      windowsHide: true,
      timeout: 5000,
    })
    if (result.status !== 0) return false
    const version = `${result.stdout || ''}${result.stderr || ''}`.trim()
    return /Python 3\./.test(version)
  } catch {
    return false
  }
}

function discoverPython(): string {
  const fromEnv = process.env.TAHP_PYTHON?.trim()
  if (fromEnv && pythonWorks(fromEnv)) return fromEnv

  if (process.platform === 'win32') {
    for (const candidate of ['py -3.12', 'py -3.11', 'py -3', 'python3', 'python']) {
      if (pythonWorks(candidate)) return candidate
    }
    return 'python'
  }

  return pythonWorks('python3') ? 'python3' : 'python'
}

const _python = discoverPython()

export const tahpPaths = {
  get projectRoot() {
    return deriveTahpProjectRoot()
  },
  python: _python,
  get knowledgeDir() {
    return join(deriveTahpProjectRoot(), 'knowledge-base')
  },
  get reportsDir() {
    return join(deriveTahpProjectRoot(), 'reports')
  },
  get skillsDir() {
    return join(deriveTahpProjectRoot(), 'skills', '.claude', 'skills')
  },
  /** JIRA / modem 日志工作区：{工程根}/jira_workspace */
  get jiraWorkspaceDir() {
    return join(deriveTahpProjectRoot(), 'jira_workspace')
  },
  selfCheckDir: join(__dirname, 'self-check'),
  flashToolDir: join(__dirname, 'self-check', 'flash_tool'),
}

/** 将 `py -3` 这类命令拆成 spawn(command, prefixArgs) 可用形式 */
export function resolvePythonSpawn(python = tahpPaths.python): { command: string; prefixArgs: string[] } {
  const parts = python.trim().split(/\s+/).filter(Boolean)
  return {
    command: parts[0] || 'python',
    prefixArgs: parts.slice(1),
  }
}

export function hasTahpProject(): boolean {
  return isValidTahpProjectRoot(tahpPaths.projectRoot)
}

export function formatTahpPathsForLog(): string {
  const root = tahpPaths.projectRoot
  return `projectRoot=${root}, skillsDir=${tahpPaths.skillsDir}, valid=${isValidTahpProjectRoot(root)}`
}
