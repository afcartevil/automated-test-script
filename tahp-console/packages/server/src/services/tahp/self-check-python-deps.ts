/**
 * 功耗自动化测试 Python 依赖 — 仅在启动功耗用例前检查/安装，不影响 Console 启动。
 */
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'

function resolveEnsureScript(): string | null {
  const candidates = [
    join(tahpPaths.projectRoot, 'tahp-console', 'scripts', 'ensure-self-check-python-deps.mjs'),
    join(__dirname, '..', '..', '..', '..', 'scripts', 'ensure-self-check-python-deps.mjs'),
    join(__dirname, '..', '..', '..', '..', '..', 'scripts', 'ensure-self-check-python-deps.mjs'),
  ]
  for (const path of candidates) {
    if (existsSync(path)) return path
  }
  return null
}

function resolveConsoleRoot(scriptPath: string): string {
  return join(scriptPath, '..', '..')
}

/** 功耗测试模块启动前同步安装/校验依赖 */
export function ensurePowerTestPythonDeps(): { ok: boolean; skipped?: boolean; error?: string } {
  if (process.env.TAHP_SKIP_POWER_DEPS === '1') {
    return { ok: true, skipped: true }
  }

  const script = resolveEnsureScript()
  if (!script) {
    return { ok: false, error: 'ensure-self-check-python-deps.mjs not found' }
  }

  const consoleRoot = resolveConsoleRoot(script)
  console.log('[device-self-check] ensuring power automation python deps...')

  const result = spawnSync(process.execPath, [script, '--for-test'], {
    cwd: consoleRoot,
    env: process.env,
    stdio: 'inherit',
    encoding: 'utf-8',
  })

  if (result.status === 0) {
    return { ok: true }
  }

  const detail = [result.stderr, result.stdout].filter(Boolean).join('\n').trim()
  const error = detail || `exit code ${result.status ?? 'unknown'}`
  return { ok: false, error }
}
