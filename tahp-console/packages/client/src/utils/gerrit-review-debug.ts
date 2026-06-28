/**
 * Gerrit Code Review 客户端诊断日志 — 批量上报 BFF 落盘 reports/gerrit-review-debug/
 */
import { tahpPost } from '@/api/tahp/client'

export interface GerritReviewDebugEntry {
  ts: number
  event: string
  taskId?: string | null
  detail?: Record<string, unknown>
}

const MAX_BUFFER = 120
const buffer: GerritReviewDebugEntry[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null

function debugEnabled(): boolean {
  if (import.meta.env.DEV) return true
  try {
    return localStorage.getItem('tahp_gerrit_debug') === '1'
  } catch {
    return false
  }
}

export function gerritReviewDebug(
  event: string,
  detail?: Record<string, unknown> & { taskId?: string | null },
): void {
  if (!debugEnabled()) return
  const { taskId, ...rest } = detail ?? {}
  buffer.push({
    ts: Date.now(),
    event,
    taskId: taskId ?? undefined,
    detail: Object.keys(rest).length ? rest : undefined,
  })
  if (buffer.length > MAX_BUFFER) buffer.splice(0, buffer.length - MAX_BUFFER)
  scheduleFlush()
}

function scheduleFlush(): void {
  if (flushTimer) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    void flushGerritReviewDebug()
  }, 1500)
}

export async function flushGerritReviewDebug(): Promise<void> {
  if (!buffer.length) return
  const entries = buffer.splice(0, buffer.length)
  try {
    await tahpPost('/api/tahp/gerrit-review/debug-log', { entries })
  } catch {
    buffer.unshift(...entries)
    if (buffer.length > MAX_BUFFER) buffer.splice(MAX_BUFFER)
  }
}
