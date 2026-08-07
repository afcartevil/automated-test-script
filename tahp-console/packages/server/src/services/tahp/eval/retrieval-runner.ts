/**
 * 检索 / skill 路由评测批跑 —— 完全离线，同步 routeIntent + rankSkills。
 *
 * 不碰 Agent Bridge，并发可更高；默认 mode=offline。
 */
import { getTaskStream } from '../task-stream'
import { logger } from '../../logger'
import { computeSkillsHash } from './fingerprint'
import {
  RETRIEVAL_OBJECTIVE_VERSION,
  collectRetrievalSignals,
  scoreRetrievalCase,
} from './retrieval-objective'
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

const DEFAULT_CONCURRENCY = 8
const aborting = new Set<string>()

function emitEval(runId: string, type: string, payload: Record<string, unknown>): void {
  getTaskStream().publish({
    type,
    task_id: runId,
    payload: { run_id: runId, suite: 'retrieval', ...payload },
    ts: Date.now(),
  })
}

function resolveConcurrency(raw?: number): number {
  const fromEnv = Number(process.env.TAHP_EVAL_CONCURRENCY)
  const value = raw ?? (Number.isFinite(fromEnv) && fromEnv > 0 ? fromEnv : DEFAULT_CONCURRENCY)
  return Math.max(1, Math.min(16, Math.round(value)))
}

function buildVariant(): EvalVariant {
  return {
    skills_hash: computeSkillsHash(),
    prompt_version: RETRIEVAL_OBJECTIVE_VERSION,
  }
}

function toBrief(evalCase: EvalCase, result: EvalCaseResult): EvalCaseBrief {
  return {
    case_id: result.case_id,
    title: evalCase.title,
    status: result.status,
    total: result.score?.total,
    verdict: result.score?.verdict,
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

function runOneCase(evalCase: EvalCase): EvalCaseResult {
  const startedAt = Date.now()
  try {
    const signals = collectRetrievalSignals(evalCase)
    const score = scoreRetrievalCase(evalCase, signals)
    const status =
      score.verdict === 'pass' ? 'passed' : score.verdict === 'warn' ? 'warned' : 'failed'
    return {
      case_id: evalCase.id,
      status,
      score,
      objective_signals: signals,
      duration_ms: Date.now() - startedAt,
    }
  } catch (err) {
    return {
      case_id: evalCase.id,
      status: 'error',
      error: (err as Error).message,
      duration_ms: Date.now() - startedAt,
    }
  }
}

export interface StartRetrievalEvalRunOptions {
  caseIds?: string[]
  concurrency?: number
}

export interface StartRetrievalEvalRunResult {
  ok: boolean
  runId?: string
  total?: number
  error?: string
}

function resolveCases(caseIds?: string[]): { cases: EvalCase[]; error?: string } {
  if (!caseIds?.length) return { cases: listEvalCases('retrieval') }
  const cases: EvalCase[] = []
  for (const id of caseIds) {
    const found = readEvalCase(id, 'retrieval')
    if (!found) return { cases: [], error: `找不到检索评测案例 ${id}` }
    cases.push(found)
  }
  return { cases }
}

async function executeEvalRun(
  summary: EvalRunSummary,
  cases: EvalCase[],
  opts: StartRetrievalEvalRunOptions,
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
        saveEvalCaseResult(summary.run_id, result, 'retrieval')
        continue
      }

      emitEval(summary.run_id, 'eval.case_started', { case_id: evalCase.id })
      const result = runOneCase(evalCase)
      saveEvalCaseResult(summary.run_id, result, 'retrieval')
      summary.cases.push(toBrief(evalCase, result))
      recomputeSummary(summary)
      saveEvalRun(summary)

      emitEval(summary.run_id, 'eval.case_done', {
        case_id: evalCase.id,
        status: result.status,
        total: result.score?.total,
        verdict: result.score?.verdict,
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
    logger.error({ err: (err as Error).message, runId: summary.run_id }, '[eval-retrieval] run failed')
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

export function startRetrievalEvalRun(
  opts: StartRetrievalEvalRunOptions = {},
): StartRetrievalEvalRunResult {
  const { cases, error } = resolveCases(opts.caseIds)
  if (error) return { ok: false, error }
  if (!cases.length) {
    return {
      ok: false,
      error: '检索评测集为空，请先导入种子案例（candidates → 转为案例 / 一键导入）',
    }
  }

  const invalid = cases.find(c => !c.rubric?.length)
  if (invalid) return { ok: false, error: `案例 ${invalid.id} 未配置评分标准` }

  const runId = genEvalRunId('retrieval')
  const summary: EvalRunSummary = {
    run_id: runId,
    suite: 'retrieval',
    started_at: new Date().toISOString(),
    status: 'running',
    variant: buildVariant(),
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
      logger.error({ err: (err as Error).message, runId }, '[eval-retrieval] unhandled')
    })
  })

  return { ok: true, runId, total: cases.length }
}

export function abortRetrievalEvalRun(runId: string): { ok: boolean } {
  aborting.add(runId)
  return { ok: true }
}

export function updateRetrievalEvalCase(evalCase: EvalCase): void {
  saveEvalCase(
    { ...evalCase, suite: 'retrieval', mode: 'offline', updated_at: new Date().toISOString() },
    'retrieval',
  )
}
