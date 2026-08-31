import { logger } from '../services/logger'
import {
  extractGkiNotifyToken,
  ingestGkiUpgradeNotice,
  resolveGkiNotifyToken,
  verifyGkiNotifyToken,
  type IngestGkiNoticeInput,
} from '../services/tahp/gki-upgrade-notices'

/** Browser-friendly probe for the POST notify endpoint. */
export async function handleGkiUpgradeNotifyInfo(ctx: any) {
  const tokenConfigured = Boolean(resolveGkiNotifyToken())
  ctx.status = 200
  ctx.body = {
    success: true,
    data: {
      endpoint: '/webhook/gki-upgrade/notify',
      method: 'POST',
      auth: tokenConfigured
        ? 'Required: Authorization Bearer <GKI_UPGRADE_NOTIFY_TOKEN> or X-Gki-Notify-Token'
        : 'Optional (GKI_UPGRADE_NOTIFY_TOKEN not set)',
      note: '此地址不是网页。请用 POST 推送 JSON；浏览器打开仅用于探测接口是否存活。',
      example: {
        source: 'tones',
        sourceId: 'gki-job-001',
        text: '本次GKI升级从android13-5.15-2025-09_r9升级到android13-5.15-2026-03_r16',
        from_tag: 'android13-5.15-2025-09_r9',
        to_tag: 'android13-5.15-2026-03_r16',
        task_kind: 'analysis',
      },
      afterNotify: '打开 Console → GKI → 工作台 → 外部通知 → 采用并填入 → 前往分析 → 确认完成',
    },
  }
}

/**
 * Public ingest for GKI upgrade notices (TONES / debug).
 * Does not start upgrade — only enqueues a pending notice.
 */
export async function handleGkiUpgradeNotify(ctx: any) {
  const token = extractGkiNotifyToken(ctx.headers || {}, ctx.query?.token)
  if (!verifyGkiNotifyToken(token)) {
    ctx.status = 401
    ctx.body = { success: false, error: 'Unauthorized' }
    return
  }

  const body = ctx.request.body
  let input: IngestGkiNoticeInput | string
  if (typeof body === 'string') {
    input = body
  } else if (body && typeof body === 'object') {
    input = body as IngestGkiNoticeInput
  } else {
    ctx.status = 400
    ctx.body = { success: false, error: 'invalid_body' }
    return
  }

  try {
    const result = ingestGkiUpgradeNotice(input)
    logger.info(
      'gki-upgrade notify: %s source=%s sourceId=%s created=%s from=%s to=%s',
      result.notice.noticeId,
      result.notice.source,
      result.notice.sourceId || '-',
      result.created,
      result.notice.fromTag || '-',
      result.notice.toTag || '-',
    )
    ctx.status = result.created ? 201 : 200
    ctx.body = {
      success: true,
      data: {
        noticeId: result.notice.noticeId,
        status: result.notice.status,
        text: result.notice.text,
        fromTag: result.notice.fromTag,
        toTag: result.notice.toTag,
        created: result.created,
      },
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'notice_text_required' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
}
