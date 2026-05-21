import { tahpGet, tahpPost } from './client'

export interface ToolSchema {
  name: string
  description?: string
  inputSchema?: unknown
}

export function listTools(): Promise<{ tools: ToolSchema[] } | ToolSchema[]> {
  return tahpGet('/api/tahp/tools')
}

export function callTool<T = unknown>(name: string, args: Record<string, unknown>): Promise<T> {
  return tahpPost<T>(`/api/tahp/tools/${encodeURIComponent(name)}`, args)
}
