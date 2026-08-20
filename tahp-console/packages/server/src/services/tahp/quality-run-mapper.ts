/**
 * 自检报告 → 中心质量看板 Run 契约映射。
 * 与 easyadapter_bff quality-store IngestRunInput / schema_version=1 对齐。
 */
import type { QualityRunPayload } from './sync/central-client'
import type {
  SelfCheckCaseItem,
  SelfCheckFailedCaseItem,
} from './self-check-reports'
import { parseAdaptAuditSummary } from './adapt-audit-summary'
import type { ModemBaselineRunMeta } from './modem-baseline'

export interface SelfCheckSummaryForUpload {
  deviceId: string
  deviceName: string
  testType: string
  startTime?: string
  endTime?: string
  status: string
  totalCases: number
  passedCases: number
  failedCases: number
  skippedCases: number
  aiSummary?: string
  aiPlanned?: boolean
  scheduleKey?: string
  project_code?: string
  campaign_id?: string
  brand?: string
}

export interface SelfCheckDetailForUpload {
  aiSummary?: string
  failedCaseItems?: SelfCheckFailedCaseItem[]
  allCaseItems?: SelfCheckCaseItem[]
}

const UNASSIGNED_PROJECT = '_unassigned'

/** scheduleKey 形态：`${project}|${node}|${triggerDate}|${testType}` */
export function parseProjectFromScheduleKey(scheduleKey?: string): string | undefined {
  if (!scheduleKey?.trim()) return undefined
  const project = scheduleKey.split('|')[0]?.trim()
  return project || undefined
}

/** 供中心 run_id：仅保留安全字符 */
export function buildSelfCheckRunId(deviceId: string, sessionDir: string): string {
  const safeDevice = deviceId.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 64)
  const safeSession = sessionDir.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 80)
  return `sc-${safeDevice}-${safeSession}`.slice(0, 180)
}

export function mapSelfCheckStatusToRunStatus(
  status: string,
  failedCases: number,
  totalCases: number,
): QualityRunPayload['status'] {
  if (status.includes('通过') && !status.includes('失败') && failedCases === 0) return 'pass'
  if (status.includes('失败') || failedCases > 0) {
    if (totalCases > 0 && failedCases < totalCases && failedCases > 0) return 'partial'
    return 'fail'
  }
  if (status.includes('错误') || status.includes('阻塞')) return 'blocked'
  if (status.includes('进行') || status.includes('刷机') || status.includes('初始化')) return 'running'
  return 'pending'
}

function mapIssueSeverity(status: string): 'critical' | 'major' | 'minor' {
  if (status === '失败') return 'critical'
  if (status === '部分通过' || status === '待确认') return 'major'
  return 'minor'
}

/**
 * 将中心项目列表与本地候选代号做匹配：
 * 精确 / 忽略大小写 / 前缀包含。
 */
export function matchCentralProject(
  candidate: string,
  projects: Array<{ code: string; name: string; active_campaign_id?: string | null }>,
): { project_code: string; campaign_id?: string } | null {
  const raw = candidate.trim()
  if (!raw || !projects.length) return null
  const upper = raw.toUpperCase()

  const exact = projects.find(p => p.code.toUpperCase() === upper || p.name.toUpperCase() === upper)
  if (exact) {
    return {
      project_code: exact.code,
      campaign_id: exact.active_campaign_id || undefined,
    }
  }

  const prefix = projects.find(p =>
    p.code.toUpperCase().startsWith(upper)
    || upper.startsWith(p.code.toUpperCase())
    || p.name.toUpperCase().includes(upper)
    || upper.includes(p.name.toUpperCase()),
  )
  if (prefix) {
    return {
      project_code: prefix.code,
      campaign_id: prefix.active_campaign_id || undefined,
    }
  }
  return null
}

