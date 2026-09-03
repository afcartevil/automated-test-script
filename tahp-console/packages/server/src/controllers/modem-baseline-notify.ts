import { logger } from '../services/logger'
import {
  extractModemNotifyToken,
  ingestModemBaselineNotice,
  resolveModemNotifyToken,
  verifyModemNotifyToken,
  type IngestModemNoticeInput,
} from '../services/tahp/modem-baseline-notices'

/**
 * Browser-friendly probe: this path is a POST API, not a webpage.
 */
export async function handleModemBaselineNotifyInfo(ctx: any) {
  const tokenConfigured = Boolean(resolveModemNotifyToken())
  ctx.status = 200
  ctx.body = {
    success: true,
    data: {
      endpoint: '/webhook/modem-baseline/notify',
      method: 'POST',
      auth: tokenConfigured
        ? 'Required: Authorization Bearer <MODEM_BASELINE_NOTIFY_TOKEN> or X-Modem-Notify-Token'
        : 'Optional (MODEM_BASELINE_NOTIFY_TOKEN not set)',
      note: '此地址不是网页。请用 POST 推送 JSON；浏览器打开仅用于探测接口是否存活。',
      example: {
        source: 'MergeTool',
        sourceId: 'baseline-job-001',
        trunk: 'tOS_mtk_A16_vnd_trunk.xml',
        newBaseline: 't-alps-release-b0.mp1.rc-V12.9.xml',
        oldBaseline: 't-alps-release-b0.mp1.rc-V11.9.xml',
      },
      fields: {
        source: '来源，默认 MergeTool',
        sourceId: '外部任务唯一 ID（建议，幂等）',
        trunk: '任务关联 manifest',
        newBaseline: '新基线 manifest',
        oldBaseline: '老基线 manifest',
      },
      displayText: [
        '任务：tOS_mtk_A16_vnd_trunk.xml 基线升级',
        '新基线：t-alps-release-b0.mp1.rc-V12.9.xml',
        '老基线：t-alps-release-b0.mp1.rc-V11.9.xml',
      ].join('\n'),
      afterNotify: '打开 Console → Modem升级 → 外部通知 → 采用并填入 → 启动基线升级 → 确认完成',
    },
  }
}

/**
 * Public ingest endpoint for baseline-complete notifications from MergeTool.
 * Does not start Modem 升级 — only enqueues a pending notice for operator confirmation.
 */
export async function handleModemBaselineNotify(ctx: any) {
  const token = extractModemNotifyToken(ctx.headers || {}, ctx.query?.token)
  if (!verifyModemNotifyToken(token)) {
    ctx.status = 401
    ctx.body = { success: false, error: 'Unauthorized' }
    return
  }

  const body = ctx.request.body
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    ctx.status = 400
    ctx.body = { success: false, error: 'invalid_body' }
    return
  }
  const input = body as IngestModemNoticeInput

  try {
    const result = ingestModemBaselineNotice(input)
    logger.info(
      'modem-baseline notify: %s source=%s sourceId=%s created=%s',
      result.notice.noticeId,
      result.notice.source,
      result.notice.sourceId || '-',
      result.created,
    )
    ctx.status = result.created ? 201 : 200
    ctx.body = {
      success: true,
      data: {
        noticeId: result.notice.noticeId,
        status: result.notice.status,
        text: result.notice.text,
        created: result.created,
      },
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = (message === 'notice_fields_required' || message === 'notice_text_required') ? 400 : 500
    ctx.body = { success: false, error: message }
  }
}
