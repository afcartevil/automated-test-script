/**
 * AI 测试规划自动执行调度
 */
import { logger } from '../logger'
import {
  getTestScheduleView,
  matchProjectToDevice,
  type PlanTestType,
  type ScheduleItem,
} from './test-planning'
import {
  markPlanExecutionCompleted,
  markPlanExecutionNoDevice,
  markPlanExecutionRunning,
} from './test-plan-executions'
import { snapshotDevices, startTest } from './device-self-check'

let timer: NodeJS.Timeout | null = null
let ticking = false

function executorIntervalMs(): number {
  const raw = Number(process.env.TAHP_PLAN_EXECUTOR_INTERVAL_MS)
  return Number.isFinite(raw) && raw > 0 ? raw : 60_000
}

function shouldAttemptExecution(item: ScheduleItem): boolean {
  if (item.phase !== 'active') return false
  if (item.runtimeStatus === 'running' || item.runtimeStatus === 'completed') return false
  return item.runtimeStatus === 'pending' || item.runtimeStatus === 'no_device'
}

export async function tickPlanExecutor(): Promise<void> {
  if (ticking) return
  ticking = true
  try {
    const view = await getTestScheduleView()
    const candidates = view.items.filter(shouldAttemptExecution)
    if (!candidates.length) return

    const devices = snapshotDevices()
    for (const item of candidates) {
      const matched = devices.find(d => matchProjectToDevice(item.project, d))
      if (!matched) {
        await markPlanExecutionNoDevice(item.scheduleKey)
        logger.info(
          { scheduleKey: item.scheduleKey, project: item.project },
          '[plan-executor] no matching idle device',
        )
        continue
      }

      const result = await startTest(
        matched.deviceId,
        item.testType as PlanTestType,
        undefined,
        { scheduleKey: item.scheduleKey },
      )
      if (!result) {
        await markPlanExecutionNoDevice(item.scheduleKey)
        logger.warn(
          { scheduleKey: item.scheduleKey, deviceId: matched.deviceId },
          '[plan-executor] startTest returned null',
        )
        continue
      }

      await markPlanExecutionRunning(item.scheduleKey, matched.deviceId)
      logger.info(
        { scheduleKey: item.scheduleKey, deviceId: matched.deviceId, testType: item.testType },
        '[plan-executor] auto-started planned test',
      )
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[plan-executor] tick failed')
  } finally {
    ticking = false
  }
}

export function startPlanExecutor(): void {
  if (timer) return
  const interval = executorIntervalMs()
  logger.info({ intervalMs: interval }, '[plan-executor] starting')
  void tickPlanExecutor()
  timer = setInterval(() => void tickPlanExecutor(), interval)
  if (typeof timer.unref === 'function') timer.unref()
}

export function stopPlanExecutor(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
