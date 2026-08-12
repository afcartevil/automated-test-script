/**
 * 代码拉取 ExternalCapability（无 Agent）：
 * ensureBridgeReady → mkdir + repo init → tmux repo sync -c（system 再 vendor）
 *
 * 路径约定 A：
 *   Linux  /work/code/$USER/code-pull/<runId>/{system,vendor}
 *   Windows <mapped-root>\code-pull\<runId>\{system,vendor}
 */
import { randomBytes } from 'crypto'
import { logger } from '../../logger'
import { assertHarnessCliReady } from '../harness-version-gate'
import {
  bridgeCancel,
  bridgeExec,
  discoverBridgeReady,
  ensureBridgeReady,
} from '../adapt-pipeline/harness-bridge-exec'
import { buildTmuxKillCommand } from '../adapt-pipeline/ez-build-tmux'
import type {
  CapabilityEvent,
  CapabilityStatus,
  ExternalCapability,
  StageAvailability,
} from '../adapt-pipeline/types'
import {
  buildRepoInitCommand,
  buildRepoSyncTmuxPoll,
  buildRepoSyncTmuxStart,
  codePullLinuxPath,
  codePullRunRel,
  codePullWinPath,
  formatRepoSyncFailure,
  parseTmuxPollOutput,
  tmuxRepoSession,
  validateRepoInitCommand,
} from './repo-sync-tmux'
import { normalizeMappedRoot } from './result-parse'
import type { CodePullInput, CodePullResult } from './types'

const SYNC_TIMEOUT_MS = 8 * 60 * 60 * 1000
const INIT_TIMEOUT_SEC = 600
const POLL_TIMEOUT_SEC = 45
const POLL_INTERVAL_MS = 20_000

interface CodePullRunCtx {
  runId: string
  startedAt: number
  status: CapabilityStatus
  cancelled: boolean
  mappedRoot?: string
  systemInit: string
  vendorInit: string
  systemPathWin?: string
  systemPathLinux?: string
  vendorPathWin?: string
  vendorPathLinux?: string
  activeSession?: string
  seenLogLines: Set<string>
  listeners: Set<(ev: CapabilityEvent) => void>
}

const runs = new Map<string, CodePullRunCtx>()

