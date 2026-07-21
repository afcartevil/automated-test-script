import { searchKb } from '../../kb-search'
import { rankSkills } from '../skill-ranker'
import type { RoutedIntent } from '../intent-router'
import {
  CASE_ONLY_KB_SOURCE_TYPES,
  FUSION_KB_SOURCE_TYPES,
  type RetrievalBundle,
  type RetrievalOptions,
} from '../types'
import { INTENT_LABELS } from '../intents'

const BASE_DIRECTIVES = [
  '以下内容由服务端预检索生成，请优先引用。',
  '禁止加载 188 个 Skill 全量目录；仅使用下列相关 Skill。',
]

export async function runAnalysisSop(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const skill_hits = rankSkills(query, {
    limit: 3,
    preferred_skill_ids: options.preferred_skill_ids,
    include_excerpt: true,
  })
  const explicit = options.explicit === true
  const kb_hits = await searchKb({
    query,
    module_hint: routed.module_hint,
    source_types: explicit ? CASE_ONLY_KB_SOURCE_TYPES : FUSION_KB_SOURCE_TYPES,
    include_archived: true,
    limit: explicit ? 2 : 4,
    min_score: explicit ? 10 : 8,
  })
  return {
    intent: 'analysis_sop',
    strategy_label: INTENT_LABELS.analysis_sop,
    kb_hits,
    skill_hits,
    lark_hits: [],
    explicit_mode: explicit,
    directives: explicit
      ? [...BASE_DIRECTIVES, '主答案来自 Skill SOP；知识库案例仅作附录参考。']
      : [
          ...BASE_DIRECTIVES,
          '优先引用本地 SOP 文档与案例；Skill 用于补充执行步骤。',
          '可提示用户参考「底软通信知识库补充参考」卡片。',
        ],
    latency_ms: Date.now() - start,
  }
}

export async function runAdaptationGuide(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const skill_hits = rankSkills(query, {
    limit: 3,
    preferred_skill_ids: options.preferred_skill_ids,
    include_excerpt: true,
  })
  const kb_hits = await searchKb({
    query,
    module_hint: routed.module_hint,
    func_type: 'code_adaptation',
    include_archived: true,
    limit: 3,
  })
  return {
    intent: 'adaptation_guide',
    strategy_label: INTENT_LABELS.adaptation_guide,
    kb_hits,
    skill_hits,
    lark_hits: [],
    directives: [...BASE_DIRECTIVES, '优先遵循适配类 Skill。'],
    latency_ms: Date.now() - start,
  }
}

export async function runPolicyStandards(
  query: string,
  _routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const skill_hits = rankSkills(query + ' coding standards review', {
    limit: 2,
    preferred_skill_ids: [...(options.preferred_skill_ids || []), 'transsion-coding-standards-review'],
    include_excerpt: true,
  })
  const kb_hits = await searchKb({
    query,
    source_types: ['doc_chunk', 'manual'],
    include_archived: true,
    limit: 2,
  })
  return {
    intent: 'policy_standards',
    strategy_label: INTENT_LABELS.policy_standards,
    kb_hits,
    skill_hits,
    lark_hits: [],
    directives: BASE_DIRECTIVES,
    latency_ms: Date.now() - start,
  }
}
