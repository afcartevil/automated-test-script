/**
 * 适配评测批跑。
 *
 * - adapt_agent + mode=rerun：重跑 startAdaptAgentRun，客观打分
 * - adapt_agent + mode=offline：读冻结信号 / 原始报告客观打分
 * - pipeline：V1 仅 offline（对冻结的 build/selfcheck 信号打分）
 *
 * 可选 soft LLM：rubric 中 scoring=llm 的项才走判官。
 */
import {
  cancelAdaptAgentRun,
  getAdaptAgentTask,
  readAdaptAgentReport,
  startAdaptAgentRun,
} from '../adapt-agent'
import { getRun } from '../adapt-pipeline/store'
import { resolveGatewayUpstream } from '../../hermes/run-chat/handle-api-run'
import { getTaskStream } from '../task-stream'
import { logger } from '../../logger'
import {
  ADAPT_OBJECTIVE_VERSION,
  mergeObjectiveAndLlm,
  scoreAdaptCase,
  signalsFromAdaptReport,
  signalsFromPipelineRun,
} from './adapt-objective'
import { computeSkillsHash } from './fingerprint'
import { judgeReport, resolveJudgeModel } from './judge'
import {
  genEvalRunId,
  listEvalCases,
  readEvalCase,
  saveEvalCase,
  saveEvalCaseResult,
  saveEvalRun,
} from './store'
import type {
  AdaptObjectiveSignals,
  EvalCase,
  EvalCaseBrief,
  EvalCaseResult,
  EvalRunSummary,
  EvalVariant,
  JudgeVerdict,
} from './types'

const DEFAULT_CONCURRENCY = 2
const DEFAULT_CASE_TIMEOUT_MS = 30 * 60_000
const POLL_INTERVAL_MS = 2000

const aborting = new Set<string>()

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function emitEval(runId: string, type: string, payload: Record<string, unknown>): void {
  getTaskStream().publish({
    type,
    task_id: runId,
    payload: { run_id: runId, suite: 'adapt', ...payload },
    ts: Date.now(),
  })
}

function resolveConcurrency(raw?: number): number {
  const fromEnv = Number(process.env.TAHP_EVAL_CONCURRENCY)
  const value = raw ?? (Number.isFinite(fromEnv) && fromEnv > 0 ? fromEnv : DEFAULT_CONCURRENCY)
  return Math.max(1, Math.min(4, Math.round(value)))
}

function resolveCaseTimeoutMs(): number {
  const raw = Number(process.env.TAHP_EVAL_CASE_TIMEOUT_MS)
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_CASE_TIMEOUT_MS
}

function resolveEvaluatedModel(opts: StartAdaptEvalRunOptions): string | undefined {
  if (opts.model) return opts.model
  if (process.env.TAHP_EVAL_MODEL) return process.env.TAHP_EVAL_MODEL
  try {
    return resolveGatewayUpstream(opts.profile ?? 'default').defaultModel
  } catch {
    return undefined
  }
}

function buildVariant(opts: StartAdaptEvalRunOptions): EvalVariant {
  return {
    model: resolveEvaluatedModel(opts),
    judge_model: resolveJudgeModel({ judgeModel: opts.judgeModel }),
    skills_hash: computeSkillsHash(),
    prompt_version: ADAPT_OBJECTIVE_VERSION,
  }
}

function toBrief(evalCase: EvalCase, result: EvalCaseResult): EvalCaseBrief {
  return {
    case_id: result.case_id,
    title: evalCase.title,
    status: result.status,
    total: result.score?.total,
    verdict: result.score?.verdict,
    task_id: result.task_id,
    error: result.error,
  }
}

function recomputeSummary(summary: EvalRunSummary): void {
  summary.passed = summary.cases.filter(c => c.status === 'passed').length
  summary.warned = summary.cases.filter(c => c.status === 'warned').length
  summary.failed = summary.cases.filter(c => c.status === 'failed').length
  summary.errored = summary.cases.filter(c => c.status === 'error').length
  const scored = summary.cases.filter(c => typeof c.total === 'number')
  summary.avg_score = scored.length
    ? scored.reduce((sum, c) => sum + (c.total as number), 0) / scored.length
    : 0
  summary.pass_rate = summary.total > 0 ? summary.passed / summary.total : 0
}

