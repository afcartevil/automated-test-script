/**
 * 适配流水线 → 中心质量看板 Run 映射。
 */
import type { QualityRunPayload } from '../sync/central-client'
import { centralClient } from '../sync/central-client'
import { matchCentralProject, UNASSIGNED_PROJECT } from '../quality-run-mapper'
import type {
  GerritChangeRef,
  PipelineDomain,
  PipelineRun,
  RunStatus,
  StageState,
} from './types'

const STAGE_KEYS = ['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'] as const
type PipelineStageKey = typeof STAGE_KEYS[number]

type StageReportStatus = 'done' | 'failed' | 'skipped' | 'pending'

export function isPipelineTerminal(status: RunStatus): boolean {
  return status === 'passed' || status === 'failed' || status === 'aborted'
}

export function pipelineStatusToQuality(status: RunStatus): QualityRunPayload['status'] {
  if (status === 'passed') return 'pass'
  if (status === 'failed' || status === 'aborted') return 'fail'
  return 'pending'
}

function sanitizeIdPart(value: string): string {
  return value.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 80)
}

export function buildAdaptPipelineMachineRunId(pipelineRunId: string): string {
  return `pl-${sanitizeIdPart(pipelineRunId)}`.slice(0, 180)
}

export function buildAdaptPipelineDomainRunId(pipelineRunId: string, domainId: string): string {
  return `pl-${sanitizeIdPart(pipelineRunId)}-${sanitizeIdPart(domainId)}`.slice(0, 180)
}

function mapStageReportStatus(st: StageState | undefined): StageReportStatus {
  if (!st) return 'pending'
  if (st.status === 'done') return 'done'
  if (st.status === 'failed') return 'failed'
  if (st.status === 'skipped') return 'skipped'
  return 'pending'
}

function summaryFromStage(key: string, st: StageState | undefined, fallback: string): string {
  if (st?.summary && typeof st.summary === 'object') {
    return JSON.stringify(st.summary).slice(0, 1500)
  }
  if (typeof st?.summary === 'string' && st.summary.trim()) return st.summary.slice(0, 1500)
  if (st?.status === 'done') return `${key} 完成 · ${st.finished_at || ''}`
  if (st?.status === 'failed') return (st.error || `${key} 失败`).slice(0, 1500)
  return fallback
}

function stageRefs(st: StageState | undefined): Record<string, string> | undefined {
  if (!st?.refs) return undefined
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(st.refs)) {
    if (typeof v === 'string' && v.trim()) out[k] = v
  }
  return Object.keys(out).length ? out : undefined
}

function adaptDomainSummary(domain: PipelineDomain): string {
  const parts = [`status=${domain.status}`]
  if (domain.adapt_task_id) parts.push(`task=${domain.adapt_task_id}`)
  if (domain.changed_files?.length) parts.push(domain.changed_files.slice(0, 20).join('\n'))
  if (domain.error) parts.push(domain.error)
  return parts.join(' · ').slice(0, 1500) || 'adapt'
}

function machineAdaptSummary(run: PipelineRun): string {
  const enabled = run.domains.filter(d => d.enabled)
  const done = enabled.filter(d => d.status === 'done').length
  const failed = enabled.filter(d => d.status === 'failed').length
  const pending = enabled.filter(d => d.status === 'pending' || d.status === 'running').length
  const skipped = enabled.filter(d => d.status === 'skipped').length
  return `done ${done} · fail ${failed} · pending ${pending} · skip ${skipped}`
}

function inferCurrentNode(run: PipelineRun): string {
  if (run.current_node) return run.current_node
  for (const key of STAGE_KEYS) {
    const st = run.stages[key]
    if (st?.status === 'failed' || st.status === 'running' || st.status === 'waiting_human') {
      return key
    }
  }
  const lastDone = [...STAGE_KEYS].reverse().find(k => run.stages[k]?.status === 'done')
  return lastDone || 'prereq'
}

function changeTouchesDomain(
  g: Pick<GerritChangeRef, 'domain_id' | 'domain_ids'>,
  domainId: string,
): boolean {
  if (g.domain_id === domainId) return true
  return (g.domain_ids ?? []).includes(domainId)
}

function domainGerrits(run: PipelineRun, domainId: string): GerritChangeRef[] {
  return (run.gerrit_changes || []).filter(g => changeTouchesDomain(g, domainId))
}

function gerritStageForDomain(run: PipelineRun, domain: PipelineDomain): {
  status: StageReportStatus
  summary: string
  gerrits: GerritChangeRef[]
} {
  const changes = domainGerrits(run, domain.domain_id)
  const flashFailed = run.stages.flash?.status === 'failed'
  const machinePassed = run.status === 'passed'
  if (!machinePassed || flashFailed) {
    return {
      status: 'pending',
      summary: flashFailed ? '整机未过 flash，本域暂无合入链接' : '整机未过线，无 Change',
      gerrits: changes,
    }
  }
  const submitted = changes.filter(c => c.status === 'submitted' && c.change_url)
  if (submitted.length) {
    return {
      status: 'done',
      summary: submitted.map(c => `${c.repo} · ${c.change_number || c.change_url}`).join('\n'),
      gerrits: changes,
    }
  }
  if (domain.status === 'failed') {
    return { status: 'pending', summary: '适配失败，未进入 Gerrit', gerrits: changes }
  }
  return { status: 'pending', summary: '无 Gerrit Change', gerrits: changes }
}

