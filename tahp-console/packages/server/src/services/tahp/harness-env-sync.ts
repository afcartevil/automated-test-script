/**
 * 一键配置表单 → ~/.tran_asf/env.yaml（优先）或 ~/.tran_harness/env.yaml 同步
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import yaml from 'js-yaml'
import { logger } from '../logger'
import type { UnifiedConfigValues } from './unified-config'

const HARNESS_JIRA_BASE_URL = 'http://jira.transsion.com'
const HARNESS_GERRIT_BASE_URL = 'https://gerrit.transsion.com'

/** harness env.yaml 模板默认值（表单未覆盖的项） */
export const HARNESS_ENV_TEMPLATE_DEFAULTS: Record<string, string> = {
  HARNESS_UPDATE_REGISTRY: 'https://artifact.transsion.com/artifactory/api/npm/tr-npm-releases/',
  HARNESS_UPDATE_CHANNEL: 'stable',
  HARNESS_QIZHI_USER: '',
  HARNESS_QIZHI_TARGET_HOST: '',
  HARNESS_QIZHI_TARGET_PASSWORD: '',
  HARNESS_QIZHI_BASTION_PASSWORD: '',
  HARNESS_QIZHI_SAMBA_PASSWORD: '',
  HARNESS_QIZHI_OTP_SECRET: '',
  HARNESS_MAP_DRIVE_ROOT: 'Z:\\',
  HARNESS_MAP_DRIVE_REMOTE_SHARE: '',
  HARNESS_MAP_DRIVE_PERSISTENT: 'true',
  HARNESS_MAP_DRIVE_STORE_CREDENTIAL: 'true',
  HARNESS_REMOTE_RUNNER_MAPPED_ROOT: 'Z:\\',
  HARNESS_REMOTE_RUNNER_REMOTE_WORKSPACE: '',
  HARNESS_REMOTE_RUNNER_APPROVED_ROOTS: '',
  OPEN_GROK_BASE_URL: 'https://androidxref.transsion.com',
  OPEN_GROK_USERNAME: '',
  OPEN_GROK_PASSWORD: '',
  HARNESS_SPUG_BASE_URL: 'http://spug.transsion.com',
  HARNESS_SPUG_USERNAME: '',
  HARNESS_SPUG_PASSWORD: '',
  HARNESS_BUILD_FEISHU_WEBHOOK_URL: '',
  HARNESS_BUILD_FEISHU_SIGN_SECRET: '',
  HARNESS_JIRA_BASE_URL,
  HARNESS_JIRA_USERNAME: '',
  HARNESS_JIRA_API_TOKEN: '',
  HARNESS_JIRA_AUTH_TYPE: 'basic',
  HARNESS_GERRIT_BASE_URL,
  HARNESS_GERRIT_CQ_BASE_URL: 'https://gerrit-cq.transsion.com',
  HARNESS_GERRIT_USERNAME: '',
  HARNESS_GERRIT_PASSWORD: '',
  HARNESS_GERRIT_AUTH_TYPE: 'form',
}

export function getHarnessEnvPath(homeDir = homedir()): string {
  const asf = join(homeDir, '.tran_asf', 'env.yaml')
  const legacy = join(homeDir, '.tran_harness', 'env.yaml')
  if (existsSync(join(homeDir, '.tran_asf')) || existsSync(asf)) return asf
  return legacy
}

export function hasHarnessRelatedUnifiedConfig(values: UnifiedConfigValues): boolean {
  const keys = [
    'domain_account',
    'domain_password',
    'linux_server_ip',
    'linux_server_password',
    'windows_map_drive',
    'qizhi_totp_secret',
  ]
  return keys.some(k => (values[k] || '').trim().length > 0)
}

function normalizeMapDriveRoot(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  if (/^[A-Za-z]:\\?$/.test(trimmed)) {
    const drive = trimmed[0].toUpperCase()
    return `${drive}:\\`
  }
  if (/^[A-Za-z]:\\/.test(trimmed)) {
    return trimmed.replace(/\\+$/, '') + '\\'
  }
  return trimmed
}

function parseHarnessEnvYaml(content: string): Record<string, string> {
  if (!content.trim()) return {}
  try {
    const doc = yaml.load(content) as Record<string, unknown> | null
    if (!doc || typeof doc !== 'object') return {}
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(doc)) {
      if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
        out[k] = String(v)
      }
    }
    return out
  } catch {
    return {}
  }
}

