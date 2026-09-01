/**
 * 射频校准 MetaCLI REST：/api/tahp/rf-calib-meta/*
 */
import Router from '@koa/router'
import {
  cancelRfCalibMeta,
  getRfCalibMetaRunDetail,
  listRfCalibMetaRunSummaries,
  probeRfCalibMeta,
  recoverRfCalibMetaRuns,
  startRfCalibMeta,
} from '../../services/tahp/rf-calib-meta'
import type { RfCalibMetaConnectionStrategy, RfCalibMetaMode } from '../../services/tahp/rf-calib-meta'

export const tahpRfCalibMetaRoutes = new Router({ prefix: '/api/tahp/rf-calib-meta' })

try {
  recoverRfCalibMetaRuns()
} catch {
  /* ignore */
}

tahpRfCalibMetaRoutes.get('/probe', async (ctx) => {
  const result = await probeRfCalibMeta()
  ctx.body = { success: true, data: result }
})

tahpRfCalibMetaRoutes.get('/runs', async (ctx) => {
  const limit = Number(ctx.query.limit || 50)
  ctx.body = {
    success: true,
    data: listRfCalibMetaRunSummaries(Number.isFinite(limit) ? limit : 50),
  }
})

tahpRfCalibMetaRoutes.get('/runs/:runId', async (ctx) => {
  const run = getRfCalibMetaRunDetail(String(ctx.params.runId || ''))
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: '任务不存在' }
    return
  }
  ctx.body = { success: true, data: run }
})

tahpRfCalibMetaRoutes.post('/runs', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const modeRaw = String(body.mode || '').trim()
  const mode: RfCalibMetaMode = modeRaw === 'restore' ? 'restore' : 'backup'
  const calFilePath = typeof body.cal_file_path === 'string'
    ? body.cal_file_path
    : typeof body.calFilePath === 'string'
      ? body.calFilePath
      : ''
  const itemsIniPath = typeof body.items_ini_path === 'string'
    ? body.items_ini_path
    : typeof body.itemsIniPath === 'string'
      ? body.itemsIniPath
      : ''
  const outputCalPath = typeof body.output_cal_path === 'string'
    ? body.output_cal_path
    : typeof body.outputCalPath === 'string'
      ? body.outputCalPath
      : undefined
  const comPort = typeof body.com_port === 'string'
    ? body.com_port
    : typeof body.comPort === 'string'
      ? body.comPort
      : undefined
  const label = typeof body.label === 'string' ? body.label : undefined
  const connRaw = String(body.connection_strategy || body.connectionStrategy || '').trim()
  const connectionStrategy: RfCalibMetaConnectionStrategy | undefined =
    connRaw === 'meta_port' ? 'meta_port'
      : connRaw === 'adb_reboot_meta' ? 'adb_reboot_meta'
        : connRaw === 'preloader_boot' ? 'preloader_boot'
          : undefined

  const result = await startRfCalibMeta({
    mode,
    calFilePath,
    itemsIniPath,
    outputCalPath,
    comPort,
    label,
    connectionStrategy,
  })
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { run_id: result.run_id } }
})

tahpRfCalibMetaRoutes.post('/runs/:runId/cancel', async (ctx) => {
  const result = await cancelRfCalibMeta(String(ctx.params.runId || ''))
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: result.error }
    return
  }
  ctx.body = { success: true, data: { ok: true } }
})
