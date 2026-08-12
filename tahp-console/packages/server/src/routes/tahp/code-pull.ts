/**
 * 代码拉取 REST：/api/tahp/code-pull/*
 */
import Router from '@koa/router'
import {
  cancelCodePull,
  getCodePullRunDetail,
  listCodePullRunSummaries,
  probeCodePull,
  recoverCodePullRuns,
  startCodePull,
} from '../../services/tahp/code-pull'

export const tahpCodePullRoutes = new Router({ prefix: '/api/tahp/code-pull' })

try {
  recoverCodePullRuns()
} catch {
  /* ignore */
}

tahpCodePullRoutes.get('/probe', async (ctx) => {
  const result = await probeCodePull()
  ctx.body = { success: true, data: result }
})

tahpCodePullRoutes.get('/runs', async (ctx) => {
  const limit = Number(ctx.query.limit || 50)
  ctx.body = { success: true, data: listCodePullRunSummaries(Number.isFinite(limit) ? limit : 50) }
})

tahpCodePullRoutes.get('/runs/:runId', async (ctx) => {
  const run = getCodePullRunDetail(String(ctx.params.runId || ''))
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: '任务不存在' }
    return
  }
  ctx.body = { success: true, data: run }
})

tahpCodePullRoutes.post('/runs', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const systemInit = typeof body.system_repo_init === 'string'
    ? body.system_repo_init
    : typeof body.systemRepoInit === 'string'
      ? body.systemRepoInit
      : ''
  const vendorInit = typeof body.vendor_repo_init === 'string'
    ? body.vendor_repo_init
    : typeof body.vendorRepoInit === 'string'
      ? body.vendorRepoInit
      : ''
  const result = await startCodePull({
    system_repo_init: systemInit,
    vendor_repo_init: vendorInit,
    mapped_root: typeof body.mapped_root === 'string' ? body.mapped_root : undefined,
  })
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { run_id: result.run_id } }
})

tahpCodePullRoutes.post('/runs/:runId/cancel', async (ctx) => {
  const result = await cancelCodePull(String(ctx.params.runId || ''))
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { ok: true } }
})