export function readHarnessEnvFile(envPath = getHarnessEnvPath()): Record<string, string> {
  if (!existsSync(envPath)) return {}
  try {
    return parseHarnessEnvYaml(readFileSync(envPath, 'utf-8'))
  } catch {
    return {}
  }
}

/** 从一键配置表单值构建 harness env.yaml 覆盖项 */
export function buildHarnessEnvOverrides(values: UnifiedConfigValues): Record<string, string> {
  const overrides: Record<string, string> = {}
  const account = (values.domain_account || '').trim()
  const password = (values.domain_password || '').trim()
  const host = (values.linux_server_ip || '').trim()
  const linuxPassword = (values.linux_server_password || '').trim()
  const mapDrive = normalizeMapDriveRoot(values.windows_map_drive || '')
  const totpSecret = (values.qizhi_totp_secret || '').trim().replace(/\s+/g, '')

  if (account) {
    overrides.HARNESS_QIZHI_USER = account
    overrides.OPEN_GROK_USERNAME = account
    overrides.HARNESS_SPUG_USERNAME = account
    overrides.HARNESS_JIRA_USERNAME = account
    overrides.HARNESS_GERRIT_USERNAME = account
  }
  if (password) {
    overrides.HARNESS_QIZHI_BASTION_PASSWORD = password
    overrides.OPEN_GROK_PASSWORD = password
    overrides.HARNESS_SPUG_PASSWORD = password
    overrides.HARNESS_JIRA_API_TOKEN = password
    overrides.HARNESS_GERRIT_PASSWORD = password
  }
  if (host) {
    overrides.HARNESS_QIZHI_TARGET_HOST = host
    if (account) {
      overrides.HARNESS_MAP_DRIVE_REMOTE_SHARE = `\\\\${host}\\${account}`
    }
  }
  if (linuxPassword) {
    overrides.HARNESS_QIZHI_TARGET_PASSWORD = linuxPassword
    overrides.HARNESS_QIZHI_SAMBA_PASSWORD = linuxPassword
  }
  if (mapDrive) {
    overrides.HARNESS_MAP_DRIVE_ROOT = mapDrive
    overrides.HARNESS_REMOTE_RUNNER_MAPPED_ROOT = mapDrive
  }
  if (totpSecret) {
    overrides.HARNESS_QIZHI_OTP_SECRET = totpSecret
  }

  return overrides
}

export function mergeHarnessEnvConfig(
  values: UnifiedConfigValues,
  existing: Record<string, string> = {},
): Record<string, string> {
  const merged: Record<string, string> = { ...HARNESS_ENV_TEMPLATE_DEFAULTS, ...existing }
  const overrides = buildHarnessEnvOverrides(values)
  for (const [k, v] of Object.entries(overrides)) {
    if (v.trim()) merged[k] = v
  }
  return merged
}

export interface SyncHarnessEnvResult {
  path: string
  synced: boolean
  keysWritten: number
}

/** 将一键配置表单中 asf/harness 相关项同步到 env.yaml */
export function syncHarnessEnvFromUnifiedConfig(
  values: UnifiedConfigValues,
  opts?: { envPath?: string; homeDir?: string },
): SyncHarnessEnvResult {
  const envPath = opts?.envPath ?? getHarnessEnvPath(opts?.homeDir)
  if (!hasHarnessRelatedUnifiedConfig(values)) {
    return { path: envPath, synced: false, keysWritten: 0 }
  }

  const existing = readHarnessEnvFile(envPath)
  const merged = mergeHarnessEnvConfig(values, existing)
  const dir = join(envPath, '..')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })

  const body = yaml.dump(merged, { lineWidth: -1, noRefs: true, sortKeys: false })
  writeFileSync(envPath, body, 'utf-8')
  logger.info({ path: envPath }, '[harness-env-sync] 已同步 harness env.yaml')

  const home = opts?.homeDir ?? homedir()
  const alt = envPath.replace(/\.tran_asf\\env\.yaml$/i, '.tran_harness\\env.yaml')
    .replace(/\.tran_asf\/env\.yaml$/i, '.tran_harness/env.yaml')
  const alt2 = envPath.replace(/\.tran_harness\\env\.yaml$/i, '.tran_asf\\env.yaml')
    .replace(/\.tran_harness\/env\.yaml$/i, '.tran_asf/env.yaml')
  for (const extra of [alt, alt2]) {
    if (extra === envPath) continue
    const extraDir = join(extra, '..')
    if (existsSync(extraDir)) {
      writeFileSync(extra, body, 'utf-8')
    }
  }

  return { path: envPath, synced: true, keysWritten: Object.keys(merged).length }
}
