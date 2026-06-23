import { searchKb } from '../../kb-search'
import { searchLarkKnowledge } from '../../lark-knowledge-retriever'
import type { RoutedIntent } from '../intent-router'
import type { RetrievalBundle, RetrievalOptions } from '../types'
import { INTENT_LABELS } from '../intents'

const BASE_DIRECTIVES = [
  '以下内容由服务端预检索生成，请优先引用。',
  '禁止 grep 全库 skills/、knowledge-base/、harness；仅当 snippet 不足时再 Read 指定路径。',
]

export async function runConceptReference(
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  const start = Date.now()
  const summaries = await searchKb({
    query,
    module_hint: routed.module_hint,
    source_types: ['doc_summary'],
    include_archived: true,
    limit: 3,
  })

  let kb_hits = summaries
  if (summaries.length > 0) {
    const chunks = await searchKb({
      query,
      source_types: ['doc_chunk'],
      include_archived: true,
      limit: 5,
      min_score: 10,
    })
    kb_hits = [...summaries, ...chunks.filter(c => !summaries.some(s => s.id === c.id))].slice(0, 6)
  } else {
    kb_hits = await searchKb({
      query,
      module_hint: routed.module_hint,
      source_types: ['doc_chunk', 'doc_summary', 'manual'],
      include_archived: true,
      limit: 5,
    })
  }

  const lark_hits = options.search_lark
    ? await searchLarkKnowledge(query, { module_hint: routed.module_hint })
    : []

  if (!options.search_lark && kb_hits.length === 0) {
    // 低命中时可提示用户开启飞书搜索
  }

  return {
    intent: 'concept_reference',
    strategy_label: INTENT_LABELS.concept_reference,
    kb_hits,
    skill_hits: [],
    lark_hits,
    directives: [
      ...BASE_DIRECTIVES,
      '主答案来自上传知识文档；飞书结果作补充并标注链接。',
    ],
    latency_ms: Date.now() - start,
  }
}
