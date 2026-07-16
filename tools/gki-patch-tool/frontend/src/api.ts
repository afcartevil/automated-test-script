export type ApiPayload = Record<string, unknown>

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init.headers || {}),
    },
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      detail = await response.text()
    }
    throw new Error(detail)
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json() as Promise<T>
  }
  return response.text() as Promise<T>
}

export const api = {
  get: <T = any>(url: string) => request<T>(url),
  post: <T = any>(url: string, body: ApiPayload = {}) =>
    request<T>(url, { method: 'POST', body: JSON.stringify(body) }),
  put: <T = any>(url: string, body: ApiPayload = {}) =>
    request<T>(url, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T = any>(url: string) => request<T>(url, { method: 'DELETE' }),
}

export function wsUrl(path: string) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}${path}`
}

export function formatDate(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function formatElapsed(seconds?: number | string | null) {
  const value = Number(seconds ?? NaN)
  if (!Number.isFinite(value) || value < 0) return ''
  const total = Math.round(value)
  if (total < 60) return `${total}秒`
  const minutes = Math.floor(total / 60)
  const remainSec = total % 60
  if (minutes < 60) {
    return remainSec > 0 ? `${minutes}分${remainSec}秒` : `${minutes}分`
  }
  const hours = Math.floor(minutes / 60)
  const remainMin = minutes % 60
  return `${hours}时${remainMin}分${remainSec}秒`
}

export function shortId(value?: string, size = 10) {
  if (!value) return '-'
  return value.length > size ? value.slice(0, size) : value
}

export function scoreClass(score: number | string | undefined) {
  const value = Number(score || 0)
  if (value >= 80) return 'score-high'
  if (value >= 60) return 'score-mid'
  return 'score-low'
}

export function statusTone(status?: string) {
  const normalized = (status || '').toLowerCase()
  if (['completed', 'done', 'committed', 'applied'].includes(normalized)) return 'success'
  if (['failed', 'conflicts', 'build_failed', 'commit_failed'].includes(normalized)) return 'danger'
  if (['cancelled', 'aborted'].includes(normalized)) return 'muted'
  if (['build_fix', 'awaiting_ssh', 'awaiting_otp', 'monthly_recommendation'].includes(normalized)) return 'info'
  if (normalized.includes('running') || normalized.includes('analyzing')) return 'info'
  return 'warning'
}
