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

async function request<T>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${base()}${path}`, { ...init, signal: controller.signal })
    const json = (await res.json().catch(() => ({}))) as { success?: boolean; data?: T; error?: string }
    if (!res.ok || json.success === false) {
      throw new Error(json.error || `中心返回 ${res.status}`)
    }
    return json.data as T
  } catch (e) {
    const err = e as Error
    if (err?.name === 'AbortError') {
      throw new Error(`连接中心超时（${Math.round(timeoutMs / 1000)}s），请确认中心已启动且 ${base()} 可达`)
    }
    throw e
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
    return request(`/api/tahp/sync/pull${qs}`, { headers: headers() }, 120_000)
  },

  async submit(payload: SubmitPayload): Promise<{ id: string; action?: string }> {
    return request('/api/tahp/sync/submit', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify(payload),
    })
  },

  async downloadSkillPackage(id: string, packageUrl?: string): Promise<Buffer> {
    let url: string
    if (packageUrl?.startsWith('http')) url = packageUrl
    else if (packageUrl?.startsWith('/')) url = `${base()}${packageUrl}`
    else url = `${base()}/api/tahp/sync/skill/${encodeURIComponent(id)}/package`
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 120_000)
    try {
      const res = await fetch(url, { headers: headers(), signal: controller.signal })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(`下载 skill 包失败 ${res.status}: ${text}`)
      }
      const ab = await res.arrayBuffer()
      return Buffer.from(ab)
    } finally {
      clearTimeout(timer)
    }
  },

  async uploadSkillPackage(
    id: string,
    archive_b64: string,
    opts?: { message?: string; local_hash?: string },
  ): Promise<{
    id?: string
    hash: string
    files?: Array<{ rel_path: string }>
    file_count?: number
    submit_id?: string
    status?: string
  }> {
    return request(
      `/api/tahp/sync/skill/${encodeURIComponent(id)}/package/submit`,
      {
        method: 'POST',
        headers: headers({ 'content-type': 'application/json' }),
        body: JSON.stringify({
          archive_b64,
          message: opts?.message,
          local_hash: opts?.local_hash,
        }),
      },
      120_000,
    )
  },

  async latestSkillSubmission(id: string): Promise<{
    submit_id: string
    skill_id: string
    status: string
    hash: string
    comment?: string
    submitted_at?: string
    reviewed_at?: string
  } | null> {
    return request(`/api/tahp/sync/skill/${encodeURIComponent(id)}/submission/latest`, {
      headers: headers(),
    })
  },

  async skillHistory(id: string, limit = 50): Promise<{
    id: string
    commits: Array<{
      sha: string
      short_sha: string
      title: string
      author_name: string
      author_email: string
      committed_at: string
      message: string
      web_url?: string
    }>
  }> {
    return request(
      `/api/tahp/sync/skill/${encodeURIComponent(id)}/history?limit=${encodeURIComponent(String(limit))}`,
      { headers: headers() },
    )
  },

  async skillBundles(): Promise<{
    version: number
    bundles: Array<{ id: string; label: string; description?: string; skill_ids: string[]; updated_at: string }>
    auto_rules: Array<{ id: string; label?: string; func_type?: string; module?: string; id_prefix?: string }>
    updated_at: string
  }> {
    return request('/api/tahp/sync/skill-bundles', { headers: headers() })
  },
}
