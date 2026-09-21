/**
 * 飞书全功能特性 checklist × SCMP 市场支持回写。
 * spawn 本目录 cli/run.py，按行解析 JSONL 并通过 TaskStream 推给前端。
 */
import { spawn, spawnSync, type ChildProcess } from 'child_process'
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { homedir } from 'os'
import { dirname, join, resolve } from 'path'
import { randomBytes } from 'crypto'
import { logger } from '../../logger'
import { applyBundledAgentEnv, getBundledHermesAgentRoot } from '../../hermes/bundled-agent'
import { resolvePythonSpawn, tahpPaths } from '../paths'
import { getTaskStream } from '../task-stream'
import {
  applyChecklistScmpEvent,
  compactChecklistScmpError,
  parseChecklistScmpLine,
  validateFeishuUrl,
} from './events'
import type { ChecklistScmpProbeResult, ChecklistScmpRun } from './types'

export {
  applyChecklistScmpEvent,
  compactChecklistScmpError,
  parseChecklistScmpLine,
  validateFeishuUrl,
} from './events'
export type {
  ChecklistScmpJsonlEvent,
  ChecklistScmpProbeResult,
  ChecklistScmpRun,
  ChecklistScmpStatus,
  ChecklistScmpSummary,
} from './types'

const TITLE_HINT = 'X6879-tOS17 全功能特性checklist_V2.5'
const runs = new Map<string, ChecklistScmpRun>()
const activeJobs = new Map<string, { proc: ChildProcess; cancelled: boolean }>()

function nowIso() {
  return new Date().toISOString()
}

function newRunId() {
  return `css-${Date.now().toString(36)}-${randomBytes(3).toString('hex')}`
}

export function resolveChecklistScmpCliRoot(): string | null {
  const candidates = [
    join(__dirname, 'cli'),
    join(__dirname, 'checklist-scmp-sync', 'cli'),
    resolve(process.cwd(), 'packages/server/src/services/tahp/checklist-scmp-sync/cli'),
    resolve(tahpPaths.projectRoot, 'tahp-console/packages/server/src/services/tahp/checklist-scmp-sync/cli'),
  ]
  for (const dir of candidates) {
    if (existsSync(join(dir, 'run.py'))) return dir
  }
  return null
}

export function resolveTonesScmpCli(): string | null {
  const fromEnv = process.env.TONES_SCMP_CLI?.trim()
  if (fromEnv && existsSync(fromEnv)) return fromEnv
  const localApp = process.env.LOCALAPPDATA || ''
  const candidates = [
    join(tahpPaths.skillsDir, 'tones-scmp', 'scripts', 'run.py'),
    join(homedir(), '.cursor', 'skills', 'tones-scmp', 'scripts', 'run.py'),
    join(localApp, 'hermes', 'skills', 'tones-scmp', 'scripts', 'run.py'),
  ]
  for (const path of candidates) {
    if (path && existsSync(path)) return path
  }
  return null
}

function hermesVenvPython(): string | null {
  applyBundledAgentEnv()
  const fromEnv = process.env.HERMES_AGENT_BRIDGE_PYTHON?.trim()
  if (fromEnv && existsSync(fromEnv)) return fromEnv
  const bundled = getBundledHermesAgentRoot()
  if (!bundled) return null
  const py = process.platform === 'win32'
    ? join(bundled, '.venv', 'Scripts', 'python.exe')
    : join(bundled, '.venv', 'bin', 'python')
  return existsSync(py) ? py : null
}

/** 优先 Hermes venv（setup:skills 把 httpx 装在这里），否则 TAHP_PYTHON / 系统 Python */
export function resolveChecklistScmpPython(): string {
  return hermesVenvPython() || tahpPaths.python
}

const TONES_IMPORTS = ['httpx', 'cryptography'] as const

