/**
 * AI 测试自规划 REST 路由
 */
import Router from '@koa/router'
import { logger } from '../../services/logger'
import {
  getProjectNodesView,
  getTestPlanRules,
  getTestScheduleView,
  saveTestPlanRules,
  syncProjectNodesFromXlsx,
  type TestPlanRule,
} from '../../services/tahp/test-planning'

export const tahpTestPlanningRoutes = new Router()

tahpTestPlanningRoutes.get('/api/tahp/test-planning/nodes', async (ctx) => {
  try {
    const data = await getProjectNodesView()
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[test-planning] get nodes failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpTestPlanningRoutes.post('/api/tahp/test-planning/nodes/sync', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { filePath?: string }
    const filePath = typeof body.filePath === 'string' ? body.filePath : undefined
    const file = await syncProjectNodesFromXlsx(filePath)
    const data = await getProjectNodesView()
    ctx.body = { success: true, data: { ...data, synced: file } }
  } catch (err) {
    const msg = (err as Error).message
    logger.warn({ err: msg }, '[test-planning] sync nodes failed')
    ctx.status = 400
    ctx.body = { success: false, error: msg }
  }
})

tahpTestPlanningRoutes.get('/api/tahp/test-planning/rules', async (ctx) => {
  try {
    const data = await getTestPlanRules()
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[test-planning] get rules failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpTestPlanningRoutes.post('/api/tahp/test-planning/rules/save', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { rules?: TestPlanRule[] }
    const rules = Array.isArray(body.rules) ? body.rules : []
    const data = await saveTestPlanRules(rules)
    ctx.body = { success: true, data }
  } catch (err) {
    const msg = (err as Error).message
    logger.warn({ err: msg }, '[test-planning] save rules failed')
    ctx.status = 400
    ctx.body = { success: false, error: msg }
  }
})

tahpTestPlanningRoutes.get('/api/tahp/test-planning/schedule', async (ctx) => {
  try {
    const data = await getTestScheduleView()
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[test-planning] get schedule failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
