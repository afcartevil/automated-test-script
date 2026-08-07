/**
 * 适配评测用例冷启动 —— 从 adapt-agent 报告或流水线 run 转存。
 */
import { existsSync, readdirSync, readFileSync } from 'fs'
import { join } from 'path'
import { readAdaptAgentReport } from '../adapt-agent'
import { getRun, listRuns } from '../adapt-pipeline/store'
import { tahpPaths } from '../paths'
import {
  DEFAULT_ADAPT_AGENT_RUBRIC,
  DEFAULT_ADAPT_PIPELINE_RUBRIC,
  signalsFromAdaptReport,
  signalsFromPipelineRun,
} from './adapt-objective'
import { listEvalCases, readEvalCase, saveEvalCase } from './store'
import type { EvalCase, Rubric } from './types'

export { DEFAULT_ADAPT_AGENT_RUBRIC, DEFAULT_ADAPT_PIPELINE_RUBRIC }

interface AdaptReportShape {
  task_id?: string
  status?: string
  domain?: string
  domainId?: string
  domain_id?: string
  domain_label?: string
  domainLabel?: string
  module?: string
  relatedSkills?: string[]
  related_skills?: string[]
  formData?: Record<string, string>
  form_data?: Record<string, string>
  formFields?: Array<{ name: string; label?: string; required?: boolean }>
  userNotes?: string
  user_notes?: string
  workspaceId?: string
  workspace_id?: string
  started_at?: string
  startedAt?: string
  files_modified?: unknown[]
  file_changes?: unknown[]
  fileChanges?: unknown[]
}

export interface AdaptEvalCandidate {
  kind: 'adapt_agent' | 'pipeline'
  id: string
  title?: string
  domain_id?: string
  domain_label?: string
  started_at?: string
  files_modified_count?: number
  pipeline_status?: string
  existing_case_id?: string
}

function sanitizeIdPart(raw: string): string {
  return raw.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
}

function uniqueCaseId(base: string): string {
  const taken = new Set(listEvalCases('adapt').map(c => c.id))
  if (!taken.has(base)) return base
  for (let i = 2; i < 100; i++) {
    const next = `${base}-${i}`
    if (!taken.has(next)) return next
  }
  return `${base}-${Date.now()}`
}

function listAdaptAgentReportIds(limit: number): string[] {
  const dir = join(tahpPaths.reportsDir, 'adapt-agent')
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter(f => f.startsWith('task-adapt-agent-') && f.endsWith('.json'))
    .sort((a, b) => b.localeCompare(a))
    .slice(0, limit)
    .map(f => f.replace(/\.json$/, ''))
}

function originIndex(): Map<string, string> {
  const map = new Map<string, string>()
  for (const c of listEvalCases('adapt')) {
    if (c.source.origin_task_id) map.set(c.source.origin_task_id, c.id)
    if (c.source.origin_pipeline_run_id) map.set(c.source.origin_pipeline_run_id, c.id)
  }
  return map
}

export function listAdaptEvalCandidates(limit = 100): AdaptEvalCandidate[] {
  const existing = originIndex()
  const candidates: AdaptEvalCandidate[] = []

  for (const taskId of listAdaptAgentReportIds(limit)) {
    const report = readAdaptAgentReport(taskId) as AdaptReportShape | null
    if (!report || report.status !== 'completed') continue
    const files =
      report.files_modified || report.file_changes || report.fileChanges || []
    candidates.push({
      kind: 'adapt_agent',
      id: taskId,
      title: report.domain_label || report.domainLabel || report.domain || taskId,
      domain_id: report.domain_id || report.domainId || report.domain,
      domain_label: report.domain_label || report.domainLabel,
      started_at: report.started_at || report.startedAt,
      files_modified_count: Array.isArray(files) ? files.length : 0,
      existing_case_id: existing.get(taskId),
    })
  }

  const pipeline = listRuns({ limit, status: ['passed', 'failed', 'aborted', 'waiting_human'] })
  for (const item of pipeline.items) {
    candidates.push({
      kind: 'pipeline',
      id: item.run_id,
      title: `${item.project_code || 'pipeline'} · ${item.status}`,
      started_at: item.updated_at || item.created_at,
      pipeline_status: item.status,
      existing_case_id: existing.get(item.run_id),
    })
  }

  return candidates
    .sort((a, b) => String(b.started_at || '').localeCompare(String(a.started_at || '')))
    .slice(0, limit)
}

export interface CreateAdaptCaseOptions {
  caseId?: string
  rubric?: Rubric[]
  labels?: string[]
  mode?: 'rerun' | 'offline'
}