export function resolveChecklistScmpRequirements(): string | null {
  const candidates = [
    join(__dirname, 'requirements.txt'),
    join(__dirname, 'checklist-scmp-sync', 'requirements.txt'),
    resolve(process.cwd(), 'packages/server/src/services/tahp/checklist-scmp-sync/requirements.txt'),
    resolve(tahpPaths.projectRoot, 'tahp-console/packages/server/src/services/tahp/checklist-scmp-sync/requirements.txt'),
  ]
  const tonesCli = resolveTonesScmpCli()
  if (tonesCli) candidates.push(join(dirname(tonesCli), 'requirements.txt'))
  for (const file of candidates) {
    if (existsSync(file)) return file
  }
  return null
}

function pythonHasModule(pythonCmd: string, moduleName: string): boolean {
  const { command, prefixArgs } = resolvePythonSpawn(pythonCmd)
  try {
    const result = spawnSync(command, [...prefixArgs, '-c', `import ${moduleName}`], {
      encoding: 'utf-8',
      windowsHide: true,
      timeout: 8000,
    })
    return result.status === 0
  } catch {
    return false
  }
}

function missingTonesImports(pythonCmd: string): string[] {
  return TONES_IMPORTS.filter(mod => !pythonHasModule(pythonCmd, mod))
}

/**
 * 把 tones-scmp 所需 httpx/cryptography 装进即将 spawn 的那套 Python。
 * 依赖清单随仓入库，不要求本机已经同步 tones-scmp Skill。
 */
export function ensureChecklistScmpPythonDeps(): { ok: boolean; python: string; error?: string } {
  const python = resolveChecklistScmpPython()
  const missing = missingTonesImports(python)
  if (!missing.length) return { ok: true, python }

  const req = resolveChecklistScmpRequirements()
  if (!req) {
    return {
      ok: false,
      python,
      error: `tones-scmp 需要 ${missing.join(', ')}，但未找到 requirements.txt。请确认已拉取 tahp-console 最新代码`,
    }
  }

  const { command, prefixArgs } = resolvePythonSpawn(python)
  logger.info({ python, req, missing }, '[checklist-scmp-sync] installing python deps')
  const result = spawnSync(command, [...prefixArgs, '-m', 'pip', 'install', '-r', req], {
    encoding: 'utf-8',
    windowsHide: true,
    timeout: 120_000,
  })
  if (result.status !== 0) {
    const detail = `${result.stderr || ''}${result.stdout || ''}`.trim().slice(0, 400)
    return {
      ok: false,
      python,
      error: `自动安装 ${missing.join(', ')} 失败（解释器: ${python}）。请检查网络后执行 npm run setup:skills${detail ? `\n${detail}` : ''}`,
    }
  }
  const still = missingTonesImports(python)
  if (still.length) {
    return {
      ok: false,
      python,
      error: `安装后仍缺少 ${still.join(', ')}（解释器: ${python}）。请执行 npm run setup:skills`,
    }
  }
  return { ok: true, python }
}

function reportsDir(runId: string) {
  return join(tahpPaths.reportsDir, 'checklist-scmp-sync', runId)
}

function persistRun(run: ChecklistScmpRun) {
  try {
    const dir = reportsDir(run.run_id)
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
    writeFileSync(join(dir, 'meta.json'), JSON.stringify(run, null, 2), 'utf-8')
  } catch (err) {
    logger.debug({ err: (err as Error).message }, '[checklist-scmp-sync] persist skipped')
  }
}

function emit(run: ChecklistScmpRun, type: string, payload: Record<string, unknown> = {}) {
  getTaskStream().publish({
    type,
    task_id: run.run_id,
    payload: {
      task_id: run.run_id,
      progress: run.progress,
      phase: run.phase,
      text: run.message,
      message: run.message,
      ...payload,
    },
    ts: Date.now(),
  })
}

function patchRun(runId: string, next: ChecklistScmpRun) {
  runs.set(runId, next)
  persistRun(next)
  return next
}