function buildStages(
  run: PipelineRun,
  scope: 'project' | 'domain',
  domain?: PipelineDomain,
): Array<{
  key: PipelineStageKey
  status: StageReportStatus
  scope: 'project' | 'domain'
  summary: string
  error?: string
  started_at?: string
  finished_at?: string
  refs?: Record<string, string>
}> {
  const stages: Array<{
    key: PipelineStageKey
    status: StageReportStatus
    scope: 'project' | 'domain'
    summary: string
    error?: string
    started_at?: string
    finished_at?: string
    refs?: Record<string, string>
  }> = []

  for (const key of STAGE_KEYS) {
    const st = run.stages[key]
    let status = mapStageReportStatus(st)
    let summary = ''
    let scopeForStage: 'project' | 'domain' = scope
    let error = st?.error

    if (key === 'adapt' && scope === 'domain' && domain) {
      scopeForStage = 'domain'
      if (domain.status === 'done') status = 'done'
      else if (domain.status === 'failed') status = 'failed'
      else status = 'pending'
      summary = adaptDomainSummary(domain)
      error = domain.error
    } else if (key === 'adapt' && scope === 'project') {
      summary = machineAdaptSummary(run)
    } else if (key === 'gerrit' && scope === 'domain' && domain) {
      const g = gerritStageForDomain(run, domain)
      status = g.status
      summary = g.summary
      scopeForStage = 'domain'
    } else if (key === 'gerrit') {
      const submitted = (run.gerrit_changes || []).filter(c => c.status === 'submitted').length
      summary = submitted
        ? `${submitted} 个仓已提交 Gerrit`
        : summaryFromStage(key, st, 'Gerrit 未跑或未完成')
    } else {
      scopeForStage = 'project'
      summary = summaryFromStage(key, st, key === 'selfcheck' && status === 'pending' ? '未执行' : '待执行')
      if (key === 'selfcheck' && status === 'pending' && run.stages.flash?.status === 'failed') {
        summary = '整机未过 flash，无自检报告'
      }
    }

    if (!summary.trim()) summary = `${key} · ${status}`

    stages.push({
      key,
      status,
      scope: scopeForStage,
      summary,
      error: error?.slice(0, 500),
      started_at: st?.started_at,
      finished_at: st?.finished_at,
      refs: stageRefs(st),
    })
  }

  return stages
}

function collectMachineArtifacts(run: PipelineRun): QualityRunPayload['artifacts'] {
  const arts: Array<{ type: string; name: string; ref?: string }> = []
  for (const key of STAGE_KEYS) {
    const st = run.stages[key]
    if (!st?.refs) continue
    for (const [name, ref] of Object.entries(st.refs)) {
      if (typeof ref === 'string' && ref.trim()) {
        arts.push({
          type: key,
          name,
          ref: ref.startsWith('local://') || ref.startsWith('http') ? ref : `local://${ref}`,
        })
      }
    }
  }
  if (run.artifacts?.build?.fingerprint) {
    arts.push({ type: 'build', name: 'fingerprint', ref: run.artifacts.build.fingerprint })
  }
  return arts.slice(0, 50)
}

function domainArtifacts(run: PipelineRun, domain: PipelineDomain): QualityRunPayload['artifacts'] {
  const arts: QualityRunPayload['artifacts'] = []
  if (domain.adapt_task_id) {
    arts.push({
      type: 'json',
      name: 'adapt-agent',
      ref: `local://adapt-agent/${domain.adapt_task_id}.json`,
    })
  }
  for (const g of domainGerrits(run, domain.domain_id)) {
    if (g.change_url && /^https?:\/\//i.test(g.change_url)) {
      arts.push({
        type: 'gerrit',
        name: g.repo || domain.domain_id,
        ref: g.change_url,
      })
    }
  }
  return arts
}

function domainHeadline(run: PipelineRun, domain: PipelineDomain): string {
  const submitted = domainGerrits(run, domain.domain_id).filter(
    c => c.status === 'submitted' && c.change_number,
  )
  if (submitted.length) {
    return submitted.map(c => `Gerrit ${c.change_number}`).join('/').slice(0, 120)
  }
  if (domain.status === 'failed') return 'adapt failed'
  if (run.stages.flash?.status === 'failed') return 'adapt done · 整机未过 flash'
  return 'adapt done · 无 Gerrit'
}

