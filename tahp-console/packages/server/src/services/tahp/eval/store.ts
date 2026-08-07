/**
 * 评估层存储 —— 按 suite 隔离评测集与结果。
 *
 * 评测集 {工程根}/.tahp-config/evals/{suite}/cases/{caseId}.json
 * 结果   {reportsDir}/evals/{suite}/{runId}/summary.json + cases/{caseId}.json
 *
 * bug-analysis 兼容：仍可读 legacy 扁平目录 {reportsDir}/evals/{runId}/。
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import { randomBytes } from 'crypto'
import { tahpPaths } from '../paths'
import type { EvalCase, EvalCaseResult, EvalRunSummary, EvalSuite, HumanLabel } from './types'
import { EVAL_SUITES, isEvalSuite } from './types'

const DEFAULT_SUITE: EvalSuite = 'bug-analysis'

function resolveSuite(suite?: EvalSuite): EvalSuite {
  return suite && isEvalSuite(suite) ? suite : DEFAULT_SUITE
}

function evalRoot(suite: EvalSuite = DEFAULT_SUITE): string {
  if (process.env.TAHP_EVAL_DIR) {
    // 显式覆盖时：若路径末尾已含 suite 名则不再拼接
    const base = process.env.TAHP_EVAL_DIR
    if (base.replace(/\\/g, '/').endsWith(`/${suite}`)) return base
    return join(base, suite)
  }
  return join(tahpPaths.projectRoot, '.tahp-config', 'evals', suite)
}

function casesDir(suite: EvalSuite = DEFAULT_SUITE): string {
  return join(evalRoot(suite), 'cases')
}

function resultsRoot(suite: EvalSuite = DEFAULT_SUITE): string {
  if (process.env.TAHP_EVAL_RESULTS_DIR) {
    const base = process.env.TAHP_EVAL_RESULTS_DIR
    if (base.replace(/\\/g, '/').endsWith(`/${suite}`)) return base
    return join(base, suite)
  }
  return join(tahpPaths.reportsDir, 'evals', suite)
}

/** legacy：早期 bug-analysis 结果写在 reports/evals/{runId}/ */
function legacyResultsRoot(): string {
  return join(tahpPaths.reportsDir, 'evals')
}

export function evalCasesDir(suite: EvalSuite = DEFAULT_SUITE): string {
  return casesDir(suite)
}

export function evalResultsDir(suite: EvalSuite = DEFAULT_SUITE): string {
  return resultsRoot(suite)
}

function runDir(runId: string, suite: EvalSuite = DEFAULT_SUITE): string {
  return join(resultsRoot(suite), runId)
}

function ensureDir(dir: string): void {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

function writeJsonAtomic(path: string, value: unknown): void {
  ensureDir(dirname(path))
  const tmp = `${path}.${randomBytes(4).toString('hex')}.tmp`
  writeFileSync(tmp, JSON.stringify(value, null, 2), 'utf-8')
  renameSync(tmp, path)
}

function readJson<T>(path: string): T | null {
  if (!existsSync(path)) return null
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T
  } catch {
    return null
  }
}

/** 用例 / run id 必须是文件名安全的 */
export function isSafeEvalId(id: string): boolean {
  return !!id && /^[A-Za-z0-9._-]{1,80}$/.test(id) && !id.includes('..')
}

export function genEvalRunId(suite: EvalSuite = DEFAULT_SUITE): string {
  const prefix =
    suite === 'adapt' ? 'eval-adapt' : suite === 'retrieval' ? 'eval-retrieval' : 'eval'
  return `${prefix}-${Date.now()}-${randomBytes(3).toString('hex')}`
}

// ─── 评测集 ──────────────────────────────────────────────────────────────────

export function readEvalCase(caseId: string, suite: EvalSuite = DEFAULT_SUITE): EvalCase | null {
  if (!isSafeEvalId(caseId)) return null
  const parsed = readJson<EvalCase>(join(casesDir(suite), `${caseId}.json`))
  if (!parsed) return null
  return { ...parsed, suite: parsed.suite || suite }
}

export function listEvalCases(suite: EvalSuite = DEFAULT_SUITE): EvalCase[] {
  const dir = casesDir(suite)
  if (!existsSync(dir)) return []
  const cases: EvalCase[] = []
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.json')) continue
    const parsed = readJson<EvalCase>(join(dir, file))
    if (parsed?.id) cases.push({ ...parsed, suite: parsed.suite || suite })
  }
  return cases.sort((a, b) => a.id.localeCompare(b.id))
}

export function saveEvalCase(evalCase: EvalCase, suite?: EvalSuite): void {
  const resolved = resolveSuite(suite || evalCase.suite)
  if (!isSafeEvalId(evalCase.id)) {
    throw new Error(`非法用例 ID: ${evalCase.id}`)
  }
  writeJsonAtomic(join(casesDir(resolved), `${evalCase.id}.json`), {
    ...evalCase,
    suite: resolved,
  })
}

export function deleteEvalCase(caseId: string, suite: EvalSuite = DEFAULT_SUITE): boolean {
  if (!isSafeEvalId(caseId)) return false
  const path = join(casesDir(suite), `${caseId}.json`)
  if (!existsSync(path)) return false
  rmSync(path)
  return true
}

