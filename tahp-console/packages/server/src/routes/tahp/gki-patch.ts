import Router from '@koa/router'
import {
  ensureGkiPatchServer,
  getGkiPatchDefaults,
  getGkiPatchStatusAsync,
  listGkiAnalysisTasks,
  listGkiUpgradeJobs,
} from '../../services/tahp/gki-patch'
import {
  listGkiUpgradeNotices,
  parseGkiUpgradeNotice,
  updateGkiUpgradeNoticeStatus,
} from '../../services/tahp/gki-upgrade-notices'

export const tahpGkiPatchRoutes = new Router({ prefix: '/api/tahp/gki-patch' })

tahpGkiPatchRoutes.get('/defaults', async (ctx) => {
  try {
    ctx.body = { success: true, data: getGkiPatchDefaults() }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.get('/status', async (ctx) => {
  try {
    ctx.body = { success: true, data: await getGkiPatchStatusAsync() }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.post('/start', async (ctx) => {
  try {
    const data = await ensureGkiPatchServer()
    ctx.body = { success: true, data }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.get('/upgrade-jobs', async (ctx) => {
  try {
    const limit = Number(ctx.query.limit || 50)
    ctx.body = { success: true, data: { jobs: await listGkiUpgradeJobs(limit) } }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.get('/analysis-tasks', async (ctx) => {
  try {
    const limit = Number(ctx.query.limit || 50)
    ctx.body = { success: true, data: { tasks: await listGkiAnalysisTasks(limit) } }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpGkiPatchRoutes.get('/notices', async (ctx) => {
  const statusRaw = String(ctx.query.status || 'pending').trim()
  const status = (statusRaw === 'all' || statusRaw === 'pending' || statusRaw === 'applied' || statusRaw === 'dismissed')
    ? statusRaw
    : 'pending'
  ctx.body = { success: true, data: { items: listGkiUpgradeNotices({ status }) } }
})

tahpGkiPatchRoutes.post('/notices/:noticeId/apply', async (ctx) => {
  try {
    ctx.body = {
      success: true,
      data: updateGkiUpgradeNoticeStatus(ctx.params.noticeId, 'applied'),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'notice_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpGkiPatchRoutes.post('/notices/:noticeId/dismiss', async (ctx) => {
  try {
    ctx.body = {
      success: true,
      data: updateGkiUpgradeNoticeStatus(ctx.params.noticeId, 'dismissed'),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'notice_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpGkiPatchRoutes.post('/parse-notice', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as {
      text?: string
      fromTag?: string
      toTag?: string
      from_tag?: string
      to_tag?: string
      taskKind?: string
      task_kind?: string
      notice_type?: string
      intent?: string
    }
    ctx.body = {
      success: true,
      data: parseGkiUpgradeNotice(String(body.text ?? ''), {
        fromTag: body.fromTag || body.from_tag,
        toTag: body.toTag || body.to_tag,
        taskKind: body.taskKind,
        task_kind: body.task_kind,
        notice_type: body.notice_type,
        intent: body.intent,
      }),
    }
  } catch (error) {
    ctx.status = 400
    ctx.body = { success: false, error: (error as Error).message }
  }
})
