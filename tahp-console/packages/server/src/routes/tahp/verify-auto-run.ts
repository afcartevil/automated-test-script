/**
 * 验测任务自动执行（测试账号）— 本机状态查询与人工干预入口。
 * 执行逻辑在 services/tahp/verify-auto-run.ts；这里只做薄 HTTP 层。
 */
import Router from '@koa/router'
import {
  cancelVerifyAutoRunTask,
  getVerifyAutoRunStatus,
  isVerifyAutoRunEligible,
  setVerifyAutoRunEnabled,
  tickVerifyAutoRun,
} from '../../services/tahp/verify-auto-run'

export const tahpVerifyAutoRunRoutes = new Router()

tahpVerifyAutoRunRoutes.get('/api/tahp/verify-auto-run/status', async (ctx) => {
  ctx.body = { success: true, data: getVerifyAutoRunStatus() }
})

/** 暂停 / 恢复自动执行（仅影响本机，不改中心任务） */
tahpVerifyAutoRunRoutes.post('/api/tahp/verify-auto-run/enabled', async (ctx) => {
  const body = (ctx.request.body || {}) as { enabled?: unknown }
  const enabled = body.enabled !== false
  ctx.body = { success: true, data: setVerifyAutoRunEnabled(enabled) }
})

/** 取消某个验测任务的自动执行；正在跑则结束测试（刷机中会先杀刷机进程） */
tahpVerifyAutoRunRoutes.post('/api/tahp/verify-auto-run/tasks/:taskId/cancel', async (ctx) => {
  const result = await cancelVerifyAutoRunTask(ctx.params.taskId)
  if (!result.cancelled) {
    ctx.status = 404
    ctx.body = { success: false, error: result.error || '任务不在本机自动化列表' }
    return
  }
  ctx.body = { success: true, data: getVerifyAutoRunStatus() }
})

/** 手动触发一轮调度（排障用；正式节奏由内部定时器驱动） */
tahpVerifyAutoRunRoutes.post('/api/tahp/verify-auto-run/tick', async (ctx) => {
  const gate = isVerifyAutoRunEligible()
  if (!gate.eligible) {
    ctx.body = { success: true, data: { eligible: false, reason: gate.reason } }
    return
  }
  ctx.body = { success: true, data: await tickVerifyAutoRun() }
})
