/**
 * Gerrit Code Review 客户端诊断日志 — 批量上报 BFF 落盘 reports/gerrit-review-debug/
 *
 * 开启方式（任选其一）：
 * - 开发模式 DEV 自动开启
 * - localStorage.setItem('tahp_gerrit_debug', '1')
 * - localStorage.setItem('tahp_gerrit_recommend_debug', '1')  ← 仅推荐用例链路，生产也可开
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

function generalDebugEnabled(): boolean {
  if (import.meta.env.DEV) return true
  try {
    return localStorage.getItem('tahp_gerrit_debug') === '1'
  } catch {
    return false
  }
}

/** 推荐用例展示问题专用 trace — 生产环境可单独开启 */
export function recommendDebugEnabled(): boolean {
  if (generalDebugEnabled()) return true
  try {
    return localStorage.getItem('tahp_gerrit_recommend_debug') === '1'
  } catch {
    return false
  }
}

export function gerritReviewDebug(
  event: string,
  detail?: Record<string, unknown> & { taskId?: string | null },
): void {
  if (!generalDebugEnabled()) return
  pushDebugEntry(event, detail)
}

/** 推荐用例链路诊断 — 同时写 console 便于复现时即时查看 */
export function gerritRecommendTrace(
  event: string,
  detail?: Record<string, unknown> & { taskId?: string | null },
): void {
  if (!recommendDebugEnabled()) return
  pushDebugEntry(event, detail)
  const { taskId, ...rest } = detail ?? {}
  const label = taskId ? `[gerrit-recommend][${String(taskId).slice(-8)}]` : '[gerrit-recommend]'
  if (event.includes('dropped') || event.includes('skip') || event.includes('blocked')) {
    console.warn(label, event, rest)
  } else {
    console.info(label, event, rest)
  }
}

function pushDebugEntry(
  event: string,
  detail?: Record<string, unknown> & { taskId?: string | null },
): void {
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
