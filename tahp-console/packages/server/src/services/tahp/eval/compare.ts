/**
 * 变体对比 —— 回归门禁的判定依据。
 */
import type { EvalComparison, EvalRunSummary, EvalVariant } from './types'

function sameVariant(a: EvalVariant, b: EvalVariant): boolean {
  return (
    a.skills_hash === b.skills_hash &&
    a.prompt_version === b.prompt_version &&
    (a.model ?? '') === (b.model ?? '') &&
    (a.judge_model ?? '') === (b.judge_model ?? '')
  )
}

/**
 * 只有 baseline 判 passed、当前不再 passed 才算回归；error 用例不计入改善。
 * variant_matched=false 时分数差异不能单一归因，调用方需要提示。
 */
export function compareEvalRuns(
  baseline: EvalRunSummary,
  current: EvalRunSummary,
): EvalComparison {
  const baselineStatus = new Map(baseline.cases.map(c => [c.case_id, c.status]))
  const regressed: string[] = []
  const improved: string[] = []

  for (const item of current.cases) {
    const before = baselineStatus.get(item.case_id)
    if (!before) continue
    if (before === 'passed' && item.status !== 'passed') regressed.push(item.case_id)
    if (before !== 'passed' && before !== 'error' && item.status === 'passed') improved.push(item.case_id)
  }

  return {
    baseline_run_id: baseline.run_id,
    current_run_id: current.run_id,
    pass_rate_delta: current.pass_rate - baseline.pass_rate,
    avg_score_delta: current.avg_score - baseline.avg_score,
    regressed,
    improved,
    variant_matched: sameVariant(baseline.variant, current.variant),
  }
}
