/**
 * 飞书 checklist × SCMP 回写：/api/tahp/checklist-scmp-sync/*
 */
import Router from '@koa/router'
import {
  cancelChecklistScmpSync,
  getActiveChecklistScmpRun,
  getChecklistScmpRun,
  listChecklistScmpRuns,
  probeChecklistScmp,
  startChecklistScmpSync,
} from '../../services/tahp/checklist-scmp-sync'

export const tahpChecklistScmpSyncRoutes = new Router({ prefix: '/api/tahp/checklist-scmp-sync' })

function httpStatus(err: unknown): number {
  const status = (err as { status?: number }).status
  return typeof status === 'number' ? status : 500
}

tahpChecklistScmpSyncRoutes.get('/probe', async (ctx) => {
  ctx.body = { success: true, data: probeChecklistScmp() }
})

tahpChecklistScmpSyncRoutes.get('/runs', async (ctx) => {
  const limit = Number(ctx.query.limit || 20)
  ctx.body = {
    success: true,
    data: {
      active: getActiveChecklistScmpRun() || null,
      items: listChecklistScmpRuns(Number.isFinite(limit) ? limit : 20),
    },
  }
})

tahpChecklistScmpSyncRoutes.get('/runs/:runId', async (ctx) => {
  const run = getChecklistScmpRun(String(ctx.params.runId || ''))
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: '任务不存在' }
    return
  }
  ctx.body = { success: true, data: run }
})

tahpChecklistScmpSyncRoutes.post('/runs', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const url = typeof body.url === 'string' ? body.url : ''
  try {
    const data = await startChecklistScmpSync({ url })
    ctx.body = { success: true, data }
  } catch (error) {
    ctx.status = httpStatus(error)
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpChecklistScmpSyncRoutes.post('/runs/:runId/cancel', async (ctx) => {
  try {
    ctx.body = { success: true, data: cancelChecklistScmpSync(String(ctx.params.runId || '')) }
  } catch (error) {
    ctx.status = httpStatus(error)
    ctx.body = { success: false, error: (error as Error).message }
  }
})
