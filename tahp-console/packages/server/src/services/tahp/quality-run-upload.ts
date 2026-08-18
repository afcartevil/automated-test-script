/**
 * 自检完成 → 中心质量看板自动上报。
 * 失败只记日志，不阻断本地报告生成。
 */
import { basename } from 'path'
import { logger } from '../logger'
import { isCentralConfigured } from './runtime-mode'
import { centralClient } from './sync/central-client'
import { resolveFlashDeviceIdentity } from './device-flash'
import { readJiraUsername } from './jira-user-config'
import type { ModemBaselineRunMeta } from './modem-baseline'
import {
  mapSelfCheckReportToQualityRun,
  mapAdaptDebugReportToQualityRun,
  mapModemBaselineMetaToQualityRun,
  mapGkiUpgradeJobToQualityRun,
  matchCentralProject,
  parseProjectFromScheduleKey,
  UNASSIGNED_PROJECT,
  type GkiUpgradeJobRow,
  type SelfCheckSummaryForUpload,
  type SelfCheckDetailForUpload,
} from './quality-run-mapper'

export interface ResolvedProjectContext {
  project_code: string
  campaign_id?: string
  brand?: string
  source: 'device' | 'schedule' | 'central-match' | 'unassigned'
}

/** Run.owner = Jira username；不回退 getLocalActor() */
export function resolveQualityRunOwner(): string | undefined {
  const fromFile = readJiraUsername()
  if (fromFile) return fromFile
  const env = process.env.TAHP_JIRA_USERNAME?.trim() || process.env.JIRA_USERNAME?.trim()
  return env || undefined
}

async function resolveProjectCode(candidate?: string): Promise<{ project_code: string; campaign_id?: string }> {
  const raw = candidate?.trim()
  if (!raw) return { project_code: UNASSIGNED_PROJECT }
  if (isCentralConfigured()) {
    try {
      const projects = await centralClient.listAdaptPrereqProjects()
      const matched = matchCentralProject(raw, projects)
      if (matched) return matched
    } catch (err) {
      logger.debug({ err: (err as Error).message }, '[quality-upload] listAdaptPrereqProjects failed')
    }
  }
  return { project_code: raw }
}

async function uploadSingleRun(run: Parameters<typeof centralClient.uploadQualityRun>[0]): Promise<{
  uploaded: boolean
  run_id?: string
  action?: string
  skipped?: string
}> {
  const payload = typeof run === 'object' && 'runs' in run ? run.runs[0] : run
  const runId = (payload as { run_id?: string }).run_id
  try {
    const res = await centralClient.uploadQualityRun(run)
    const first = res.results?.[0]
    if (first && !first.ok) {
      logger.warn({ runId, error: first.error }, '[quality-upload] upload rejected')
      return { uploaded: false, run_id: runId, skipped: first.error }
    }
    return { uploaded: true, run_id: runId, action: first?.action }
  } catch (err) {
    logger.warn({ runId, err: (err as Error).message }, '[quality-upload] upload failed')
    return { uploaded: false, run_id: runId, skipped: (err as Error).message }
  }
}

/**
 * 解析项目归属：设备 ADB → scheduleKey → 中心列表匹配 → _unassigned
 */
export async function resolveSelfCheckProjectContext(input: {
  deviceId: string
  deviceName?: string
  scheduleKey?: string
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
    owner: resolveQualityRunOwner(),
  })

  const result = await uploadSingleRun(run)
  if (result.uploaded) {
    logger.info(
      { runId: run.run_id, project: run.project_code, status: run.status },
      '[quality-upload] self-check report uploaded',
    )
  }
  return result
}

export async function uploadAdaptDebugFromCtx(ctx: {
  taskId: string
  workspaceId: string
  domainId: string
  domainLabel: string
  startedAt: string
  completedAt?: string
  status: string
  fileChanges: Array<{ path: string }>
  auditReport?: string
  llmResponse?: string
  error?: string
  formData: Record<string, string>
}): Promise<void> {
  if (!isCentralConfigured()) return
  const owner = resolveQualityRunOwner()
  const candidate = projectFromCtx(ctx)
  const { project_code, campaign_id } = await resolveProjectCode(candidate)
  const run = mapAdaptDebugReportToQualityRun({
    taskId: ctx.taskId,
    status: ctx.status === 'completed' ? 'completed' : 'failed',
    workspaceId: ctx.workspaceId,
    domainId: ctx.domainId,
    domainLabel: ctx.domainLabel,
    startedAt: ctx.startedAt,
    completedAt: ctx.completedAt,
    filesModified: ctx.fileChanges.map(f => f.path),
    auditReport: ctx.auditReport,
    llmResponse: ctx.llmResponse,
    error: ctx.error,
    formData: ctx.formData,
    project_code,
    campaign_id,
    owner,
  })
  const result = await uploadSingleRun(run)
  if (result.uploaded) {
    logger.info({ runId: run.run_id }, '[quality-upload] adapt-debug uploaded')
  }
}

function projectFromCtx(ctx: AdaptAgentTaskCtx): string | undefined {
  for (const key of ['project_code', 'project', '项目', 'build_project', 'AP_lable']) {
    const v = ctx.formData?.[key]?.trim()
    if (v) return v
  }
  return undefined
}

export async function uploadModemPatchRunToCentral(meta: ModemBaselineRunMeta): Promise<void> {
  if (!isCentralConfigured()) return
  if (meta.status === 'running') return

  const owner = resolveQualityRunOwner()
  const candidate = meta.config?.AP_lable || meta.config?.build_project
  const { project_code } = await resolveProjectCode(candidate)
  const run = mapModemBaselineMetaToQualityRun(meta, owner, project_code)
  const result = await uploadSingleRun(run)
  if (result.uploaded) {
    logger.info({ runId: run.run_id }, '[quality-upload] modem-patch uploaded')
  }
}

export async function uploadGkiPatchJobToCentral(
  job: GkiUpgradeJobRow,
): Promise<{ uploaded: boolean; run_id?: string }> {
  if (!isCentralConfigured()) return { uploaded: false }

  const owner = resolveQualityRunOwner()
  const candidate = job.repo || job.options
  const { project_code } = await resolveProjectCode(candidate)
  const run = mapGkiUpgradeJobToQualityRun(job, owner, project_code)
  const result = await uploadSingleRun(run)
  if (result.uploaded) {
    logger.info({ runId: run.run_id }, '[quality-upload] gki-patch uploaded')
  }
  return { uploaded: result.uploaded, run_id: run.run_id }
}
