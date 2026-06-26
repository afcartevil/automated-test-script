/**
 * 本地写入收口：当本机为 local 且已配置中心时，
 * 新建条目/草稿在本地落盘的同时同步提交中心待审；审核类接口本地禁用（提示去中心后台）。
 *
 * 未配置中心（独立运行）时一切保持原行为，确保离线/单机可用。
 */
import type { Context } from 'koa'
import { isLocal, isCentralConfigured } from '../runtime-mode'

/** 是否应把新建内容同步到中心（local 且中心已配置） */
export function shouldRedirectWrites(): boolean {
  return isLocal() && isCentralConfigured()
}

/** 审核类接口在本地是否禁用（local 且中心已配置） */
export function isReviewDisabledLocally(): boolean {
  return isLocal() && isCentralConfigured()
}

/** 统一返回「请到中心后台操作」 */
export function respondReviewDisabled(ctx: Context): void {
  ctx.status = 409
  ctx.body = {
    success: false,
    error: '审核操作已集中到中心后台，请在中心管理界面处理。本地仅负责检索与执行。',
    code: 'REVIEW_CENTRALIZED',
  }
}
