import { describe, it, expect } from 'vitest'
import {
  aggregateScore,
  buildJudgePrompt,
  parseJudgeVerdict,
  PASS_THRESHOLD,
  WARN_THRESHOLD,
} from '../../packages/server/src/services/tahp/eval/judge'
import type { EvalCase, JudgeVerdict, Rubric } from '../../packages/server/src/services/tahp/eval/types'

const rubric: Rubric[] = [
  { id: 'root_cause', weight: 3, must: true, criterion: '指出根因为 modem 侧 NAS 重附着失败' },
  { id: 'evidence', weight: 2, must: true, criterion: '引用 log 具体时间戳，未编造寄存器' },
  { id: 'actionable', weight: 1, criterion: '给出可执行的下一步验证动作' },
]

const evalCase: EvalCase = {
  id: 'eval-tel-001',
  title: 'VoLTE 掉话',
  source: { type: 'jira', jira_key: 'TEL-123' },
  rubric,
  created_at: '2026-08-07T00:00:00.000Z',
}

function verdictOf(entries: Array<[string, boolean, number]>): JudgeVerdict {
  return {
    rubrics: entries.map(([id, pass, score]) => ({ id, pass, score, reason: 'r' })),
  }
}

describe('parseJudgeVerdict', () => {
  it('parses plain JSON', () => {
    const parsed = parseJudgeVerdict(
      '{"rubrics":[{"id":"root_cause","pass":true,"score":0.9,"reason":"命中"}],"summary":"还行"}',
    )
    expect(parsed?.rubrics).toHaveLength(1)
    expect(parsed?.rubrics[0]).toMatchObject({ id: 'root_cause', pass: true, score: 0.9 })
    expect(parsed?.summary).toBe('还行')
  })

  it('parses fenced JSON', () => {
    const parsed = parseJudgeVerdict(`\`\`\`json
{"rubrics":[{"id":"evidence","pass":false,"score":0,"reason":"无引用"}]}
\`\`\``)
    expect(parsed?.rubrics[0]?.id).toBe('evidence')
    expect(parsed?.rubrics[0]?.pass).toBe(false)
  })

  it('returns null for non-JSON or wrong shape', () => {
    expect(parseJudgeVerdict('not json at all')).toBeNull()
    expect(parseJudgeVerdict('{"items":[]}')).toBeNull()
    expect(parseJudgeVerdict('')).toBeNull()
  })

  it('normalizes a 0-10 score into 0-1', () => {
    const parsed = parseJudgeVerdict('{"rubrics":[{"id":"a","pass":true,"score":8}]}')
    expect(parsed?.rubrics[0]?.score).toBeCloseTo(0.8)
  })

  it('clamps out-of-range scores', () => {
    const parsed = parseJudgeVerdict('{"rubrics":[{"id":"a","pass":true,"score":-3},{"id":"b","pass":true,"score":42}]}')
    expect(parsed?.rubrics[0]?.score).toBe(0)
    expect(parsed?.rubrics[1]?.score).toBe(1)
  })

  it('defaults a missing score from the pass flag', () => {
    const parsed = parseJudgeVerdict('{"rubrics":[{"id":"a","pass":true},{"id":"b","pass":false}]}')
    expect(parsed?.rubrics[0]?.score).toBe(1)
    expect(parsed?.rubrics[1]?.score).toBe(0)
  })

  it('drops entries without an id', () => {
    const parsed = parseJudgeVerdict('{"rubrics":[{"pass":true,"score":1},{"id":"ok","pass":true,"score":1}]}')
    expect(parsed?.rubrics).toHaveLength(1)
    expect(parsed?.rubrics[0]?.id).toBe('ok')
  })

  it('treats a non-boolean pass as not passing', () => {
    const parsed = parseJudgeVerdict('{"rubrics":[{"id":"a","pass":"yes","score":1}]}')
    expect(parsed?.rubrics[0]?.pass).toBe(false)
  })
})

