/**
 * TAHP 评估层路由（bug-analysis / adapt / retrieval）
 *
 * 通过 ?suite= 分域；默认 bug-analysis 保持兼容。
 * 批跑进度走 Socket.IO /tahp-run（eval.* 事件）。
 */
import Router from '@koa/router'
import {
  EVAL_SUITES,
  abortAdaptEvalRun,
  abortEvalRun,
  abortRetrievalEvalRun,
  compareEvalRuns,
  computeAgreement,
  createAdaptCaseFromCandidate,
  createEvalCaseFromReport,
  createRetrievalCaseFromSeed,
  deleteEvalCase,
  importMissingRetrievalSeeds,
  isEvalSuite,
  isJudgeTrustworthy,
  listAdaptEvalCandidates,
  listEvalCaseCandidates,
  listEvalCaseResults,
  listEvalCases,
  listEvalRuns,
  listRetrievalEvalCandidates,
  readEvalCase,
  readEvalCaseResult,
  readEvalRun,
  setHumanLabel,
  startAdaptEvalRun,
  startEvalRun,
  startRetrievalEvalRun,
  updateAdaptEvalCase,
  updateEvalCase,
  updateRetrievalEvalCase,
  exportEvalBundle,
  importEvalBundle,
  DEFAULT_ADAPT_AGENT_RUBRIC,
  DEFAULT_ADAPT_PIPELINE_RUBRIC,
  DEFAULT_RETRIEVAL_RUBRIC,
  DEFAULT_RUBRIC,
  MIN_AGREEMENT_RATE,
  MIN_LABELED_SAMPLES,
} from '../../services/tahp/eval'
import type { CaseVerdict, EvalSuite, Rubric } from '../../services/tahp/eval'
import { logger } from '../../services/logger'

export const tahpEvalRoutes = new Router({ prefix: '/api/tahp/eval' })

const SUITE_HINT = `suite 必须是 ${EVAL_SUITES.join(' / ')}`

function parseLimit(raw: unknown, fallback: number): number {
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? Math.min(500, Math.round(value)) : fallback
}

function fail(ctx: any, status: number, error: string): void {
  ctx.status = status
  ctx.body = { success: false, error }
}

function parseSuite(raw: unknown, fallback: EvalSuite = 'bug-analysis'): EvalSuite | null {
  if (raw === undefined || raw === null || raw === '') return fallback
  if (isEvalSuite(raw)) return raw
  return null
}

function parseSuiteOptional(raw: unknown): EvalSuite | undefined | null {
  if (raw === undefined || raw === null || raw === '') return undefined
  if (isEvalSuite(raw)) return raw
  return null
}

function suiteFromCtx(ctx: any, fallback: EvalSuite = 'bug-analysis'): EvalSuite | null {
  return parseSuite(ctx.query.suite ?? ctx.request.body?.suite, fallback)
}

function parseRubric(raw: unknown): { rubric?: Rubric[]; error?: string } {
  if (raw === undefined) return {}
  if (!Array.isArray(raw)) return { error: 'rubric 必须是数组' }

  const rubric: Rubric[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    if (!item || typeof item !== 'object') return { error: 'rubric 项必须是对象' }
    const entry = item as Record<string, unknown>
    const id = String(entry.id ?? '').trim()
    const criterion = String(entry.criterion ?? '').trim()
    const weight = Number(entry.weight)
    if (!id) return { error: 'rubric 项缺少 id' }
    if (seen.has(id)) return { error: `rubric id 重复: ${id}` }
    if (!criterion) return { error: `rubric ${id} 缺少 criterion` }
    if (!Number.isFinite(weight) || weight < 0) return { error: `rubric ${id} 的 weight 非法` }
    seen.add(id)
    const scoring =
      entry.scoring === 'objective' || entry.scoring === 'llm' ? entry.scoring : undefined
    rubric.push({ id, weight, criterion, must: entry.must === true, scoring })
  }

  if (!rubric.length) return { error: 'rubric 不能为空' }
  return { rubric }
}

