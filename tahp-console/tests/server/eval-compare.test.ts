import { describe, it, expect } from 'vitest'
import { compareEvalRuns } from '../../packages/server/src/services/tahp/eval/compare'
import type { EvalCaseBrief, EvalRunSummary, EvalVariant } from '../../packages/server/src/services/tahp/eval/types'

const variant: EvalVariant = {
  model: 'claude-x',
  judge_model: 'gpt-y',
  skills_hash: 'abc123',
  prompt_version: 'v1',
}

function makeRun(
  runId: string,
  cases: EvalCaseBrief[],
  overrides: Partial<EvalRunSummary> = {},
): EvalRunSummary {
  const passed = cases.filter(c => c.status === 'passed').length
  const scored = cases.filter(c => typeof c.total === 'number')
  return {
    run_id: runId,
    suite: 'bug-analysis',
    started_at: '2026-08-07T00:00:00.000Z',
    status: 'completed',
    variant,
    total: cases.length,
    passed,
    warned: cases.filter(c => c.status === 'warned').length,
    failed: cases.filter(c => c.status === 'failed').length,
    errored: cases.filter(c => c.status === 'error').length,
    avg_score: scored.length
      ? scored.reduce((sum, c) => sum + (c.total as number), 0) / scored.length
      : 0,
    pass_rate: cases.length ? passed / cases.length : 0,
    cases,
    ...overrides,
  }
}

describe('compareEvalRuns', () => {
  it('flags cases that stopped passing as regressed', () => {
    const baseline = makeRun('base', [
      { case_id: 'a', status: 'passed', total: 0.9 },
      { case_id: 'b', status: 'passed', total: 0.85 },
    ])
    const current = makeRun('cur', [
      { case_id: 'a', status: 'passed', total: 0.9 },
      { case_id: 'b', status: 'failed', total: 0.3 },
    ])

    const result = compareEvalRuns(baseline, current)
    expect(result.regressed).toEqual(['b'])
    expect(result.improved).toEqual([])
    expect(result.pass_rate_delta).toBeCloseTo(-0.5)
    expect(result.avg_score_delta).toBeLessThan(0)
  })

  it('flags newly passing cases as improved', () => {
    const baseline = makeRun('base', [{ case_id: 'a', status: 'warned', total: 0.7 }])
    const current = makeRun('cur', [{ case_id: 'a', status: 'passed', total: 0.95 }])

    const result = compareEvalRuns(baseline, current)
    expect(result.improved).toEqual(['a'])
    expect(result.regressed).toEqual([])
  })

  it('does not credit an improvement when the baseline case errored', () => {
    // baseline 没跑出结果，不能说明当前变体更好
    const baseline = makeRun('base', [{ case_id: 'a', status: 'error', error: 'timeout' }])
    const current = makeRun('cur', [{ case_id: 'a', status: 'passed', total: 0.9 }])

    expect(compareEvalRuns(baseline, current).improved).toEqual([])
  })

  it('ignores cases absent from the baseline', () => {
    const baseline = makeRun('base', [{ case_id: 'a', status: 'passed', total: 0.9 }])
    const current = makeRun('cur', [
      { case_id: 'a', status: 'passed', total: 0.9 },
      { case_id: 'new', status: 'failed', total: 0.1 },
    ])

    const result = compareEvalRuns(baseline, current)
    expect(result.regressed).toEqual([])
    expect(result.improved).toEqual([])
  })

  it('reports a variant mismatch when skills changed', () => {
    const baseline = makeRun('base', [{ case_id: 'a', status: 'passed', total: 0.9 }])
    const current = makeRun('cur', [{ case_id: 'a', status: 'passed', total: 0.9 }], {
      variant: { ...variant, skills_hash: 'changed' },
    })

    expect(compareEvalRuns(baseline, current).variant_matched).toBe(false)
  })

  it('treats an identical variant as matched', () => {
    const baseline = makeRun('base', [{ case_id: 'a', status: 'passed', total: 0.9 }])
    const current = makeRun('cur', [{ case_id: 'a', status: 'passed', total: 0.9 }])

    const result = compareEvalRuns(baseline, current)
    expect(result.variant_matched).toBe(true)
    expect(result.pass_rate_delta).toBe(0)
    expect(result.avg_score_delta).toBe(0)
  })
})
