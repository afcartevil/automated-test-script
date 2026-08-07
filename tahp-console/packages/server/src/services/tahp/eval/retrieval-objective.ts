/**
 * 检索 / skill 路由客观判分 —— 完全离线，不调 Agent / LLM。
 *
 * 核心断言：routeIntent + rankSkills
 *   intent 选对了没、top1/topk skill 命中、preferred 是否顶置、mode 覆盖是否生效。
 */
import { parseSlashIntent, routeIntent } from '../chat-retrieval/intent-router'
import { retrievalModeToIntent, type RetrievalMode } from '../chat-retrieval/intents'
import { rankSkills } from '../chat-retrieval/skill-ranker'
import { extractPreferredSkillIds } from '../context-injector'
import { aggregateScore } from './judge'
import type {
  CaseScore,
  EvalCase,
  JudgeVerdict,
  RetrievalObjectiveSignals,
  Rubric,
  RubricVerdict,
} from './types'

export const RETRIEVAL_OBJECTIVE_VERSION = 'retrieval-obj-v1'

/** 这些意图的策略不产出 skill_hits，top1/topk 记 N/A */
export const INTENTS_WITHOUT_SKILL_RANKING = new Set([
  'historical_case',
  'concept_reference',
  'direct_lookup',
  'version_scope',
  'integration_config',
])

export const DEFAULT_RETRIEVAL_RUBRIC: Rubric[] = [
  {
    id: 'intent_match',
    weight: 3,
    must: true,
    scoring: 'objective',
    criterion: 'routeIntent（含 slash 剥离）得到的 intent 与期望一致',
  },
  {
    id: 'top1_skill',
    weight: 3,
    must: true,
    scoring: 'objective',
    criterion: 'rankSkills 的 top-1 skill_id 与期望一致（不适用时记 N/A）',
  },
  {
    id: 'topk_skill_hit',
    weight: 2,
    scoring: 'objective',
    criterion: '期望 skill 集合被 top-k 覆盖的比例',
  },
  {
    id: 'preferred_skill_boost',
    weight: 1,
    scoring: 'objective',
    criterion: '声明的 preferred_skill_ids 出现在 top-k（relevance 顶置）',
  },
  {
    id: 'mode_override',
    weight: 1,
    scoring: 'objective',
    criterion: 'retrieval_mode ≠ auto 时，intent 被强制为对应映射且 explicit_override=true',
  },
]

function verdict(
  id: string,
  pass: boolean,
  score: number,
  reason: string,
  evidence?: string,
): RubricVerdict {
  return { id, pass, score, reason, evidence }
}

function normalizeMode(raw?: string): RetrievalMode | undefined {
  if (!raw || raw === 'auto') return undefined
  if (raw === 'historical' || raw === 'concept' || raw === 'sop' || raw === 'adapt') return raw
  return undefined
}

export function resolveRetrievalQuery(evalCase: EvalCase): string {
  return (
    evalCase.source.query?.trim() ||
    evalCase.source.problem_description?.trim() ||
    evalCase.title?.trim() ||
    ''
  )
}

/**
 * 对单条查询跑路由 + skill 排序，产出客观信号。
 */
export function collectRetrievalSignals(evalCase: EvalCase): RetrievalObjectiveSignals {
  const query = resolveRetrievalQuery(evalCase)
  const mode = normalizeMode(evalCase.source.retrieval_mode)
  const preferredFromText = extractPreferredSkillIds(query)
  const preferred = Array.from(
    new Set([...(evalCase.source.preferred_skill_ids || []), ...preferredFromText]),
  )

  const slash = parseSlashIntent(query)
  const effectiveQuery = (slash.rest || query).trim() || query
  const routed = routeIntent(effectiveQuery, {
    retrieval_mode: mode || (evalCase.source.retrieval_mode as RetrievalMode | undefined),
    slash_intent: slash.intent,
  })

  const expectSkills =
    evalCase.source.expect_skill_ranking !== false &&
    !INTENTS_WITHOUT_SKILL_RANKING.has(
      evalCase.source.expected_intent || routed.intent,
    )

  const topK = Math.max(
    1,
    Number(evalCase.source.form_data?.top_k) ||
      Math.max(3, evalCase.source.expected_top_k_skills?.length || 0),
  )

  const ranked = expectSkills
    ? rankSkills(effectiveQuery, {
        limit: topK,
        preferred_skill_ids: preferred,
      })
    : []

  const topk_skills = ranked.map(h => h.skill_id)
  const expected_top1 = evalCase.source.expected_top1_skill ?? null
  const expected_topk =
    evalCase.source.expected_top_k_skills?.length
      ? evalCase.source.expected_top_k_skills
      : expected_top1
        ? [expected_top1]
        : evalCase.source.related_skills || []

  const expected_intent = evalCase.source.expected_intent || ''
  const intent_matched = expected_intent
    ? routed.intent === expected_intent
    : true

  let top1_matched: boolean | null = null
  if (!expectSkills || !expected_top1) top1_matched = null
  else top1_matched = topk_skills[0] === expected_top1

  let topk_hit_ratio: number | null = null
  if (!expectSkills || !expected_topk.length) topk_hit_ratio = null
  else {
    const set = new Set(topk_skills.map(s => s.toLowerCase()))
    const hits = expected_topk.filter(s => set.has(s.toLowerCase()))
    topk_hit_ratio = hits.length / expected_topk.length
  }

  let preferred_boosted: boolean | null = null
  if (!preferred.length || !expectSkills) preferred_boosted = null
  else {
    const set = new Set(topk_skills.map(s => s.toLowerCase()))
    preferred_boosted = preferred.every(id => set.has(id.toLowerCase()))
  }

  let mode_override_ok: boolean | null = null
  if (!mode) mode_override_ok = null
  else {
    const mapped = retrievalModeToIntent(mode)
    mode_override_ok = routed.intent === mapped && routed.explicit_override === true
  }

  return {
    query: effectiveQuery,
    actual_intent: routed.intent,
    expected_intent: expected_intent || undefined,
    intent_matched,
    explicit_override: !!routed.explicit_override,
    top1_skill: expectSkills ? topk_skills[0] || null : null,
    expected_top1_skill: expectSkills ? expected_top1 : null,
    top1_matched,
    topk_skills,
    expected_topk: expectSkills ? expected_topk : [],
    topk_hit_ratio,
    preferred_ids: preferred,
    preferred_boosted,
    mode_override_ok,
  }
}

