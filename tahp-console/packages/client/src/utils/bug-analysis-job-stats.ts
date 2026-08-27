/**
 * 批量队列成功 / 失败 / 取消计数。
 * 以子任务当前状态为准，避免左侧沿用 job.completed/failed（取消与重启中断不入账）导致和右侧对不上。
 */

export interface BugJobQueueCounts {
  all: number
  pending: number
  running: number
  completed: number
  failed: number
  cancelled: number
}

export function countBugJobQueue(
  taskIds: string[],
  statusOf: (taskId: string) => string | undefined,
): BugJobQueueCounts {
  const counts: BugJobQueueCounts = {
    all: 0,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  }
  for (const tid of taskIds) {
    const status = statusOf(tid) || 'pending'
    counts.all += 1
    if (status === 'completed') counts.completed += 1
    else if (status === 'failed') counts.failed += 1
    else if (status === 'cancelled') counts.cancelled += 1
    else if (status === 'running' || status === 'waiting_user_input') counts.running += 1
    else counts.pending += 1
  }
  return counts
}

/** 已落到终态的单数，用于进度条（成功 + 失败 + 取消）。 */
export function bugJobSettledCount(counts: BugJobQueueCounts): number {
  return counts.completed + counts.failed + counts.cancelled
}

/** 用子任务实时状态覆盖 job 落盘计数（running 中途 completed 不会写回 job.completed）。 */
export function overlayBugJobCounts<T extends { task_ids?: string[]; completed: number; failed: number }>(
  job: T,
  statusOf: (taskId: string) => string | undefined,
): T {
  const ids = job.task_ids || []
  if (!ids.length) return job
  // 子任务还没进 store 时不要把 API 计数打成 0
  if (!ids.some(id => statusOf(id) !== undefined)) return job
  const counts = countBugJobQueue(ids, statusOf)
  if (job.completed === counts.completed && job.failed === counts.failed) return job
  return { ...job, completed: counts.completed, failed: counts.failed }
}
