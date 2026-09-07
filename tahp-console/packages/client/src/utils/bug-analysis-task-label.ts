/** 终态任务卡片文案：不依赖 phase/title 是否还在（重启恢复时常为空）。 */

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

export function bugTaskStatusPhase(status?: string): string | undefined {
  if (status === 'completed') return 'COMPLETED'
  if (status === 'failed') return 'FAILED'
  if (status === 'cancelled') return 'CANCELLED'
  if (status === 'pending') return 'QUEUED'
  if (status === 'waiting_user_input') return 'WAITING_USER_INPUT'
  return undefined
}

/** 列表/队列卡片用的 phase：终态以 status 为准，避免空 phase 显示成「准备中」。 */
export function bugTaskCardPhase(status?: string, phase?: string): string | undefined {
  if (phase === 'MARK_DUPLICATE') return 'MARK_DUPLICATE'
  if (status && TERMINAL.has(status)) return bugTaskStatusPhase(status)
  return phase || bugTaskStatusPhase(status)
}

export function bugTaskListTitle(task: { title?: string; jira_key?: string; status?: string }): string {
  const title = task.title?.trim()
  if (title) return title
  if (task.status && TERMINAL.has(task.status)) return task.jira_key?.trim() || '无标题'
  return '(等待获取标题)'
}

/** 已出结论的单默认看报告；进行中 / 取消仍看实时进展。 */
export function bugTaskDefaultDetailTab(status?: string): 'live' | 'report' {
  return status === 'completed' || status === 'failed' ? 'report' : 'live'
}
