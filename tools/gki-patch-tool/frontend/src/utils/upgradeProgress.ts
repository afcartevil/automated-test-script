import { effectiveUpgradeStatus } from './upgrade'

export const UPGRADE_STEP_DEFS = [
  { key: 'prepare', icon: '🔧', label: '准备环境', hint: '检查 git 仓库、工作区、创建备份分支' },
  { key: 'apply', icon: '📦', label: '合入 Patch', hint: 'git am --3way 或 git apply --reject' },
  { key: 'build', icon: '🔨', label: '编译验证', hint: '在指定目录执行编译命令' },
  { key: 'commit', icon: '💾', label: '提交代码', hint: '编译成功后统一 git commit / push' },
  { key: 'done', icon: '✅', label: '完成', hint: '升级流程结束' },
] as const

const STEP_ORDER = UPGRADE_STEP_DEFS.map((s) => s.key)

/** Map backend/internal phases to a visible step key in UPGRADE_STEP_DEFS. */
export function effectiveUpgradePhase(job?: Record<string, any>, prog?: Record<string, any>): string {
  job = job || {}
  prog = prog || {}
  let phase = String(prog.phase || job.phase || '').trim()

  if (!phase || phase === 'resume') {
    phase = String(
      job.options?.last_active_phase
        || job.options?.resume_point?.phase
        || '',
    ).trim()
  }

  const phaseTimings = (prog.phase_timings || job.options?.phase_timings || {}).phases || {}
  const buildTiming = phaseTimings.build
  const buildFixRunning = Boolean(
    (prog.build_fix || job.options?.build_fix || {}).status === 'running',
  )

  if (buildTiming?.running || buildFixRunning || phase === 'build_fix' || phase === 'build_failed') {
    return 'build'
  }

  const alias: Record<string, string> = {
    conflicts: 'apply',
    applied: 'build',
    committed: 'commit',
    commit_failed: 'commit',
    cancelled: 'prepare',
    failed: 'prepare',
  }
  if (alias[phase]) return alias[phase]
  if (STEP_ORDER.includes(phase as (typeof STEP_ORDER)[number])) return phase
  return 'prepare'
}

export function isBuildPhaseActive(job?: Record<string, any>, prog?: Record<string, any>): boolean {
  job = job || {}
  prog = prog || {}
  const phase = String(prog.phase || job.phase || '').trim()
  if (phase === 'build' || phase === 'build_fix') return true
  const buildTiming = (prog.phase_timings || job.options?.phase_timings || {}).phases?.build
  if (buildTiming?.running) return true
  if ((prog.build_fix || job.options?.build_fix || {}).status === 'running') return true
  if (prog.status === 'running' && ['build', 'build_fix'].includes(phase)) return true
  return false
}

export const UPGRADE_STATE_LABEL: Record<string, string> = {
  done: '✓ 完成',
  running: '▶ 进行中',
  pending: '○ 等待',
  conflicts: '⚠ 有冲突',
  manual: '👆 待手动',
  skipped: '— 跳过',
  failed: '✗ 失败',
  cancelled: '⊘ 已取消',
}