// ─── 评测结果 ────────────────────────────────────────────────────────────────

export function saveEvalRun(summary: EvalRunSummary): void {
  const suite = resolveSuite(summary.suite)
  if (!isSafeEvalId(summary.run_id)) {
    throw new Error(`非法评测 run ID: ${summary.run_id}`)
  }
  writeJsonAtomic(join(runDir(summary.run_id, suite), 'summary.json'), {
    ...summary,
    suite,
  })
}

function readEvalRunAt(root: string, runId: string): EvalRunSummary | null {
  return readJson<EvalRunSummary>(join(root, runId, 'summary.json'))
}

export function readEvalRun(runId: string, suite?: EvalSuite): EvalRunSummary | null {
  if (!isSafeEvalId(runId)) return null

  if (suite) {
    const found = readEvalRunAt(resultsRoot(suite), runId)
    if (found) return { ...found, suite: found.suite || suite }
  } else {
    for (const s of EVAL_SUITES) {
      const found = readEvalRunAt(resultsRoot(s), runId)
      if (found) return { ...found, suite: found.suite || s }
    }
  }

  // legacy 扁平目录（仅 bug-analysis）
  if (!suite || suite === 'bug-analysis') {
    const legacy = readEvalRunAt(legacyResultsRoot(), runId)
    if (legacy && (!legacy.suite || legacy.suite === 'bug-analysis')) {
      // 避免把 suite 子目录本身当成 run
      if (EVAL_SUITES.includes(runId as EvalSuite)) return null
      return { ...legacy, suite: 'bug-analysis' }
    }
  }
  return null
}

export function listEvalRuns(limit = 50, suite: EvalSuite = DEFAULT_SUITE): EvalRunSummary[] {
  const runs: EvalRunSummary[] = []
  const root = resultsRoot(suite)
  if (existsSync(root)) {
    for (const entry of readdirSync(root)) {
      if (EVAL_SUITES.includes(entry as EvalSuite)) continue
      const summary = readJson<EvalRunSummary>(join(root, entry, 'summary.json'))
      if (summary?.run_id) runs.push({ ...summary, suite: summary.suite || suite })
    }
  }

  // bug-analysis：合并 legacy 扁平结果
  if (suite === 'bug-analysis') {
    const legacy = legacyResultsRoot()
    if (existsSync(legacy)) {
      const seen = new Set(runs.map(r => r.run_id))
      for (const entry of readdirSync(legacy)) {
        if (EVAL_SUITES.includes(entry as EvalSuite)) continue
        if (seen.has(entry)) continue
        const summary = readJson<EvalRunSummary>(join(legacy, entry, 'summary.json'))
        if (summary?.run_id && (!summary.suite || summary.suite === 'bug-analysis')) {
          runs.push({ ...summary, suite: 'bug-analysis' })
        }
      }
    }
  }

  return runs
    .sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)))
    .slice(0, limit)
}

export function saveEvalCaseResult(runId: string, result: EvalCaseResult, suite: EvalSuite = DEFAULT_SUITE): void {
  if (!isSafeEvalId(runId) || !isSafeEvalId(result.case_id)) return
  writeJsonAtomic(join(runDir(runId, suite), 'cases', `${result.case_id}.json`), result)
}

export function readEvalCaseResult(
  runId: string,
  caseId: string,
  suite?: EvalSuite,
): EvalCaseResult | null {
  if (!isSafeEvalId(runId) || !isSafeEvalId(caseId)) return null
  const summary = readEvalRun(runId, suite)
  const resolved = summary?.suite || suite || DEFAULT_SUITE

  const primary = readJson<EvalCaseResult>(join(runDir(runId, resolved), 'cases', `${caseId}.json`))
  if (primary) return primary

  if (resolved === 'bug-analysis') {
    return readJson<EvalCaseResult>(join(legacyResultsRoot(), runId, 'cases', `${caseId}.json`))
  }
  return null
}

export function listEvalCaseResults(runId: string, suite?: EvalSuite): EvalCaseResult[] {
  if (!isSafeEvalId(runId)) return []
  const summary = readEvalRun(runId, suite)
  const resolved = summary?.suite || suite || DEFAULT_SUITE

  let dir = join(runDir(runId, resolved), 'cases')
  if (!existsSync(dir) && resolved === 'bug-analysis') {
    dir = join(legacyResultsRoot(), runId, 'cases')
  }
  if (!existsSync(dir)) return []

  const results: EvalCaseResult[] = []
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.json')) continue
    const parsed = readJson<EvalCaseResult>(join(dir, file))
    if (parsed?.case_id) results.push(parsed)
  }
  return results.sort((a, b) => a.case_id.localeCompare(b.case_id))
}

export function setHumanLabel(
  runId: string,
  caseId: string,
  label: HumanLabel,
  suite?: EvalSuite,
): EvalCaseResult | null {
  const result = readEvalCaseResult(runId, caseId, suite)
  if (!result) return null
  const summary = readEvalRun(runId, suite)
  const resolved = summary?.suite || suite || DEFAULT_SUITE
  const updated: EvalCaseResult = { ...result, human_label: label }
  saveEvalCaseResult(runId, updated, resolved)
  return updated
}
