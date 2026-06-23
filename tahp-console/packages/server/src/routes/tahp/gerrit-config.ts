/**
 * Gerrit 账号配置 REST 路由
 */
import Router from '@koa/router'
import { logger } from '../../services/logger'
import {
  getGerritConfigPublic,
  saveGerritConfig,
  type SaveGerritConfigInput,
} from '../../services/tahp/gerrit-credentials'

export const tahpGerritConfigRoutes = new Router()

// GET /api/tahp/gerrit-config — 获取配置（不含明文密码）
tahpGerritConfigRoutes.get('/api/tahp/gerrit-config', async (ctx) => {
  try {
    ctx.body = { success: true, data: getGerritConfigPublic() }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gerrit-config] get failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// PUT /api/tahp/gerrit-config — 保存配置
tahpGerritConfigRoutes.put('/api/tahp/gerrit-config', saveGerritConfigHandler)

// POST /api/tahp/gerrit-config/save — 保存配置（与 adapt config 一致，兼容部分代理环境）
tahpGerritConfigRoutes.post('/api/tahp/gerrit-config/save', saveGerritConfigHandler)

async function saveGerritConfigHandler(ctx: import('koa').Context) {
  try {
    const body = (ctx.request.body || {}) as Partial<SaveGerritConfigInput>
    const input: SaveGerritConfigInput = {
      host: typeof body.host === 'string' ? body.host : undefined,
      user: typeof body.user === 'string' ? body.user : '',
      password: typeof body.password === 'string' ? body.password : undefined,
    }
    const data = await saveGerritConfig(input)
    ctx.body = { success: true, data }
  } catch (err) {
    const msg = (err as Error).message
    logger.warn({ err: msg }, '[gerrit-config] save failed')
    ctx.status = 400
    ctx.body = { success: false, error: msg }
  }
}
