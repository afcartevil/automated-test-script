/**
 * TAHP 路径解析 — 集中处理 skills / knowledge-base / reports 等位置。
 *
 * 优先级:
 *   1. 环境变量 TAHP_PROJECT_ROOT
 *   2. tahp-console 上级目录（含 skills 或 knowledge-base）
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

function deriveProjectRoot(): string {
  const fromEnv = process.env.TAHP_PROJECT_ROOT?.trim()
  if (fromEnv) return resolve(fromEnv)

  const consoleRoot = deriveConsoleRoot()
  const parentOfConsole = resolve(consoleRoot, '..')
  if (isTahpProjectRoot(parentOfConsole)) return parentOfConsole

  let dir = process.cwd()
  for (let i = 0; i < 10; i++) {
    if (isTahpProjectRoot(dir)) return dir
    const up = resolve(dir, '..')
    if (up === dir || isDriveRoot(up)) break
    dir = up
  }

  if (isTahpProjectRoot(parentOfConsole)) return parentOfConsole
  if (!isDriveRoot(parentOfConsole)) return parentOfConsole

  return consoleRoot
}

const projectRoot = deriveProjectRoot()

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

export const tahpPaths = {
  projectRoot,
  python: discoverPython(),
  knowledgeDir: join(projectRoot, 'knowledge-base'),
  reportsDir: join(projectRoot, 'reports'),
  skillsDir: join(projectRoot, 'skills', '.claude', 'skills'),
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
  return isTahpProjectRoot(tahpPaths.projectRoot)
}
