/**
 * TAHP API 客户端 — 复用 hermes/client.ts 的 fetch 风格.
 * 响应统一格式: { success: boolean, data?: T, error?: string }
 */
import { request as baseRequest } from '../client'

export interface ApiEnvelope<T = unknown> {
  success: boolean
  data?: T
  error?: string
}

export async function tahpRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await baseRequest<ApiEnvelope<T>>(path, options)
  if (!res.success) {
    throw new Error(res.error || 'TAHP 请求失败')
  }
  return (res.data as T) ?? (undefined as unknown as T)
}

export function tahpGet<T>(path: string): Promise<T> {
  return tahpRequest<T>(path, { method: 'GET' })
}

export function tahpPost<T>(path: string, body?: unknown): Promise<T> {
  return tahpRequest<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

export function tahpPut<T>(path: string, body?: unknown): Promise<T> {
  return tahpRequest<T>(path, {
    method: 'PUT',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}
