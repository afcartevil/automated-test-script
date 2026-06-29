/**
 * 在 BFF 中启动 Python 脚本（Windows `py -3.12` 需拆分；优先选用已安装 jira 的解释器）
 */
import { spawnSync } from 'child_process'
import { resolvePythonSpawn, tahpPaths } from './paths'

export function spawnOutputText(r: ReturnType<typeof spawnSync>): string {
  return [r.stdout, r.stderr].map((chunk) => (chunk == null ? '' : String(chunk))).join('').trim()
}

export function defaultPythonCandidates(): string[] {
  return [
    process.env.TAHP_PYTHON?.trim(),
    'python',
    'python3',
    'py -3',
    'py -3.12',
    'py -3.11',
    tahpPaths.python,
  ].filter((v, i, arr): v is string => !!v?.trim() && arr.indexOf(v) === i)
}

function pythonImportsJira(candidate: string): boolean {
  const { command, prefixArgs } = resolvePythonSpawn(candidate)
  const r = spawnSync(command, [...prefixArgs, '-c', 'import jira'], {
    encoding: 'utf-8',
    windowsHide: true,
    timeout: 15_000,
  })
  return r.status === 0
}

/** 脚本执行候选：优先能 `import jira` 的解释器（jira-ops 等） */
export function pythonCandidatesForScripts(): string[] {
  const all = defaultPythonCandidates()
  const withJira = all.filter(pythonImportsJira)
  return withJira.length > 0 ? withJira : all
}

export interface SpawnPythonOptions {
  cwd: string
  args: string[]
  env?: NodeJS.ProcessEnv
  timeout?: number
  /** 为 true 时优先返回输出可解析为 JSON 的一次运行（setup-check / api_jira） */
  preferJsonOutput?: boolean
}

export function spawnPythonScript(opts: SpawnPythonOptions): ReturnType<typeof spawnSync> {
  const {
    cwd,
    args,
    env = process.env,
    timeout = 90_000,
    preferJsonOutput = false,
  } = opts
  const candidates = pythonCandidatesForScripts()
  let last: ReturnType<typeof spawnSync> | null = null

  for (const candidate of candidates) {
    const { command, prefixArgs } = resolvePythonSpawn(candidate)
    const r = spawnSync(command, [...prefixArgs, ...args], {
      cwd,
      encoding: 'utf-8',
      timeout,
      windowsHide: true,
      env,
    })
    last = r
    if (r.status === null) continue
    const out = spawnOutputText(r)
    if (!preferJsonOutput) {
      if (r.status === 0 || out) return r
      continue
    }
    if (!out) continue
    try {
      JSON.parse(out)
      return r
    } catch {
      if (/ModuleNotFoundError|No module named/i.test(out)) continue
      if (r.status === 0) return r
      return r
    }
  }

  const shellPy = process.env.TAHP_PYTHON?.trim() || 'python'
  const quoted = args.map((a) => (/\s/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a))
  return spawnSync(`${shellPy} ${quoted.join(' ')}`, {
    cwd,
    encoding: 'utf-8',
    timeout,
    windowsHide: true,
    shell: true,
    env,
  })
}

export function extractJsonErrorMessage(output: string): string | null {
  try {
    const json = JSON.parse(output) as {
      ok?: boolean
      error?: { message?: string; code?: string } | string
    }
    if (json.ok !== false) return null
    const err = json.error
    if (typeof err === 'string') return err
    if (err?.message) {
      return err.code ? `${err.code}: ${err.message}` : err.message
    }
  } catch { /* ignore */ }
  return null
}

export function formatPythonSpawnError(label: string, r: ReturnType<typeof spawnSync>, output: string): string {
  const fromJson = extractJsonErrorMessage(output)
  if (fromJson) return fromJson.slice(0, 500)
  if (output) return output.slice(0, 500)
  if (r.error?.message) return `${label} 启动失败: ${r.error.message}`
  return `${label} 退出码 ${r.status ?? 'null'}`
}