function defaultRubric(suite: EvalSuite) {
  if (suite === 'adapt') return DEFAULT_ADAPT_AGENT_RUBRIC
  if (suite === 'retrieval') return DEFAULT_RETRIEVAL_RUBRIC
  return DEFAULT_RUBRIC
}

function defaultRubrics(suite: EvalSuite) {
  if (suite === 'adapt') {
    return { agent: DEFAULT_ADAPT_AGENT_RUBRIC, pipeline: DEFAULT_ADAPT_PIPELINE_RUBRIC }
  }
  if (suite === 'retrieval') return { retrieval: DEFAULT_RETRIEVAL_RUBRIC }
  return { bug: DEFAULT_RUBRIC }
}

function updateCaseBySuite(suite: EvalSuite, next: Parameters<typeof updateEvalCase>[0]): void {
  if (suite === 'adapt') updateAdaptEvalCase(next)
  else if (suite === 'retrieval') updateRetrievalEvalCase(next)
  else updateEvalCase(next)
}

function startRunBySuite(
  suite: EvalSuite,
  opts: {
    caseIds?: string[]
    model?: string
    judgeModel?: string
    profile?: string
    concurrency?: number
  },
) {
  if (suite === 'adapt') return startAdaptEvalRun(opts)
  if (suite === 'retrieval') return startRetrievalEvalRun(opts)
  return startEvalRun(opts)
}

function abortRunBySuite(suite: EvalSuite, runId: string): void {
  if (suite === 'adapt') abortAdaptEvalRun(runId)
  else if (suite === 'retrieval') abortRetrievalEvalRun(runId)
  else abortEvalRun(runId)
}

// ─── 评测集 ──────────────────────────────────────────────────────────────────

tahpEvalRoutes.get('/cases', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  ctx.body = {
    success: true,
    data: {
      suite,
      cases: listEvalCases(suite),
      default_rubric: defaultRubric(suite),
      default_rubrics: defaultRubrics(suite),
    },
  }
})

tahpEvalRoutes.get('/cases/:caseId', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  const evalCase = readEvalCase(ctx.params.caseId, suite)
  if (!evalCase) return fail(ctx, 404, `找不到评测案例 ${ctx.params.caseId}`)
  ctx.body = { success: true, data: evalCase }
})

tahpEvalRoutes.put('/cases/:caseId', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  const existing = readEvalCase(ctx.params.caseId, suite)
  if (!existing) return fail(ctx, 404, `找不到评测案例 ${ctx.params.caseId}`)

  const body = (ctx.request.body || {}) as Record<string, unknown>
  const { rubric, error } = parseRubric(body.rubric)
  if (error) return fail(ctx, 400, error)

  updateCaseBySuite(suite, {
    ...existing,
    title: typeof body.title === 'string' ? body.title.trim() : existing.title,
    labels: Array.isArray(body.labels) ? body.labels.map(String) : existing.labels,
    rubric: rubric ?? existing.rubric,
    mode:
      body.mode === 'rerun' || body.mode === 'offline'
        ? body.mode
        : existing.mode,
  })

  ctx.body = { success: true, data: readEvalCase(ctx.params.caseId, suite) }
})

tahpEvalRoutes.delete('/cases/:caseId', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  if (!deleteEvalCase(ctx.params.caseId, suite)) {
    return fail(ctx, 404, `找不到评测案例 ${ctx.params.caseId}`)
  }
  ctx.body = { success: true, data: { deleted: true, case_id: ctx.params.caseId } }
})

tahpEvalRoutes.get('/candidates', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  const limit = parseLimit(ctx.query.limit, 100)
  const data =
    suite === 'adapt'
      ? listAdaptEvalCandidates(limit)
      : suite === 'retrieval'
        ? listRetrievalEvalCandidates()
        : listEvalCaseCandidates(limit)
  ctx.body = { success: true, data }
})

