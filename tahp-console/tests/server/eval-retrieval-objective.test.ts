import { describe, it, expect } from 'vitest'
import {
  DEFAULT_RETRIEVAL_RUBRIC,
  collectRetrievalSignals,
  scoreRetrievalCase,
  scoreRetrievalRubrics,
} from '../../packages/server/src/services/tahp/eval/retrieval-objective'
import type { EvalCase, RetrievalObjectiveSignals } from '../../packages/server/src/services/tahp/eval/types'

function makeCase(partial: Partial<EvalCase['source']> & { id?: string }): EvalCase {
  return {
    id: partial.id || 'retrieval-demo',
    suite: 'retrieval',
    source: {
      type: 'retrieval_query',
      query: '通信 VoWiFi 问题怎么分析',
      expected_intent: 'analysis_sop',
      expect_skill_ranking: false,
      ...partial,
    },
    rubric: DEFAULT_RETRIEVAL_RUBRIC,
    created_at: '2026-08-07T00:00:00.000Z',
    mode: 'offline',
  }
}

describe('collectRetrievalSignals', () => {
  it('routes historical keywords to historical_case without skill ranking', () => {
    const signals = collectRetrievalSignals(
      makeCase({
        query: '有没有类似的 VozWiFi 历史 Bug',
        expected_intent: 'historical_case',
        expect_skill_ranking: false,
      }),
    )
    expect(signals.actual_intent).toBe('historical_case')
    expect(signals.intent_matched).toBe(true)
    expect(signals.top1_matched).toBeNull()
    expect(signals.topk_hit_ratio).toBeNull()
  })

  it('honors retrieval_mode override with explicit_override', () => {
    const signals = collectRetrievalSignals(
      makeCase({
        query: '任意问题',
        expected_intent: 'analysis_sop',
        retrieval_mode: 'sop',
        expect_skill_ranking: true,
        expected_top1_skill: null,
      }),
    )
    expect(signals.actual_intent).toBe('analysis_sop')
    expect(signals.explicit_override).toBe(true)
    expect(signals.mode_override_ok).toBe(true)
  })

  it('strips slash intent prefix before routing', () => {
    const signals = collectRetrievalSignals(
      makeCase({
        query: '/历史 VozWiFi',
        expected_intent: 'historical_case',
        expect_skill_ranking: false,
      }),
    )
    expect(signals.actual_intent).toBe('historical_case')
    expect(signals.query).toBe('VozWiFi')
  })
})

describe('scoreRetrievalRubrics', () => {
  it('passes when all objective signals align', () => {
    const signals: RetrievalObjectiveSignals = {
      query: 'demo',
      actual_intent: 'analysis_sop',
      expected_intent: 'analysis_sop',
      intent_matched: true,
      explicit_override: false,
      top1_skill: 'com-comm-analysis-foundation',
      expected_top1_skill: 'com-comm-analysis-foundation',
      top1_matched: true,
      topk_skills: ['com-comm-analysis-foundation', 'other'],
      expected_topk: ['com-comm-analysis-foundation'],
      topk_hit_ratio: 1,
      preferred_ids: [],
      preferred_boosted: null,
      mode_override_ok: null,
    }
    const verdict = scoreRetrievalRubrics(DEFAULT_RETRIEVAL_RUBRIC, signals)
    expect(verdict.rubrics.every(r => r.pass)).toBe(true)
    const score = scoreRetrievalCase(makeCase({ expect_skill_ranking: true }), signals)
    expect(score.verdict).toBe('pass')
    expect(score.must_failed).toEqual([])
    expect(score.total).toBe(1)
  })

  it('fails must intent_match and short-circuits', () => {
    const signals: RetrievalObjectiveSignals = {
      query: 'demo',
      actual_intent: 'direct_lookup',
      expected_intent: 'historical_case',
      intent_matched: false,
      explicit_override: false,
      top1_skill: null,
      expected_top1_skill: null,
      top1_matched: null,
      topk_skills: [],
      expected_topk: [],
      topk_hit_ratio: null,
      preferred_ids: [],
      preferred_boosted: null,
      mode_override_ok: null,
    }
    const score = scoreRetrievalCase(
      makeCase({
        expected_intent: 'historical_case',
        expect_skill_ranking: false,
      }),
      signals,
    )
    expect(score.must_failed).toContain('intent_match')
    expect(score.verdict).toBe('fail')
  })

  it('scores partial topk coverage below pass', () => {
    const signals: RetrievalObjectiveSignals = {
      query: 'demo',
      actual_intent: 'analysis_sop',
      expected_intent: 'analysis_sop',
      intent_matched: true,
      explicit_override: false,
      top1_skill: 'skill-a',
      expected_top1_skill: 'skill-a',
      top1_matched: true,
      topk_skills: ['skill-a'],
      expected_topk: ['skill-a', 'skill-b'],
      topk_hit_ratio: 0.5,
      preferred_ids: ['skill-b'],
      preferred_boosted: false,
      mode_override_ok: null,
    }
    const score = scoreRetrievalCase(
      makeCase({
        expected_intent: 'analysis_sop',
        expected_top1_skill: 'skill-a',
        expect_skill_ranking: true,
      }),
      signals,
    )
    const topk = score.rubrics.find(r => r.id === 'topk_skill_hit')
    expect(topk?.score).toBe(0.5)
    expect(topk?.pass).toBe(false)
    const preferred = score.rubrics.find(r => r.id === 'preferred_skill_boost')
    expect(preferred?.pass).toBe(false)
    expect(score.total).toBeLessThan(1)
  })
})