export function mapSelfCheckReportToQualityRun(input: {
  summary: SelfCheckSummaryForUpload
  detail?: SelfCheckDetailForUpload | null
  sessionDir: string
  reportRelPath: string
  owner?: string
}): QualityRunPayload {
  const { summary, detail, sessionDir, reportRelPath, owner } = input
  const total = summary.totalCases ?? 0
  const passed = summary.passedCases ?? 0
  const failed = summary.failedCases ?? 0
  const skipped = summary.skippedCases ?? 0
  const passRate = total > 0 ? Math.round((passed / total) * 1000) / 1000 : undefined

  const failedItems = detail?.failedCaseItems ?? []
  const issues = failedItems.map(item => ({
    key: item.caseKey,
    title: item.caseName,
    module: item.module,
    severity: mapIssueSeverity(item.status),
    status: item.status === '通过' ? 'pass' : 'fail',
    message: item.message,
  }))

  const projectCode = summary.project_code?.trim() || UNASSIGNED_PROJECT

  return {
    run_id: buildSelfCheckRunId(summary.deviceId, sessionDir),
    dimension: 'self-check',
    project_code: projectCode,
    campaign_id: summary.campaign_id?.trim() || undefined,
    owner,
    device: { id: summary.deviceId, name: summary.deviceName },
    status: mapSelfCheckStatusToRunStatus(summary.status, failed, total),
    started_at: summary.startTime,
    ended_at: summary.endTime,
    metrics: {
      total,
      passed,
      failed,
      skipped,
      ...(passRate !== undefined ? { pass_rate: passRate } : {}),
    },
    issues,
    artifacts: [
      { type: 'json', name: 'summary.json', ref: `local://${reportRelPath}/summary.json` },
      { type: 'json', name: 'detail.json', ref: `local://${reportRelPath}/detail.json` },
      { type: 'xlsx', name: 'test_report.xlsx', ref: `local://${reportRelPath}/test_report.xlsx` },
    ],
    ai_summary: detail?.aiSummary || summary.aiSummary,
    source: {
      tool: 'tahp-console',
      version: 'self-check',
    },
    schema_version: 1,
  }
}

export function buildAdaptDebugRunId(taskId: string): string {
  return `ad-${taskId.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 170)}`.slice(0, 180)
}

export function buildModemPatchRunId(runId: string): string {
  return `mp-${runId.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 170)}`.slice(0, 180)
}

export function buildGkiPatchRunId(jobId: string | number): string {
  return `gk-${String(jobId).replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 170)}`.slice(0, 180)
}

function projectFromFormData(formData?: Record<string, string>): string | undefined {
  if (!formData) return undefined
  for (const key of ['project_code', 'project', '项目', 'build_project', 'AP_lable']) {
    const v = formData[key]?.trim()
    if (v) return v
  }
  return undefined
}

export function mapAdaptDebugReportToQualityRun(input: {
  taskId: string
  status: 'completed' | 'failed'
  workspaceId?: string
  domainId?: string
  domainLabel?: string
  startedAt?: string
  completedAt?: string
  filesModified?: string[]
  auditReport?: string
  llmResponse?: string
  error?: string
  formData?: Record<string, string>
  project_code?: string
  campaign_id?: string
  owner?: string
}): QualityRunPayload {
  const auditItems = input.auditReport
    ? parseAdaptAuditSummary(input.auditReport, input.llmResponse)
    : []
  const auditFail = auditItems.filter(i => i.status === 'fail').length
  const auditWarn = auditItems.filter(i => i.status === 'warn').length

  let status: QualityRunPayload['status'] = 'pass'
  if (input.status === 'failed') status = 'fail'
  else if (auditFail > 0) status = 'partial'

  const issues = auditItems
    .filter(i => i.status === 'fail' || i.status === 'warn')
    .map(i => ({
      key: i.key || i.label,
      title: i.label,
      severity: i.status === 'fail' ? 'critical' : 'major',
      status: 'fail',
      message: i.reason,
    }))

  const projectCode = input.project_code?.trim()
    || projectFromFormData(input.formData)
    || UNASSIGNED_PROJECT

  const artifacts = [{
    type: 'json',
    name: `${input.taskId}.json`,
    ref: `local://adapt-agent/${input.taskId}.json`,
  }]

  const summary = input.error
    ? input.error.slice(0, 500)
    : (input.llmResponse?.slice(0, 500) || `audit fail=${auditFail} warn=${auditWarn}`)

  return {
    run_id: buildAdaptDebugRunId(input.taskId),
    dimension: 'adapt-debug',
    project_code: projectCode,
    campaign_id: input.campaign_id,
    workspace_id: input.workspaceId,
    domain_id: input.domainId,
    owner: input.owner,
    status,
    started_at: input.startedAt,
    ended_at: input.completedAt,
    metrics: {
      files_total: input.filesModified?.length ?? 0,
      audit_fail: auditFail,
      audit_warn: auditWarn,
    },
    issues,
    artifacts: input.status === 'completed' ? artifacts : [],
    ai_summary: summary,
    source: { tool: 'tahp-console', version: 'adapt-debug' },
    schema_version: 1,
  }
}

