/**
 * Skill 同步 API — Phase 1/2
 *   GET  /api/tahp/skills/sync-status
 *   POST /api/tahp/skills/sync
 *   POST /api/tahp/skills/reinject
 *   POST /api/tahp/skills/publish-package
 *   POST /api/tahp/skills/publish-packages
 */
import Router from '@koa/router'
import { HermesSkillInjector } from '../../services/hermes/skill-injector'
import { logger } from '../../services/logger'
import { isCentralConfigured } from '../../services/tahp/runtime-mode'
import { publishSkillPackage, runPull } from '../../services/tahp/sync/pull'
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
        requirements_changed: pull?.requirements_changed || [],
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

tahpSkillSyncRoutes.post('/api/tahp/skills/publish-package', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 400
    ctx.body = { success: false, error: '中心未配置（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN）' }
    return
  }
  const body = (ctx.request.body || {}) as { skill_id?: string }
  const skillId = String(body.skill_id || '').trim()
  if (!skillId || !/^[a-zA-Z0-9_-]+$/.test(skillId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少合法 skill_id' }
    return
  }
  try {
    const data = await publishSkillPackage(skillId)
    ctx.body = { success: true, data }
  } catch (err) {
    logger.error({ err, skillId }, '[skill-sync] publish-package failed')
    ctx.status = 502
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpSkillSyncRoutes.post('/api/tahp/skills/publish-packages', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 400
    ctx.body = { success: false, error: '中心未配置（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN）' }
    return
  }
  const body = (ctx.request.body || {}) as { skill_ids?: string[] }
  const skillIds = Array.isArray(body.skill_ids)
    ? [...new Set(body.skill_ids.map(String).map(s => s.trim()).filter(id => /^[a-zA-Z0-9_-]+$/.test(id)))]
    : []
  if (!skillIds.length) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 skill_ids' }
    return
  }

  const ok: Array<{ id: string; hash: string; file_count: number }> = []
  const failed: Array<{ id: string; error: string }> = []
  for (const skillId of skillIds) {
    try {
      ok.push(await publishSkillPackage(skillId))
    } catch (err) {
      const error = (err as Error).message
      failed.push({ id: skillId, error })
      logger.warn({ err, skillId }, '[skill-sync] publish-packages item failed')
    }
  }

  ctx.body = {
    success: true,
    data: {
      total: skillIds.length,
      ok_count: ok.length,
      failed_count: failed.length,
      ok,
      failed,
    },
  }
})
