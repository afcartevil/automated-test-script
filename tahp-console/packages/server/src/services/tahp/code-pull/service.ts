/**
 * 代码拉取编排：Capability ↔ 落盘 run ↔ TaskStream（Socket.IO /tahp-run）
 * 无 Hermes Agent；长跑为堡垒机 tmux repo sync。
 */
import { logger } from '../../logger'
import { getTaskStream } from '../task-stream'
import { codePullCapability } from './capability'
import {
  appendCodePullLog,
  createCodePullRun,
  getCodePullRun,
  listActiveCodePullRuns,
  listCodePullRuns,
  patchCodePullRun,
  saveCodePullRun,
} from './store'
import type { CodePullInput, CodePullResult, CodePullRunRecord, CodePullRunSummary } from './types'

const unsubs = new Map<string, () => void>()
let recovered = false

function emit(taskId: string, type: string, payload: Record<string, unknown> = {}) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function persistLog(runId: string, line: string) {
  appendCodePullLog(runId, line)
  const run = getCodePullRun(runId)
  if (run && run.log_tail.length % 20 === 0) {
    saveCodePullRun(run)
  }
}

function applyPathFields(
  patch: Partial<CodePullRunRecord>,
  result: Record<string, unknown> | undefined,
) {
  if (!result) return
  if (result.mapped_root) patch.mapped_root = String(result.mapped_root)
  if (result.system_path_win) {
    patch.system_path_win = String(result.system_path_win)
    patch.code_path_win = String(result.system_path_win)
  }
  if (result.system_path_linux) {
    patch.system_path_linux = String(result.system_path_linux)
    patch.code_path_linux = String(result.system_path_linux)
  }
  if (result.vendor_path_win) patch.vendor_path_win = String(result.vendor_path_win)
  if (result.vendor_path_linux) patch.vendor_path_linux = String(result.vendor_path_linux)
  if (Array.isArray(result.failed_repos)) {
    patch.failed_repos = result.failed_repos as CodePullRunRecord['failed_repos']
  }
}

function bindCapability(run: CodePullRunRecord, capabilityRunId: string) {
  const prev = unsubs.get(run.run_id)
  if (prev) prev()

  const off = codePullCapability.subscribe?.(capabilityRunId, (ev) => {
    if (ev.line) {
      persistLog(run.run_id, ev.line)
      emit(run.run_id, 'task.message', { level: 'stream', text: ev.line, phase: ev.phase })
    }
    const st = ev.status
    if (!st) return

    const patch: Partial<CodePullRunRecord> = {
      phase: st.phase,
      progress: st.progress,
      message: st.message,
      capability_run_id: capabilityRunId,
    }

    if (st.state === 'running' || st.state === 'pending') {
      patch.status = 'running'
      applyPathFields(patch, st.result)
      patchCodePullRun(run.run_id, patch)
      emit(run.run_id, 'task.phase', {
        phase: st.phase,
        progress: st.progress,
        message: st.message,
        ...patch,
      })
    } else if (st.state === 'success') {
      const result = (st.result || {}) as Partial<CodePullResult>
      patch.status = 'completed'
      applyPathFields(patch, result as Record<string, unknown>)
      patch.duration_ms = result.duration_ms
      patch.completed_at = new Date().toISOString()
      patch.progress = 100
      patch.message = '代码拉取完成'
      const saved = patchCodePullRun(run.run_id, patch)
      emit(run.run_id, 'task.completed', {
        result,
        system_path_win: result.system_path_win,
        vendor_path_win: result.vendor_path_win,
        system_path_linux: result.system_path_linux,
        vendor_path_linux: result.vendor_path_linux,
      })
      if (saved) saveCodePullRun(saved)
      unsubs.get(run.run_id)?.()
      unsubs.delete(run.run_id)
    } else if (st.state === 'failed' || st.state === 'cancelled') {
      patch.status = st.state === 'cancelled' ? 'cancelled' : 'failed'
      patch.error = st.error
      patch.completed_at = new Date().toISOString()
      applyPathFields(patch, st.result)
      const saved = patchCodePullRun(run.run_id, patch)
      emit(run.run_id, st.state === 'cancelled' ? 'task.cancelled' : 'task.failed', {
        error: st.error,
        failed_repos: patch.failed_repos,
      })
      if (saved) saveCodePullRun(saved)
      unsubs.get(run.run_id)?.()
      unsubs.delete(run.run_id)
    }
  })

  if (off) unsubs.set(run.run_id, off)
}

