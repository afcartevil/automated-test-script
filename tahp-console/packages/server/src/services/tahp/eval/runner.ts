/**
 * 评测批跑 —— 对评测集重跑 Bug 分析并送判官打分。
 *
 * 必须跑在 BFF 进程内：Bug 分析走的 Agent Bridge 只在这里活着。
 * CLI 通过 REST 触发，不自己起流程。
 */
import {
  cancelBugTask,
  getBugTask,
  readBugReport,
  startLocalLogBugAnalysis,
  startSingleBugAnalysis,
} from '../bug-analysis'
import { resolveGatewayUpstream } from '../../hermes/run-chat/handle-api-run'
import { getTaskStream } from '../task-stream'
import { logger } from '../../logger'
import { computeSkillsHash } from './fingerprint'
import { JUDGE_PROMPT_VERSION, judgeReport, resolveJudgeModel } from './judge'
import {
  genEvalRunId,
  listEvalCases,
  readEvalCase,
  saveEvalCase,
  saveEvalCaseResult,
  saveEvalRun,
} from './store'
import type {
  EvalCase,
  EvalCaseBrief,
  EvalCaseResult,
  EvalRunSummary,
  EvalVariant,
} from './types'

const DEFAULT_CONCURRENCY = 2
const DEFAULT_CASE_TIMEOUT_MS = 30 * 60_000
const POLL_INTERVAL_MS = 2000

