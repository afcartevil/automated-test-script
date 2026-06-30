/**
 * Gerrit Code Review REST 路由
 */
import Router from '@koa/router'
import { appendFileSync, existsSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { logger } from '../../services/logger'
import { sendGerritReviewChat, cancelGerritReviewTask } from '../../services/tahp/gerrit-review'
import { recommendTestCasesWithMeta } from '../../services/tahp/gerrit-case-recommendation'
import { tahpPaths } from '../../services/tahp/paths'

export const tahpGerritReviewRoutes = new Router()

function gerritReviewDebugLogDir(): string {
  const d = join(tahpPaths.reportsDir, 'gerrit-review-debug')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

function appendGerritReviewClientLog(entries: unknown[]): void {
  const day = new Date().toISOString().slice(0, 10)
  const file = join(gerritReviewDebugLogDir(), `client-${day}.jsonl`)
  for (const entry of entries) {
    appendFileSync(file, `${JSON.stringify(entry)}\n`, 'utf-8')
  }
}

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

tahpGerritReviewRoutes.post('/api/tahp/gerrit-review/recommend-cases', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as {
      modules?: string[]
      p0_items?: string[]
    }
    const modules = Array.isArray(body.modules) ? body.modules.map(String) : []
    const p0Items = Array.isArray(body.p0_items) ? body.p0_items.map(String) : []
    const { cases: recommended_cases, source } = await recommendTestCasesWithMeta(p0Items, modules)
    logger.info(
      {
        p0Count: p0Items.length,
        moduleCount: modules.length,
        recommendedCount: recommended_cases.length,
        source,
      },
      '[gerrit-review] recommend-cases',
    )
    ctx.body = { success: true, data: { recommended_cases } }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gerrit-review] recommend-cases failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpGerritReviewRoutes.post('/api/tahp/gerrit-review/debug-log', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { entries?: unknown[] }
    const entries = Array.isArray(body.entries) ? body.entries : []
    if (entries.length) {
      appendGerritReviewClientLog(entries)
    }
    ctx.body = { success: true, data: { written: entries.length } }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gerrit-review] debug-log failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpGerritReviewRoutes.post('/api/tahp/gerrit-review/tasks/:id/cancel', async (ctx) => {
  try {
    const result = await cancelGerritReviewTask(ctx.params.id)
    if (!result.ok) {
      ctx.status = 400
      ctx.body = { success: false, error: result.error }
      return
    }
    ctx.body = { success: true, data: result }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[gerrit-review] cancel failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})
