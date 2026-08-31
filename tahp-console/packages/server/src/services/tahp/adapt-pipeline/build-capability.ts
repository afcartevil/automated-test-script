/**
 * 编译能力：经 bridgeExec（升级机 asf bridge cmd，旧机 bridge-exec）部署脚本，
 * tmux 内跑 ez-build.sh，再以短命令轮询 tmux 会话 + 日志心跳 / done 文件。
 */
import { randomBytes } from 'crypto'
import { join } from 'path'
import { logger } from '../../logger'
import { assertHarnessCliReady } from '../harness-version-gate'
import { tahpPaths } from '../paths'
import {
  buildResultFilePath,
  writeBuildResult,
  type BuildResultContract,
} from './build-result-contract'
import {
  bridgeCancel,
  bridgeExec,
  ensureBridgeReady,
  loadEzBuildScript,
} from './harness-bridge-exec'
import { isAsfBridgeSshDisconnected } from '../host-tool-runtime'
import {
  EA_BUILD_DIR,
  copyConfJsonToMappedEaBuild,
  buildDeployCommand,
  buildTmuxKillCommand,
  buildTmuxPollCommand,
  buildTmuxStartCommand,
  detectBuildFailureInLog,
  detectBuildSuccessInLog,
  parseTmuxPollOutput,
  tmuxSessionName,
  tmuxStartConfirmed,
} from './ez-build-tmux'
import { resolveLatestTrsysConf } from './trsys-conf-share'
import {
  composeBuildTargetRaw,
  needsTrsysForTargetOs,
  resolveEzBuildTargets,
  winMappedPathToLinuxWorkCode,
  winMappedPathToLinuxWorkCodeOptional,
} from './win-path-to-linux'
import type {
  BuildCapabilityInput,
  CapabilityEvent,
  CapabilityStatus,
  ExternalCapability,
  StageAvailability,
} from './types'

/** 整机编译可达数小时 */
const BUILD_TIMEOUT_MS = 8 * 60 * 60 * 1000
const DEPLOY_TIMEOUT_SEC = 120
const TMUX_START_TIMEOUT_SEC = 60
const POLL_TIMEOUT_SEC = 45
/** ez-build KEEPALIVE_INTERVAL=15，轮询略宽 */
const POLL_INTERVAL_MS = 20_000
/** 心跳超时告警（进行中…） */
const HEARTBEAT_STALE_MS = 5 * 60_000

interface BuildRunCtx {
  runId: string
  pipelineRunId: string
  project: string
  startedAt: number
  status: CapabilityStatus
  cancelled: boolean
  resultPath: string
  tmuxSession?: string
  logFile?: string
  doneFile?: string
  lastHeartbeatAt?: number
  seenLogLines: Set<string>
  listeners: Set<(ev: CapabilityEvent) => void>
}

const runs = new Map<string, BuildRunCtx>()

