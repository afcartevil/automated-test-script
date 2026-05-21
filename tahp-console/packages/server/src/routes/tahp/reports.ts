/**
 * 报告浏览路由.
 */
import Router from '@koa/router'
import { listReports, readReport } from '../../services/tahp/reports-fs'

export const tahpReportsRoutes = new Router()

tahpReportsRoutes.get('/api/tahp/reports', async (ctx) => {
  try {
    const sub = typeof ctx.query.path === 'string' ? ctx.query.path : ''
    const entries = await listReports(sub)
    ctx.body = { success: true, data: entries }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpReportsRoutes.get('/api/tahp/reports/content', async (ctx) => {
  const sub = typeof ctx.query.path === 'string' ? ctx.query.path : ''
  if (!sub) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 path' }
    return
  }
  try {
    const text = await readReport(sub)
    ctx.body = { success: true, data: { path: sub, content: text } }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})
