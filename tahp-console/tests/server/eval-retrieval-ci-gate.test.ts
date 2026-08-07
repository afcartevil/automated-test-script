import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import {
  RETRIEVAL_CI_SAFE_SEED_IDS,
  runRetrievalCiGate,
  seedSpecToEvalCase,
} from '../../packages/server/src/services/tahp/eval/retrieval-ci-gate'
import { RETRIEVAL_SEED_SPECS } from '../../packages/server/src/services/tahp/eval/retrieval-case-builder'
import { validateEvalBundle } from '../../packages/server/src/services/tahp/eval/bundle'
import {
  DEFAULT_RETRIEVAL_RUBRIC,
  EVAL_BUNDLE_FORMAT,
} from '../../packages/server/src/services/tahp/eval'

describe('retrieval CI gate', () => {
  it('passes all CI-safe seeds offline (no BFF / no skills disk)', () => {
    const result = runRetrievalCiGate()
    if (!result.ok) {
      // eslint-disable-next-line no-console
      console.error(JSON.stringify(result.failed, null, 2))
    }
    expect(result.ok).toBe(true)
    expect(result.passed).toBe(RETRIEVAL_CI_SAFE_SEED_IDS.length)
    expect(result.failed).toEqual([])
  })

  it('ships a desensitized baseline fixture for team sharing', () => {
    const fixturePath = resolve(
      __dirname,
      '../../fixtures/evals/retrieval-ci-baseline.json',
    )
    const raw = JSON.parse(readFileSync(fixturePath, 'utf-8'))
    const validated = validateEvalBundle(raw)
    expect(validated.ok).toBe(true)
    if (!validated.ok) return
    expect(validated.bundle.format).toBe(EVAL_BUNDLE_FORMAT)
    expect(validated.bundle.suite).toBe('retrieval')
    expect(validated.bundle.redacted).toBe(true)
    for (const id of RETRIEVAL_CI_SAFE_SEED_IDS) {
      expect(validated.bundle.cases.some(c => c.id === id)).toBe(true)
    }
  })

  it('seedSpecToEvalCase keeps expected intent', () => {
    const seed = RETRIEVAL_SEED_SPECS.find(s => s.id === 'retrieval-slash-history')
    expect(seed).toBeTruthy()
    const evalCase = seedSpecToEvalCase(seed!)
    expect(evalCase.source.expected_intent).toBe('historical_case')
    expect(evalCase.rubric).toHaveLength(DEFAULT_RETRIEVAL_RUBRIC.length)
  })
})
