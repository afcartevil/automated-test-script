/**
 * Skill 同步 API — Phase 1
 *   GET  /api/tahp/skills/sync-status
 *   POST /api/tahp/skills/sync
 *   POST /api/tahp/skills/reinject
 */
import Router from '@koa/router'
import { HermesSkillInjector } from '../../services/hermes/skill-injector'
import { logger } from '../../services/logger'
import { isCentralConfigured } from '../../services/tahp/runtime-mode'
import { runPull } from '../../services/tahp/sync/pull'
import { getSkillSyncStatus } from '../../services/tahp/sync/status'

export const tahpSkillSyncRoutes = new Router()

tahpSkillSyncRoutes.get('/api/tahp/skills/sync-status', async (ctx) => {
  try {
    const data = await getSkillSyncStatus()
    ctx.body = { success: true, data }
  } catch (err) {
    logger.error({ err }, '[skill-sync] sync-status failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpSkillSyncRoutes.post('/api/tahp/skills/sync', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 400
    ctx.body = { success: false, error: '中心未配置（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN）' }
    return
  }
  const body = (ctx.request.body || {}) as { skill_ids?: string[] }
  const skillIds = Array.isArray(body.skill_ids)
    ? body.skill_ids.map(String).filter(Boolean)
    : undefined

  try {
    // 手动同步：全量 pull；若指定 skill_ids 则仅 reinject 这些
    const pull = await runPull(false, {
      reinjectSkillIds: skillIds?.length ? skillIds : undefined,
    })
    const status = await getSkillSyncStatus()
    ctx.body = {
      success: true,
      data: {
        pull,
        reinjected: pull?.reinjected || [],
        reinject_error: pull?.reinject_error,
        status: {
          behind_count: status.behind_count,
          last_pulled_at: status.last_pulled_at,
          connected: status.connected,
          configured: status.configured,
        },
      },
    }
  } catch (err) {
    logger.error({ err }, '[skill-sync] sync failed')
    ctx.status = 502
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpSkillSyncRoutes.post('/api/tahp/skills/reinject', async (ctx) => {
  const body = (ctx.request.body || {}) as { skill_ids?: string[] }
  const skillIds = Array.isArray(body.skill_ids)
    ? body.skill_ids.map(String).filter(Boolean)
    : undefined

  try {
    const result = await new HermesSkillInjector().injectMissingSkills(
      skillIds?.length ? skillIds : undefined,
    )
    ctx.body = { success: true, data: result }
  } catch (err) {
    logger.error({ err }, '[skill-sync] reinject failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