function labelFromInits(systemInit: string, vendorInit: string): string {
  const m = systemInit.match(/-m\s+(\S+)/i) || vendorInit.match(/-m\s+(\S+)/i)
  if (m?.[1]) return m[1].replace(/\.xml$/i, '')
  const b = systemInit.match(/-b\s+(\S+)/i)
  if (b?.[1]) return `repo-${b[1]}`
  return `repo-${new Date().toISOString().slice(0, 16).replace(/[T:]/g, '')}`
}

export async function probeCodePull(): Promise<{ available: boolean; reason?: string }> {
  return codePullCapability.probe()
}

export async function startCodePull(input: {
  system_repo_init: string
  vendor_repo_init: string
  mapped_root?: string
}): Promise<{ ok: true; run_id: string } | { ok: false; error: string }> {
  const systemInit = String(input.system_repo_init || '').trim()
  const vendorInit = String(input.vendor_repo_init || '').trim()
  if (!systemInit || !vendorInit) {
    return { ok: false, error: '请同时填写 system 与 vendor 的 repo init 命令' }
  }

  const probe = await codePullCapability.probe()
  if (!probe.available) {
    return { ok: false, error: probe.reason || '代码拉取能力不可用' }
  }

  const run = createCodePullRun({
    label: labelFromInits(systemInit, vendorInit),
    systemRepoInit: systemInit,
    vendorRepoInit: vendorInit,
  })
  emit(run.run_id, 'task.started', {
    project_name: run.project_name,
    message: '开始 system/vendor repo 拉取',
  })

  try {
    const capInput: CodePullInput = {
      systemRepoInit: systemInit,
      vendorRepoInit: vendorInit,
      mappedRoot: input.mapped_root,
    }
    const { runId: capId } = await codePullCapability.start(capInput)
    patchCodePullRun(run.run_id, {
      status: 'running',
      capability_run_id: capId,
      phase: 'init',
      progress: 1,
    })
    bindCapability(run, capId)
  } catch (err) {
    patchCodePullRun(run.run_id, {
      status: 'failed',
      error: (err as Error).message,
      completed_at: new Date().toISOString(),
    })
    emit(run.run_id, 'task.failed', { error: (err as Error).message })
    return { ok: false, error: (err as Error).message }
  }

  return { ok: true, run_id: run.run_id }
}

export function getCodePullRunDetail(runId: string): CodePullRunRecord | undefined {
  return getCodePullRun(runId)
}

export function listCodePullRunSummaries(limit = 50): CodePullRunSummary[] {
  return listCodePullRuns(limit)
}

export async function cancelCodePull(runId: string): Promise<{ ok: boolean; error?: string }> {
  const run = getCodePullRun(runId)
  if (!run) return { ok: false, error: '任务不存在' }
  if (run.status !== 'running' && run.status !== 'pending') {
    return { ok: false, error: `任务已结束（${run.status}）` }
  }
  if (run.capability_run_id) {
    try {
      await codePullCapability.cancel(run.capability_run_id)
    } catch (err) {
      logger.warn({ err: (err as Error).message, runId }, '[code-pull] cancel capability')
    }
  }
  patchCodePullRun(runId, {
    status: 'cancelled',
    error: '已取消',
    completed_at: new Date().toISOString(),
  })
  emit(runId, 'task.cancelled', { error: '已取消' })
  unsubs.get(runId)?.()
  unsubs.delete(runId)
  return { ok: true }
}

/**
 * BFF 启动时：进行中的 tmux sync 无法可靠接管，标记失败并提示重跑。
 */
export function recoverCodePullRuns(): void {
  if (recovered) return
  recovered = true
  for (const run of listActiveCodePullRuns()) {
    patchCodePullRun(run.run_id, {
      status: 'failed',
      error: '服务重启导致拉取中断（repo sync 不支持跨进程续跑），请重新开始',
      completed_at: new Date().toISOString(),
      message: 'lost_after_restart',
    })
    emit(run.run_id, 'task.failed', {
      error: '服务重启导致拉取中断，请重新开始',
    })
  }
}

export function resetCodePullServiceForTest(): void {
  recovered = false
  for (const off of unsubs.values()) off()
  unsubs.clear()
}
