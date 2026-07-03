import Router from '@koa/router'
import {
  createModemBaselineRun,
  continueModemBaselineRun,
  getModemBaselineDefaults,
  listModemBaselineRuns,
  openModemBaselineConflictFile,
  readModemBaselineLog,
  readModemBaselineRun,
  refreshModemBaselineConflicts,
  registerModemBaselineSseClient,
  unregisterModemBaselineSseClient,
} from '../../services/tahp/modem-baseline'

export const tahpModemBaselineRoutes = new Router({ prefix: '/api/tahp/modem-baseline' })

tahpModemBaselineRoutes.get('/defaults', async (ctx) => {
  try {
    ctx.body = { success: true, data: getModemBaselineDefaults() }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpModemBaselineRoutes.get('/runs', async (ctx) => {
  ctx.body = { success: true, data: listModemBaselineRuns() }
})

tahpModemBaselineRoutes.get('/runs/:runId', async (ctx) => {
  const meta = readModemBaselineRun(ctx.params.runId)
  if (!meta) {
    ctx.status = 404
    ctx.body = { success: false, error: 'not_found' }
    return
  }
  ctx.body = { success: true, data: meta }
})

tahpModemBaselineRoutes.get('/runs/:runId/log', async (ctx) => {
  const meta = readModemBaselineRun(ctx.params.runId)
  if (!meta?.logPath) {
    ctx.status = 404
    ctx.body = { success: false, error: 'not_found' }
    return
  }
  ctx.body = { success: true, data: { content: readModemBaselineLog(ctx.params.runId) } }
})

tahpModemBaselineRoutes.get('/runs/:runId/events', async (ctx) => {
  try {
    const runId = ctx.params.runId
    ctx.set({
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    })
    ctx.status = 200
    ctx.respond = false

    const res = ctx.res as any
    registerModemBaselineSseClient(runId, res)

    const keepAlive = setInterval(() => {
      try {
        res.write(': keepalive\n\n')
      } catch {
        clearInterval(keepAlive)
        unregisterModemBaselineSseClient(runId, res)
      }
    }, 15000)

    ctx.req.on('close', () => {
      clearInterval(keepAlive)
      unregisterModemBaselineSseClient(runId, res)
    })
  } catch (error) {
    ctx.status = 404
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpModemBaselineRoutes.post('/runs', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { config?: unknown }
    ctx.body = { success: true, data: createModemBaselineRun(body.config) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_config' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/continue', async (ctx) => {
  try {
    ctx.body = { success: true, data: continueModemBaselineRun(ctx.params.runId) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found'
      ? 404
      : message === 'running'
        ? 409
        : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/refresh-conflicts', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { autoStageResolved?: boolean }
    ctx.body = {
      success: true,
      data: await refreshModemBaselineConflicts(ctx.params.runId, body.autoStageResolved !== false),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/open-conflict-file', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { file?: string }
    ctx.body = {
      success: true,
      data: openModemBaselineConflictFile(ctx.params.runId, body.file || ''),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found' || message === 'file_not_found'
      ? 404
      : 400
    ctx.body = { success: false, error: message }
  }
})