export function createAdaptCaseFromAgentReport(
  taskId: string,
  opts: CreateAdaptCaseOptions = {},
): { ok: boolean; evalCase?: EvalCase; error?: string } {
  const report = readAdaptAgentReport(taskId) as AdaptReportShape | null
  if (!report) return { ok: false, error: `找不到适配报告 ${taskId}` }
  if (report.status !== 'completed') {
    return { ok: false, error: '只接受 status=completed 的适配报告' }
  }

  const domainId = report.domain_id || report.domainId || report.domain || ''
  const formData = report.formData || report.form_data || {}
  const related = report.relatedSkills || report.related_skills || []
  if (!domainId) return { ok: false, error: '报告缺少 domain_id' }
  if (!Object.keys(formData).length) {
    return { ok: false, error: '报告缺少 formData，无法复现' }
  }

  const baseId = sanitizeIdPart(opts.caseId || `adapt-${domainId}-${taskId.slice(-8)}`)
  if (!baseId) return { ok: false, error: '无法生成合法的用例 ID' }
  const caseId = opts.caseId ? baseId : uniqueCaseId(baseId)
  if (opts.caseId && readEvalCase(caseId, 'adapt')) {
    return { ok: false, error: `用例 ${caseId} 已存在` }
  }

  const signals = signalsFromAdaptReport(report as Record<string, unknown>, related)

  const evalCase: EvalCase = {
    id: caseId,
    suite: 'adapt',
    title: report.domain_label || report.domainLabel || domainId,
    source: {
      type: 'adapt_agent',
      origin_task_id: taskId,
      domain_id: domainId,
      domain_label: report.domain_label || report.domainLabel,
      module: report.module || '',
      related_skills: related,
      form_data: Object.fromEntries(
        Object.entries(formData).map(([k, v]) => [k, String(v ?? '')]),
      ),
      form_fields: report.formFields,
      user_notes: report.userNotes || report.user_notes,
      workspace_id: report.workspaceId || report.workspace_id,
      frozen_signals: signals,
    },
    rubric: opts.rubric?.length
      ? opts.rubric
      : DEFAULT_ADAPT_AGENT_RUBRIC.map(r => ({ ...r })),
    labels: opts.labels,
    created_at: new Date().toISOString(),
    mode: opts.mode || 'rerun',
  }

  saveEvalCase(evalCase, 'adapt')
  return { ok: true, evalCase }
}

export function createAdaptCaseFromPipelineRun(
  runId: string,
  opts: CreateAdaptCaseOptions = {},
): { ok: boolean; evalCase?: EvalCase; error?: string } {
  const run = getRun(runId)
  if (!run) return { ok: false, error: `找不到流水线 run ${runId}` }

  const enabled = (run.domains || []).filter(d => d.enabled !== false)
  if (!enabled.length) return { ok: false, error: '流水线没有启用的适配域' }

  // 多域时取第一个启用域作为可重跑的 agent 输入快照；客观分仍看整链
  const primary = enabled[0]
  const formData: Record<string, string> = {}
  for (const [k, v] of Object.entries(primary.form_data || {})) {
    formData[k] = String(v ?? '')
  }

  const baseId = sanitizeIdPart(opts.caseId || `pipe-${run.project_code || runId.slice(-8)}`)
  const caseId = opts.caseId ? baseId : uniqueCaseId(baseId)
  if (opts.caseId && readEvalCase(caseId, 'adapt')) {
    return { ok: false, error: `用例 ${caseId} 已存在` }
  }

  const signals = signalsFromPipelineRun(run)

  const evalCase: EvalCase = {
    id: caseId,
    suite: 'adapt',
    title: `${run.project_code || runId} / ${primary.domain_label || primary.domain_id}`,
    source: {
      type: 'pipeline',
      origin_pipeline_run_id: runId,
      origin_task_id: primary.adapt_task_id,
      domain_id: primary.domain_id,
      domain_label: primary.domain_label,
      module: primary.module,
      related_skills: primary.related_skills,
      form_data: formData,
      workspace_id: primary.workspace_id,
      frozen_signals: signals,
    },
    rubric: opts.rubric?.length
      ? opts.rubric
      : DEFAULT_ADAPT_PIPELINE_RUBRIC.map(r => ({ ...r })),
    labels: opts.labels,
    created_at: new Date().toISOString(),
    // V1：流水线用例默认离线客观打分，避免拉起整链编译/刷机
    mode: opts.mode || 'offline',
  }

  saveEvalCase(evalCase, 'adapt')
  return { ok: true, evalCase }
}

/** 兼容入口：按 kind 分发 */
export function createAdaptCaseFromCandidate(
  kind: 'adapt_agent' | 'pipeline',
  id: string,
  opts: CreateAdaptCaseOptions = {},
): { ok: boolean; evalCase?: EvalCase; error?: string } {
  return kind === 'pipeline'
    ? createAdaptCaseFromPipelineRun(id, opts)
    : createAdaptCaseFromAgentReport(id, opts)
}

/** 供调试：直接读磁盘报告（不经 adapt-agent API） */
export function readRawAdaptReportFile(taskId: string): Record<string, unknown> | null {
  const p = join(tahpPaths.reportsDir, 'adapt-agent', `${taskId}.json`)
  if (!existsSync(p)) return null
  try {
    return JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
  } catch {
    return null
  }
}
