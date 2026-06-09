/**
 * 域布局云端同步后端（可插拔）
 *
 * 环境变量：
 *   TAHP_ADAPT_LAYOUT_CLOUD_URL  — 云端 manifest 根 URL（GET/PUT 同一资源）
 *   TAHP_ADAPT_LAYOUT_CLOUD_TOKEN — Bearer Token（可选）
 */
import { logger } from '../../logger'
import type { AdaptLayoutManifest } from './types'

export function isAdaptLayoutCloudConfigured(): boolean {
  return !!String(process.env.TAHP_ADAPT_LAYOUT_CLOUD_URL || '').trim()
}

function cloudUrl(): string {
  const base = String(process.env.TAHP_ADAPT_LAYOUT_CLOUD_URL || '').trim().replace(/\/+$/, '')
  if (!base) throw new Error('TAHP_ADAPT_LAYOUT_CLOUD_URL 未配置')
  return `${base}/manifest.json`
}

function cloudHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  }
  const token = String(process.env.TAHP_ADAPT_LAYOUT_CLOUD_TOKEN || '').trim()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

/** 从云端拉取 manifest；未配置或 404 时返回 null */
export async function fetchCloudLayoutManifest(): Promise<AdaptLayoutManifest | null> {
  if (!isAdaptLayoutCloudConfigured()) return null
  const url = cloudUrl()
  try {
    const res = await fetch(url, { method: 'GET', headers: cloudHeaders() })
    if (res.status === 404) return null
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`云端拉取失败 HTTP ${res.status}: ${text.slice(0, 200)}`)
    }
    return (await res.json()) as AdaptLayoutManifest
  } catch (err) {
    logger.warn({ err, url }, '[adapt-layout-cloud] fetch failed')
    throw err
  }
}

/** 推送 manifest 到云端；返回云端 revision（响应头或 body） */
export async function pushCloudLayoutManifest(
  manifest: AdaptLayoutManifest,
): Promise<{ cloud_revision: string }> {
  if (!isAdaptLayoutCloudConfigured()) {
    return { cloud_revision: manifest.sync.cloud_revision || '' }
  }
  const url = cloudUrl()
  const res = await fetch(url, {
    method: 'PUT',
    headers: cloudHeaders(),
    body: JSON.stringify(manifest),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`云端推送失败 HTTP ${res.status}: ${text.slice(0, 200)}`)
  }
  let cloudRevision = res.headers.get('x-cloud-revision') || ''
  try {
    const body = (await res.json()) as { cloud_revision?: string; revision?: string }
    cloudRevision = body.cloud_revision || body.revision || cloudRevision
  } catch {
    // 空 body 也可接受
  }
  return { cloud_revision: cloudRevision || new Date().toISOString() }
}
