import Router from '@koa/router'
import {
  ensureGkiPatchServer,
  getGkiPatchDefaults,
  getGkiPatchStatusAsync,
} from '../../services/tahp/gki-patch'

export const tahpGkiPatchRoutes = new Router({ prefix: '/api/tahp/gki-patch' })

tahpGkiPatchRoutes.get('/defaults', async (ctx) => {
  try {
    ctx.body = { success: true, data: getGkiPatchDefaults() }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.get('/status', async (ctx) => {
  try {
    ctx.body = { success: true, data: await getGkiPatchStatusAsync() }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.post('/start', async (ctx) => {
  try {
    const data = await ensureGkiPatchServer()
    ctx.body = { success: true, data }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})
