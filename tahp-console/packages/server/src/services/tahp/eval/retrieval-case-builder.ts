/**
 * 检索评测用例 —— 内置种子案例 + 手工创建。
 *
 * 种子来自 intent-router 单测与 DOMAIN_ROUTERS，保证开箱可跑、完全离线。
 */
import {
  DEFAULT_RETRIEVAL_RUBRIC,
  INTENTS_WITHOUT_SKILL_RANKING,
} from './retrieval-objective'
import { listEvalCases, readEvalCase, saveEvalCase } from './store'
import type { EvalCase, Rubric } from './types'

export { DEFAULT_RETRIEVAL_RUBRIC }

export interface RetrievalSeedSpec {
  id: string
  title: string
  query: string
  expected_intent: string
  expected_top1_skill?: string | null
  expected_top_k_skills?: string[]
  retrieval_mode?: string
  preferred_skill_ids?: string[]
  expect_skill_ranking?: boolean
  labels?: string[]
}

/** 开箱种子：与 tests/server/intent-router.test.ts + DOMAIN_ROUTERS 对齐 */
export const RETRIEVAL_SEED_SPECS: RetrievalSeedSpec[] = [
  {
    id: 'retrieval-port-burn-history',
    title: '端口防烧现象 → historical_case',
    query: '插入充电器充电，小板NTC加热至70°C触发端口防烧，但通知栏不显示通知',
    expected_intent: 'historical_case',
    expect_skill_ranking: false,
    labels: ['intent', 'seed'],
  },
  {
    id: 'retrieval-vowifi-history',
    title: '历史 Bug 关键词 → historical_case',
    query: '有没有类似的 VozWiFi 历史 Bug',
    expected_intent: 'historical_case',
    expect_skill_ranking: false,
    labels: ['intent', 'seed'],
  },
  {
    id: 'retrieval-vowifi-concept',
    title: '是什么 → concept_reference',
    query: 'VozWiFi 是什么',
    expected_intent: 'concept_reference',
    expect_skill_ranking: false,
    labels: ['intent', 'seed'],
  },
  {
    id: 'retrieval-vowifi-sop',
    title: '怎么分析 → analysis_sop + 通信 foundation',
    query: '通信 VoWiFi 问题怎么分析',
    expected_intent: 'analysis_sop',
    expected_top1_skill: 'com-comm-analysis-foundation',
    expected_top_k_skills: ['com-comm-analysis-foundation'],
    expect_skill_ranking: true,
    labels: ['intent', 'skill-top1', 'seed'],
  },
  {
    id: 'retrieval-jira-direct',
    title: 'JIRA Key → direct_lookup',
    query: 'TOS163-37004 详情',
    expected_intent: 'direct_lookup',
    expect_skill_ranking: false,
    labels: ['intent', 'seed'],
  },
  {
    id: 'retrieval-mode-sop-override',
    title: 'UI mode=sop 强制覆盖',
    query: '任意问题',
    expected_intent: 'analysis_sop',
    retrieval_mode: 'sop',
    expect_skill_ranking: true,
    labels: ['mode', 'seed'],
  },
  {
    id: 'retrieval-slash-history',
    title: '斜杠 /历史',
    query: '/历史 VozWiFi',
    expected_intent: 'historical_case',
    expect_skill_ranking: false,
    labels: ['slash', 'seed'],
  },
  {
    id: 'retrieval-mtk-adapt-router',
    title: 'MTK 适配域路由',
    query: 'mtk 充电器件 adapt 怎么做',
    expected_intent: 'adaptation_guide',
    expected_top1_skill: 'mtk-adapt-template-router',
    expected_top_k_skills: ['mtk-adapt-template-router'],
    expect_skill_ranking: true,
    labels: ['skill-top1', 'seed'],
  },
  {
    id: 'retrieval-coding-standards',
    title: '编码规范 → policy + standards skill',
    query: '请按编码规范做 code review',
    expected_intent: 'policy_standards',
    expected_top1_skill: 'transsion-coding-standards-review',
    expected_top_k_skills: ['transsion-coding-standards-review'],
    expect_skill_ranking: true,
    labels: ['skill-top1', 'seed'],
  },
  {
    id: 'retrieval-preferred-boost',
    title: '关联 Skills 顶置',
    query: '通信问题怎么分析\n**关联 Skills**: com-comm-analysis-foundation',
    expected_intent: 'analysis_sop',
    expected_top1_skill: 'com-comm-analysis-foundation',
    expected_top_k_skills: ['com-comm-analysis-foundation'],
    preferred_skill_ids: ['com-comm-analysis-foundation'],
    expect_skill_ranking: true,
    labels: ['preferred', 'seed'],
  },
]

export interface RetrievalEvalCandidate {
  kind: 'seed'
  id: string
  title: string
  query: string
  expected_intent: string
  existing_case_id?: string
}

function sanitizeIdPart(raw: string): string {
  return raw.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
}