function genRunId(): string {
  return `build-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function emit(ctx: BuildRunCtx, line?: string) {
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

function toCapabilityResult(result: BuildResultContract): Record<string, unknown> {
  return {
    artifactsDir: result.artifacts_dir,
    artifacts_dir: result.artifacts_dir,
    pkgPath: result.pkg_path,
    pkg_path: result.pkg_path,
    artifacts: result.artifacts,
    durationMs: result.duration_ms,
    failedStage: result.failed_stage,
    skillId: result.skill_id,
    status: result.status,
    notes: result.notes,
  }
}

function applyResult(ctx: BuildRunCtx, result: BuildResultContract) {
  if (result.status === 'pass') {
    ctx.status = {
      state: 'success',
      progress: 100,
      phase: 'done',
      message: '编译成功',
      result: toCapabilityResult(result),
    }
  } else {
    ctx.status = {
      state: 'failed',
      phase: result.failed_stage ?? 'build',
      error: result.error || '编译失败',
      result: toCapabilityResult(result),
    }
  }
  emit(ctx)
}

function isKeepaliveLine(line: string): boolean {
  return /进行中\.\.\./.test(line) || /finished: status=/i.test(line)
}

function flushNewLogLines(ctx: BuildRunCtx, lines: string[]) {
  for (const line of lines) {
    const key = line.slice(0, 240)
    if (ctx.seenLogLines.has(key)) continue
    ctx.seenLogLines.add(key)
    if (ctx.seenLogLines.size > 2000) {
      const arr = [...ctx.seenLogLines]
      ctx.seenLogLines = new Set(arr.slice(-1000))
    }
    emit(ctx, line.slice(0, 500))
    if (isKeepaliveLine(line)) {
      ctx.lastHeartbeatAt = Date.now()
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

function flushLogLines(ctx: BuildRunCtx, buf: { text: string }, chunk: string) {
  buf.text += chunk
  const parts = buf.text.split(/\r?\n/)
  buf.text = parts.pop() ?? ''
  for (const line of parts) {
    const t = line.trim()
    if (t) emit(ctx, t.slice(0, 500))
  }
}

function bridgeOutput(result: { output?: string; error?: string }): string {
  return String(result.output || result.error || '')
}

async function killTmuxSession(session: string, signal?: { cancelled: boolean }): Promise<void> {
  try {
    await bridgeExec(buildTmuxKillCommand(session), {
      timeoutSec: 30,
      signal,
    })
  } catch { /* ignore */ }
}

async function runEzBuild(ctx: BuildRunCtx, input: BuildCapabilityInput): Promise<void> {
  const started = Date.now()
  const needPack = Boolean(input.needPack)
  ctx.status = { state: 'running', progress: 3, phase: 'init', message: '确保 ASF Bridge READY' }
  emit(ctx, '检查 / 静默拉起 ASF Bridge…')

  const signal = { cancelled: false }
  const watchCancel = setInterval(() => {
    if (ctx.cancelled) signal.cancelled = true
  }, 1000)

  try {
    await ensureBridgeReady({
      timeoutMs: 3 * 60_000,
      signal,
      onLog: (line) => emit(ctx, line),
    })
  } catch (err) {
    clearInterval(watchCancel)
    throw err
  }

  if (ctx.cancelled) {
    clearInterval(watchCancel)
    ctx.status = { state: 'cancelled', error: '已取消' }
    emit(ctx)
    return
  }

  const systemLinux = winMappedPathToLinuxWorkCodeOptional(input.systemPath ?? '')
  const vendorLinux = winMappedPathToLinuxWorkCode(input.vendorPath)
  const trsysEnabled = needsTrsysForTargetOs(input.toOs)
  const trsysLinux = trsysEnabled
    ? winMappedPathToLinuxWorkCodeOptional(input.trsysRootPath ?? '')
    : ''
  const targets = resolveEzBuildTargets({
    targets: input.buildTargets,
    trsysRoot: trsysEnabled ? (input.trsysRootPath ?? '') : input.trsysRootPath,
    toOs: input.toOs,
  })
  const targetRaw = composeBuildTargetRaw(targets, input.needPack)
  const session = tmuxSessionName(ctx.runId, input.project)
  ctx.tmuxSession = session
  ctx.logFile = `${EA_BUILD_DIR}/${session}.log`
  ctx.doneFile = `${EA_BUILD_DIR}/${session}.done`

  ctx.status = { state: 'running', progress: 10, phase: 'deploy', message: '部署 ez-build.sh' }
  emit(ctx, `部署脚本到 ${EA_BUILD_DIR}`)
  emit(ctx, `system=${systemLinux} vendor=${vendorLinux} trsys=${trsysLinux || '(empty)'} targets=${targetRaw}`)

  const script = loadEzBuildScript()
  const scriptB64 = Buffer.from(script, 'utf-8').toString('base64')

  try {
    const deployOut = { text: '' }
    const deploy = await bridgeExec(buildDeployCommand(scriptB64), {
      timeoutSec: DEPLOY_TIMEOUT_SEC,
      signal,
      onStdout: (c) => flushLogLines(ctx, deployOut, c),
      onStderr: (c) => flushLogLines(ctx, deployOut, c),
    })
    if (ctx.cancelled) {
      ctx.status = { state: 'cancelled', error: '已取消' }
      emit(ctx)
      return
    }
    if (Number(deploy.exit_code) !== 0 && String(deploy.status).toLowerCase() !== 'ok') {
      throw new Error(deploy.error || deploy.output || `部署脚本失败 exit=${deploy.exit_code}`)
    }
    if (deploy.output) emit(ctx, String(deploy.output).slice(0, 300))

    const needPipeTrsys = targets.includes('trsys') && !trsysLinux
    if (needPipeTrsys) {
      const branch = String(input.trsysBranch ?? '').trim()
      if (!branch) {
        emit(ctx, '未选 trsys 分支，跳过拉取 conf.json（请自行放到 ea-build）')
      } else {
        ctx.status = { state: 'running', progress: 14, phase: 'deploy', message: '部署 conf.json' }
        emit(ctx, `从共享盘拉取 conf.json（分支 ${branch}）`)
        const conf = resolveLatestTrsysConf(branch, input.variant)
        emit(ctx, `conf snapshot=${conf.snapshot}`)
        const dest = copyConfJsonToMappedEaBuild(conf.confPath)
        emit(ctx, `已拷贝到 ${dest}（映射盘，对应 ${EA_BUILD_DIR}/conf.json）`)
      }
    }

    ctx.status = { state: 'running', progress: 20, phase: 'tmux', message: 'tmux 启动 ez-build' }
    emit(ctx, `tmux 会话启动: ${session}`)

    const start = await bridgeExec(
      buildTmuxStartCommand({
        session,
        project: input.project,
        variant: input.variant,
        buildFlag: input.buildFlag,
        targetRaw,
        systemLinux,
        vendorLinux,
        trsysLinux,
        sysVersion: input.sysVersion,
      }),
      { timeoutSec: TMUX_START_TIMEOUT_SEC, signal },
    )
    const startOut = bridgeOutput(start)
    if (ctx.cancelled) {
      await killTmuxSession(session, signal)
      ctx.status = { state: 'cancelled', error: '已取消' }
      emit(ctx)
      return
    }
    if (isAsfBridgeSshDisconnected(startOut) || isAsfBridgeSshDisconnected(start.error || '')) {
      throw new Error(`齐治 SSH 已断开，tmux 未真正启动: ${(start.error || startOut).slice(0, 400)}`)
    }
    if (Number(start.exit_code) !== 0 && String(start.status).toLowerCase() !== 'ok') {
      throw new Error(start.error || startOut || `tmux 启动失败 exit=${start.exit_code}`)
    }
    if (!tmuxStartConfirmed(startOut, session)) {
      throw new Error(`tmux 启动未确认（须 TMUX_STARTED:${session}）: ${startOut.slice(0, 500)}`)
    }
    emit(ctx, startOut.split(/\r?\n/).find(l => l.includes('TMUX_STARTED')) || `已启动 ${session}`)
    emit(ctx, '开始编译（tmux）…')
    ctx.lastHeartbeatAt = Date.now()

    ctx.status = { state: 'running', progress: 25, phase: 'build', message: 'tmux 编译中' }

    let deadWithoutDone = 0
    while (Date.now() - started < BUILD_TIMEOUT_MS) {
      if (ctx.cancelled) {
        await killTmuxSession(session, signal)
        ctx.status = { state: 'cancelled', error: '已取消' }
        emit(ctx)
        return
      }

      let pollRaw = ''
      let pollError = ''
      try {
        const poll = await bridgeExec(buildTmuxPollCommand(session), {
          timeoutSec: POLL_TIMEOUT_SEC,
          signal,
        })
        pollRaw = bridgeOutput(poll)
        pollError = String(poll.error || '')
        if (Number(poll.exit_code) !== 0 && String(poll.status).toLowerCase() !== 'ok' && !pollRaw) {
          emit(ctx, `轮询 bridge-exec 异常 exit=${poll.exit_code}`)
          await sleep(POLL_INTERVAL_MS)
          continue
        }
      } catch (err) {
        emit(ctx, `轮询失败: ${(err as Error).message}`)
        await sleep(POLL_INTERVAL_MS)
        continue
      }

      const snap = parseTmuxPollOutput(pollRaw)
      const elapsed = Math.round((Date.now() - started) / 1000)
      const pollLost = isAsfBridgeSshDisconnected(pollRaw) || isAsfBridgeSshDisconnected(pollError)
      if (pollLost || !snap.recognized) {
        emit(
          ctx,
          pollLost
            ? `齐治已回到登录界面，未在远端 shell 中轮询 tmux（${elapsed}s）`
            : `轮询未得到 tmux=alive/dead（${elapsed}s），忽略本次采样`,
        )
        if (pollLost) {
          throw new Error('齐治 SSH 已断开（密码/账号选择界面）。远端 tmux 可能仍在运行，请确认凭据后重新编译。')
        }
        await sleep(POLL_INTERVAL_MS)
        continue
      }
      flushNewLogLines(ctx, snap.lines)

      const logFail = detectBuildFailureInLog(snap.lines)
      const hbAge = ctx.lastHeartbeatAt ? Date.now() - ctx.lastHeartbeatAt : 0

      if (snap.alive && hbAge > HEARTBEAT_STALE_MS) {
        emit(ctx, `心跳超时告警: ${Math.round(hbAge / 1000)}s 未见「进行中…」(tmux 仍 alive)`)
        ctx.lastHeartbeatAt = Date.now()
      }

      // done 文件是权威退出码（避免 bridge-exec 误报 0）
      if (snap.doneCode != null) {
        const durationMs = Date.now() - started
        const success = snap.doneCode === 0 && !logFail
        if (success) {
          const pkgPath = `Z:\\ea-build\\output_version_${input.project}`
          const sawPack = detectBuildSuccessInLog(snap.lines, true)
          const contract: BuildResultContract = {
            schema_version: 1,
            status: 'pass',
            duration_ms: durationMs,
            skill_id: 'ez-build',
            pkg_path: needPack || sawPack ? pkgPath : undefined,
            artifacts_dir: needPack || sawPack ? pkgPath : undefined,
            notes: `ea-build tmux=${session} targets=${targetRaw}`,
          }
          writeBuildResult(ctx.resultPath, contract)
          applyResult(ctx, contract)
          return
        }
        const contract: BuildResultContract = {
          schema_version: 1,
          status: 'fail',
          failed_stage: 'build',
          error: logFail || `ez-build 失败 exit_code=${snap.doneCode}`,
          duration_ms: durationMs,
          skill_id: 'ez-build',
          notes: snap.lines.slice(-30).join('\n').slice(0, 2000),
        }
        writeBuildResult(ctx.resultPath, contract)
        applyResult(ctx, contract)
        return
      }

      if (!snap.alive) {
        deadWithoutDone += 1
        if (logFail || deadWithoutDone >= 2) {
          const contract: BuildResultContract = {
            schema_version: 1,
            status: 'fail',
            failed_stage: 'build',
            error: logFail || 'tmux 会话已结束，但未找到 done 文件',
            duration_ms: Date.now() - started,
            skill_id: 'ez-build',
            notes: snap.lines.slice(-30).join('\n').slice(0, 2000),
          }
          writeBuildResult(ctx.resultPath, contract)
          applyResult(ctx, contract)
          return
        }
        emit(ctx, `tmux 已结束，等待 done 文件… (${elapsed}s)`)
      } else {
        deadWithoutDone = 0
        const p = Math.min(90, 25 + Math.floor((Date.now() - started) / BUILD_TIMEOUT_MS * 65))
        ctx.status = {
          state: 'running',
          progress: p,
          phase: 'build',
          message: `tmux 编译中 ${elapsed}s`
            + (ctx.lastHeartbeatAt
              ? ` · 心跳 ${Math.round((Date.now() - ctx.lastHeartbeatAt) / 1000)}s 前`
              : ''),
        }
        emit(ctx)
      }

      await sleep(POLL_INTERVAL_MS)
    }

    await killTmuxSession(session, signal)
    throw new Error(`齐治 tmux 编译超时（>${Math.round(BUILD_TIMEOUT_MS / 3600000)}h） session=${session}`)
  } finally {
    clearInterval(watchCancel)
  }
}

export const buildCapability: ExternalCapability<BuildCapabilityInput> = {
  id: 'ez-build-remote',

  async probe(): Promise<StageAvailability> {
    try {
      assertHarnessCliReady()
    } catch (err) {
      return { available: false, reason: (err as Error).message }
    }
    try {
      loadEzBuildScript()
    } catch (err) {
      return { available: false, reason: (err as Error).message }
    }
    return { available: true }
  },

  async start(input: BuildCapabilityInput): Promise<{ runId: string }> {
    if (!input.project?.trim()) throw new Error('缺少 project')
    if (!input.vendorPath?.trim()) throw new Error('缺少 NEW_VENDOR_ROOT')
    if (!input.variant?.trim()) throw new Error('缺少 variant')
    if (!input.buildFlag?.trim()) throw new Error('缺少 build_flag')
    const needSystem = Boolean(input.needPack) || (input.buildTargets ?? []).includes('sys')
    if (needSystem && !input.systemPath?.trim()) throw new Error('缺少 NEW_SYSTEM_ROOT')

    const runId = genRunId()
    const resultPath = buildResultFilePath(
      join(tahpPaths.reportsDir, 'adapt-pipeline', input.pipelineRunId),
    )
    const ctx: BuildRunCtx = {
      runId,
      pipelineRunId: input.pipelineRunId,
      project: input.project.trim(),
      startedAt: Date.now(),
      status: { state: 'pending', progress: 0, phase: 'init' },
      cancelled: false,
      resultPath,
      seenLogLines: new Set(),
      listeners: new Set(),
    }
    runs.set(runId, ctx)

    void runEzBuild(ctx, input).catch((err) => {
      logger.warn({ err: (err as Error).message, runId }, '[build-capability] ez-build failed')
      const contract: BuildResultContract = {
        schema_version: 1,
        status: 'fail',
        failed_stage: 'build',
        error: (err as Error).message,
        skill_id: 'ez-build',
      }
      try { writeBuildResult(ctx.resultPath, contract) } catch { /* ignore */ }
      applyResult(ctx, contract)
      emit(ctx, (err as Error).message)
    })

    return { runId }
  },

  async getStatus(runId: string): Promise<CapabilityStatus> {
    const ctx = runs.get(runId)
    if (!ctx) return { state: 'failed', error: '未知编译任务' }
    return ctx.status
  },

  async cancel(runId: string): Promise<void> {
    const ctx = runs.get(runId)
    if (!ctx) return
    ctx.cancelled = true
    ctx.status = { state: 'cancelled', error: '已取消' }
    if (ctx.tmuxSession) {
      try { await killTmuxSession(ctx.tmuxSession) } catch { /* ignore */ }
    }
    try { await bridgeCancel() } catch { /* ignore */ }
    emit(ctx)
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
