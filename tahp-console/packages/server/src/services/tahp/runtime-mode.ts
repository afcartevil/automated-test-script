/**
 * TAHP 运行角色判定。
 * - local（默认）：研发本机。读本地副本；新建条目/草稿 push 到中心待审；审核接口禁用。
 * - central：权威源（由 easyadapter_bff 承担）。
 *
 * actor 取本机账号名，用于同步提交与审计对齐。
 */
import os from 'os'
import { config } from '../../config'

export function isLocal(): boolean {
  return config.tahp.role !== 'central'
}

export function isCentral(): boolean {
  return config.tahp.role === 'central'
}

/** 中心已配置（有基址 + token）才启用同步薄层 */
export function isCentralConfigured(): boolean {
  return !!(config.tahp.centralUrl && config.tahp.centralToken)
}

export interface RuntimeModeInfo {
  role: 'local' | 'central'
  central_configured: boolean
  central_url: string | null
}

export function getRuntimeModeInfo(): RuntimeModeInfo {
  return {
    role: config.tahp.role,
    central_configured: isCentralConfigured(),
    central_url: config.tahp.centralUrl || null,
  }
}

let cachedActor: string | null = null
export function getLocalActor(): string {
  if (cachedActor) return cachedActor
  try {
    const name = os.userInfo().username?.trim()
    cachedActor = name ? `${name}@${os.hostname()}` : `unknown@${os.hostname()}`
  } catch {
    cachedActor = 'unknown@local'
  }
  return cachedActor
}
