/**
 * Gerrit Code Review REST 路由
 */
import Router from '@koa/router'
import { logger } from '../../services/logger'
import { sendGerritReviewChat } from '../../services/tahp/gerrit-review'

export const tahpGerritReviewRoutes = new Router()

// POST /api/tahp/gerrit-review/chat — 发送消息（新建或继续会话）
tahpGerritReviewRoutes.post('/api/tahp/gerrit-review/chat', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    const sessionId = typeof body.session_id === 'string' ? body.session_id.trim() : undefined
    const message = typeof body.message === 'string' ? body.message : ''

    const result = sendGerritReviewChat({ sessionId, message })
    if (!result.ok) {
      ctx.status = 400
      ctx.body = { success: false, error: result.error }
      return
    }

    ctx.body = {
      success: true,
      data: {
        session_id: result.sessionId,
        task_id: result.taskId,
        status: 'running',
      },
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gerrit-review] chat failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
