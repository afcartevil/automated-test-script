/**
 * 自检完成 → 中心质量看板自动上报。
 * 失败只记日志，不阻断本地报告生成。
 */
import { basename } from 'path'
import { logger } from '../logger'
import { isCentralConfigured, getLocalActor } from './runtime-mode'
import { centralClient } from './sync/central-client'
import { resolveFlashDeviceIdentity } from './device-flash'
import {
  mapSelfCheckReportToQualityRun,
  matchCentralProject,
  parseProjectFromScheduleKey,
  UNASSIGNED_PROJECT,
  type SelfCheckSummaryForUpload,
  type SelfCheckDetailForUpload,
} from './quality-run-mapper'

export interface ResolvedProjectContext {
  project_code: string
  campaign_id?: string
  brand?: string
  source: 'device' | 'schedule' | 'central-match' | 'unassigned'
}

/**
 * 解析项目归属：设备 ADB → scheduleKey → 中心列表匹配 → _unassigned
 */
export async function resolveSelfCheckProjectContext(input: {
  deviceId: string
  deviceName?: string
  scheduleKey?: string
  /** 已解析出的候选（例如刷机 daily-options） */
  hintProject?: string
}): Promise<ResolvedProjectContext> {
  let candidate: string | undefined = input.hintProject?.trim() || undefined
  let brand: string | undefined
  let source: ResolvedProjectContext['source'] = 'unassigned'

  if (!candidate) {
    try {
      const identity = await resolveFlashDeviceIdentity(input.deviceId)
      candidate = identity.project
      brand = identity.brand
      source = 'device'
    } catch (err) {
      logger.debug(
        { deviceId: input.deviceId, err: (err as Error).message },
        '[quality-upload] resolveFlashDeviceIdentity failed, try scheduleKey',
      )
    }
  } else {
    source = 'device'
  }

  if (!candidate) {
    candidate = parseProjectFromScheduleKey(input.scheduleKey)
    if (candidate) source = 'schedule'
  }

  if (!candidate && input.deviceName?.trim()) {
    candidate = input.deviceName.trim()
  }

  if (!candidate) {
    return { project_code: UNASSIGNED_PROJECT, source: 'unassigned' }
  }

  // 与中心适配前置项目列表对齐，顺带拿 active_campaign_id
  if (isCentralConfigured()) {
    try {
      const projects = await centralClient.listAdaptPrereqProjects()
      const matched = matchCentralProject(candidate, projects)
      if (matched) {
        return {
          project_code: matched.project_code,
          campaign_id: matched.campaign_id,
          brand,
          source: source === 'unassigned' ? 'central-match' : source,
        }
      }
    } catch (err) {
      logger.debug(
        { err: (err as Error).message },
        '[quality-upload] listAdaptPrereqProjects failed',
      )
    }
  }

  return {
    project_code: candidate,
    brand,
    source: source === 'unassigned' ? 'device' : source,
  }
}

/**
 * 将已落盘的自检报告上报到中心（幂等）。中心未配置时跳过。
 */
export async function uploadSelfCheckReportToCentral(input: {
  summary: SelfCheckSummaryForUpload
  detail?: SelfCheckDetailForUpload | null
  resultDir: string
  reportRelPath: string
}): Promise<{ uploaded: boolean; run_id?: string; action?: string; skipped?: string }> {
  if (!isCentralConfigured()) {
    return { uploaded: false, skipped: 'central_not_configured' }
  }

  const sessionDir = basename(input.resultDir)
  const run = mapSelfCheckReportToQualityRun({
    summary: input.summary,
    detail: input.detail,
    sessionDir,
    reportRelPath: input.reportRelPath.replace(/\\/g, '/'),
    owner: getLocalActor(),
  })

  try {
    const res = await centralClient.uploadQualityRun(run)
    const first = res.results?.[0]
    if (first && !first.ok) {
      logger.warn(
        { runId: run.run_id, error: first.error },
        '[quality-upload] self-check upload rejected',
      )
      return { uploaded: false, run_id: run.run_id, skipped: first.error }
    }
    logger.info(
      {
        runId: run.run_id,
        action: first?.action,
        project: run.project_code,
        status: run.status,
      },
      '[quality-upload] self-check report uploaded',
    )
    return { uploaded: true, run_id: run.run_id, action: first?.action }
  } catch (err) {
    logger.warn(
      { runId: run.run_id, err: (err as Error).message },
      '[quality-upload] self-check upload failed; local report kept',
    )
    return { uploaded: false, run_id: run.run_id, skipped: (err as Error).message }
  }
}
