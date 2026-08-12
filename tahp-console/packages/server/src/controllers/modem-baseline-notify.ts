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
        source: 'tones',
        sourceId: 'baseline-job-001',
        text: '7月基线升级 GEN99-V V11.35',
        platform: 'GEN99-V',
        version: 'V11.35',
      },
      afterNotify: '打开 Console → Modem升级 → 外部通知 → 采用并填入 → 启动基线升级 → 确认完成',
    },
  }
}

/**
 * Public ingest endpoint for baseline-complete notifications from TONES / other tools.
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
  let input: IngestModemNoticeInput | string
  if (typeof body === 'string') {
    input = body
  } else if (body && typeof body === 'object') {
    input = body as IngestModemNoticeInput
  } else {
    ctx.status = 400
    ctx.body = { success: false, error: 'invalid_body' }
    return
  }

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
    ctx.status = message === 'notice_text_required' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
}
