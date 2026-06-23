import { hasTahpProject } from '../paths'
import { buildHistoricalCaseDirective, buildSkillExecutionDirective } from '../context-injector'
import type { RetrievalOptions } from './types'
import { runRetrieval } from './orchestrator'
import { formatRetrievalPrompt } from './prompt-formatter'

export type { ChatIntent, RetrievalMode } from './intents'
export type { RetrievalBundle, RetrievalOptions } from './types'
export { routeIntent } from './intent-router'
export { runRetrieval } from './orchestrator'
export { formatRetrievalPrompt } from './prompt-formatter'

/**
 * 对话场景：意图路由 + 分场景检索 → 注入 system prompt。
 */
export async function buildChatRetrievalContext(
  userInput: string,
  options?: RetrievalOptions & { preferred_skill_ids?: string[] },
): Promise<string> {
  if (!hasTahpProject()) return ''

  const preferred = options?.preferred_skill_ids || []
  const isHistorical = options?.retrieval_mode === 'historical'
  const skillDirective = isHistorical
    ? buildHistoricalCaseDirective()
    : buildSkillExecutionDirective({
        preferredSkillIds: preferred,
        scenario: 'chat',
      })

  try {
    const { bundle } = await runRetrieval(userInput, {
      retrieval_mode: options?.retrieval_mode,
      search_lark: options?.search_lark,
      preferred_skill_ids: preferred,
      module_hint: options?.module_hint,
    })
    const retrievalBlock = formatRetrievalPrompt(bundle)
    return [skillDirective, retrievalBlock].filter(Boolean).join('\n\n')
  } catch {
    return skillDirective
  }
}