export function upgradeStepState(
  stepKey: string,
  job?: Record<string, any>,
  prog?: Record<string, any>,
): string {
  job = job || {}
  prog = prog || {}
  const status = effectiveUpgradeStatus(job, prog) || job.status || prog.status || ''
  const phase = effectiveUpgradePhase(job, prog)
  const options = job.options || {}
  const order = STEP_ORDER
  const ki = order.indexOf(stepKey as (typeof order)[number])
  if (ki < 0) return 'pending'

  if (status === 'completed') return stepKey === 'done' ? 'done' : ki <= order.indexOf('done') ? 'done' : 'pending'

  if (status === 'cancelled') {
    const pi = Math.max(0, order.indexOf(phase as (typeof order)[number]))
    if (ki < pi) return 'done'
    if (ki === pi) return 'cancelled'
    return 'pending'
  }

  if (status === 'failed') {
    const pi = Math.max(0, order.indexOf(phase as (typeof order)[number]))
    if (ki < pi) return 'done'
    if (ki === pi) return 'failed'
    return 'pending'
  }

  if (status === 'conflicts') {
    if (stepKey === 'apply') return 'conflicts'
    if (ki < order.indexOf('apply')) return 'done'
    return 'pending'
  }

  if (status === 'applied') {
    if (ki <= order.indexOf('apply')) return 'done'
    if (stepKey === 'build') return options.auto_build ? 'pending' : 'manual'
    if (stepKey === 'commit') return 'pending'
    return 'pending'
  }

  if (status === 'committed' || status === 'build_failed' || status === 'commit_failed') {
    if (isBuildPhaseActive(job, prog) && stepKey === 'build') return 'running'
    if (ki <= order.indexOf('apply')) return 'done'
    if (stepKey === 'build') {
      if (status === 'build_failed') return 'failed'
      if (status === 'commit_failed' || status === 'committed') return 'done'
      return options.auto_build ? 'done' : 'manual'
    }
    if (stepKey === 'commit') {
      if (status === 'commit_failed') return 'failed'
      return status === 'committed' ? 'done' : 'pending'
    }
    if (stepKey === 'done') return status === 'commit_failed' ? 'pending' : 'pending'
    return 'pending'
  }

  if (status === 'running' || status === 'pending') {
    const pi = Math.max(0, order.indexOf(phase as (typeof order)[number]))
    if (ki < pi) return 'done'
    if (ki === pi) return 'running'
    return 'pending'
  }

  return 'pending'
}

export function buildUpgradePhaseSteps(job?: Record<string, any>, prog?: Record<string, any>) {
  const phaseMap = (prog?.phase_timings || job?.options?.phase_timings || {}).phases || {}
  return UPGRADE_STEP_DEFS.map((s) => {
    const st = upgradeStepState(s.key, job, prog)
    const pt = phaseMap[s.key]
    let durText = ''
    if (pt?.elapsed_sec && s.key !== 'done') {
      const sec = Number(pt.elapsed_sec)
      durText = sec < 60 ? `${sec.toFixed(1)}s` : `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
      if (pt.running) durText += '…'
    }
    return { ...s, status: st, duration: durText }
  })
}

export function upgradeProgressLogs(prog?: Record<string, any>, job?: Record<string, any>) {
  const log = prog?.log
  if (Array.isArray(log) && log.length) return log
  const pl = job?.options?.progress_log
  if (Array.isArray(pl)) {
    return pl.map((e: any) => ({
      time: e.time || '',
      phase: e.phase || '',
      msg: e.msg || e.message || '',
    }))
  }
  return []
}

export function upgradeProgressPercent(prog?: Record<string, any>, job?: Record<string, any>) {
  const status = effectiveUpgradeStatus(job, prog) || job?.status || prog?.status || ''
  if (status === 'completed') return 100
  const p = Number(prog?.percent ?? 0)
  if (p > 0) return Math.min(100, p)
  if (isBuildPhaseActive(job, prog)) return Math.max(p, 90)
  if (status === 'applied') return 60
  if (status === 'conflicts') return 55
  if (status === 'build_failed' && !isBuildPhaseActive(job, prog)) return 95
  if (status === 'commit_failed') return 98
  return 0
}

/** Hide conflict / build-fix panels while automated phases are running. */
export function isUpgradeAutomatedRunning(job?: Record<string, any>, prog?: Record<string, any>) {
  job = job || {}
  prog = prog || {}
  const status = job.status || prog.status || ''
  const phase = prog.phase || job.phase || ''
  if (['awaiting_ssh', 'awaiting_otp', 'pending'].includes(status)) return true
  if (status !== 'running') return false
  return ['prepare', 'apply', 'commit', 'build', 'build_fix'].includes(phase)
}
