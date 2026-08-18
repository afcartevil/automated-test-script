/**
 * 适配流水线终态 → 中心质量看板上报（去抖）。
 */
import { logger } from '../../logger'
import { isCentralConfigured } from '../runtime-mode'
import { centralClient } from '../sync/central-client'
import { resolveQualityRunOwner } from '../quality-run-upload'
import type { PipelineRun } from './types'
import { isPipelineTerminal, mapPipelineRunToQualityRuns } from './quality-mapper'

const lastNotified = new Map<string, string>()

export async function notifyPipelineQuality(run: PipelineRun): Promise<void> {
  if (!isPipelineTerminal(run.status)) return

  const notifyKey = `${run.status}|${run.finished_at || ''}`
  if (lastNotified.get(run.run_id) === notifyKey) return
  lastNotified.set(run.run_id, notifyKey)

  if (!isCentralConfigured()) return

  const owner = resolveQualityRunOwner()
  try {
    const runs = await mapPipelineRunToQualityRuns(run, owner)
    if (!runs.length) return

    const res = await centralClient.uploadQualityRun({ runs })
    const failed = res.results?.filter(r => !r.ok) || []
    if (failed.length) {
      logger.warn(
        { pipelineRunId: run.run_id, failed },
        '[quality-upload] adapt-pipeline partial rejection',
      )
      return
    }
    logger.info(
      { pipelineRunId: run.run_id, count: runs.length },
      '[quality-upload] adapt-pipeline uploaded',
    )
  } catch (err) {
    logger.warn(
      { pipelineRunId: run.run_id, err: (err as Error).message },
      '[quality-upload] adapt-pipeline upload failed',
    )
  }
}

/** 测试用：清空去抖缓存 */
export function resetPipelineQualityNotifyForTest(): void {
  lastNotified.clear()
}
