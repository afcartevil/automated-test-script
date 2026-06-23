/**
 * Gerrit 账号配置 API
 */
import { tahpGet, tahpPost } from './client'

export interface GerritConfigPublic {
  host: string
  user: string
  configured: boolean
  passwordSet: boolean
}

export interface SaveGerritConfigRequest {
  host?: string
  user: string
  password?: string
}

export function fetchGerritConfig(): Promise<GerritConfigPublic> {
  return tahpGet<GerritConfigPublic>('/api/tahp/gerrit-config')
}

export function saveGerritConfig(req: SaveGerritConfigRequest): Promise<GerritConfigPublic> {
  return tahpPost<GerritConfigPublic>('/api/tahp/gerrit-config/save', req)
}
