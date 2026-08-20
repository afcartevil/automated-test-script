/**
 * Console 页面 JIRA 凭据（智能诊断弹窗 localStorage 的服务端镜像）
 *
 * 落盘：{TAHP工程根}/.tahp/jira-user-config.json
 * 优先级（resolveJiraConfig）：请求头覆盖 > 本文件 > TAHP_JIRA_* 环境变量
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'
import { getJiraWorkspaceRoot } from './jira-workspace'
import { getJiraConfig, type JiraConfig } from './jira'

export interface JiraUserConfigRecord {
  username: string
  password: string
  base_url?: string
  updated_at?: string
}

function tahpConfigDir(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function jiraUserConfigPath(): string {
  return join(tahpConfigDir(), 'jira-user-config.json')
}

function readUnifiedDomainCredentials(): { username: string; password: string } | null {
  const p = join(tahpConfigDir(), 'unified-config.json')
  if (!existsSync(p)) return null
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const username = String(raw.domain_account || '').trim()
    const password = String(raw.domain_password || '')
    if (!username) return null
    return { username, password }
  } catch {
    return null
  }
}

export function readJiraUsername(): string | undefined {
  const p = jiraUserConfigPath()
  if (existsSync(p)) {
    try {
      const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
      const username = String(raw.username || '').trim()
      if (username) return username
    } catch {
      /* fall through to unified-config */
    }
  }
  return readUnifiedDomainCredentials()?.username
}

/** 若只有一键配置、尚未派生 jira-user-config，则补写一份（供 bind / 在线通道使用） */
export function ensureDerivedJiraUserConfig(): JiraUserConfigRecord | null {
  const existing = readJiraUserConfig()
  if (existing) return existing
  const fromUnified = readUnifiedDomainCredentials()
  if (!fromUnified?.password) return null
  try {
    return writeJiraUserConfig(fromUnified)
  } catch {
    return null
  }
}

export function readJiraUserConfig(): JiraUserConfigRecord | null {
  const p = jiraUserConfigPath()
  if (!existsSync(p)) return null
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const username = String(raw.username || '').trim()
    const password = String(raw.password || '')
    if (!username || !password) return null
    const baseUrl = String(raw.base_url || raw.baseUrl || '').trim()
    return {
      username,
      password,
      base_url: baseUrl || undefined,
      updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : undefined,
    }
  } catch {
    return null
  }
}

export function writeJiraUserConfig(input: {
  username: string
  password: string
  baseUrl?: string
}): JiraUserConfigRecord {
  const username = input.username.trim()
  const password = input.password
  if (!username || !password) {
    throw new Error('JIRA 用户名和密码不能为空')
  }
  const record: JiraUserConfigRecord = {
    username,
    password,
    base_url: (input.baseUrl || process.env.TAHP_JIRA_BASE_URL || 'http://jira.transsion.com')
      .replace(/\/+$/, ''),
    updated_at: new Date().toISOString(),
  }
  writeFileSync(jiraUserConfigPath(), JSON.stringify(record, null, 2), 'utf-8')
  return record
}

/** 合并凭据：override（请求头）> 页面同步文件 > 环境变量 */
export function resolveJiraConfig(override?: Partial<JiraConfig> | null): JiraConfig {
  const envCfg = getJiraConfig()
  const stored = readJiraUserConfig()
  const cfg: JiraConfig = {
    baseUrl: envCfg.baseUrl,
    username: envCfg.username,
    password: envCfg.password,
    token: envCfg.token,
    cookie: envCfg.cookie,
  }
  if (stored) {
    if (stored.base_url) cfg.baseUrl = stored.base_url
    cfg.username = stored.username
    cfg.password = stored.password
  }
  if (override?.baseUrl) cfg.baseUrl = override.baseUrl.replace(/\/+$/, '')
  if (override?.username) cfg.username = override.username
  if (override?.password) cfg.password = override.password
  if (override?.token) cfg.token = override.token
  if (override?.cookie) cfg.cookie = override.cookie
  return cfg
}

export function hasJiraBasicCredentials(cfg: JiraConfig): boolean {
  return Boolean(cfg.username?.trim() && cfg.password)
}

export function applyJiraUserConfigToEnv(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {
    ...env,
    TAHP_PROJECT_ROOT: tahpPaths.projectRoot,
    WORKSPACE_ROOT: getJiraWorkspaceRoot().replace(/\\/g, '/'),
  }
  const cfg = resolveJiraConfig()
  if (cfg.baseUrl) out.JIRA_SERVER = cfg.baseUrl
  if (cfg.username) out.JIRA_USERNAME = cfg.username
  if (cfg.password) out.JIRA_PASSWORD = cfg.password
  return out
}
