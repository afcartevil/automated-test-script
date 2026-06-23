import type { ChatIntent, RetrievalMode } from './intents'
import { retrievalModeToIntent } from './intents'
import { parseKbQuery } from '../kb-search/query-parser'

export interface RoutedIntent {
  intent: ChatIntent
  confidence: number
  module_hint?: string
  func_type_hint?: string
  explicit_override?: boolean
  signals: string[]
}

interface IntentRule {
  intent: ChatIntent
  patterns: RegExp[]
  weight: number
}

const INTENT_RULES: IntentRule[] = [
  {
    intent: 'direct_lookup',
    patterns: [/\bkb-[a-f0-9]{8}\b/i, /\bdoc-[a-f0-9]{8}\b/i, /\b[A-Z][A-Z0-9]+-\d+\b/],
    weight: 1.0,
  },
  {
    intent: 'historical_case',
    patterns: [
      /类似|历史|以前|案例|沉淀|有没有.*bug|有没有.*问题|won'?t fix|根因|jira/i,
      /触发.*防烧|端口防烧|通知栏.*不显示|不显示.*通知|NTC.*70|70.*NTC|插入.*充电/i,
      /有哪些|列出|列表|列举|相关案例|案例有哪些/i,
    ],
    weight: 0.85,
  },
  {
    intent: 'concept_reference',
    patterns: [/是什么|什么叫|定义|机制|原理|特性|概念|什么意思/i],
    weight: 0.8,
  },
  {
    intent: 'analysis_sop',
    patterns: [/怎么分析|如何分析|分析步骤|排查步骤|分诊|sop|流程|从哪看|怎么看/i],
    weight: 0.85,
  },
  {
    intent: 'adaptation_guide',
    patterns: [/适配|p1|升级路径|移植|榫卯|migration|adapt/i],
    weight: 0.8,
  },
  {
    intent: 'integration_config',
    patterns: [/如何配置|集成步骤|参数|配置方法|怎么配/i],
    weight: 0.75,
  },
  {
    intent: 'api_spec',
    patterns: [/api\b|接口定义|调用方法|interface\b|函数签名/i],
    weight: 0.75,
  },
  {
    intent: 'version_scope',
    patterns: [/哪些版本|适用版本|平台差异|android\s*\d|分支范围/i],
    weight: 0.7,
  },
  {
    intent: 'troubleshooting_checklist',
    patterns: [/检查项|快速定位|症状|清单|checklist/i],
    weight: 0.75,
  },
  {
    intent: 'policy_standards',
    patterns: [/编码规范|提交流程|评审标准|code review|standards/i],
    weight: 0.7,
  },
]

const FUNC_TYPE_HINTS: Array<{ hint: string; patterns: RegExp[] }> = [
  { hint: 'bug_analysis', patterns: [/bug|故障|crash|jira/i] },
  { hint: 'code_adaptation', patterns: [/适配|adapt|移植/i] },
]

export function routeIntent(
  userInput: string,
  options?: { retrieval_mode?: RetrievalMode; slash_intent?: ChatIntent },
): RoutedIntent {
  const text = userInput.trim()
  const signals: string[] = []

  if (options?.slash_intent) {
    return {
      intent: options.slash_intent,
      confidence: 1,
      explicit_override: true,
      signals: ['slash'],
    }
  }

  const forced = retrievalModeToIntent(options?.retrieval_mode)
  if (forced) {
    return {
      intent: forced,
      confidence: 1,
      explicit_override: true,
      signals: [`mode:${options?.retrieval_mode}`],
    }
  }

  const parsed = parseKbQuery(text)
  if (parsed.jira_key || parsed.entry_id || parsed.document_id) {
    signals.push('direct_signal')
    return {
      intent: 'direct_lookup',
      confidence: 0.95,
      module_hint: parsed.module_hint,
      signals,
    }
  }

  const scores = new Map<ChatIntent, number>()
  for (const rule of INTENT_RULES) {
    let hit = 0
    for (const p of rule.patterns) {
      if (p.test(text)) hit++
    }
    if (hit > 0) {
      scores.set(rule.intent, (scores.get(rule.intent) || 0) + rule.weight * hit)
      signals.push(`${rule.intent}:${hit}`)
    }
  }

  let func_type_hint: string | undefined
  for (const { hint, patterns } of FUNC_TYPE_HINTS) {
    if (patterns.some(p => p.test(text))) {
      func_type_hint = hint
      break
    }
  }

  const ranked = [...scores.entries()].sort((a, b) => b[1] - a[1])
  if (ranked.length === 0) {
    return {
      intent: 'mixed_explore',
      confidence: 0.4,
      module_hint: parsed.module_hint,
      func_type_hint,
      signals: ['no_rule_hit'],
    }
  }

  const [topIntent, topScore] = ranked[0]
  const secondScore = ranked[1]?.[1] ?? 0
  if (topScore < 0.55 || topScore - secondScore < 0.12) {
    return {
      intent: 'mixed_explore',
      confidence: topScore,
      module_hint: parsed.module_hint,
      func_type_hint,
      signals: [...signals, 'low_confidence'],
    }
  }

  return {
    intent: topIntent,
    confidence: Math.min(1, topScore),
    module_hint: parsed.module_hint,
    func_type_hint,
    signals,
  }
}

export function parseSlashIntent(text: string): { intent?: ChatIntent; rest: string } {
  const m = text.match(/^\/(历史|概念|sop|适配|规范)\s*(.*)$/i)
  if (!m) return { rest: text }
  const map: Record<string, ChatIntent> = {
    历史: 'historical_case',
    概念: 'concept_reference',
    sop: 'analysis_sop',
    适配: 'adaptation_guide',
    规范: 'policy_standards',
  }
  const key = m[1].toLowerCase()
  const intent = map[key] || map[m[1]]
  return { intent, rest: m[2].trim() || text }
}
