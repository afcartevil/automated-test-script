import Router from '@koa/router'
import { runSelfCheck } from '../../services/tahp/self-check'

export const tahpSelfCheckRoutes = new Router()

tahpSelfCheckRoutes.get('/api/tahp/self-check', async (ctx) => {
  try {
    const data = await runSelfCheck()
    ctx.body = { success: true, data }
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { success: false, error: err?.message || 'Self-check failed' }
  }
})