function scoreIntentMatch(signals: RetrievalObjectiveSignals): RubricVerdict {
  if (!signals.expected_intent) {
    return verdict('intent_match', true, 1, '未声明期望 intent，跳过', 'expected_intent=')
  }
  const pass = signals.intent_matched === true
  return verdict(
    'intent_match',
    pass,
    pass ? 1 : 0,
    pass
      ? `intent 命中 ${signals.actual_intent}`
      : `期望 ${signals.expected_intent}，实际 ${signals.actual_intent}`,
    `actual=${signals.actual_intent}`,
  )
}

function scoreTop1(signals: RetrievalObjectiveSignals): RubricVerdict {
  if (signals.top1_matched === null) {
    return verdict('top1_skill', true, 1, '本用例不适用 skill top-1', 'top1=N/A')
  }
  const pass = signals.top1_matched === true
  return verdict(
    'top1_skill',
    pass,
    pass ? 1 : 0,
    pass
      ? `top1 命中 ${signals.top1_skill}`
      : `期望 ${signals.expected_top1_skill}，实际 ${signals.top1_skill || '(空)'}`,
    `topk=[${(signals.topk_skills || []).join(', ')}]`,
  )
}

function scoreTopk(signals: RetrievalObjectiveSignals): RubricVerdict {
  if (signals.topk_hit_ratio == null) {
    return verdict('topk_skill_hit', true, 1, '本用例不适用 skill top-k', 'topk=N/A')
  }
  const ratio = Number(signals.topk_hit_ratio)
  const pass = ratio >= 1
  return verdict(
    'topk_skill_hit',
    pass,
    ratio,
    pass
      ? '期望 skill 全部落入 top-k'
      : `覆盖率 ${(ratio * 100).toFixed(0)}%（期望 ${signals.expected_topk?.join(', ')}）`,
    `topk=[${(signals.topk_skills || []).join(', ')}]`,
  )
}

function scorePreferred(signals: RetrievalObjectiveSignals): RubricVerdict {
  if (signals.preferred_boosted === null) {
    return verdict('preferred_skill_boost', true, 1, '未声明 preferred skill，跳过', 'preferred=[]')
  }
  const pass = signals.preferred_boosted === true
  return verdict(
    'preferred_skill_boost',
    pass,
    pass ? 1 : 0,
    pass
      ? 'preferred skill 已顶置进 top-k'
      : `preferred 未全部出现在 top-k：${signals.preferred_ids?.join(', ')}`,
    `topk=[${(signals.topk_skills || []).join(', ')}]`,
  )
}

function scoreModeOverride(signals: RetrievalObjectiveSignals): RubricVerdict {
  if (signals.mode_override_ok === null) {
    return verdict('mode_override', true, 1, 'retrieval_mode=auto，跳过覆盖检查', 'mode=auto')
  }
  const pass = signals.mode_override_ok === true
  return verdict(
    'mode_override',
    pass,
    pass ? 1 : 0,
    pass
      ? 'mode 覆盖生效且 explicit_override=true'
      : `mode 覆盖未按预期生效（intent=${signals.actual_intent}, explicit=${signals.explicit_override}）`,
    `intent=${signals.actual_intent}`,
  )
}

const SCORERS: Record<string, (s: RetrievalObjectiveSignals) => RubricVerdict> = {
  intent_match: scoreIntentMatch,
  top1_skill: scoreTop1,
  topk_skill_hit: scoreTopk,
  preferred_skill_boost: scorePreferred,
  mode_override: scoreModeOverride,
}

export function scoreRetrievalRubrics(
  rubric: Rubric[],
  signals: RetrievalObjectiveSignals,
): JudgeVerdict {
  const rubrics: RubricVerdict[] = []
  for (const item of rubric) {
    const isObjective = item.scoring === 'objective' || (!item.scoring && item.id in SCORERS)
    if (!isObjective) continue
    const scorer = SCORERS[item.id]
    if (!scorer) {
      rubrics.push(verdict(item.id, false, 0, `未知客观项 ${item.id}`, 'no scorer'))
      continue
    }
    rubrics.push(scorer(signals))
  }
  return {
    rubrics,
    summary: `intent=${signals.actual_intent}; top1=${signals.top1_skill || 'N/A'}`,
  }
}

export function scoreRetrievalCase(
  evalCase: EvalCase,
  signals?: RetrievalObjectiveSignals,
): CaseScore {
  const resolved = signals || collectRetrievalSignals(evalCase)
  return aggregateScore(scoreRetrievalRubrics(evalCase.rubric, resolved), evalCase.rubric)
}
