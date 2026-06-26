/**
 * 向中心提交新建条目 / Skill 草稿（进入中心 pending_review 待审）。
 * 本地不写权威库，由中心审核通过后再经 pull 下发全员。
 */
import { logger } from '../../logger'
import { centralClient } from './central-client'

export async function pushEntry(entry: Record<string, unknown>): Promise<{ id: string; action?: string }> {
  const res = await centralClient.submit({ kind: 'entry', entry })
  logger.info({ centralId: res.id, action: res.action }, '[sync] entry submitted to central')
  return res
}

export async function pushSkillDraft(draft: Record<string, unknown>): Promise<{ id: string; action?: string }> {
  const res = await centralClient.submit({ kind: 'skill_draft', draft })
  logger.info({ centralId: res.id, action: res.action }, '[sync] skill draft submitted to central')
  return res
}
