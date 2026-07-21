import { searchKb, searchKbCatalog } from '../../kb-search'
import {
  extractCatalogFocus,
  isCatalogQuery,
  resolveDomainKeywords,
} from '../catalog-query'
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
  '禁止 grep/search_files 全库 skills/、knowledge-base/、harness。',
]

const EXPLICIT_CATALOG_DIRECTIVES = [
  '用户在做案例目录查询：仅输出知识库案例表格，禁止列举 Skill。',
  '表格列：JIRA | 标题/现象 | 一句话结论（摘自下方摘要，勿编造）。',
  '不要输出「一、Skill 列表」、不要推荐加载 Skill、不要写通用排查框架。',
  '若预检索条目不足，如实说明「知识库目前仅有 N 条匹配」，不要改用 Skill 充数。',
]

function buildDirectives(explicit: boolean, catalog: boolean): string[] {
  if (explicit) {
    return [
      ...BASE_DIRECTIVES,
      '主答案必须来自智能诊断沉淀案例（bug_distill），禁止改答 Skill 目录。',
      ...(catalog ? EXPLICIT_CATALOG_DIRECTIVES : []),
    ]
  }
  return [
    ...BASE_DIRECTIVES,
    '优先引用本地案例（bug_distill）与文档（doc_chunk/doc_summary）；案例优先于文档。',
    '如需执行排查步骤，可按需 Read 相关 Skill（1～3 个）；禁止全盘搜 Skill 目录。',
    '可提示用户参考稍后出现的「底软通信知识库补充参考」卡片。',
    ...(catalog
      ? ['用户在做列举类查询：优先列出案例表格；若无案例可综述文档要点，勿编造通用分类表。']
      : []),
  ]
}

export async function runHistoricalCase(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const explicit = options.explicit === true
  const catalog = isCatalogQuery(query)
  const focus = catalog ? extractCatalogFocus(query) : query
  const domainKeywords = resolveDomainKeywords(focus, routed.module_hint)
  const sourceTypes = explicit ? CASE_ONLY_KB_SOURCE_TYPES : FUSION_KB_SOURCE_TYPES

  const kb_hits = catalog
    ? await searchKbCatalog({
        query: focus,
        domain_keywords: domainKeywords,
        source_types: sourceTypes,
        include_archived: true,
        limit: 15,
        min_score: 6,
      })
    : await searchKb({
        query: focus || query,
        module_hint: routed.module_hint,
        source_types: sourceTypes,
        include_archived: true,
        limit: 5,
        ...(explicit ? {} : { min_score: 8 }),
      })

  return {
    intent: 'historical_case',
    strategy_label: INTENT_LABELS.historical_case,
    kb_hits,
    skill_hits: [],
    lark_hits: [],
    catalog_mode: catalog,
    explicit_mode: explicit,
    directives: buildDirectives(explicit, catalog),
    latency_ms: Date.now() - start,
  }
}
