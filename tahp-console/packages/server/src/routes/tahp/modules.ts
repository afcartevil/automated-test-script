/**
 * 模块与约束矩阵路由 — 直接读 constraints/ 目录, 不经过 MCP.
 */
import Router from '@koa/router'
import { listModules } from '../../services/tahp/constraints-fs'

export const tahpModuleRoutes = new Router()

tahpModuleRoutes.get('/api/tahp/modules', async (ctx) => {
  try {
    const modules = await listModules()
    ctx.body = { success: true, data: modules }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpModuleRoutes.get('/api/tahp/modules/:name', async (ctx) => {
  try {
    const modules = await listModules()
    const m = modules.find(x => x.name === ctx.params.name)
    if (!m) {
      ctx.status = 404
      ctx.body = { success: false, error: '模块不存在' }
      return
    }
    ctx.body = { success: true, data: m }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
