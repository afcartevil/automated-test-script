import { describe, it, expect } from 'vitest'
import {
  computeAgreement,
  isJudgeTrustworthy,
  MIN_LABELED_SAMPLES,
} from '../../packages/server/src/services/tahp/eval/calibration'
import type { CaseVerdict, EvalCaseResult } from '../../packages/server/src/services/tahp/eval/types'

function result(
  caseId: string,
  judge: CaseVerdict | null,
  human?: CaseVerdict,
): EvalCaseResult {
  return {
    case_id: caseId,
    status: judge === 'pass' ? 'passed' : judge === 'warn' ? 'warned' : judge ? 'failed' : 'error',
    score: judge
      ? { total: judge === 'pass' ? 0.9 : 0.5, verdict: judge, must_failed: [], rubrics: [] }
      : undefined,
    human_label: human ? { verdict: human, labeled_at: '2026-08-07T00:00:00.000Z' } : undefined,
  }
}

describe('computeAgreement', () => {
  it('counts only cases that carry a human label', () => {
    const report = computeAgreement([
      result('a', 'pass', 'pass'),
      result('b', 'fail'),
      result('c', 'warn', 'warn'),
    ])
    expect(report.labeled).toBe(2)
    expect(report.agreed).toBe(2)
    expect(report.agreement_rate).toBe(1)
  })

  it('records disagreements with both verdicts', () => {
    const report = computeAgreement([
      result('a', 'pass', 'fail'),
      result('b', 'pass', 'pass'),
    ])
    expect(report.agreement_rate).toBe(0.5)
    expect(report.disagreements).toEqual([
      { case_id: 'a', judge: 'pass', human: 'fail', note: undefined },
    ])
  })

  it('skips cases where the judge produced no verdict', () => {
    // 判官没跑出结论时无从比对，不能算作不一致
    const report = computeAgreement([result('a', null, 'pass')])
    expect(report.labeled).toBe(0)
    expect(report.agreement_rate).toBe(0)
  })

  it('returns a zero rate rather than NaN when nothing is labeled', () => {
    const report = computeAgreement([result('a', 'pass')])
    expect(report.agreement_rate).toBe(0)
    expect(Number.isNaN(report.agreement_rate)).toBe(false)
  })

  it('carries the reviewer note into the disagreement list', () => {
    const withNote: EvalCaseResult = {
      ...result('a', 'pass', 'fail'),
      human_label: { verdict: 'fail', note: '根因写反了', labeled_at: '2026-08-07T00:00:00.000Z' },
    }
    expect(computeAgreement([withNote]).disagreements[0]?.note).toBe('根因写反了')
  })
})

describe('isJudgeTrustworthy', () => {
  it('refuses to conclude from too few samples even at perfect agreement', () => {
    const report = computeAgreement([result('a', 'pass', 'pass'), result('b', 'pass', 'pass')])
    expect(report.agreement_rate).toBe(1)
    expect(isJudgeTrustworthy(report)).toBe(false)
  })

  it('accepts a large enough sample that agrees', () => {
    const results = Array.from({ length: MIN_LABELED_SAMPLES }, (_, i) =>
      result(`c${i}`, 'pass', 'pass'),
    )
    expect(isJudgeTrustworthy(computeAgreement(results))).toBe(true)
  })

  it('rejects a large sample that disagrees too often', () => {
    const results = Array.from({ length: MIN_LABELED_SAMPLES }, (_, i) =>
      result(`c${i}`, 'pass', i < 5 ? 'pass' : 'fail'),
    )
    expect(isJudgeTrustworthy(computeAgreement(results))).toBe(false)
  })
})
