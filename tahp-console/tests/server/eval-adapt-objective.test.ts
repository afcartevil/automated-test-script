import { describe, it, expect } from 'vitest'
import {
  DEFAULT_ADAPT_AGENT_RUBRIC,
  DEFAULT_ADAPT_PIPELINE_RUBRIC,
  mergeObjectiveAndLlm,
  scoreAdaptCase,
  scoreObjectiveRubrics,
  signalsFromAdaptReport,
  signalsFromPipelineRun,
} from '../../packages/server/src/services/tahp/eval/adapt-objective'
import type { EvalCase, JudgeVerdict } from '../../packages/server/src/services/tahp/eval/types'

const agentCase: EvalCase = {
  id: 'adapt-demo',
  suite: 'adapt',
  source: { type: 'adapt_agent', domain_id: 'audio' },
  rubric: DEFAULT_ADAPT_AGENT_RUBRIC,
  created_at: '2026-08-07T00:00:00.000Z',
}

const pipelineCase: EvalCase = {
  id: 'pipe-demo',
  suite: 'adapt',
  source: { type: 'pipeline', domain_id: 'audio' },
  rubric: DEFAULT_ADAPT_PIPELINE_RUBRIC,
  created_at: '2026-08-07T00:00:00.000Z',
  mode: 'offline',
}

describe('signalsFromAdaptReport', () => {
  it('extracts completed status, file changes and skills', () => {
    const signals = signalsFromAdaptReport(
      {
        status: 'completed',
        files_modified: ['a.c', 'b.h'],
        skills_used: [{ skill_id: 'DRV_Audio_Adapt' }, 'other'],
      },
      ['DRV_Audio_Adapt'],
    )
    expect(signals.adapt_completed).toBe(true)
    expect(signals.files_modified_count).toBe(2)
    expect(signals.skills_used).toEqual(['DRV_Audio_Adapt', 'other'])
    expect(signals.build_pass).toBeNull()
  })

  it('marks incomplete reports as not completed', () => {
    const signals = signalsFromAdaptReport({ status: 'failed', fileChanges: [] })
    expect(signals.adapt_completed).toBe(false)
    expect(signals.files_modified_count).toBe(0)
  })
})

describe('signalsFromPipelineRun', () => {
  it('requires changed files for adapt_completed', () => {
    const signals = signalsFromPipelineRun({
      status: 'passed',
      domains: [
        { status: 'done', changed_files: ['x.c'], related_skills: ['s1'] },
      ],
      stages: {
        build: { status: 'done', progress: { state: 'success' }, summary: { pkg_path: '/out/a.zip' } },
        selfcheck: { status: 'done', progress: { state: 'success', passed: 3, failed: 0, total: 3 } },
      },
    })
    expect(signals.adapt_completed).toBe(true)
    expect(signals.build_pass).toBe(true)
    expect(signals.build_has_artifact).toBe(true)
    expect(signals.selfcheck_pass).toBe(true)
    expect(signals.pipeline_passed).toBe(true)
  })

  it('fails selfcheck when any case failed', () => {
    const signals = signalsFromPipelineRun({
      status: 'failed',
      domains: [{ status: 'done', changed_files: ['a.c'] }],
      stages: {
        build: { status: 'done', progress: { state: 'success' }, summary: { artifacts_dir: '/out' } },
        selfcheck: { status: 'failed', progress: { state: 'case_failed', passed: 2, failed: 1, total: 3 } },
      },
    })
    expect(signals.selfcheck_pass).toBe(false)
    expect(signals.pipeline_passed).toBe(false)
  })
})

describe('scoreAdaptCase', () => {
  it('passes an agent case with changes and skill hit', () => {
    const score = scoreAdaptCase(agentCase, {
      adapt_completed: true,
      files_modified_count: 2,
      skills_used: ['DRV_Audio_Adapt'],
      expected_skills: ['DRV_Audio_Adapt'],
      build_pass: null,
      selfcheck_pass: null,
      pipeline_passed: null,
    })
    expect(score.must_failed).toEqual([])
    expect(score.verdict).toBe('pass')
    expect(score.total).toBe(1)
  })

  it('fails must has_changes even when completed', () => {
    const score = scoreAdaptCase(agentCase, {
      adapt_completed: true,
      files_modified_count: 0,
      skills_used: [],
      expected_skills: [],
    })
    expect(score.must_failed).toContain('has_changes')
    expect(score.verdict).toBe('fail')
  })

  it('scores pipeline objective signals', () => {
    const score = scoreAdaptCase(pipelineCase, {
      adapt_completed: true,
      files_modified_count: 1,
      build_pass: true,
      build_has_artifact: true,
      selfcheck_pass: true,
      selfcheck_passed: 5,
      selfcheck_failed: 0,
      selfcheck_total: 5,
      pipeline_passed: true,
    })
    expect(score.verdict).toBe('pass')
    expect(score.must_failed).toEqual([])
  })

  it('fails pipeline when build has no artifact', () => {
    const score = scoreAdaptCase(pipelineCase, {
      adapt_completed: true,
      files_modified_count: 1,
      build_pass: true,
      build_has_artifact: false,
      selfcheck_pass: true,
      selfcheck_failed: 0,
      pipeline_passed: true,
    })
    expect(score.must_failed).toContain('build_pass')
    expect(score.verdict).toBe('fail')
  })
})

describe('mergeObjectiveAndLlm', () => {
  it('lets objective scores override same-id llm verdicts', () => {
    const llm: JudgeVerdict = {
      rubrics: [
        { id: 'adapt_completed', pass: false, score: 0, reason: 'llm wrong' },
        { id: 'soft_quality', pass: true, score: 1, reason: 'ok' },
      ],
    }
    const hybrid: EvalCase = {
      ...agentCase,
      rubric: [
        ...DEFAULT_ADAPT_AGENT_RUBRIC,
        { id: 'soft_quality', weight: 1, scoring: 'llm', criterion: '软质量' },
      ],
    }
    const score = mergeObjectiveAndLlm(
      hybrid.rubric,
      {
        adapt_completed: true,
        files_modified_count: 1,
        skills_used: ['a'],
        expected_skills: ['a'],
      },
      llm,
    )
    const adapt = score.rubrics.find(r => r.id === 'adapt_completed')
    expect(adapt?.pass).toBe(true)
    expect(adapt?.reason).not.toContain('llm wrong')
    expect(score.rubrics.find(r => r.id === 'soft_quality')?.pass).toBe(true)
  })
})

describe('scoreObjectiveRubrics', () => {
  it('skips llm-only rubric ids', () => {
    const verdict = scoreObjectiveRubrics(
      [
        { id: 'adapt_completed', weight: 1, scoring: 'objective', criterion: 'x' },
        { id: 'soft', weight: 1, scoring: 'llm', criterion: 'y' },
      ],
      { adapt_completed: true },
    )
    expect(verdict.rubrics.map(r => r.id)).toEqual(['adapt_completed'])
  })
})
