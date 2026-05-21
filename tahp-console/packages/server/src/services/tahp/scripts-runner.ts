/**
 * 运行 TAHP 的 Python CLI 脚本 (scripts/*.py) — 收集 stdout/stderr/exitCode.
 */
import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'
import { logger } from '../logger'

export interface ScriptResult {
  exitCode: number
  stdout: string
  stderr: string
}

export interface ScriptOptions {
  capture?: boolean
  timeoutMs?: number
  cwd?: string
}

const DEFAULT_TIMEOUT = 5 * 60 * 1000

export function runPythonScript(scriptName: string, args: string[], opts: ScriptOptions = {}): Promise<ScriptResult> {
  return new Promise((resolve, reject) => {
    const scriptPath = join(tahpPaths.scriptsDir, scriptName)
    if (!existsSync(scriptPath)) {
      reject(new Error(`脚本不存在: ${scriptPath}`))
      return
    }
    const child = spawn(tahpPaths.python, [scriptPath, ...args], {
      cwd: opts.cwd || tahpPaths.projectRoot,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    })
    let stdout = ''
    let stderr = ''
    let timer: NodeJS.Timeout | null = null
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT

    timer = setTimeout(() => {
      logger.warn({ scriptName }, '[tahp-script] timeout, killing')
      try { child.kill('SIGKILL') } catch {}
      reject(new Error(`脚本超时: ${scriptName} (${timeoutMs}ms)`))
    }, timeoutMs)

    child.stdout.setEncoding('utf-8')
    child.stderr.setEncoding('utf-8')
    child.stdout.on('data', (c: string) => { if (opts.capture !== false) stdout += c })
    child.stderr.on('data', (c: string) => { if (opts.capture !== false) stderr += c })
    child.on('error', (err) => {
      if (timer) clearTimeout(timer)
      reject(err)
    })
    child.on('exit', (code) => {
      if (timer) clearTimeout(timer)
      resolve({ exitCode: code ?? -1, stdout, stderr })
    })
  })
}