tahpEvalRoutes.post('/cases/from-report', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const suite = parseSuite(body.suite ?? ctx.query.suite, 'bug-analysis')
  if (!suite) return fail(ctx, 400, SUITE_HINT)

  const { rubric, error } = parseRubric(body.rubric)
  if (error) return fail(ctx, 400, error)

  if (suite === 'adapt') {
    const kind = body.kind === 'pipeline' ? 'pipeline' : 'adapt_agent'
    const id = String(body.task_id ?? body.id ?? body.run_id ?? '').trim()
    if (!id) return fail(ctx, 400, 'task_id / run_id 不能为空')
    const result = createAdaptCaseFromCandidate(kind, id, {
      caseId: typeof body.case_id === 'string' ? body.case_id.trim() : undefined,
      rubric,
      labels: Array.isArray(body.labels) ? body.labels.map(String) : undefined,
      mode: body.mode === 'rerun' || body.mode === 'offline' ? body.mode : undefined,
    })
    if (!result.ok) return fail(ctx, 400, result.error || '转存失败')
    ctx.body = { success: true, data: result.evalCase }
    return
  }

  if (suite === 'retrieval') {
    const seedId = String(body.id ?? body.seed_id ?? body.task_id ?? '').trim()
    if (!seedId) return fail(ctx, 400, 'seed id 不能为空')
    const result = createRetrievalCaseFromSeed(seedId, {
      caseId: typeof body.case_id === 'string' ? body.case_id.trim() : undefined,
      rubric,
      labels: Array.isArray(body.labels) ? body.labels.map(String) : undefined,
    })
    if (!result.ok) return fail(ctx, 400, result.error || '转存失败')
    ctx.body = { success: true, data: result.evalCase }
    return
  }

  const taskId = String(body.task_id ?? '').trim()
  if (!taskId) return fail(ctx, 400, 'task_id 不能为空')
  const result = createEvalCaseFromReport(taskId, {
    caseId: typeof body.case_id === 'string' ? body.case_id.trim() : undefined,
    rubric,
    labels: Array.isArray(body.labels) ? body.labels.map(String) : undefined,
  })
  if (!result.ok) return fail(ctx, 400, result.error || '转存失败')
  ctx.body = { success: true, data: result.evalCase }
})

/** 检索评测：一键导入全部缺失种子案例 */
tahpEvalRoutes.post('/retrieval/import-seeds', async (ctx) => {
  const result = importMissingRetrievalSeeds()
  ctx.body = { success: true, data: result }
})

/** 导出评测集（默认脱敏） */
tahpEvalRoutes.get('/bundle/export', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  const idsRaw = ctx.query.ids
  const caseIds = typeof idsRaw === 'string' && idsRaw.trim()
    ? idsRaw.split(',').map(s => s.trim()).filter(Boolean)
    : undefined
  const redact = ctx.query.redact !== '0' && ctx.query.redact !== 'false'
  const result = exportEvalBundle(suite, { caseIds, redact })
  if (!result.ok) return fail(ctx, 400, result.error || '导出失败')
  ctx.body = { success: true, data: result.bundle }
})

/** 导入评测集（脱敏包） */
tahpEvalRoutes.post('/bundle/import', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const suite = parseSuite(body.suite ?? ctx.query.suite)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  const bundle = body.bundle ?? body
  const result = importEvalBundle(bundle, {
    suite,
    overwrite: body.overwrite === true,
  })
  if (!result.ok) return fail(ctx, 400, result.error || '导入失败')
  ctx.body = { success: true, data: result }
})

// ─── 评测批跑 ────────────────────────────────────────────────────────────────

tahpEvalRoutes.get('/runs', async (ctx) => {
  const suite = suiteFromCtx(ctx)
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  ctx.body = { success: true, data: listEvalRuns(parseLimit(ctx.query.limit, 50), suite) }
})