function uniqueCaseId(base: string): string {
  const taken = new Set(listEvalCases('retrieval').map(c => c.id))
  if (!taken.has(base)) return base
  for (let i = 2; i < 100; i++) {
    const next = `${base}-${i}`
    if (!taken.has(next)) return next
  }
  return `${base}-${Date.now()}`
}

function inferExpectSkillRanking(intent: string, explicit?: boolean): boolean {
  if (explicit === false) return false
  if (explicit === true) return true
  return !INTENTS_WITHOUT_SKILL_RANKING.has(intent)
}

export function listRetrievalEvalCandidates(): RetrievalEvalCandidate[] {
  const existing = new Map(
    listEvalCases('retrieval').map(c => [c.id, c.id]),
  )
  // 也按 seed id 匹配（转存时用同 id）
  for (const c of listEvalCases('retrieval')) {
    if (c.source.origin_task_id) existing.set(c.source.origin_task_id, c.id)
  }

  return RETRIEVAL_SEED_SPECS.map(seed => ({
    kind: 'seed' as const,
    id: seed.id,
    title: seed.title,
    query: seed.query,
    expected_intent: seed.expected_intent,
    existing_case_id: existing.get(seed.id),
  }))
}

export interface CreateRetrievalCaseOptions {
  caseId?: string
  rubric?: Rubric[]
  labels?: string[]
}

export function createRetrievalCaseFromSeed(
  seedId: string,
  opts: CreateRetrievalCaseOptions = {},
): { ok: boolean; evalCase?: EvalCase; error?: string } {
  const seed = RETRIEVAL_SEED_SPECS.find(s => s.id === seedId)
  if (!seed) return { ok: false, error: `找不到种子案例 ${seedId}` }
  return createRetrievalCase({
    ...seed,
    caseId: opts.caseId || seed.id,
    rubric: opts.rubric,
    labels: opts.labels || seed.labels,
  })
}

export function createRetrievalCase(input: {
  caseId?: string
  title?: string
  query: string
  expected_intent: string
  expected_top1_skill?: string | null
  expected_top_k_skills?: string[]
  retrieval_mode?: string
  preferred_skill_ids?: string[]
  expect_skill_ranking?: boolean
  rubric?: Rubric[]
  labels?: string[]
}): { ok: boolean; evalCase?: EvalCase; error?: string } {
  const query = input.query?.trim()
  if (!query) return { ok: false, error: 'query 不能为空' }
  if (!input.expected_intent?.trim()) return { ok: false, error: 'expected_intent 不能为空' }

  const requestedId = input.caseId?.trim()
  const baseId = sanitizeIdPart(requestedId || `retrieval-${input.expected_intent}`)
  if (!baseId) return { ok: false, error: '无法生成合法的案例 ID' }
  if (requestedId && readEvalCase(requestedId, 'retrieval')) {
    return { ok: false, error: `案例 ${requestedId} 已存在` }
  }
  const caseId = requestedId || uniqueCaseId(baseId)

  const expectSkills = inferExpectSkillRanking(
    input.expected_intent,
    input.expect_skill_ranking,
  )

  const evalCase: EvalCase = {
    id: caseId,
    suite: 'retrieval',
    title: input.title || query.slice(0, 40),
    source: {
      type: 'retrieval_query',
      query,
      problem_description: query,
      expected_intent: input.expected_intent,
      expected_top1_skill: expectSkills
        ? (input.expected_top1_skill ?? null)
        : null,
      expected_top_k_skills: expectSkills
        ? (input.expected_top_k_skills ||
          (input.expected_top1_skill ? [input.expected_top1_skill] : []))
        : [],
      related_skills: expectSkills
        ? (input.expected_top_k_skills ||
          (input.expected_top1_skill ? [input.expected_top1_skill] : []))
        : [],
      retrieval_mode: input.retrieval_mode || 'auto',
      preferred_skill_ids: input.preferred_skill_ids || [],
      expect_skill_ranking: expectSkills,
      origin_task_id: input.caseId?.startsWith('retrieval-') ? input.caseId : caseId,
    },
    rubric: input.rubric?.length
      ? input.rubric
      : DEFAULT_RETRIEVAL_RUBRIC.map(r => ({ ...r })),
    labels: input.labels,
    created_at: new Date().toISOString(),
    mode: 'offline',
  }

  saveEvalCase(evalCase, 'retrieval')
  return { ok: true, evalCase }
}

/** 一键导入全部尚未转存的种子案例 */
export function importMissingRetrievalSeeds(): {
  ok: boolean
  imported: string[]
  skipped: string[]
  errors: string[]
} {
  const imported: string[] = []
  const skipped: string[] = []
  const errors: string[] = []
  for (const seed of RETRIEVAL_SEED_SPECS) {
    if (readEvalCase(seed.id, 'retrieval')) {
      skipped.push(seed.id)
      continue
    }
    const result = createRetrievalCaseFromSeed(seed.id)
    if (result.ok) imported.push(seed.id)
    else errors.push(`${seed.id}: ${result.error}`)
  }
  return { ok: errors.length === 0, imported, skipped, errors }
}