/** 正在中止的 run */
const aborting = new Set<string>()

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function emitEval(runId: string, type: string, payload: Record<string, unknown>): void {
  getTaskStream().publish({
    type,
    task_id: runId,
    payload: { run_id: runId, ...payload },
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

/**
 * 被评模型只是个标签：实际模型由 Hermes profile 决定，这里记录下来用于区分变体，
 * 不代表 runner 能改变 Agent 用的模型。
 */
function resolveEvaluatedModel(opts: StartEvalRunOptions): string | undefined {
  if (opts.model) return opts.model
  if (process.env.TAHP_EVAL_MODEL) return process.env.TAHP_EVAL_MODEL
  try {
    return resolveGatewayUpstream(opts.profile ?? 'default').defaultModel
  } catch {
    return undefined
  }
}

function buildVariant(opts: StartEvalRunOptions): EvalVariant {
  return {
    model: resolveEvaluatedModel(opts),
    judge_model: resolveJudgeModel({ judgeModel: opts.judgeModel }),
    skills_hash: computeSkillsHash(),
    prompt_version: JUDGE_PROMPT_VERSION,
  }
}

const SUITE = 'bug-analysis' as const

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

// ─── 单例执行 ────────────────────────────────────────────────────────────────

function startAnalysisForCase(evalCase: EvalCase): { ok: boolean; taskId?: string; error?: string } {
  if (evalCase.source.type === 'local') {
    const result = startLocalLogBugAnalysis({
      logPath: evalCase.source.log_path ?? '',
      problemDescription: evalCase.source.problem_description ?? '',
    })
    return { ok: result.ok, taskId: result.taskId, error: result.error }
  }
  const result = startSingleBugAnalysis({
    rawInput: evalCase.source.jira_key ?? '',
    userDescription: evalCase.source.problem_description,
  })
  return { ok: result.ok, taskId: result.taskId, error: result.error }
}

async function waitForBugTask(
  taskId: string,
  timeoutMs: number,
  isAborted: () => boolean,
): Promise<{ ok: boolean; error?: string }> {
  const deadline = Date.now() + timeoutMs

  for (;;) {
    const ctx = getBugTask(taskId)
    if (!ctx) return { ok: false, error: '任务上下文丢失（BFF 可能已重启）' }

    if (ctx.status === 'completed') return { ok: true }
    if (ctx.status === 'failed') return { ok: false, error: ctx.error || 'Bug 分析失败' }
    if (ctx.status === 'cancelled') return { ok: false, error: 'Bug 分析被取消' }

    // 评测场景没有人在旁边应答，挂着只会占住 Bridge 会话
    if (ctx.status === 'waiting_user_input') {
      await cancelBugTask(taskId).catch(() => {})
      return { ok: false, error: 'Agent 请求人工输入，评测场景无人应答，已终止该用例' }
    }

    if (isAborted()) {
      await cancelBugTask(taskId).catch(() => {})
      return { ok: false, error: '评测已中止' }
    }

    if (Date.now() > deadline) {
      await cancelBugTask(taskId).catch(() => {})
      return { ok: false, error: `用例超时（${Math.round(timeoutMs / 60_000)} 分钟）` }
    }

    await sleep(POLL_INTERVAL_MS)
  }
}

function extractReportBody(taskId: string): string {
  const report = readBugReport(taskId) as Record<string, unknown> | null
  if (!report) return ''
  return String(report.report_body || report.llm_response || '').trim()
}

async function runOneCase(
  runId: string,
  evalCase: EvalCase,
  opts: StartEvalRunOptions,
): Promise<EvalCaseResult> {
  const startedAt = Date.now()
  const isAborted = () => aborting.has(runId)

  const started = startAnalysisForCase(evalCase)
  if (!started.ok || !started.taskId) {
    return {
      case_id: evalCase.id,
      status: 'error',
      error: started.error || '无法启动 Bug 分析',
      duration_ms: Date.now() - startedAt,
    }
  }

  const taskId = started.taskId
  emitEval(runId, 'eval.case_started', { case_id: evalCase.id, task_id: taskId })

  const waited = await waitForBugTask(taskId, resolveCaseTimeoutMs(), isAborted)
  if (!waited.ok) {
    return {
      case_id: evalCase.id,
      status: 'error',
      task_id: taskId,
      error: waited.error,
      duration_ms: Date.now() - startedAt,
    }
  }

  const reportBody = extractReportBody(taskId)
  if (!reportBody) {
    return {
      case_id: evalCase.id,
      status: 'error',
      task_id: taskId,
      error: '报告正文为空',
      duration_ms: Date.now() - startedAt,
    }
  }

  try {
    const score = await judgeReport(evalCase, reportBody, {
      judgeModel: opts.judgeModel,
      profile: opts.profile,
    })
    const status = score.verdict === 'pass' ? 'passed' : score.verdict === 'warn' ? 'warned' : 'failed'
    return {
      case_id: evalCase.id,
      status,
      task_id: taskId,
      score,
      duration_ms: Date.now() - startedAt,
    }
  } catch (err) {
    // 判不出来和判得差是两回事，记 error 不记 0 分
    return {
      case_id: evalCase.id,
      status: 'error',
      task_id: taskId,
      error: `判官打分失败: ${(err as Error).message}`,
      duration_ms: Date.now() - startedAt,
    }
  }
}

// ─── 批跑 ────────────────────────────────────────────────────────────────────

export interface StartEvalRunOptions {
  caseIds?: string[]
  /** 被评模型标签（实际模型由 Hermes profile 决定） */
  model?: string
  judgeModel?: string
  profile?: string
  concurrency?: number
}

export interface StartEvalRunResult {
  ok: boolean
  runId?: string
  total?: number
  error?: string
}

function resolveCases(caseIds?: string[]): { cases: EvalCase[]; error?: string } {
  if (!caseIds?.length) return { cases: listEvalCases(SUITE) }
  const cases: EvalCase[] = []
  for (const id of caseIds) {
    const found = readEvalCase(id, SUITE)
    if (!found) return { cases: [], error: `找不到评测用例 ${id}` }
    cases.push(found)
  }
  return { cases }
}

async function executeEvalRun(
  summary: EvalRunSummary,
  cases: EvalCase[],
  opts: StartEvalRunOptions,
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
        saveEvalCaseResult(summary.run_id, result, SUITE)
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

      saveEvalCaseResult(summary.run_id, result, SUITE)
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
    logger.error({ err: (err as Error).message, runId: summary.run_id }, '[eval] run failed')
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

export function startEvalRun(opts: StartEvalRunOptions = {}): StartEvalRunResult {
  const { cases, error } = resolveCases(opts.caseIds)
  if (error) return { ok: false, error }
  if (!cases.length) return { ok: false, error: '评测集为空，请先从历史报告转存用例' }

  const invalid = cases.find(c => !c.rubric?.length)
  if (invalid) return { ok: false, error: `用例 ${invalid.id} 未配置评分标准` }

  const runId = genEvalRunId(SUITE)
  const summary: EvalRunSummary = {
    run_id: runId,
    suite: SUITE,
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
      logger.error({ err: (err as Error).message, runId }, '[eval] unhandled')
    })
  })

  return { ok: true, runId, total: cases.length }
}

export function abortEvalRun(runId: string): { ok: boolean; error?: string } {
  aborting.add(runId)
  return { ok: true }
}

/** 供 UI 手工微调 rubric 后落盘 */
export function updateEvalCase(evalCase: EvalCase): void {
  saveEvalCase({ ...evalCase, suite: SUITE, updated_at: new Date().toISOString() }, SUITE)
}
