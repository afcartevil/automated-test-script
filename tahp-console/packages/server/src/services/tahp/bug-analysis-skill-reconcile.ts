/**
 * 诊断任务结束后延迟再扫 curator ledger。
 * Hermes 可能在 BFF 已落盘报告之后才追加 jsonl，结束时那一次 merge 会漏。
 */

export const SKILL_IMPROVE_RECONCILE_DELAYS_MS = [15_000, 60_000, 180_000]

export interface SkillImproveReconcileTimers {
  setTimeout: typeof setTimeout
  clearTimeout: typeof clearTimeout
}

const pending = new Map<string, Array<ReturnType<typeof setTimeout>>>()

export function cancelSkillImproveReconcile(taskId: string, timers: SkillImproveReconcileTimers = defaultTimers()): void {
  const list = pending.get(taskId)
  if (!list) return
  for (const handle of list) timers.clearTimeout(handle)
  pending.delete(taskId)
}

export function scheduleSkillImproveReconcile(
  taskId: string,
  run: (taskId: string) => void | Promise<void>,
  delaysMs: number[] = SKILL_IMPROVE_RECONCILE_DELAYS_MS,
  timers: SkillImproveReconcileTimers = defaultTimers(),
): void {
  const tid = String(taskId || '').trim()
  if (!tid || !delaysMs.length) return
  cancelSkillImproveReconcile(tid, timers)
  const handles: Array<ReturnType<typeof setTimeout>> = []
  for (const ms of delaysMs) {
    const handle = timers.setTimeout(() => {
      Promise.resolve(run(tid)).catch(() => { /* caller logs */ })
    }, ms)
    if (typeof (handle as NodeJS.Timeout).unref === 'function') {
      (handle as NodeJS.Timeout).unref()
    }
    handles.push(handle)
  }
  pending.set(tid, handles)
}

function defaultTimers(): SkillImproveReconcileTimers {
  return { setTimeout, clearTimeout }
}
