/**
 * Windows：自动发现 Git for Windows 的 bash.exe，供 Hermes Agent 终端工具使用。
 * 与 hermes install.ps1 的 Set-GitBashEnvVar 策略一致，并额外从 PATH 上的 git.exe 推导安装根目录。
 */
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'

const DOTENV_HEADER = '# --- TAHP bundled hermes-agent (auto-generated) ---'
const DOTENV_FOOTER = '# --- end TAHP bundled hermes-agent ---'

/** @param {string} gitExe */
export function bashCandidatesFromGitExe(gitExe) {
  const gitCmdDir = dirname(gitExe)
  const gitRoot = dirname(gitCmdDir)
  return [
    join(gitRoot, 'bin', 'bash.exe'),
    join(gitRoot, 'usr', 'bin', 'bash.exe'),
  ]
}

/** @param {NodeJS.ProcessEnv} [env] */
export function standardWindowsBashCandidates(env = process.env) {
  const localAppData = env.LOCALAPPDATA || ''
  const pf = env.ProgramFiles || 'C:\\Program Files'
  const pf86 = env['ProgramFiles(x86)'] || ''
  /** @type {string[]} */
  const candidates = []
  if (localAppData) {
    candidates.push(
      join(localAppData, 'hermes', 'git', 'bin', 'bash.exe'),
      join(localAppData, 'hermes', 'git', 'usr', 'bin', 'bash.exe'),
      join(localAppData, 'Programs', 'Git', 'bin', 'bash.exe'),
    )
  }
  candidates.push(join(pf, 'Git', 'bin', 'bash.exe'))
  if (pf86) candidates.push(join(pf86, 'Git', 'bin', 'bash.exe'))
  return candidates
}

function firstExecutableLine(stdout) {
  return String(stdout || '')
    .split(/\r?\n/)
    .map(s => s.trim())
    .find(Boolean) || null
}

function findOnPath(command) {
  const tool = process.platform === 'win32' ? 'where.exe' : 'which'
  const r = spawnSync(tool, [command], { encoding: 'utf-8', windowsHide: true })
  if (r.status !== 0) return null
  return firstExecutableLine(r.stdout)
}

/**
 * @param {NodeJS.ProcessEnv} [env]
 * @param {{ exists?: (p: string) => boolean, findGitExe?: () => string | null, findBashOnPath?: () => string | null }} [deps]
 * @returns {string | null}
 */
export function discoverGitBashPath(env = process.env, deps = {}) {
  if (process.platform !== 'win32') return null

  const exists = deps.exists ?? existsSync
  const custom = env.HERMES_GIT_BASH_PATH?.trim()
  if (custom && exists(custom)) return custom

  /** @type {string[]} */
  const candidates = []
  const bashOnPath = deps.findBashOnPath ? deps.findBashOnPath() : findOnPath('bash')
  if (bashOnPath) candidates.push(bashOnPath)

  candidates.push(...standardWindowsBashCandidates(env))

  const gitExe = deps.findGitExe ? deps.findGitExe() : findOnPath('git')
  if (gitExe) candidates.push(...bashCandidatesFromGitExe(gitExe))

  const seen = new Set()
  for (const candidate of candidates) {
    if (!candidate) continue
    const key = candidate.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    if (exists(candidate)) return candidate
  }
  return null
}

/**
 * @param {string} consoleRoot
 * @param {Record<string, string>} entries
 */
export function mergeConsoleEnvBlock(consoleRoot, entries) {
  const envPath = join(consoleRoot, '.env')
  const header = DOTENV_HEADER
  const footer = DOTENV_FOOTER
  let content = existsSync(envPath) ? readFileSync(envPath, 'utf-8') : ''
  const start = content.indexOf(header)
  const end = content.indexOf(footer)

  const existing = new Map()
  if (start >= 0 && end > start) {
    const block = content.slice(start, end)
    for (const line of block.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      const eq = trimmed.indexOf('=')
      if (eq <= 0) continue
      existing.set(trimmed.slice(0, eq).trim(), trimmed.slice(eq + 1).trim())
    }
  }
  for (const [k, v] of Object.entries(entries)) {
    if (v !== undefined && v !== '') existing.set(k, v)
  }

  const block = [
    header,
    ...[...existing.entries()].map(([k, v]) => `${k}=${v}`),
    footer,
    '',
  ].join('\n')

  if (start >= 0 && end > start) {
    content = `${content.slice(0, start)}${block}${content.slice(end + footer.length).replace(/^\n+/, '')}`
  } else {
    content = `${content.trimEnd()}\n\n${block}`
  }
  writeFileSync(envPath, content, 'utf-8')
}

/**
 * @param {{ consoleRoot?: string, quiet?: boolean, persist?: boolean, env?: Record<string, string | undefined> }} [opts]
 * @returns {{ ok: boolean, path?: string, source?: string, skipped?: boolean, reason?: string, error?: string }}
 */
export function ensureGitBashEnv(opts = {}) {
  if (process.platform !== 'win32') {
    return { ok: true, skipped: true, reason: 'non-windows' }
  }

  const env = { ...process.env, ...opts.env }
  const existing = env.HERMES_GIT_BASH_PATH?.trim()
  if (existing && existsSync(existing)) {
    process.env.HERMES_GIT_BASH_PATH = existing
    return { ok: true, path: existing, source: 'env' }
  }

  const path = discoverGitBashPath(env)
  if (!path) {
    return {
      ok: false,
      error:
        '未找到 Git Bash（bash.exe）。Hermes Agent 在 Windows 上需要 Git for Windows。\n'
        + '  请安装 https://git-scm.com/download/win\n'
        + '  或在 tahp-console\\.env 中设置 HERMES_GIT_BASH_PATH=你的\\bash.exe 完整路径',
    }
  }

  process.env.HERMES_GIT_BASH_PATH = path
  if (opts.persist !== false && opts.consoleRoot) {
    mergeConsoleEnvBlock(opts.consoleRoot, { HERMES_GIT_BASH_PATH: path })
  }
  if (!opts.quiet) {
    console.log(`  ✓ Git Bash: ${path}`)
  }
  return { ok: true, path, source: 'discovered' }
}
