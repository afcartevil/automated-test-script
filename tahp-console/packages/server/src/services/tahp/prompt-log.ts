/**
 * 将发往 Agent Bridge 的最终 system / user 提示词落盘，便于审计与排障。
 */
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { tahpPaths } from './paths'

export interface AgentPromptLogMeta {
  taskId: string
  channel: string
  savedAt: string
  systemPromptChars: number
  userPromptChars: number
  promptDir: string
}

/**
 * 保存 Agent 提示词到 reports/{channel}/prompts/{taskId}/
 * - system-prompt.md
 * - user-prompt.md
 * - prompts-meta.json
 */
export function saveAgentPromptLog(
  taskId: string,
  channel: string,
  systemPrompt: string,
  userPrompt: string,
): AgentPromptLogMeta {
  const promptDir = join(tahpPaths.reportsDir, channel, 'prompts', taskId)
  if (!existsSync(promptDir)) mkdirSync(promptDir, { recursive: true })

  const meta: AgentPromptLogMeta = {
    taskId,
    channel,
    savedAt: new Date().toISOString(),
    systemPromptChars: systemPrompt.length,
    userPromptChars: userPrompt.length,
    promptDir,
  }

  try {
    writeFileSync(join(promptDir, 'system-prompt.md'), systemPrompt, 'utf-8')
    writeFileSync(join(promptDir, 'user-prompt.md'), userPrompt, 'utf-8')
    writeFileSync(join(promptDir, 'prompts-meta.json'), JSON.stringify(meta, null, 2), 'utf-8')
    logger.info(
      { taskId, channel, systemPromptChars: meta.systemPromptChars, userPromptChars: meta.userPromptChars },
      '[agent-prompt-log] saved',
    )
  } catch (err) {
    logger.warn({ err, taskId, channel }, '[agent-prompt-log] write failed')
  }

  return meta
}
