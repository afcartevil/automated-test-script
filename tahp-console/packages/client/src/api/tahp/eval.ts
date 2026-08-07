/**
 * 评估层 API（bug-analysis / adapt / retrieval）
 */
import { tahpGet, tahpPost, tahpPut, tahpDelete } from './client'

export type EvalSuite = 'bug-analysis' | 'adapt' | 'retrieval'

export interface Rubric {
  id: string
  weight: number
  must?: boolean
  criterion: string
  scoring?: 'objective' | 'llm'
}

export interface EvalCaseSource {
  type: 'jira' | 'local' | 'adapt_agent' | 'pipeline' | 'retrieval_query'
  jira_key?: string
  log_path?: string
  problem_description?: string
  origin_task_id?: string
  domain_id?: string
  domain_label?: string
  module?: string
  related_skills?: string[]
  form_data?: Record<string, string>
  user_notes?: string
  workspace_id?: string
  origin_pipeline_run_id?: string
  query?: string
  expected_intent?: string
  expected_top1_skill?: string | null
  expected_top_k_skills?: string[]
  retrieval_mode?: string
  preferred_skill_ids?: string[]
  expect_skill_ranking?: boolean
}

export interface EvalCase {
  id: string
  suite?: EvalSuite
  title?: string
  source: EvalCaseSource
  rubric: Rubric[]
  labels?: string[]
  created_at: string
  updated_at?: string
  had_corrections?: boolean
  mode?: 'rerun' | 'offline'
}

export interface RubricVerdict {
  id: string
  pass: boolean
  score: number
  reason: string
  evidence?: string
}

export type CaseVerdict = 'pass' | 'warn' | 'fail'

export interface CaseScore {
  total: number
  verdict: CaseVerdict
  must_failed: string[]
  rubrics: RubricVerdict[]
  summary?: string
}

export type EvalCaseStatus = 'passed' | 'warned' | 'failed' | 'error'

export interface HumanLabel {
  verdict: CaseVerdict
  note?: string
  labeled_at: string
}

export interface EvalCaseResult {
  case_id: string
  status: EvalCaseStatus
  task_id?: string
  pipeline_run_id?: string
  score?: CaseScore
  duration_ms?: number
  error?: string
  human_label?: HumanLabel
}

export interface CalibrationReport {
  labeled: number
  agreed: number
  agreement_rate: number
  disagreements: Array<{ case_id: string; judge: CaseVerdict; human: CaseVerdict; note?: string }>
  trustworthy: boolean
  min_agreement_rate: number
  min_labeled_samples: number
}

export interface EvalCaseBrief {
  case_id: string
  title?: string
  status: EvalCaseStatus
  total?: number
  verdict?: CaseVerdict
  task_id?: string
  error?: string
}

export interface EvalVariant {
  model?: string
  judge_model?: string
  skills_hash: string
  prompt_version: string
}

export interface EvalRunSummary {
  run_id: string
  suite: EvalSuite
  started_at: string
  completed_at?: string
  status: 'running' | 'completed' | 'failed' | 'aborted'
  variant: EvalVariant
  total: number
  passed: number
  warned: number
  failed: number
  errored: number
  avg_score: number
  pass_rate: number
  cases: EvalCaseBrief[]
  error?: string
}

export interface EvalComparison {
  baseline_run_id: string
  current_run_id: string
  pass_rate_delta: number
  avg_score_delta: number
  regressed: string[]
  improved: string[]
  variant_matched: boolean
}

export interface EvalCaseCandidate {
  // bug-analysis
  task_id?: string
  jira_key?: string
  title?: string
  analysis_mode?: string
  started_at?: string
  corrections_count?: number
  existing_case_id?: string
  // adapt / retrieval
  kind?: 'adapt_agent' | 'pipeline' | 'seed'
  id?: string
  domain_id?: string
  domain_label?: string
  files_modified_count?: number
  pipeline_status?: string
  query?: string
  expected_intent?: string
}

function withSuite(path: string, suite: EvalSuite): string {
  const sep = path.includes('?') ? '&' : '?'
  return `${path}${sep}suite=${encodeURIComponent(suite)}`
}

// ── 评测集 ──────────────────────────────────────────────────────────────────

export function listEvalCases(
  suite: EvalSuite = 'bug-analysis',
): Promise<{ cases: EvalCase[]; default_rubric: Rubric[]; suite: EvalSuite }> {
  return tahpGet(withSuite('/api/tahp/eval/cases', suite))
}

export function getEvalCase(caseId: string, suite: EvalSuite = 'bug-analysis'): Promise<EvalCase> {
  return tahpGet(withSuite(`/api/tahp/eval/cases/${encodeURIComponent(caseId)}`, suite))
}