function needsLlm(evalCase: EvalCase): boolean {
  return evalCase.rubric.some(r => r.scoring === 'llm')
}

async function maybeJudgeSoft(
  evalCase: EvalCase,
  reportBody: string,
  signals: AdaptObjectiveSignals,
  opts: StartAdaptEvalRunOptions,
): Promise<ReturnType<typeof scoreAdaptCase>> {
  if (!needsLlm(evalCase) || !reportBody.trim()) {
    return scoreAdaptCase(evalCase, signals)
  }
  try {
    const softCase: EvalCase = {
      ...evalCase,
      rubric: evalCase.rubric.filter(r => r.scoring === 'llm'),
    }
    const softScore = await judgeReport(softCase, reportBody, {
      judgeModel: opts.judgeModel,
      profile: opts.profile,
    })
    const llm: JudgeVerdict = {
      rubrics: softScore.rubrics,
      summary: softScore.summary,
    }
    return mergeObjectiveAndLlm(evalCase.rubric, signals, llm)
  } catch (err) {
    // soft LLM 失败时仍返回客观分，不把整例打成 error
    logger.warn({ err: (err as Error).message, caseId: evalCase.id }, '[eval-adapt] soft llm skipped')
    return scoreAdaptCase(evalCase, signals)
  }
}

async function waitForAdaptTask(
  taskId: string,
  timeoutMs: number,
  isAborted: () => boolean,
): Promise<{ ok: boolean; error?: string }> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const ctx = getAdaptAgentTask(taskId)
    if (!ctx) return { ok: false, error: '任务上下文丢失（BFF 可能已重启）' }
    if (ctx.status === 'completed') return { ok: true }
    if (ctx.status === 'failed') return { ok: false, error: ctx.error || '适配失败' }

    if (ctx.status === 'waiting_user_input' || ctx.status === 'waiting_user') {
      await cancelAdaptAgentRun(taskId).catch(() => {})
      return { ok: false, error: 'Agent 请求人工输入，评测场景无人应答，已终止该用例' }
    }

    if (isAborted()) {
      await cancelAdaptAgentRun(taskId).catch(() => {})
      return { ok: false, error: '评测已中止' }
    }
    if (Date.now() > deadline) {
      await cancelAdaptAgentRun(taskId).catch(() => {})
      return { ok: false, error: `用例超时（${Math.round(timeoutMs / 60_000)} 分钟）` }
    }
    await sleep(POLL_INTERVAL_MS)
  }
}

async function runOfflineCase(evalCase: EvalCase, opts: StartAdaptEvalRunOptions): Promise<EvalCaseResult> {
  const startedAt = Date.now()
  let signals = evalCase.source.frozen_signals
  let taskId = evalCase.source.origin_task_id
  let pipelineRunId = evalCase.source.origin_pipeline_run_id
  let reportBody = ''

  if (evalCase.source.type === 'pipeline' && pipelineRunId) {
    const run = getRun(pipelineRunId)
    if (run) signals = signalsFromPipelineRun(run)
  } else if (evalCase.source.type === 'adapt_agent' && taskId) {
    const report = readAdaptAgentReport(taskId) as Record<string, unknown> | null
    if (report) {
      signals = signalsFromAdaptReport(report, evalCase.source.related_skills)
      reportBody = String(report.llm_response || report.transcript || report.audit_report || '')
    }
  }

  if (!signals) {
    return {
      case_id: evalCase.id,
      status: 'error',
      task_id: taskId,
      pipeline_run_id: pipelineRunId,
      error: '缺少客观信号（frozen_signals / 原始报告）',
      duration_ms: Date.now() - startedAt,
    }
  }

  const score = await maybeJudgeSoft(evalCase, reportBody, signals, opts)
  const status = score.verdict === 'pass' ? 'passed' : score.verdict === 'warn' ? 'warned' : 'failed'
  return {
    case_id: evalCase.id,
    status,
    task_id: taskId,
    pipeline_run_id: pipelineRunId,
    score,
    objective_signals: signals,
    duration_ms: Date.now() - startedAt,
  }
}