export function listChecklistScmpRuns(limit = 20): ChecklistScmpRun[] {
  return [...runs.values()]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, limit)
}

export function getChecklistScmpRun(runId: string): ChecklistScmpRun | undefined {
  return runs.get(runId)
}

export function getActiveChecklistScmpRun(): ChecklistScmpRun | undefined {
  return [...runs.values()].find(run => run.status === 'pending' || run.status === 'running')
}

export function probeChecklistScmp(): ChecklistScmpProbeResult {
  const cliRoot = resolveChecklistScmpCliRoot()
  if (!cliRoot) {
    return { available: false, reason: '未找到 checklist-scmp-sync/cli/run.py' }
  }
  const python = resolveChecklistScmpPython()
  const tones = resolveTonesScmpCli()
  const missing = missingTonesImports(python)
  const reasons: string[] = []
  if (!tones) {
    reasons.push(`tones-scmp 未自动定位。文档标题须含项目编码与 tOS，例如 ${TITLE_HINT}`)
  }
  if (missing.length) {
    reasons.push(`当前 Python 缺少 ${missing.join(', ')}，点「开始」或 Console 启动时会按随仓 requirements.txt 自动安装`)
  }
  return {
    available: true,
    python,
    cli_root: cliRoot,
    tones_cli: tones,
    reason: reasons.join('；') || undefined,
  }
}

function killTree(proc: ChildProcess) {
  const pid = proc.pid
  if (!pid) {
    try { proc.kill() } catch { /* ignore */ }
    return
  }
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    return
  }
  try { proc.kill('SIGTERM') } catch { /* ignore */ }
}

