/**
 * 同步调度：启动拉一次 + 定时增量。中心不可用静默跳过（离线容忍）。
 */
import { config } from '../../../config'
import { logger } from '../../logger'
import { isCentralConfigured, isLocal } from '../runtime-mode'
import { runPull } from './pull'

let timer: NodeJS.Timeout | null = null
let running = false

async function safePull(incremental: boolean): Promise<void> {
  if (running) return
  running = true
  try {
    await runPull(incremental)
  } catch (e) {
    // 离线容忍：中心不可用时仅记录，不影响本地使用
    logger.warn({ err: (e as Error).message }, '[sync] pull skipped (central unavailable?)')
  } finally {
    running = false
  }
}

export function startSyncScheduler(): void {
  if (!isLocal()) {
    logger.info('[sync] role=central, scheduler disabled')
    return
  }
  if (!isCentralConfigured()) {
    logger.info('[sync] central not configured (TAHP_CENTRAL_URL/TOKEN), scheduler disabled; 本地以现有副本运行')
    return
  }

  logger.info({ url: config.tahp.centralUrl, intervalMs: config.tahp.syncIntervalMs }, '[sync] scheduler starting')
  // 启动后异步拉一次全量，不阻塞 bootstrap
  void safePull(false)

  const interval = config.tahp.syncIntervalMs
  if (interval > 0) {
    timer = setInterval(() => void safePull(true), interval)
    if (typeof timer.unref === 'function') timer.unref()
  }
}

export function stopSyncScheduler(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