function genRunId(): string {
  return `cpull-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

function emit(ctx: CodePullRunCtx, line?: string) {
  const ev: CapabilityEvent = {
    type: line ? 'log' : 'progress',
    status: ctx.status,
    line,
    phase: ctx.status.phase,
    progress: ctx.status.progress,
  }
  for (const fn of ctx.listeners) {
    try { fn(ev) } catch { /* ignore */ }
  }
}

function setStatus(ctx: CodePullRunCtx, patch: Partial<CapabilityStatus>, line?: string) {
  ctx.status = { ...ctx.status, ...patch }
  emit(ctx, line)
}

function bridgeOutput(result: { output?: string; error?: string }): string {
  return String(result.output || result.error || '')
}

/** 从 discover JSON 抽取首选 mapped-root */
export function pickMappedRootFromDiscover(raw: unknown, preferred?: string): string | undefined {
  if (preferred?.trim()) return normalizeMappedRoot(preferred.trim())
  if (!raw || typeof raw !== 'object') return undefined
  const obj = raw as Record<string, unknown>

  const tryList = (list: unknown): string | undefined => {
    if (!Array.isArray(list)) return undefined
    for (const item of list) {
      if (typeof item === 'string' && item.trim()) {
        return normalizeMappedRoot(item)
      }
      if (item && typeof item === 'object') {
        const rec = item as Record<string, unknown>
        if (rec.approved_for_runner === false || rec.suspicious_runner_root === true) continue
        const cand = String(
          rec.mapped_root || rec.mappedRoot || rec.root || rec.path || '',
        ).trim()
        if (cand) return normalizeMappedRoot(cand)
      }
    }
    return undefined
  }

  const direct = tryList(obj.mapped_roots)
    || tryList(obj.mappedRoots)
    || tryList(obj.runners)
    || tryList(obj.candidates)
  if (direct) return direct

  const data = obj.data as Record<string, unknown> | undefined
  if (data) {
    const fromData = tryList(data.mapped_roots)
      || tryList(data.mappedRoots)
      || tryList(data.runners)
      || tryList(data.candidates)
    if (fromData) return fromData
  }

  const single = String(obj.mapped_root || obj.mappedRoot || '').trim()
  return single ? normalizeMappedRoot(single) : undefined
}

function flushNewLogLines(ctx: CodePullRunCtx, lines: string[]) {
  for (const line of lines) {
    const key = line.slice(0, 240)
    if (ctx.seenLogLines.has(key)) continue
    ctx.seenLogLines.add(key)
    if (ctx.seenLogLines.size > 2000) {
      ctx.seenLogLines = new Set([...ctx.seenLogLines].slice(-1000))
    }
    emit(ctx, line.slice(0, 500))
  }
}

async function killSession(session: string | undefined, signal?: { cancelled: boolean }) {
  if (!session) return
  try {
    await bridgeExec(buildTmuxKillCommand(session), { timeoutSec: 30, signal })
  } catch { /* ignore */ }
}

function partialResult(ctx: CodePullRunCtx): Record<string, unknown> {
  return {
    mapped_root: ctx.mappedRoot,
    run_rel: codePullRunRel(ctx.runId),
    system_path_win: ctx.systemPathWin,
    system_path_linux: ctx.systemPathLinux,
    vendor_path_win: ctx.vendorPathWin,
    vendor_path_linux: ctx.vendorPathLinux,
    code_path_win: ctx.systemPathWin,
    code_path_linux: ctx.systemPathLinux,
  }
}

async function runRepoInit(
  ctx: CodePullRunCtx,
  kind: 'system' | 'vendor',
  linuxPath: string,
  initCmd: string,
  signal: { cancelled: boolean },
): Promise<void> {
  setStatus(ctx, {
    state: 'running',
    phase: `${kind}_init`,
    message: `${kind} repo init`,
    result: partialResult(ctx),
  }, `[${kind}] mkdir + repo init …`)

  const cmd = buildRepoInitCommand(linuxPath, initCmd)
  const res = await bridgeExec(cmd, { timeoutSec: INIT_TIMEOUT_SEC, signal })
  const out = bridgeOutput(res)
  for (const line of out.split(/\r?\n/).filter(Boolean).slice(-30)) {
    emit(ctx, `[${kind}:init] ${line.slice(0, 400)}`)
  }
  if (ctx.cancelled) throw new Error('已取消')
  if (Number(res.exit_code) !== 0 && String(res.status).toLowerCase() !== 'ok') {
    throw new Error(`${kind} repo init 失败: ${res.error || out.slice(0, 500) || `exit=${res.exit_code}`}`)
  }
  if (!/REPO_INIT_OK/.test(out) && Number(res.exit_code) !== 0) {
    throw new Error(`${kind} repo init 未确认成功`)
  }
  emit(ctx, `[${kind}] repo init 完成`)
}

async function runRepoSyncTmux(
  ctx: CodePullRunCtx,
  kind: 'system' | 'vendor',
  linuxPath: string,
  progressBase: number,
  progressSpan: number,
  signal: { cancelled: boolean },
): Promise<void> {
  const session = tmuxRepoSession(ctx.runId, kind)
  ctx.activeSession = session
  setStatus(ctx, {
    state: 'running',
    phase: `${kind}_sync`,
    progress: progressBase,
    message: `${kind} repo sync -c`,
    result: partialResult(ctx),
  }, `[${kind}] 启动 tmux repo sync -c …`)

  const start = await bridgeExec(buildRepoSyncTmuxStart({ session, linuxPath }), {
    timeoutSec: 60,
    signal,
  })
  const startOut = bridgeOutput(start)
  emit(ctx, startOut.split(/\r?\n/).find(l => l.includes('TMUX_STARTED')) || `[${kind}] tmux 已请求启动`)
  if (Number(start.exit_code) !== 0 && String(start.status).toLowerCase() !== 'ok') {
    throw new Error(`${kind} sync 启动失败: ${start.error || startOut.slice(0, 400)}`)
  }
  if (!/TMUX_STARTED:/.test(startOut)) {
    throw new Error(`${kind} sync tmux 未确认启动: ${startOut.slice(0, 400)}`)
  }

  const watchStarted = Date.now()
  let deadWithoutDone = 0
  while (Date.now() - watchStarted < SYNC_TIMEOUT_MS) {
    if (ctx.cancelled) {
      await killSession(session, signal)
      throw new Error('已取消')
    }

    let pollRaw = ''
    try {
      const poll = await bridgeExec(buildRepoSyncTmuxPoll(session), {
        timeoutSec: POLL_TIMEOUT_SEC,
        signal,
      })
      pollRaw = bridgeOutput(poll)
    } catch (err) {
      emit(ctx, `[${kind}] 轮询失败: ${(err as Error).message}`)
      await sleep(POLL_INTERVAL_MS)
      continue
    }

    const snap = parseTmuxPollOutput(pollRaw)
    const tagged = snap.lines.map(l => `[${kind}] ${l}`)
    flushNewLogLines(ctx, tagged)

    if (snap.doneCode != null) {
      if (snap.doneCode === 0) {
        emit(ctx, `[${kind}] repo sync 完成`)
        ctx.activeSession = undefined
        return
      }
      throw new Error(formatRepoSyncFailure({
        kind,
        lines: snap.lines,
        doneCode: snap.doneCode,
        fallback: `repo sync 失败 exit=${snap.doneCode}`,
      }))
    }

    if (!snap.alive) {
      deadWithoutDone += 1
      if (deadWithoutDone >= 2) {
        throw new Error(formatRepoSyncFailure({
          kind,
          lines: snap.lines,
          fallback: 'tmux 已结束但未找到 done 文件',
        }))
      }
      emit(ctx, `[${kind}] tmux 已结束，等待 done…`)
    } else {
      deadWithoutDone = 0
      const elapsed = Math.round((Date.now() - watchStarted) / 1000)
      const p = Math.min(
        progressBase + progressSpan - 1,
        progressBase + Math.floor((Date.now() - watchStarted) / SYNC_TIMEOUT_MS * progressSpan),
      )
      setStatus(ctx, {
        state: 'running',
        phase: `${kind}_sync`,
        progress: p,
        message: `${kind} sync ${elapsed}s`,
        result: partialResult(ctx),
      })
    }

    await sleep(POLL_INTERVAL_MS)
  }

  await killSession(session, signal)
  throw new Error(`${kind} repo sync 超时（>${Math.round(SYNC_TIMEOUT_MS / 3600000)}h）`)
}

async function runCodePull(ctx: CodePullRunCtx): Promise<void> {
  const signal = { cancelled: false }
  const watchCancel = setInterval(() => {
    if (ctx.cancelled) signal.cancelled = true
  }, 1000)

  try {
    setStatus(ctx, { state: 'running', progress: 3, phase: 'bridge', message: '确保 Bridge READY' }, '检查/拉起齐治 Bridge…')
    await ensureBridgeReady({
      timeoutMs: 3 * 60_000,
      onLog: (line) => emit(ctx, line),
      signal,
    })
    if (ctx.cancelled) throw new Error('已取消')

    const disc = discoverBridgeReady()
    const mapped = pickMappedRootFromDiscover(disc.raw, ctx.mappedRoot)
    if (!mapped) {
      throw new Error('未能 discover 到 mapped-root，请确认映射盘 / runner 已部署')
    }
    ctx.mappedRoot = mapped
    emit(ctx, `mapped-root: ${mapped}`)

    ctx.systemPathLinux = codePullLinuxPath(ctx.runId, 'system')
    ctx.vendorPathLinux = codePullLinuxPath(ctx.runId, 'vendor')
    ctx.systemPathWin = codePullWinPath(mapped, ctx.runId, 'system')
    ctx.vendorPathWin = codePullWinPath(mapped, ctx.runId, 'vendor')

    setStatus(ctx, {
      progress: 8,
      phase: 'paths',
      message: '已分配 system/vendor 目录',
      result: partialResult(ctx),
    }, `system → ${ctx.systemPathLinux}`)
    emit(ctx, `vendor → ${ctx.vendorPathLinux}`)

    // —— system ——
    await runRepoInit(ctx, 'system', ctx.systemPathLinux, ctx.systemInit, signal)
    setStatus(ctx, { progress: 15, result: partialResult(ctx) })
    await runRepoSyncTmux(ctx, 'system', ctx.systemPathLinux, 15, 40, signal)

    // —— vendor ——
    await runRepoInit(ctx, 'vendor', ctx.vendorPathLinux, ctx.vendorInit, signal)
    setStatus(ctx, { progress: 58, result: partialResult(ctx) })
    await runRepoSyncTmux(ctx, 'vendor', ctx.vendorPathLinux, 58, 40, signal)

    const result: CodePullResult = {
      mapped_root: mapped,
      run_rel: codePullRunRel(ctx.runId),
      system_path_win: ctx.systemPathWin!,
      system_path_linux: ctx.systemPathLinux!,
      vendor_path_win: ctx.vendorPathWin!,
      vendor_path_linux: ctx.vendorPathLinux!,
      code_path_win: ctx.systemPathWin,
      code_path_linux: ctx.systemPathLinux,
      duration_ms: Date.now() - ctx.startedAt,
    }
    ctx.status = {
      state: 'success',
      progress: 100,
      phase: 'done',
      message: 'system + vendor 拉取完成',
      result: result as unknown as Record<string, unknown>,
    }
    emit(ctx, `完成 system=${result.system_path_win}`)
    emit(ctx, `完成 vendor=${result.vendor_path_win}`)
  } finally {
    clearInterval(watchCancel)
  }
}

export const codePullCapability: ExternalCapability<CodePullInput> = {
  id: 'code-pull-repo-sync',

  async probe(): Promise<StageAvailability> {
    try {
      assertHarnessCliReady()
    } catch (err) {
      return { available: false, reason: (err as Error).message }
    }
    return { available: true }
  },

  async start(input: CodePullInput): Promise<{ runId: string }> {
    const systemInit = validateRepoInitCommand(input.systemRepoInit, 'system')
    const vendorInit = validateRepoInitCommand(input.vendorRepoInit, 'vendor')

    const runId = genRunId()
    const ctx: CodePullRunCtx = {
      runId,
      startedAt: Date.now(),
      status: { state: 'pending', progress: 0, phase: 'init' },
      cancelled: false,
      mappedRoot: input.mappedRoot ? normalizeMappedRoot(input.mappedRoot) : undefined,
      systemInit,
      vendorInit,
      seenLogLines: new Set(),
      listeners: new Set(),
    }
    runs.set(runId, ctx)

    void runCodePull(ctx).catch((err) => {
      logger.warn({ err: (err as Error).message, runId }, '[code-pull] failed')
      if (ctx.cancelled) {
        ctx.status = { state: 'cancelled', error: '已取消', result: partialResult(ctx) }
      } else {
        ctx.status = {
          state: 'failed',
          error: (err as Error).message,
          phase: ctx.status.phase,
          progress: ctx.status.progress,
          result: partialResult(ctx),
        }
      }
      emit(ctx, (err as Error).message)
    })

    return { runId }
  },

  async getStatus(runId: string): Promise<CapabilityStatus> {
    const ctx = runs.get(runId)
    if (!ctx) return { state: 'failed', error: '未知代码拉取任务' }
    return ctx.status
  },

  async cancel(runId: string): Promise<void> {
    const ctx = runs.get(runId)
    if (!ctx) return
    ctx.cancelled = true
    ctx.status = { state: 'cancelled', error: '已取消', result: partialResult(ctx) }
    await killSession(ctx.activeSession)
    try { await bridgeCancel() } catch { /* ignore */ }
    emit(ctx, '已请求取消')
  },

  subscribe(runId: string, onEvent: (ev: CapabilityEvent) => void): () => void {
    const ctx = runs.get(runId)
    if (!ctx) return () => {}
    ctx.listeners.add(onEvent)
    onEvent({
      type: 'progress',
      status: ctx.status,
      phase: ctx.status.phase,
      progress: ctx.status.progress,
    })
    return () => { ctx.listeners.delete(onEvent) }
  },
}

export function resetCodePullCapabilityForTest(): void {
  runs.clear()
}

/**
 * BFF 重启后：若已有路径与 init 命令，无法可靠续跑半截 tmux，标记由 service 处理。
 * 保留导出以兼容旧 service import；现改为 no-op 返回失败提示由 service 决策。
 */
export async function resumeCodePullWatch(_opts: {
  capabilityRunId: string
  [k: string]: unknown
}): Promise<{ runId: string }> {
  throw new Error('repo sync 长跑不支持跨进程续跑，请重新开始拉取')
}
