/**
 * 域布局云端同步（按模块提交审核 / 拉取已发布版本）
 *
 * 环境变量：
 *   TAHP_ADAPT_LAYOUT_CLOUD_URL   — 远程服务根 URL（不含路径，如 http://host:8660）
 *   TAHP_ADAPT_LAYOUT_CLOUD_TOKEN — Bearer Token（可选）
 *
 * 远程路径前缀：{base}/api/v1/adapt-layouts
 */
import { logger } from '../../logger'
import { getLocalActor } from '../runtime-mode'
import type {
  AdaptLayoutReviewQuery,
  AdaptLayoutReviewState,
  AdaptLayoutSubmitResult,
  AdaptPublishedWorkspaceLayouts,
} from './types'

const REMOTE_PREFIX = '/api/v1/adapt-layouts'
const FETCH_TIMEOUT_MS = 8_000

export class AdaptLayoutCloudError extends Error {
  constructor(
    message: string,
    public httpStatus: number,
    public code?: string,
    public details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'AdaptLayoutCloudError'
  }
}

export function isAdaptLayoutCloudConfigured(): boolean {
  return !!String(process.env.TAHP_ADAPT_LAYOUT_CLOUD_URL || '').trim()
}

function cloudBase(): string {
  const base = String(process.env.TAHP_ADAPT_LAYOUT_CLOUD_URL || '').trim().replace(/\/+$/, '')
  if (!base) throw new Error('TAHP_ADAPT_LAYOUT_CLOUD_URL 未配置')
  return base
}

function cloudHeaders(hasJsonBody = false): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'x-tahp-actor': getLocalActor(),
  }
  if (hasJsonBody) headers['Content-Type'] = 'application/json'
  const token = String(process.env.TAHP_ADAPT_LAYOUT_CLOUD_TOKEN || '').trim()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

interface Envelope<T> {
  success?: boolean
  data?: T
  error?: string
}

async function cloudFetch<T>(
  path: string,
  init: RequestInit,
): Promise<{ status: number; data: T | null; error?: string; extra?: Record<string, unknown> }> {
  const url = `${cloudBase()}${REMOTE_PREFIX}${path}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { ...cloudHeaders(!!init.body), ...(init.headers as Record<string, string> || {}) },
    })
    const text = await res.text().catch(() => '')
    let body: Envelope<T> & Record<string, unknown> = {}
    if (text) {
      try {
        body = JSON.parse(text) as Envelope<T> & Record<string, unknown>
      } catch {
        body = {}
      }
    }
    const extra = (body.data && typeof body.data === 'object')
      ? (body.data as Record<string, unknown>)
      : undefined
    if (!res.ok || body.success === false) {
      return {
        status: res.status,
        data: null,
        error: body.error || `云端返回 HTTP ${res.status}`,
        extra,
      }
    }
    return { status: res.status, data: (body.data as T) ?? (body as unknown as T) }
  } catch (err) {
    const e = err as Error
    if (e?.name === 'AbortError') {
      throw new AdaptLayoutCloudError(`连接布局服务超时（${Math.round(FETCH_TIMEOUT_MS / 1000)}s）`, 504, 'TIMEOUT')
    }
    logger.warn({ err, url }, '[adapt-layout-cloud] request failed')
    throw new AdaptLayoutCloudError(e.message || '布局服务不可达', 502, 'UNREACHABLE')
  } finally {
    clearTimeout(timer)
  }
}

function throwCloud(status: number, error: string, extra?: Record<string, unknown>): never {
  const code = typeof extra?.code === 'string' ? extra.code : undefined
  throw new AdaptLayoutCloudError(error, status || 502, code, extra)
}

/** 拉取某工作区全部已发布布局 + 各模块审核状态 */
export async function fetchPublishedWorkspaceLayouts(
  workspaceId: string,
): Promise<AdaptPublishedWorkspaceLayouts | null> {
  if (!isAdaptLayoutCloudConfigured()) return null
  const result = await cloudFetch<AdaptPublishedWorkspaceLayouts>(
    `/workspaces/${encodeURIComponent(workspaceId)}/published`,
    { method: 'GET' },
  )
  if (result.status === 404) return { workspace_id: workspaceId, layouts: {}, reviews: {} }
  if (result.error) throwCloud(result.status, result.error, result.extra)
  const data = result.data
  if (!data || typeof data !== 'object') {
    return { workspace_id: workspaceId, layouts: {}, reviews: {} }
  }
  return {
    workspace_id: data.workspace_id || workspaceId,
    layouts: data.layouts && typeof data.layouts === 'object' ? data.layouts : {},
    reviews: data.reviews && typeof data.reviews === 'object' ? data.reviews : {},
  }
}

export async function fetchDomainReview(
  workspaceId: string,
  domainId: string,
): Promise<AdaptLayoutReviewQuery | null> {
  if (!isAdaptLayoutCloudConfigured()) return null
  const result = await cloudFetch<AdaptLayoutReviewQuery>(
    `/workspaces/${encodeURIComponent(workspaceId)}/domains/${encodeURIComponent(domainId)}/review`,
    { method: 'GET' },
  )
  if (result.status === 404) return null
  if (result.error) throwCloud(result.status, result.error, result.extra)
  return result.data
}

export async function submitDomainLayoutToCloud(input: {
  workspaceId: string
  domainId: string
  schemaVersion: number
  baseRevision: number
  fields: unknown
  relatedSkills: string[]
  comment?: string
}): Promise<AdaptLayoutSubmitResult> {
  if (!isAdaptLayoutCloudConfigured()) {
    throw new AdaptLayoutCloudError('未配置布局云端服务（TAHP_ADAPT_LAYOUT_CLOUD_URL）', 400, 'CLOUD_DISABLED')
  }
  const result = await cloudFetch<AdaptLayoutSubmitResult>(
    `/workspaces/${encodeURIComponent(input.workspaceId)}/domains/${encodeURIComponent(input.domainId)}/submit`,
    {
      method: 'POST',
      body: JSON.stringify({
        workspace_id: input.workspaceId,
        domain_id: input.domainId,
        schema_version: input.schemaVersion,
        base_revision: input.baseRevision,
        layout: {
          fields: input.fields,
          related_skills: input.relatedSkills,
        },
        comment: input.comment || '',
        submitted_by: getLocalActor(),
      }),
    },
  )
  if (result.error || !result.data) {
    throwCloud(result.status || 502, result.error || '提交审核失败', result.extra)
  }
  return result.data
}

export function reviewStateOrIdle(review?: AdaptLayoutReviewState | null): AdaptLayoutReviewState {
  if (!review || !review.status) return { status: 'idle' }
  return review
}
