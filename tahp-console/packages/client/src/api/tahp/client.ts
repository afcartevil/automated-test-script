/**
 * TAHP API 客户端 — 复用 hermes/client.ts 的 fetch 风格.
 * 响应统一格式: { success: boolean, data?: T, error?: string }
 */
import { clearApiKey, getApiKey, getBaseUrlValue } from '../client'
import router from '@/router'

export interface ApiEnvelope<T = unknown> {
  success: boolean
  data?: T
  error?: string
}

async function tahpFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${getBaseUrlValue()}${path}`
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  const apiKey = getApiKey()
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`
  }

  const res = await fetch(url, { ...options, headers })
  const text = await res.text().catch(() => '')

  let body: ApiEnvelope<T> | null = null
  if (text) {
    try {
      body = JSON.parse(text) as ApiEnvelope<T>
    } catch {
      body = null
    }
  }

  if (res.status === 401) {
    clearApiKey()
    if (router.currentRoute.value.name !== 'login') {
      router.replace({ name: 'login' })
    }
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    throw new Error(body?.error || `API Error ${res.status}`)
  }

  if (!body?.success) {
    throw new Error(body?.error || 'TAHP 请求失败')
  }

  return (body.data as T) ?? (undefined as unknown as T)
}

export async function tahpRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return tahpFetch<T>(path, options)
}

export function tahpGet<T>(path: string, options: RequestInit = {}): Promise<T> {
  return tahpRequest<T>(path, { ...options, method: 'GET' })
}

export function tahpPost<T>(path: string, body?: unknown, options: RequestInit = {}): Promise<T> {
  return tahpRequest<T>(path, {
    ...options,
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

export function tahpPut<T>(path: string, body?: unknown, options: RequestInit = {}): Promise<T> {
  return tahpRequest<T>(path, {
    ...options,
    method: 'PUT',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

export function tahpDelete<T>(path: string, options: RequestInit = {}): Promise<T> {
  return tahpRequest<T>(path, { ...options, method: 'DELETE' })
}
