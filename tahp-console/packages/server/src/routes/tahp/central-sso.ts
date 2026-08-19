/**
 * 从本机 EA 打开中心网页：向中心换一次性 ticket，不把密码放进 URL。
 * GET /api/tahp/central/sso-url?next=/
 */
import Router from '@koa/router'
import { config } from '../../config'
import { logger } from '../../services/logger'
import { readJiraUserConfig } from '../../services/tahp/jira-user-config'
import { readCentralUserSession } from '../../services/tahp/central-user-session'
import { isCentralConfigured } from '../../services/tahp/runtime-mode'
import { bindJiraToCentral } from '../../services/tahp/sync/jira-bind'
import { centralClient } from '../../services/tahp/sync/central-client'

export const tahpCentralSsoRoutes = new Router()

function sanitizeNext(raw: unknown): string {
  const next = String(raw || '/').trim() || '/'
  if (next.startsWith('/') && !next.startsWith('//')) return next
  return '/'
}

tahpCentralSsoRoutes.get('/api/tahp/central/sso-url', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 400
    ctx.body = { success: false, error: '中心未配置（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN）' }
    return
  }
  const next = sanitizeNext(ctx.query.next)
  try {
    let sessionToken = readCentralUserSession()?.token || ''
    if (!sessionToken) {
      const jira = readJiraUserConfig()
      if (!jira) {
        ctx.status = 400
        ctx.body = { success: false, error: '请先在 EasyAdapter 填写 Jira 账号密码' }
        return
      }
      const bound = await bindJiraToCentral({
        username: jira.username,
        password: jira.password,
        baseUrl: jira.base_url,
      })
      sessionToken = bound?.token || ''
    }
    if (!sessionToken) {
      ctx.status = 502
      ctx.body = { success: false, error: '绑定中心失败，请确认中心可达且 Jira 密码正确' }
      return
    }

    let ticket: { ticket: string; consume_path: string }
    try {
      ticket = await centralClient.issueAuthTicket(sessionToken, next)
    } catch {
      const jira = readJiraUserConfig()
      if (!jira) throw new Error('中心会话已过期，且本机没有 Jira 凭据')
      const bound = await bindJiraToCentral({
        username: jira.username,
        password: jira.password,
        baseUrl: jira.base_url,
      })
      if (!bound?.token) throw new Error('重新绑定中心失败')
      ticket = await centralClient.issueAuthTicket(bound.token, next)
    }

    const base = config.tahp.centralUrl.replace(/\/+$/, '')
    ctx.body = {
      success: true,
      data: {
        url: `${base}${ticket.consume_path}`,
        consume_path: ticket.consume_path,
      },
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[central-sso] sso-url failed')
    ctx.status = 502
    ctx.body = { success: false, error: (err as Error).message }
  }
})
