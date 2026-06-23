/**
 * TAHP — Gerrit 凭证存储（Console 设置页配置，供 Gerrit Code Review Agent 使用）
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'
import { safeFileStore } from '../safe-file-store'
import { tahpPaths } from './paths'

export const DEFAULT_GERRIT_HOST = 'https://gerrit.transsion.com'

export interface GerritConfig {
  host: string
  user: string
  password: string
}

export interface GerritConfigPublic {
  host: string
  user: string
  configured: boolean
  passwordSet: boolean
}

export interface SaveGerritConfigInput {
  host?: string
  user: string
  password?: string
}

function configDir(): string {
  if (process.env.TAHP_GERRIT_CONFIG_DIR) {
    return resolve(process.env.TAHP_GERRIT_CONFIG_DIR)
  }
  return join(tahpPaths.projectRoot, '.tahp-config')
}

export function gerritConfigPath(): string {
  return join(configDir(), 'gerrit.json')
}

export function gerritRuntimeCredPath(): string {
  return join(configDir(), 'gerrit-cred.runtime.json')
}

function normalizeHost(host: string | undefined): string {
  return String(host || DEFAULT_GERRIT_HOST).trim().replace(/\/+$/, '') || DEFAULT_GERRIT_HOST
}

function ensureConfigDir(): void {
  const dir = configDir()
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

function readConfigSync(): GerritConfig | null {
  const path = gerritConfigPath()
  if (!existsSync(path)) return null
  try {
    const raw = readFileSync(path, 'utf-8')
    const data = JSON.parse(raw) as Partial<GerritConfig>
    return {
      host: normalizeHost(data.host),
      user: String(data.user || '').trim(),
      password: String(data.password || '').trim(),
    }
  } catch {
    return null
  }
}

export function getGerritConfig(): GerritConfig | null {
  const cfg = readConfigSync()
  if (!cfg) return null
  return cfg
}

export function toGerritConfigPublic(cfg: GerritConfig | null): GerritConfigPublic {
  const host = cfg?.host ? normalizeHost(cfg.host) : DEFAULT_GERRIT_HOST
  const user = cfg?.user?.trim() || ''
  const passwordSet = Boolean(cfg?.password?.trim())
  return {
    host,
    user,
    configured: Boolean(user && passwordSet),
    passwordSet,
  }
}

export function getGerritConfigPublic(): GerritConfigPublic {
  return toGerritConfigPublic(getGerritConfig())
}

export function isGerritConfigured(): boolean {
  const cfg = getGerritConfig()
  return Boolean(cfg?.user?.trim() && cfg?.password?.trim())
}

export async function saveGerritConfig(input: SaveGerritConfigInput): Promise<GerritConfigPublic> {
  const user = String(input.user || '').trim()
  if (!user) {
    throw new Error('Gerrit 账号不能为空')
  }

  const existing = getGerritConfig()
  const password = String(input.password || '').trim() || existing?.password || ''
  if (!password) {
    throw new Error('Gerrit HTTP Password 不能为空')
  }

  const config: GerritConfig = {
    host: normalizeHost(input.host ?? existing?.host),
    user,
    password,
  }

  ensureConfigDir()
  await safeFileStore.writeText(gerritConfigPath(), JSON.stringify(config, null, 2))
  return toGerritConfigPublic(config)
}

export function writeRuntimeCredFile(): string {
  const cfg = getGerritConfig()
  if (!cfg?.user?.trim() || !cfg?.password?.trim()) {
    throw new Error('Gerrit 凭证未配置')
  }

  ensureConfigDir()
  const path = resolve(gerritRuntimeCredPath())
  const payload = {
    host: normalizeHost(cfg.host),
    user: cfg.user.trim(),
    password: cfg.password.trim(),
  }
  writeFileSync(path, JSON.stringify(payload, null, 2), 'utf-8')
  return path
}