async function runRerunCase(
  runId: string,
  evalCase: EvalCase,
  opts: StartAdaptEvalRunOptions,
): Promise<EvalCaseResult> {
  const startedAt = Date.now()
  const isAborted = () => aborting.has(runId)

  if (evalCase.source.type === 'pipeline') {
    return {
      case_id: evalCase.id,
      status: 'error',
      error: 'V1 流水线用例仅支持 offline 客观打分，请将 mode 设为 offline',
      duration_ms: Date.now() - startedAt,
    }
  }

  const domainId = evalCase.source.domain_id
  const formData = evalCase.source.form_data
  if (!domainId || !formData) {
    return {
      case_id: evalCase.id,
      status: 'error',
      error: '用例缺少 domain_id / form_data，无法重跑',
      duration_ms: Date.now() - startedAt,
    }
  }

  const started = startAdaptAgentRun({
    domainId,
    domainLabel: evalCase.source.domain_label || domainId,
    module: evalCase.source.module || '',
    relatedSkills: evalCase.source.related_skills || [],
    formData,
    formFields: evalCase.source.form_fields?.map(f => ({
      name: f.name,
      label: f.label || f.name,
      required: f.required,
    })),
    userNotes: evalCase.source.user_notes,
    workspaceId: evalCase.source.workspace_id,
    interactionMode: false,
  })

  if (!started.ok) {
    return {
      case_id: evalCase.id,
      status: 'error',
      error: started.error || '无法启动适配 Agent',
      duration_ms: Date.now() - startedAt,
    }
  }

  const taskId = started.taskId
  emitEval(runId, 'eval.case_started', { case_id: evalCase.id, task_id: taskId, suite: 'adapt' })

  const waited = await waitForAdaptTask(taskId, resolveCaseTimeoutMs(), isAborted)
  if (!waited.ok) {
    return {
      case_id: evalCase.id,
      status: 'error',
      task_id: taskId,
      error: waited.error,
      duration_ms: Date.now() - startedAt,
    }
  }

  const report = readAdaptAgentReport(taskId) as Record<string, unknown> | null
  if (!report) {
    return {
      case_id: evalCase.id,
      status: 'error',
      task_id: taskId,
      error: '适配报告未落盘',
      duration_ms: Date.now() - startedAt,
    }
  }

  const signals = signalsFromAdaptReport(report, evalCase.source.related_skills)
  const reportBody = String(report.llm_response || report.transcript || report.audit_report || '')
  const score = await maybeJudgeSoft(evalCase, reportBody, signals, opts)
  const status = score.verdict === 'pass' ? 'passed' : score.verdict === 'warn' ? 'warned' : 'failed'

  return {
    case_id: evalCase.id,
    status,
    task_id: taskId,
    score,
    objective_signals: signals,
    duration_ms: Date.now() - startedAt,
  }
}

async function runOneCase(
  runId: string,
  evalCase: EvalCase,
  opts: StartAdaptEvalRunOptions,
): Promise<EvalCaseResult> {
  const mode = evalCase.mode || (evalCase.source.type === 'pipeline' ? 'offline' : 'rerun')
  if (mode === 'offline') return runOfflineCase(evalCase, opts)
  return runRerunCase(runId, evalCase, opts)
}

export interface StartAdaptEvalRunOptions {
  caseIds?: string[]
  model?: string
  judgeModel?: string
  profile?: string
  concurrency?: number
}

export interface StartAdaptEvalRunResult {
  ok: boolean
  runId?: string
  total?: number
  error?: string
}

function resolveCases(caseIds?: string[]): { cases: EvalCase[]; error?: string } {
  if (!caseIds?.length) return { cases: listEvalCases('adapt') }
  const cases: EvalCase[] = []
  for (const id of caseIds) {
    const found = readEvalCase(id, 'adapt')
    if (!found) return { cases: [], error: `找不到适配评测用例 ${id}` }
    cases.push(found)
  }
  return { cases }
}

