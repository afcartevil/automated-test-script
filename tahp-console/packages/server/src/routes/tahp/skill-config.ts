/**
 * TAHP — 常用 Skill 配置 API
 */
import Router from '@koa/router'
import {
  listRequiredSkills,
  getSkillPreview,
  startSkillConfigAgent,
  startBatchSkillConfigAgent,
  continueSkillConfigAgent,
  respondSkillConfigApproval,
  markSkillConfigured,
  clearSkillConfigured,
  getRequiredSkillsManifestPath,
} from '../../services/tahp/skill-config'
import {
  getUnifiedConfigPublic,
  writeUnifiedConfig,
  type UnifiedConfigValues,
} from '../../services/tahp/unified-config'

export const tahpSkillConfigRoutes = new Router({ prefix: '/api/tahp/skill-config' })

tahpSkillConfigRoutes.get('/', async (ctx) => {
  ctx.body = { success: true, data: listRequiredSkills() }
})

// ─── 一键配置表单 ─────────────────────────────────────────────────────────────
tahpSkillConfigRoutes.get('/unified-form', async (ctx) => {
  ctx.body = { success: true, data: getUnifiedConfigPublic() }
})

tahpSkillConfigRoutes.put('/unified-form', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const rawValues = (body.values && typeof body.values === 'object')
    ? body.values as Record<string, unknown>
    : body
  const values: UnifiedConfigValues = {}
  for (const [k, v] of Object.entries(rawValues)) {
    if (typeof v === 'string') values[k] = v
  }
  const saved = writeUnifiedConfig(values)
  ctx.body = { success: true, data: getUnifiedConfigPublic(), updated_at: saved.__updated_at }
})

// ─── Skill 配置检查（批量 Agent）───────────────────────────────────────────
tahpSkillConfigRoutes.post('/configure-all', async (ctx) => {
  const result = startBatchSkillConfigAgent()
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { task_id: result.taskId, status: 'running' } }
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
  markSkillConfigured(ctx.params.skillId, { by: 'manual', note: '手动标记完成' })
  ctx.body = { success: true, data: { skill_id: ctx.params.skillId, status: 'configured' } }
})