export function isModemTerminal(status: string): boolean {
  return status === 'success' || status === 'failed' || status === 'conflict'
}

export function mapModemBaselineMetaToQualityRun(
  meta: ModemBaselineRunMeta,
  owner?: string,
  project_code?: string,
): QualityRunPayload {
  let status: QualityRunPayload['status'] = 'pending'
  if (meta.status === 'success') status = 'pass'
  else if (meta.status === 'failed') status = 'fail'
  else if (meta.status === 'conflict') status = 'blocked'

  const conflicts = meta.conflictFiles || []
  const issues: QualityRunPayload['issues'] = conflicts.map((f, i) => ({
    key: `conflict-${i}`,
    title: f,
    severity: 'critical',
    status: 'fail',
  }))
  if (meta.error) {
    issues.push({
      key: 'error',
      title: 'Modem error',
      severity: 'critical',
      status: 'fail',
      message: meta.error.slice(0, 500),
    })
  }

  const artifacts: QualityRunPayload['artifacts'] = []
  if (meta.reportPath) {
    artifacts.push({ type: 'json', name: 'report', ref: meta.reportPath })
  }
  artifacts.push({
    type: 'json',
    name: 'meta.json',
    ref: `local://modem-baseline/${meta.runId}/meta.json`,
  })

  return {
    run_id: buildModemPatchRunId(meta.runId),
    dimension: 'modem-patch',
    project_code: project_code || UNASSIGNED_PROJECT,
    owner,
    status,
    started_at: meta.startedAt,
    ended_at: meta.finishedAt,
    metrics: {
      conflict_count: conflicts.length,
      errors: meta.status === 'failed' ? 1 : 0,
    },
    issues,
    artifacts,
    ai_summary: `${meta.phase || ''} ${meta.status} · conflict=${conflicts.length}`.trim(),
    source: { tool: 'tahp-console', version: 'modem-patch' },
    schema_version: 1,
  }
}

export interface GkiUpgradeJobRow {
  id: number | string
  status: string
  applied_commits?: number
  total_commits?: number
  conflict_files?: string[]
  error_msg?: string
  created_at?: string
  completed_at?: string
  repo?: string
  options?: string
}

export function isGkiTerminal(status: string): boolean {
  return [
    'conflicts', 'build_failed', 'commit_failed', 'cancelled',
    'committed', 'applied', 'success', 'failed', 'done',
  ].includes(status)
}

export function mapGkiUpgradeJobToQualityRun(
  job: GkiUpgradeJobRow,
  owner?: string,
  project_code?: string,
): QualityRunPayload {
  const conflicts = job.conflict_files || []
  let status: QualityRunPayload['status'] = 'pending'
  if (['committed', 'applied', 'success', 'done'].includes(job.status)) status = 'pass'
  else if (job.status === 'conflicts') status = 'blocked'
  else if (['build_failed', 'commit_failed', 'failed'].includes(job.status)) status = 'fail'

  const issues: QualityRunPayload['issues'] = conflicts.map((f, i) => ({
    key: `conflict-${i}`,
    title: f,
    severity: 'critical',
    status: 'fail',
  }))
  if (job.error_msg) {
    issues.push({
      key: 'error',
      title: 'GKI error',
      severity: 'critical',
      status: 'fail',
      message: job.error_msg.slice(0, 500),
    })
  }

  return {
    run_id: buildGkiPatchRunId(job.id),
    dimension: 'gki-patch',
    project_code: project_code || UNASSIGNED_PROJECT,
    owner,
    status,
    started_at: job.created_at,
    ended_at: job.completed_at,
    metrics: {
      applied_commits: job.applied_commits ?? 0,
      total_commits: job.total_commits ?? 0,
      conflict_count: conflicts.length,
    },
    issues,
    artifacts: [{
      type: 'job',
      name: 'upgrade_job',
      ref: `gki://upgrade/jobs/${job.id}`,
    }],
    ai_summary: `${job.status} · applied=${job.applied_commits ?? 0}/${job.total_commits ?? 0}`,
    source: { tool: 'tahp-console', version: 'gki-patch' },
    schema_version: 1,
  }
}

export { UNASSIGNED_PROJECT }