async function executeEvalRun(
  summary: EvalRunSummary,
  cases: EvalCase[],
  opts: StartAdaptEvalRunOptions,
): Promise<void> {
  const concurrency = resolveConcurrency(opts.concurrency)
  let cursor = 0

  async function worker(): Promise<void> {
    for (;;) {
      const index = cursor++
      if (index >= cases.length) return
      const evalCase = cases[index]

      if (aborting.has(summary.run_id)) {
        const result: EvalCaseResult = {
          case_id: evalCase.id,
          status: 'error',
          error: '评测已中止',
        }
        summary.cases.push(toBrief(evalCase, result))
        saveEvalCaseResult(summary.run_id, result, 'adapt')
        continue
      }

      let result: EvalCaseResult
      try {
        result = await runOneCase(summary.run_id, evalCase, opts)
      } catch (err) {
        result = {
          case_id: evalCase.id,
          status: 'error',
          error: (err as Error).message,
        }
      }

      saveEvalCaseResult(summary.run_id, result, 'adapt')
      summary.cases.push(toBrief(evalCase, result))
      recomputeSummary(summary)
      saveEvalRun(summary)

      emitEval(summary.run_id, 'eval.case_done', {
        case_id: evalCase.id,
        status: result.status,
        total: result.score?.total,
        verdict: result.score?.verdict,
        task_id: result.task_id,
        error: result.error,
        done: summary.cases.length,
        total_cases: summary.total,
      })
    }
  }

  try {
    await Promise.all(Array.from({ length: Math.min(concurrency, cases.length) }, () => worker()))
    summary.status = aborting.has(summary.run_id) ? 'aborted' : 'completed'
  } catch (err) {
    summary.status = 'failed'
    summary.error = (err as Error).message
    logger.error({ err: (err as Error).message, runId: summary.run_id }, '[eval-adapt] run failed')
  } finally {
    aborting.delete(summary.run_id)
    summary.completed_at = new Date().toISOString()
    recomputeSummary(summary)
    saveEvalRun(summary)
    emitEval(summary.run_id, summary.status === 'failed' ? 'eval.failed' : 'eval.completed', {
      status: summary.status,
      total: summary.total,
      passed: summary.passed,
      warned: summary.warned,
      failed: summary.failed,
      errored: summary.errored,
      avg_score: summary.avg_score,
      pass_rate: summary.pass_rate,
      error: summary.error,
    })
  }
}

export function startAdaptEvalRun(opts: StartAdaptEvalRunOptions = {}): StartAdaptEvalRunResult {
  const { cases, error } = resolveCases(opts.caseIds)
  if (error) return { ok: false, error }
  if (!cases.length) return { ok: false, error: '适配评测集为空，请先从历史报告 / 流水线 run 转存用例' }

  const invalid = cases.find(c => !c.rubric?.length)
  if (invalid) return { ok: false, error: `用例 ${invalid.id} 未配置评分标准` }

  const runId = genEvalRunId('adapt')
  const summary: EvalRunSummary = {
    run_id: runId,
    suite: 'adapt',
    started_at: new Date().toISOString(),
    status: 'running',
    variant: buildVariant(opts),
    total: cases.length,
    passed: 0,
    warned: 0,
    failed: 0,
    errored: 0,
    avg_score: 0,
    pass_rate: 0,
    cases: [],
  }
  saveEvalRun(summary)

  emitEval(runId, 'eval.started', {
    total: cases.length,
    variant: summary.variant,
    case_ids: cases.map(c => c.id),
  })

  setImmediate(() => {
    executeEvalRun(summary, cases, opts).catch(err => {
      logger.error({ err: (err as Error).message, runId }, '[eval-adapt] unhandled')
    })
  })

  return { ok: true, runId, total: cases.length }
}

export function abortAdaptEvalRun(runId: string): { ok: boolean } {
  aborting.add(runId)
  return { ok: true }
}

export function updateAdaptEvalCase(evalCase: EvalCase): void {
  saveEvalCase({ ...evalCase, suite: 'adapt', updated_at: new Date().toISOString() }, 'adapt')
}
