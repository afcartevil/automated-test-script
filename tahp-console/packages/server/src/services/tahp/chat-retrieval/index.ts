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
 * 仅显式「历史案例」模式禁用 Skill；自动模式融合本地 KB + Skill + Dify 补充。
 */
export async function buildChatRetrievalContext(
  userInput: string,
  options?: RetrievalOptions & { preferred_skill_ids?: string[] },
): Promise<string> {
  if (!hasTahpProject()) return ''

  const preferred = options?.preferred_skill_ids || []
  const modeHistorical = options?.retrieval_mode === 'historical'
  const skillDirective = buildSkillExecutionDirective({
    preferredSkillIds: preferred,
    scenario: 'chat',
  })
  const historicalDirective = buildHistoricalCaseDirective()

  try {
    const { bundle } = await runRetrieval(userInput, {
      retrieval_mode: options?.retrieval_mode,
      search_lark: options?.search_lark,
      preferred_skill_ids: preferred,
      module_hint: options?.module_hint,
    })
    const directive = modeHistorical ? historicalDirective : skillDirective
    const retrievalBlock = formatRetrievalPrompt(bundle)
    return [directive, retrievalBlock].filter(Boolean).join('\n\n')
  } catch {
    return modeHistorical ? historicalDirective : skillDirective
  }
}