tahpEvalRoutes.post('/runs', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const suite = parseSuite(body.suite ?? ctx.query.suite, 'bug-analysis')
  if (!suite) return fail(ctx, 400, SUITE_HINT)
  const concurrency = Number(body.concurrency)

  const result = startRunBySuite(suite, {
    caseIds: Array.isArray(body.case_ids) ? body.case_ids.map(String) : undefined,
    model: typeof body.model === 'string' ? body.model.trim() : undefined,
    judgeModel: typeof body.judge_model === 'string' ? body.judge_model.trim() : undefined,
    profile: typeof body.profile === 'string' ? body.profile.trim() : undefined,
    concurrency: Number.isFinite(concurrency) ? concurrency : undefined,
  })
  if (!result.ok) return fail(ctx, 400, result.error || '启动评测失败')

  logger.info({ runId: result.runId, total: result.total, suite }, '[eval] run started')
  ctx.body = { success: true, data: { run_id: result.runId, total: result.total, suite } }
})

tahpEvalRoutes.get('/runs/:runId', async (ctx) => {
  const suite = parseSuiteOptional(ctx.query.suite)
  if (suite === null) return fail(ctx, 400, SUITE_HINT)
  const summary = readEvalRun(ctx.params.runId, suite)
  if (!summary) return fail(ctx, 404, `找不到评测 ${ctx.params.runId}`)
  ctx.body = { success: true, data: summary }
})

tahpEvalRoutes.post('/runs/:runId/abort', async (ctx) => {
  const summary = readEvalRun(ctx.params.runId)
  if (!summary) return fail(ctx, 404, `找不到评测 ${ctx.params.runId}`)
  abortRunBySuite(summary.suite, ctx.params.runId)
  ctx.body = { success: true, data: { aborted: true, run_id: ctx.params.runId } }
})

tahpEvalRoutes.get('/runs/:runId/cases/:caseId', async (ctx) => {
  const summary = readEvalRun(ctx.params.runId)
  if (!summary) return fail(ctx, 404, `找不到评测 ${ctx.params.runId}`)
  const result = readEvalCaseResult(ctx.params.runId, ctx.params.caseId, summary.suite)
  if (!result) return fail(ctx, 404, '找不到该案例的评测明细')
  ctx.body = {
    success: true,
    data: { result, case: readEvalCase(ctx.params.caseId, summary.suite) },
  }
})

const HUMAN_VERDICTS = new Set(['pass', 'warn', 'fail'])

tahpEvalRoutes.put('/runs/:runId/cases/:caseId/label', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const verdict = String(body.verdict ?? '').trim()
  if (!HUMAN_VERDICTS.has(verdict)) {
    return fail(ctx, 400, 'verdict 必须是 pass / warn / fail')
  }

  const summary = readEvalRun(ctx.params.runId)
  if (!summary) return fail(ctx, 404, `找不到评测 ${ctx.params.runId}`)

  const updated = setHumanLabel(
    ctx.params.runId,
    ctx.params.caseId,
    {
      verdict: verdict as CaseVerdict,
      note: typeof body.note === 'string' ? body.note.trim() || undefined : undefined,
      labeled_at: new Date().toISOString(),
    },
    summary.suite,
  )
  if (!updated) return fail(ctx, 404, '找不到该案例的评测明细')

  ctx.body = { success: true, data: updated }
})

tahpEvalRoutes.get('/runs/:runId/calibration', async (ctx) => {
  const summary = readEvalRun(ctx.params.runId)
  if (!summary) return fail(ctx, 404, `找不到评测 ${ctx.params.runId}`)

  const report = computeAgreement(listEvalCaseResults(ctx.params.runId, summary.suite))
  ctx.body = {
    success: true,
    data: {
      ...report,
      trustworthy: isJudgeTrustworthy(report),
      min_agreement_rate: MIN_AGREEMENT_RATE,
      min_labeled_samples: MIN_LABELED_SAMPLES,
    },
  }
})

tahpEvalRoutes.get('/runs/:runId/compare', async (ctx) => {
  const baselineId = String(ctx.query.baseline ?? '').trim()
  if (!baselineId) return fail(ctx, 400, 'baseline 不能为空')

  const current = readEvalRun(ctx.params.runId)
  const baseline = readEvalRun(baselineId)
  if (!current || !baseline) return fail(ctx, 404, '找不到待对比的评测记录')

  ctx.body = { success: true, data: compareEvalRuns(baseline, current) }
})
