/**
 * 自检报告 → 中心质量看板 Run 契约映射。
 * 与 easyadapter_bff quality-store IngestRunInput / schema_version=1 对齐。
 */
import type { QualityRunPayload } from './sync/central-client'
import type {
  SelfCheckCaseItem,
  SelfCheckFailedCaseItem,
} from './self-check-reports'

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

export { UNASSIGNED_PROJECT }
