export type ChatIntent =
  | 'historical_case'
  | 'concept_reference'
  | 'analysis_sop'
  | 'adaptation_guide'
  | 'integration_config'
  | 'api_spec'
  | 'version_scope'
  | 'troubleshooting_checklist'
  | 'direct_lookup'
  | 'policy_standards'
  | 'mixed_explore'

export type RetrievalMode =
  | 'auto'
  | 'historical'
  | 'concept'
  | 'sop'
  | 'adapt'

export const INTENT_LABELS: Record<ChatIntent, string> = {
  historical_case: '历史案例检索',
  concept_reference: '概念/文档检索',
  analysis_sop: '分析 SOP 检索',
  adaptation_guide: '适配指南检索',
  integration_config: '集成配置检索',
  api_spec: 'API 规范检索',
  version_scope: '版本范围检索',
  troubleshooting_checklist: '故障检查清单',
  direct_lookup: '精确查找',
  policy_standards: '规范标准检索',
  mixed_explore: '综合探索',
}

export function retrievalModeToIntent(mode?: RetrievalMode): ChatIntent | undefined {
  switch (mode) {
    case 'historical': return 'historical_case'
    case 'concept': return 'concept_reference'
    case 'sop': return 'analysis_sop'
    case 'adapt': return 'adaptation_guide'
    default: return undefined
  }
}