describe('aggregateScore', () => {
  it('weights rubric scores by their weight', () => {
    const score = aggregateScore(
      verdictOf([['root_cause', true, 1], ['evidence', true, 1], ['actionable', true, 0]]),
      rubric,
    )
    // (3*1 + 2*1 + 1*0) / 6
    expect(score.total).toBeCloseTo(5 / 6)
    expect(score.verdict).toBe('pass')
    expect(score.must_failed).toEqual([])
  })

  it('short-circuits to fail when a must rubric fails, regardless of total', () => {
    const score = aggregateScore(
      verdictOf([['root_cause', false, 0.95], ['evidence', true, 1], ['actionable', true, 1]]),
      rubric,
    )
    expect(score.must_failed).toEqual(['root_cause'])
    expect(score.verdict).toBe('fail')
    expect(score.total).toBeGreaterThan(PASS_THRESHOLD)
  })

  it('counts a rubric the judge skipped as not passing', () => {
    const score = aggregateScore(verdictOf([['root_cause', true, 1], ['evidence', true, 1]]), rubric)
    const actionable = score.rubrics.find(r => r.id === 'actionable')
    expect(actionable).toMatchObject({ pass: false, score: 0 })
    expect(actionable?.reason).toContain('未对该项给出结论')
    expect(score.rubrics).toHaveLength(3)
  })

  it('ignores verdict entries not present in the rubric', () => {
    const score = aggregateScore(
      verdictOf([
        ['root_cause', true, 1],
        ['evidence', true, 1],
        ['actionable', true, 1],
        ['hallucinated', true, 1],
      ]),
      rubric,
    )
    expect(score.rubrics.map(r => r.id)).toEqual(['root_cause', 'evidence', 'actionable'])
    expect(score.total).toBe(1)
  })

  it('maps totals onto pass / warn / fail bands', () => {
    const soft: Rubric[] = [{ id: 'a', weight: 1, criterion: 'x' }]
    expect(aggregateScore(verdictOf([['a', true, PASS_THRESHOLD]]), soft).verdict).toBe('pass')
    expect(aggregateScore(verdictOf([['a', true, WARN_THRESHOLD]]), soft).verdict).toBe('warn')
    expect(aggregateScore(verdictOf([['a', false, 0.1]]), soft).verdict).toBe('fail')
  })

  it('fails an empty rubric instead of silently scoring 0 as pass', () => {
    const score = aggregateScore(verdictOf([]), [])
    expect(score.verdict).toBe('fail')
    expect(score.total).toBe(0)
  })

  it('tolerates zero-weight rubrics without dividing by zero', () => {
    const score = aggregateScore(verdictOf([['a', true, 1]]), [{ id: 'a', weight: 0, criterion: 'x' }])
    expect(Number.isFinite(score.total)).toBe(true)
    expect(score.total).toBe(0)
  })

  it('carries the judge summary through', () => {
    const score = aggregateScore(
      { rubrics: [{ id: 'a', pass: true, score: 1, reason: 'r' }], summary: '结论可靠' },
      [{ id: 'a', weight: 1, criterion: 'x' }],
    )
    expect(score.summary).toBe('结论可靠')
  })
})

describe('buildJudgePrompt', () => {
  it('lists every rubric id and marks must items', () => {
    const { instructions, userMessage } = buildJudgePrompt(evalCase, '# 根因\nNAS 重附着失败')
    for (const item of rubric) {
      expect(userMessage).toContain(`id=${item.id}`)
    }
    expect(userMessage).toContain('必过项')
    expect(userMessage).toContain('NAS 重附着失败')
    expect(instructions).toContain('禁止调用任何工具')
  })

  it('does not leak the expected answer into the instructions block', () => {
    const { instructions } = buildJudgePrompt(evalCase, 'body')
    expect(instructions).not.toContain('NAS 重附着失败')
  })
})
