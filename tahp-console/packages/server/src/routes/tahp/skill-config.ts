/**
 * TAHP — 必要 Skill 配置 API
 */
import Router from '@koa/router'
import {
  listRequiredSkills,
  getSkillPreview,
  startSkillConfigAgent,
  continueSkillConfigAgent,
  respondSkillConfigApproval,
  verifySkillConfig,
  markSkillConfigured,
  clearSkillConfigured,
  getRequiredSkillsManifestPath,
} from '../../services/tahp/skill-config'

export const tahpSkillConfigRoutes = new Router({ prefix: '/api/tahp/skill-config' })

tahpSkillConfigRoutes.get('/', async (ctx) => {
  ctx.body = { success: true, data: listRequiredSkills() }
})

tahpSkillConfigRoutes.get('/manifest-path', async (ctx) => {
  ctx.body = { success: true, data: { path: getRequiredSkillsManifestPath() } }
})

tahpSkillConfigRoutes.post('/tasks/:taskId/continue', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const message = typeof body.message === 'string' ? body.message.trim() : ''
  if (!message) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 message' }
    return
  }
  const result = continueSkillConfigAgent(ctx.params.taskId, message)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { task_id: ctx.params.taskId } }
})

tahpSkillConfigRoutes.post('/tasks/:taskId/approval', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const approvalId = typeof body.approval_id === 'string' ? body.approval_id.trim() : ''
  const choice = typeof body.choice === 'string' ? body.choice.trim() : 'deny'
  if (!approvalId) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 approval_id' }
    return
  }
  const result = await respondSkillConfigApproval(ctx.params.taskId, approvalId, choice)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { approval_id: approvalId, choice } }
})

tahpSkillConfigRoutes.get('/:skillId/preview', async (ctx) => {
  const preview = getSkillPreview(ctx.params.skillId)
  if (!preview) {
    ctx.status = 404
    ctx.body = { success: false, error: 'Skill 不存在或未在清单中' }
    return
  }
  ctx.body = { success: true, data: preview }
})

tahpSkillConfigRoutes.post('/:skillId/verify', async (ctx) => {
  const result = verifySkillConfig(ctx.params.skillId)
  ctx.body = { success: true, data: result }
})

tahpSkillConfigRoutes.post('/:skillId/start', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const force = body.force === true
  const result = startSkillConfigAgent(ctx.params.skillId, force)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { task_id: result.taskId, status: 'running' } }
})

tahpSkillConfigRoutes.post('/:skillId/reset', async (ctx) => {
  clearSkillConfigured(ctx.params.skillId)
  ctx.body = { success: true, data: { skill_id: ctx.params.skillId, status: 'not_configured' } }
})

tahpSkillConfigRoutes.post('/:skillId/mark-complete', async (ctx) => {
  const verify = verifySkillConfig(ctx.params.skillId)
  if (!verify.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: `校验未通过: ${verify.detail}` }
    return
  }
  markSkillConfigured(ctx.params.skillId, { by: 'manual', note: '手动标记完成' })
  ctx.body = { success: true, data: { skill_id: ctx.params.skillId, status: 'configured' } }
})