export function saveEvalCase(
  caseId: string,
  payload: { title?: string; labels?: string[]; rubric?: Rubric[]; mode?: 'rerun' | 'offline' },
  suite: EvalSuite = 'bug-analysis',
): Promise<EvalCase> {
  return tahpPut(withSuite(`/api/tahp/eval/cases/${encodeURIComponent(caseId)}`, suite), {
    ...payload,
    suite,
  })
}

export function deleteEvalCase(
  caseId: string,
  suite: EvalSuite = 'bug-analysis',
): Promise<{ deleted: boolean }> {
  return tahpDelete(withSuite(`/api/tahp/eval/cases/${encodeURIComponent(caseId)}`, suite))
}

export function listEvalCandidates(
  suite: EvalSuite = 'bug-analysis',
  limit = 100,
): Promise<EvalCaseCandidate[]> {
  return tahpGet(withSuite(`/api/tahp/eval/candidates?limit=${limit}`, suite))
}

export function createEvalCaseFromReport(
  payload: {
    task_id?: string
    id?: string
    run_id?: string
    seed_id?: string
    kind?: 'adapt_agent' | 'pipeline' | 'seed'
    case_id?: string
    rubric?: Rubric[]
    labels?: string[]
    mode?: 'rerun' | 'offline'
    suite?: EvalSuite
  },
): Promise<EvalCase> {
  const suite = payload.suite || 'bug-analysis'
  return tahpPost(withSuite('/api/tahp/eval/cases/from-report', suite), { ...payload, suite })
}

export function importRetrievalSeeds(): Promise<{
  imported: string[]
  skipped: string[]
  errors: string[]
}> {
  return tahpPost('/api/tahp/eval/retrieval/import-seeds', {})
}

export interface EvalBundle {
  format: string
  version: number
  suite: EvalSuite
  exported_at: string
  redacted: boolean
  cases: EvalCase[]
  redaction_notes?: string[]
}

export function exportEvalBundle(
  suite: EvalSuite,
  opts: { caseIds?: string[]; redact?: boolean } = {},
): Promise<EvalBundle> {
  const params = new URLSearchParams()
  params.set('suite', suite)
  if (opts.caseIds?.length) params.set('ids', opts.caseIds.join(','))
  if (opts.redact === false) params.set('redact', '0')
  return tahpGet(`/api/tahp/eval/bundle/export?${params.toString()}`)
}

export function importEvalBundle(payload: {
  suite: EvalSuite
  bundle: EvalBundle | Record<string, unknown>
  overwrite?: boolean
}): Promise<{
  suite: EvalSuite
  imported: string[]
  skipped: string[]
  overwritten: string[]
}> {
  return tahpPost('/api/tahp/eval/bundle/import', payload)
}

// ── 评测批跑 ────────────────────────────────────────────────────────────────

export function listEvalRuns(
  suite: EvalSuite = 'bug-analysis',
  limit = 50,
): Promise<EvalRunSummary[]> {
  return tahpGet(withSuite(`/api/tahp/eval/runs?limit=${limit}`, suite))
}

export function getEvalRun(runId: string, suite?: EvalSuite): Promise<EvalRunSummary> {
  const path = `/api/tahp/eval/runs/${encodeURIComponent(runId)}`
  return tahpGet(suite ? withSuite(path, suite) : path)
}

export function startEvalRun(payload: {
  case_ids?: string[]
  model?: string
  judge_model?: string
  concurrency?: number
  suite?: EvalSuite
}): Promise<{ run_id: string; total: number; suite: EvalSuite }> {
  const suite = payload.suite || 'bug-analysis'
  return tahpPost(withSuite('/api/tahp/eval/runs', suite), { ...payload, suite })
}

export function abortEvalRun(runId: string): Promise<{ aborted: boolean }> {
  return tahpPost(`/api/tahp/eval/runs/${encodeURIComponent(runId)}/abort`)
}

export function getEvalCaseResult(
  runId: string,
  caseId: string,
): Promise<{ result: EvalCaseResult; case: EvalCase | null }> {
  return tahpGet(
    `/api/tahp/eval/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}`,
  )
}

export function setHumanLabel(
  runId: string,
  caseId: string,
  payload: { verdict: CaseVerdict; note?: string },
): Promise<EvalCaseResult> {
  return tahpPut(
    `/api/tahp/eval/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/label`,
    payload,
  )
}

export function getCalibration(runId: string): Promise<CalibrationReport> {
  return tahpGet(`/api/tahp/eval/runs/${encodeURIComponent(runId)}/calibration`)
}

export function compareEvalRuns(runId: string, baseline: string): Promise<EvalComparison> {
  return tahpGet(
    `/api/tahp/eval/runs/${encodeURIComponent(runId)}/compare?baseline=${encodeURIComponent(baseline)}`,
  )
}
