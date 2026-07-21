import { searchKb } from '../../kb-search'
import { searchLarkKnowledge } from '../../lark-knowledge-retriever'
import type { RoutedIntent } from '../intent-router'
import {
  CASE_ONLY_KB_SOURCE_TYPES,
  FUSION_KB_SOURCE_TYPES,
  type RetrievalBundle,
  type RetrievalOptions,
} from '../types'
import { INTENT_LABELS } from '../intents'

export async function runIntegrationConfig(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const kb_hits = await searchKb({
    query,
    module_hint: routed.module_hint,
    source_types: ['doc_chunk', 'doc_summary'],
    include_archived: true,
    limit: 5,
  })
  const lark_hits = options.search_lark
    ? await searchLarkKnowledge(query, { module_hint: routed.module_hint })
    : []
  return {
    intent: 'integration_config',
    strategy_label: INTENT_LABELS.integration_config,
    kb_hits,
    skill_hits: [],
    lark_hits,
    directives: ['优先引用文档与飞书配置说明。'],
    latency_ms: Date.now() - start,
  }
}

export async function runApiSpec(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const kb_hits = await searchKb({
    query,
    module_hint: routed.module_hint,
    source_types: ['doc_chunk', 'manual'],
    include_archived: true,
    limit: 5,
  })
  const { rankSkills } = await import('../skill-ranker')
  const skill_hits = rankSkills(query + ' API', { limit: 1, include_excerpt: true })
  return {
    intent: 'api_spec',
    strategy_label: INTENT_LABELS.api_spec,
    kb_hits,
    skill_hits,
    lark_hits: [],
    directives: ['引用 API 规范文档，避免臆造接口。'],
    latency_ms: Date.now() - start,
  }
}

export async function runVersionScope(
  query: string,
  routed: RoutedIntent,
  _options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const kb_hits = await searchKb({
    query,
    module_hint: routed.module_hint,
    include_archived: true,
    limit: 5,
  })
  return {
    intent: 'version_scope',
    strategy_label: INTENT_LABELS.version_scope,
    kb_hits,
    skill_hits: [],
    lark_hits: [],
    directives: ['关注 applicable_versions 与文档中的版本说明。'],
    latency_ms: Date.now() - start,
  }
}

export async function runTroubleshootingChecklist(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const { rankSkills } = await import('../skill-ranker')
  const skill_hits = rankSkills(query, { limit: 2, include_excerpt: true })
  const explicit = options.explicit === true
  const kb_hits = await searchKb({
    query,
    module_hint: routed.module_hint,
    source_types: explicit ? CASE_ONLY_KB_SOURCE_TYPES : FUSION_KB_SOURCE_TYPES,
    include_archived: true,
    limit: 3,
    ...(explicit ? {} : { min_score: 8 }),
  })
  return {
    intent: 'troubleshooting_checklist',
    strategy_label: INTENT_LABELS.troubleshooting_checklist,
    kb_hits,
    skill_hits,
    lark_hits: [],
    directives: ['输出分诊检查清单，引用 Skill 与历史案例。'],
    latency_ms: Date.now() - start,
  }
}

export async function runDirectLookup(
  query: string,
  _routed: RoutedIntent,
  _options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const kb_hits = await searchKb({
    query,
    include_archived: true,
    jira_fast_path: true,
    limit: 3,
    min_score: 0,
  })
  return {
    intent: 'direct_lookup',
    strategy_label: INTENT_LABELS.direct_lookup,
    kb_hits,
    skill_hits: [],
    lark_hits: [],
    directives: ['精确命中条目，直接引用 content。'],
    latency_ms: Date.now() - start,
  }
}

export async function runMixedExplore(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const { rankSkills } = await import('../skill-ranker')
  const [kb_hits, skill_hits, lark_hits] = await Promise.all([
    searchKb({ query, module_hint: routed.module_hint, include_archived: true, limit: 2 }),
    Promise.resolve(rankSkills(query, { limit: 1 })),
    options.search_lark ? searchLarkKnowledge(query, { limit: 2 }) : Promise.resolve([]),
  ])
  return {
    intent: 'mixed_explore',
    strategy_label: INTENT_LABELS.mixed_explore,
    kb_hits,
    skill_hits,
    lark_hits,
    directives: ['意图不明确，已混合检索；请说明最相关来源。'],
    latency_ms: Date.now() - start,
  }
}
