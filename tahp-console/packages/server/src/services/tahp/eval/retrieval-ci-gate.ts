/**
 * 检索评测 CI 门禁 —— 不依赖 BFF / Agent / 本机 skills 落盘。
 *
 * 只断言「intent / slash / mode」类种子；skill top1 依赖磁盘的用例留给本机全量评测。
 */
import {
  DEFAULT_RETRIEVAL_RUBRIC,
  collectRetrievalSignals,
  scoreRetrievalCase,
} from './retrieval-objective'
import { RETRIEVAL_SEED_SPECS, type RetrievalSeedSpec } from './retrieval-case-builder'
import type { EvalCase } from './types'

/** 不依赖 skills 目录即可稳定通过的种子 id */
export const RETRIEVAL_CI_SAFE_SEED_IDS = [
  'retrieval-port-burn-history',
  'retrieval-vowifi-history',
  'retrieval-vowifi-concept',
  'retrieval-jira-direct',
  'retrieval-mode-sop-override',
  'retrieval-slash-history',
] as const

export function isRetrievalCiSafeSeed(id: string): boolean {
  return (RETRIEVAL_CI_SAFE_SEED_IDS as readonly string[]).includes(id)
}

export function seedSpecToEvalCase(seed: RetrievalSeedSpec): EvalCase {
  return {
    id: seed.id,
    suite: 'retrieval',
    title: seed.title,
    source: {
      type: 'retrieval_query',
      query: seed.query,
      problem_description: seed.query,
      expected_intent: seed.expected_intent,
      expected_top1_skill: seed.expected_top1_skill ?? null,
      expected_top_k_skills: seed.expected_top_k_skills || [],
      retrieval_mode: seed.retrieval_mode || 'auto',
      preferred_skill_ids: seed.preferred_skill_ids || [],
      expect_skill_ranking: seed.expect_skill_ranking !== false,
    },
    rubric: DEFAULT_RETRIEVAL_RUBRIC.map(r => ({ ...r })),
    labels: seed.labels || ['ci'],
    created_at: '2026-08-07T00:00:00.000Z',
    mode: 'offline',
  }
}

export interface RetrievalCiGateResult {
  ok: boolean
  total: number
  passed: number
  failed: Array<{
    id: string
    verdict?: string
    must_failed?: string[]
    summary?: string
    actual_intent?: string
  }>
}

/** 对 CI-safe 种子跑客观打分；任一 fail 则 ok=false */
export function runRetrievalCiGate(
  seedIds: readonly string[] = RETRIEVAL_CI_SAFE_SEED_IDS,
): RetrievalCiGateResult {
  const failed: RetrievalCiGateResult['failed'] = []
  let passed = 0

  for (const id of seedIds) {
    const seed = RETRIEVAL_SEED_SPECS.find(s => s.id === id)
    if (!seed) {
      failed.push({ id, summary: '种子定义缺失' })
      continue
    }
    const evalCase = seedSpecToEvalCase(seed)
    // CI 安全集强制关闭 skill 排序依赖（mode 覆盖用例除外的 top1 N/A 已由 expected_top1 空处理）
    if (!seed.expected_top1_skill) {
      evalCase.source.expect_skill_ranking = false
    }
    const signals = collectRetrievalSignals(evalCase)
    const score = scoreRetrievalCase(evalCase, signals)
    if (score.verdict === 'pass') {
      passed += 1
    } else {
      failed.push({
        id,
        verdict: score.verdict,
        must_failed: score.must_failed,
        summary: score.summary,
        actual_intent: signals.actual_intent,
      })
    }
  }

  return {
    ok: failed.length === 0,
    total: seedIds.length,
    passed,
    failed,
  }
}
