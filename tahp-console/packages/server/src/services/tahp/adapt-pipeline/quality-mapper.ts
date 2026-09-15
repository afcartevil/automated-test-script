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

type StageFact = { label: string; value: string }

type StageReport = {
  key: PipelineStageKey
  status: StageReportStatus
  scope: 'project' | 'domain'
  summary: string
  headline?: string
  facts?: StageFact[]
  error?: string
  error_brief?: string
  started_at?: string
  finished_at?: string
  duration_ms?: number
  refs?: Record<string, string>
}

const STAGE_ZH: Record<PipelineStageKey, string> = {
  prereq: '前置',
  adapt: '适配',
  build: '编译',
  flash: '烧录',
  selfcheck: '自检',
  gerrit: '合入',
}

function clipText(value: string, max: number): string {
  return value.length <= max ? value : value.slice(0, max)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed.startsWith('{')) {
      try {
        const parsed = JSON.parse(trimmed) as unknown
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed as Record<string, unknown>
        }
      } catch { /* ignore */ }
    }
  }
  return null
}

function pickField(obj: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const raw = obj[key]
    if (typeof raw === 'string' && raw.trim()) return raw.trim()
    if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw)
  }
  return ''
}

function formatDurationMs(ms?: number): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return ''
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec} 秒`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  if (min < 60) return rem ? `${min} 分 ${rem} 秒` : `${min} 分`
  const hour = Math.floor(min / 60)
  return `${hour} 小时 ${min % 60} 分`
}

function durationOf(st: StageState | undefined, payload?: Record<string, unknown>): number | undefined {
  const fromPayload = payload ? Number(payload.durationMs ?? payload.duration_ms) : NaN
  if (Number.isFinite(fromPayload) && fromPayload >= 0) return fromPayload
  if (!st?.started_at || !st.finished_at) return undefined
  const start = Date.parse(st.started_at)
  const end = Date.parse(st.finished_at)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return undefined
  return end - start
}

function errorBriefOf(error?: string): string | undefined {
  if (!error?.trim()) return undefined
  const lines = error.split(/\r?\n/).filter(line => line.trim()).slice(0, 12)
  return clipText(lines.join('\n'), 800)
}

function isUnreadableSummary(raw: string): boolean {
  const trimmed = raw.trim()
  if (!trimmed) return true
  if (trimmed === '0' || trimmed === '{}' || trimmed === 'null') return true
  return /^[0-9]+$/.test(trimmed) && trimmed.length < 4
}

function stagePayload(st: StageState | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const fromSummary = asRecord(st?.summary)
  if (fromSummary) Object.assign(out, fromSummary)
  if (st?.progress && typeof st.progress === 'object' && !Array.isArray(st.progress)) {
    Object.assign(out, st.progress)
  }
  return out
}

function parseBuildNotes(notes: string): { tmux?: string; targets?: string } {
  return {
    tmux: notes.match(/tmux=(\S+)/)?.[1],
    targets: notes.match(/targets=(\S+)/)?.[1],
  }
}

function mapStageReportStatus(
  st: StageState | undefined,
  run: PipelineRun,
): StageReportStatus {
  if (!st) return 'pending'
  if (st.status === 'done') return 'done'
  if (st.status === 'failed') return 'failed'
  if (st.status === 'skipped') return 'skipped'
  if (st.status === 'waiting_human' && isPipelineTerminal(run.status)) return 'failed'
  return 'pending'
}

function factsFromPayload(
  key: PipelineStageKey,
  payload: Record<string, unknown>,
  st: StageState | undefined,
): StageFact[] {
  const facts: StageFact[] = []
  const push = (label: string, value: string) => {
    if (value.trim()) facts.push({ label, value: clipText(value.trim(), 240) })
  }
  if (key === 'prereq') {
    push('源系统', pickField(payload, ['from_os', 'fromOs']))
    push('目标系统', pickField(payload, ['to_os', 'toOs']))
    push('战役', pickField(payload, ['campaign_id', 'campaignId']))
    push('启用域数', pickField(payload, ['domain_count', 'domainCount']))
    return facts
  }
  if (key === 'build') {
    push('产物目录', pickField(payload, ['artifactsDir', 'artifacts_dir']))
    push('包路径', pickField(payload, ['pkgPath', 'pkg_path']))
    const notes = pickField(payload, ['notes'])
    const parsed = notes ? parseBuildNotes(notes) : {}
    push('编译模块', parsed.targets?.replace(/,/g, ' / ') || '')
    push('构建 ID', parsed.tmux || pickField(payload, ['build_run_id']))
    push('Skill', pickField(payload, ['skillId', 'skill_id']))
    const dur = durationOf(st, payload)
    push('耗时', formatDurationMs(dur))
    return facts
  }
  if (key === 'flash') {
    push('设备', pickField(payload, ['device', 'device_id', 'deviceId', 'serial']))
    push('刷机日志', pickField(payload, ['flash_log_path', 'log_path']) || String(st?.refs?.flash_log_path || ''))
    return facts
  }
  if (key === 'selfcheck') {
    push('报告', pickField(payload, ['selfcheck_report_id']) || String(st?.refs?.selfcheck_report_id || ''))
    push('通过 / 失败', pickField(payload, ['passed_failed', 'result']))
    return facts
  }
  return facts
}

function describeStage(
  key: PipelineStageKey,
  status: StageReportStatus,
  st: StageState | undefined,
  run: PipelineRun,
  presetSummary: string,
): { summary: string; headline: string; facts: StageFact[] } {
  const zh = STAGE_ZH[key]
  const payload = stagePayload(st)
  const facts = factsFromPayload(key, payload, st)
  const rawText = typeof st?.summary === 'string' ? st.summary.trim() : ''
  const preset = presetSummary.trim()

  if (key === 'prereq') {
    const enabled = run.domains.filter(d => d.enabled)
    const incomplete = enabled.reduce((n, d) => n + d.incomplete_required.length, 0)
    const os = [run.from_os || pickField(payload, ['from_os']), run.to_os || pickField(payload, ['to_os'])]
      .filter(Boolean).join(' → ')
    const names = enabled.map(d => d.domain_label || d.domain_id).slice(0, 4).join(', ')
    if (status === 'failed' && incomplete > 0) {
      const headline = `前置未完成 · 缺 ${incomplete} 项必填`
      return { summary: headline, headline, facts }
    }
    const headline = status === 'done'
      ? `前置完成 · ${os || '系统跨度未知'} · ${enabled.length} 域${names ? `（${names}）` : ''}`
      : preset || `${zh}未执行`
    if (os && !facts.some(f => f.label === '源系统' || f.label === '目标系统')) {
      if (run.from_os) facts.unshift({ label: '源系统', value: run.from_os })
      if (run.to_os) facts.splice(run.from_os ? 1 : 0, 0, { label: '目标系统', value: run.to_os })
    }
    if (enabled.length && !facts.some(f => f.label === '启用域数')) {
      facts.push({ label: '启用域', value: names || String(enabled.length) })
    }
    return { summary: clipText(headline, 1500), headline, facts }
  }

  if (key === 'adapt') {
    const headline = status === 'done'
      ? (preset.startsWith('adapt ') ? preset : `适配完成 · ${preset}`)
      : status === 'failed'
        ? (st?.error || preset || '适配失败')
        : (preset || '适配未执行')
    return { summary: clipText(headline, 1500), headline: clipText(headline, 180), facts }
  }

  if (key === 'build') {
    if (status === 'failed') {
      const headline = st?.error ? `编译失败 · ${st.error.split(/\r?\n/)[0]}` : '编译失败'
      return { summary: clipText(headline, 1500), headline: clipText(headline, 180), facts }
    }
    if (status === 'done') {
      const dur = formatDurationMs(durationOf(st, payload))
      const headline = dur ? `编译通过 · 产物已就绪 · ${dur}` : '编译通过 · 产物已就绪'
      return { summary: headline, headline, facts }
    }
    return { summary: preset || '编译未执行', headline: preset || '编译未执行', facts }
  }

  if (key === 'flash') {
    if (status === 'failed') {
      const headline = st?.error ? `烧录失败 · ${st.error.split(/\r?\n/)[0]}` : '烧录失败'
      return { summary: clipText(headline, 1500), headline: clipText(headline, 180), facts }
    }
    if (status === 'done' && isUnreadableSummary(rawText || preset)) {
      const headline = `烧录已标记完成，但上报摘要无法解读（原始值：${rawText || preset || '空'}）`
      facts.push({ label: '原始摘要', value: rawText || preset || '空' })
      return { summary: headline, headline, facts }
    }
    if (status === 'done') {
      const headline = preset && !preset.startsWith('{') && !isUnreadableSummary(preset)
        ? preset
        : '烧录完成'
      return { summary: clipText(headline, 1500), headline: clipText(headline, 180), facts }
    }
    return { summary: preset || '烧录未执行', headline: preset || '烧录未执行', facts }
  }

  if (key === 'selfcheck') {
    if (status === 'pending' && run.stages.flash?.status === 'failed') {
      const headline = '整机未过 flash，无自检报告'
      return { summary: headline, headline, facts }
    }
    if (status === 'skipped' || (status === 'pending' && (preset === '未执行' || preset === '待执行'))) {
      const headline = status === 'skipped' ? '本轮跳过自检 · 未执行用例' : '自检未执行'
      return { summary: headline, headline, facts }
    }
    if (status === 'failed') {
      const headline = st?.error ? `自检失败 · ${st.error.split(/\r?\n/)[0]}` : '自检失败'
      return { summary: clipText(headline, 1500), headline: clipText(headline, 180), facts }
    }
    if (status === 'done') {
      const headline = '自检完成'
      return { summary: headline, headline, facts }
    }
    return { summary: preset || '自检未执行', headline: preset || '自检未执行', facts }
  }

  const headline = preset || (status === 'done' ? `${zh}完成` : `${zh}未执行`)
  return { summary: clipText(headline, 1500), headline: clipText(headline, 180), facts }
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
  if (domain.status === 'failed') return (domain.error || 'adapt failed').slice(0, 1500)
  const n = domain.changed_files?.length ?? 0
  const files = n ? `改 ${n} 个文件` : '无代码变更需要合入'
  return `adapt done · ${files}`.slice(0, 1500)
}

function machineAdaptSummary(run: PipelineRun): string {
  const enabled = run.domains.filter(d => d.enabled)
  const done = enabled.filter(d => d.status === 'done').length
  const failed = enabled.filter(d => d.status === 'failed').length
  const pending = enabled.filter(d => d.status === 'pending' || d.status === 'running').length
  const skipped = enabled.filter(d => d.status === 'skipped').length
  return `通过 ${done} · 失败 ${failed} · 未终态 ${pending} · 跳过 ${skipped}`
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

function rawFallbackSummary(st: StageState | undefined, fallback: string): string {
  if (typeof st?.summary === 'string' && st.summary.trim() && !st.summary.trim().startsWith('{')) {
    return st.summary.trim().slice(0, 1500)
  }
  if (st?.status === 'done') return fallback
  if (st?.status === 'failed') return (st.error || fallback).slice(0, 1500)
  return fallback
}

function snapshotFormData(
  data: Record<string, unknown> | undefined,
  fields?: Array<{ name: string }>,
): Record<string, string> {
  const out: Record<string, string> = {}
  const keys = fields?.length ? fields.map(f => f.name) : Object.keys(data || {})
  for (const key of keys.slice(0, 24)) {
    const raw = data?.[key]
    if (raw == null || raw === '') {
      out[key] = ''
      continue
    }
    const text = typeof raw === 'string' ? raw : JSON.stringify(raw)
    out[key] = clipText(text, 160)
  }
  return out
}

function snapshotPrereq(run: PipelineRun): Record<string, unknown> {
  const enabled = run.domains.filter(d => d.enabled).slice(0, 8)
  const bc = run.build_context
  return {
    from_os: run.from_os,
    to_os: run.to_os,
    campaign_id: run.campaign_id,
    device_id: run.device_id,
    test_plan: run.test_plan
      ? { mode: run.test_plan.mode, test_type: run.test_plan.test_type }
      : undefined,
    build_context: bc
      ? {
        mapped_root: bc.mapped_root,
        linux_root: bc.linux_root,
        workspace: bc.workspace,
        variant: bc.variant,
        project: bc.project,
        build_kind: bc.build_kind,
        build_targets: bc.build_targets,
        need_pack: bc.need_pack,
        gerrit_issue_id: bc.gerrit_issue_id,
      }
      : undefined,
    domains: enabled.map(d => ({
      domain_id: d.domain_id,
      domain_label: d.domain_label,
      related_skills: (d.related_skills || []).slice(0, 8),
      incomplete_required: (d.incomplete_required || []).slice(0, 20),
      layout_fields: (d.layout_fields || []).slice(0, 24).map(f => ({
        name: f.name,
        label: f.label,
        required: !!f.required,
      })),
      form_data: snapshotFormData(d.form_data, d.layout_fields),
    })),
  }
}

function buildStages(
  run: PipelineRun,
  scope: 'project' | 'domain',
  domain?: PipelineDomain,
): StageReport[] {
  const stages: StageReport[] = []

  for (const key of STAGE_KEYS) {
    const st = run.stages[key]
    let status = mapStageReportStatus(st, run)
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
        : rawFallbackSummary(st, 'Gerrit 未跑或未完成')
    } else {
      scopeForStage = 'project'
      summary = rawFallbackSummary(
        st,
        key === 'selfcheck' && status === 'pending' ? '未执行' : '待执行',
      )
      if (key === 'selfcheck' && status === 'pending' && run.stages.flash?.status === 'failed') {
        summary = '整机未过 flash，无自检报告'
      }
    }

    if (!summary.trim()) summary = `${STAGE_ZH[key]} · ${status}`
    const described = describeStage(key, status, st, run, summary)
    const payload = stagePayload(st)
    const durationMs = durationOf(st, payload)

    stages.push({
      key,
      status,
      scope: scopeForStage,
      summary: described.summary,
      headline: described.headline,
      facts: described.facts.length ? described.facts : undefined,
      error: error?.slice(0, 500),
      error_brief: errorBriefOf(error),
      started_at: st?.started_at,
      finished_at: st?.finished_at,
      duration_ms: durationMs,
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
      ...(scope === 'project' ? { prereq: snapshotPrereq(run) } : {}),
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