export async function startChecklistScmpSync(input: { url: string }): Promise<{ run_id: string }> {
  const urlError = validateFeishuUrl(input.url)
  if (urlError) {
    const err = new Error(urlError)
    ;(err as Error & { status?: number }).status = 400
    throw err
  }
  const active = getActiveChecklistScmpRun()
  if (active) {
    const err = new Error(`已有任务进行中（${active.run_id}），请等待完成或取消后再试`)
    ;(err as Error & { status?: number }).status = 409
    throw err
  }
  const cliRoot = resolveChecklistScmpCliRoot()
  if (!cliRoot) {
    throw new Error('未找到 checklist-scmp-sync CLI（cli/run.py）')
  }

  const deps = ensureChecklistScmpPythonDeps()
  if (!deps.ok) throw new Error(deps.error || 'tones-scmp Python 依赖未就绪')
  const pythonCmd = deps.python
  const tonesCli = resolveTonesScmpCli()

  const runId = newRunId()
  const created = nowIso()
  const run: ChecklistScmpRun = {
    run_id: runId,
    url: input.url.trim(),
    status: 'pending',
    progress: 0,
    phase: 'queued',
    message: '正在启动 checklist-scmp-sync',
    log_tail: ['正在启动 checklist-scmp-sync'],
    created_at: created,
    updated_at: created,
  }
  runs.set(runId, run)
  persistRun(run)

  const outDir = reportsDir(runId)
  mkdirSync(outDir, { recursive: true })
  const logFile = join(outDir, 'events.jsonl')
  run.log_file = logFile

  const { command, prefixArgs } = resolvePythonSpawn(pythonCmd)
  const args = [
    ...prefixArgs,
    '-u',
    join(cliRoot, 'run.py'),
    '--url',
    input.url.trim(),
    '--format',
    'jsonl',
    '--log-file',
    logFile,
  ]
  if (tonesCli) args.push('--tones-cli', tonesCli)

  emit(run, 'task.started', { text: run.message })

  const proc = spawn(command, args, {
    cwd: cliRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      LARKSUITE_CLI_NO_UPDATE_NOTIFIER: '1',
      LARKSUITE_CLI_NO_SKILLS_NOTIFIER: '1',
    },
    windowsHide: true,
  })
  activeJobs.set(runId, { proc, cancelled: false })
  patchRun(runId, { ...run, status: 'running', phase: 'start', updated_at: nowIso() })

  let stdoutBuf = ''
  const onChunk = (chunk: Buffer | string, fromStderr = false) => {
    const text = chunk.toString()
    stdoutBuf += text
    const parts = stdoutBuf.split(/\r?\n/)
    stdoutBuf = parts.pop() || ''
    for (const line of parts) {
      const parsed = parseChecklistScmpLine(line)
      const current = runs.get(runId)
      if (!current) continue
      if (parsed) {
        const prevStatus = current.status
        const next = applyChecklistScmpEvent(current, parsed)
        patchRun(runId, next)
        const becameTerminal = prevStatus !== next.status
          && (next.status === 'completed' || next.status === 'failed')
        emit(next, becameTerminal
          ? (next.status === 'completed' ? 'task.completed' : 'task.failed')
          : 'task.message', parsed.event === 'done' || parsed.event === 'error'
          ? { summary: next.summary, error: next.error }
          : {})
        if (!becameTerminal && next.status === 'running') {
          emit(next, 'task.progress', { progress: next.progress })
        }
      } else if (line.trim()) {
        const next = applyChecklistScmpEvent(current, {
          event: fromStderr ? 'stderr' : 'log',
          message: line.trim(),
        })
        patchRun(runId, next)
        emit(next, 'task.message')
      }
    }
  }

  proc.stdout?.on('data', (chunk: Buffer) => onChunk(chunk, false))
  proc.stderr?.on('data', (chunk: Buffer) => onChunk(chunk, true))

  proc.on('error', (err) => {
    const current = runs.get(runId)
    if (!current) return
    const next = applyChecklistScmpEvent(current, {
      event: 'error',
      message: `启动失败: ${err.message}`,
      error: { message: err.message },
    })
    patchRun(runId, next)
    emit(next, 'task.failed', { error: next.error })
    activeJobs.delete(runId)
  })

  proc.on('close', (code) => {
    const job = activeJobs.get(runId)
    activeJobs.delete(runId)
    if (stdoutBuf.trim()) onChunk('\n', false)
    const current = runs.get(runId)
    if (!current) return
    if (job?.cancelled) {
      const next: ChecklistScmpRun = {
        ...current,
        status: 'cancelled',
        message: '已取消',
        completed_at: nowIso(),
        updated_at: nowIso(),
        exit_code: code,
        log_tail: [...current.log_tail, '已取消'].slice(-200),
      }
      patchRun(runId, next)
      emit(next, 'task.cancelled')
      return
    }
    if (current.status === 'pending' || current.status === 'running') {
      const ok = code === 0
      const rawFail = current.error || current.log_tail.slice(-12).join('\n') || `CLI 退出码 ${code}`
      const failMsg = compactChecklistScmpError(rawFail)
      const next: ChecklistScmpRun = {
        ...current,
        status: ok ? 'completed' : 'failed',
        progress: 100,
        exit_code: code,
        completed_at: nowIso(),
        updated_at: nowIso(),
        error: ok ? undefined : failMsg,
        message: ok ? (current.message || '全部处理完成') : failMsg,
      }
      patchRun(runId, next)
      emit(next, ok ? 'task.completed' : 'task.failed', { error: next.error })
    } else {
      patchRun(runId, { ...current, exit_code: code, updated_at: nowIso() })
    }
  })

  logger.info({ runId, url: input.url.trim() }, '[checklist-scmp-sync] started')
  return { run_id: runId }
}

export function cancelChecklistScmpSync(runId: string): { ok: boolean } {
  const job = activeJobs.get(runId)
  const run = runs.get(runId)
  if (!run) {
    const err = new Error('任务不存在')
    ;(err as Error & { status?: number }).status = 404
    throw err
  }
  if (!job || (run.status !== 'pending' && run.status !== 'running')) {
    return { ok: true }
  }
  job.cancelled = true
  killTree(job.proc)
  return { ok: true }
}