function machineHeadline(run: PipelineRun): string {
  const node = inferCurrentNode(run)
  const enabled = run.domains.filter(d => d.enabled)
  const done = enabled.filter(d => d.status === 'done').length
  const total = enabled.length
  const failedNames = enabled.filter(d => d.status === 'failed').map(d => d.domain_label || d.domain_id)
  let h = `${node} · ${done}/${total} 域`
  if (failedNames.length) h += ` · ${failedNames[0]} fail`
  return h.slice(0, 120)
}

function machineMetrics(run: PipelineRun): Record<string, number> {
  const enabled = run.domains.filter(d => d.enabled)
  const gerritSubmitted = (run.gerrit_changes || []).filter(c => c.status === 'submitted').length
  return {
    domains_total: enabled.length,
    domains_done: enabled.filter(d => d.status === 'done').length,
    domains_failed: enabled.filter(d => d.status === 'failed').length,
    domains_pending: enabled.filter(d => d.status === 'pending' || d.status === 'running').length,
    domains_skipped: enabled.filter(d => d.status === 'skipped').length,
    iteration: run.iteration,
    gerrit_submitted: gerritSubmitted,
  }
}

async function resolveProject(run: PipelineRun): Promise<{ project_code: string; campaign_id?: string }> {
  const candidate = run.project_code?.trim()
  if (!candidate) return { project_code: UNASSIGNED_PROJECT }
  try {
    const projects = await centralClient.listAdaptPrereqProjects()
    const matched = matchCentralProject(candidate, projects)
    if (matched) return matched
  } catch { /* 降级 */ }
  return {
    project_code: candidate,
    campaign_id: run.campaign_id,
  }
}

function pipelineExtra(
  run: PipelineRun,
  scope: 'project' | 'domain',
  stages: ReturnType<typeof buildStages>,
  domain?: PipelineDomain,
): Record<string, unknown> {
  const gerrits = (run.gerrit_changes || []).map(g => ({
    domain_id: g.domain_id,
    domain_ids: g.domain_ids,
    repo: g.repo,
    change_url: g.change_url,
    change_number: g.change_number,
    status: g.status,
  }))
  return {
    pipeline: {
      schema: 1,
      scope,
      pipeline_run_id: run.run_id,
      workflow_id: run.workflow_id,
      iteration: run.iteration,
      domain_label: domain?.domain_label,
      stages,
      gerrits: scope === 'domain' && domain
        ? gerrits.filter(g => changeTouchesDomain(g, domain.domain_id))
        : gerrits,
    },
  }
}

export async function mapPipelineRunToQualityRuns(
  run: PipelineRun,
  owner?: string,
): Promise<QualityRunPayload[]> {
  if (!isPipelineTerminal(run.status)) return []

  const { project_code, campaign_id } = await resolveProject(run)
  const machineRunId = buildAdaptPipelineMachineRunId(run.run_id)
  const machineStages = buildStages(run, 'project')
  const machine: QualityRunPayload = {
    run_id: machineRunId,
    dimension: 'adapt-pipeline',
    project_code,
    campaign_id,
    owner,
    status: pipelineStatusToQuality(run.status),
    started_at: run.created_at,
    ended_at: run.finished_at || run.updated_at,
    current_node: inferCurrentNode(run).slice(0, 64),
    headline: machineHeadline(run),
    metrics: machineMetrics(run),
    artifacts: collectMachineArtifacts(run),
    extra: pipelineExtra(run, 'project', machineStages),
    ai_summary: machineHeadline(run),
    source: { tool: 'tahp-console', version: 'adapt-pipeline' },
    schema_version: 1,
  }

  const domainRuns: QualityRunPayload[] = []
  for (const domain of run.domains) {
    if (domain.status !== 'done' && domain.status !== 'failed') continue
    const domainStages = buildStages(run, 'domain', domain)
    const issues = domain.error
      ? [{
        key: domain.domain_id,
        title: domain.domain_label || domain.domain_id,
        module: domain.module,
        severity: 'critical' as const,
        status: 'fail',
        message: domain.error,
      }]
      : []

    domainRuns.push({
      run_id: buildAdaptPipelineDomainRunId(run.run_id, domain.domain_id),
      dimension: 'adapt-pipeline',
      project_code,
      campaign_id,
      parent_run_id: machineRunId,
      workspace_id: domain.workspace_id,
      domain_id: domain.domain_id,
      owner,
      status: domain.status === 'done' ? 'pass' : 'fail',
      started_at: run.created_at,
      ended_at: run.finished_at || run.updated_at,
      headline: domainHeadline(run, domain),
      metrics: {
        files_total: domain.changed_files?.length ?? 0,
        gerrit_count: domainGerrits(run, domain.domain_id).filter(c => c.status === 'submitted').length,
      },
      issues,
      artifacts: domainArtifacts(run, domain),
      extra: pipelineExtra(run, 'domain', domainStages, domain),
      source: { tool: 'tahp-console', version: 'adapt-pipeline' },
      schema_version: 1,
    })
  }

  return [machine, ...domainRuns]
}
