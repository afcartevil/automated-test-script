/**
 * 中心 BFF HTTP 客户端 — 自动携带共享 token 与本机 actor 头。
 */
import { config } from '../../../config'
import { getLocalActor } from '../runtime-mode'
import type { SyncManifest, PullPayload, SubmitPayload } from './manifest'

function base(): string {
  return config.tahp.centralUrl.replace(/\/+$/, '')
}

function headers(extra?: Record<string, string>): Record<string, string> {
  return {
    'x-tahp-token': config.tahp.centralToken,
    'x-tahp-actor': getLocalActor(),
    ...extra,
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${base()}${path}`, { ...init, signal: controller.signal })
    const json = (await res.json().catch(() => ({}))) as { success?: boolean; data?: T; error?: string }
    if (!res.ok || json.success === false) {
      throw new Error(json.error || `中心返回 ${res.status}`)
    }
    return json.data as T
  } finally {
    clearTimeout(timer)
  }
}

export const centralClient = {
  async ping(): Promise<{ pong: boolean; drafts_pending?: number }> {
    return request('/api/tahp/sync/ping', { headers: headers() })
  },

  async manifest(): Promise<SyncManifest> {
    return request('/api/tahp/sync/manifest', { headers: headers() })
  },

  async pull(since?: string): Promise<PullPayload> {
    const qs = since ? `?since=${encodeURIComponent(since)}` : ''
    return request(`/api/tahp/sync/pull${qs}`, { headers: headers() })
  },

  async submit(payload: SubmitPayload): Promise<{ id: string; action?: string }> {
    return request('/api/tahp/sync/submit', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify(payload),
    })
  },
}
