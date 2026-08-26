/**
 * 智能诊断 — 把 Console/Hermes 已配置 Provider Key 写入 loginsight-remote-cli。
 *
 * Agent 实际 `cd` 的是 Hermes 运行时副本（%LOCALAPPDATA%/hermes/skills/...），
 * 不是工程内 skills/.claude/skills/。必须两边都写，否则 doctor 仍报 local_llm_api_key 缺失。
 */
import { dirname, join, resolve } from 'path'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import yaml from 'js-yaml'
import { PROVIDER_ENV_MAP } from '../config-helpers'
import { detectHermesHome, detectHermesRootHome } from '../hermes/hermes-path'
import { getActiveConfigPath, getActiveEnvPath, getActiveProfileDir } from '../hermes/hermes-profile'
import { tahpPaths } from './paths'
import { readJiraUserConfig } from './jira-user-config'
import {
  readBugAnalysisChannelConfig,
  resolveRemoteSkillPath,
} from './bug-analysis-config'
import type { ParsedUserInputRequest, UserInputField } from './bug-analysis-interaction'
import { logger } from '../logger'

const DEFAULT_LOGINSIGHT_BASE_URL = 'https://chat.transsion.com/bugfix/stability-matrix-tools'
const EXTRA_ENV_KEYS = ['TAHP_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']

export interface PickedLlmApiKey {
  apiKey: string
  source: 'active_custom' | 'active_env' | 'sw_aimodel' | 'any_custom' | 'any_env' | 'tahp_env'
}

export interface CustomProviderEntry {
  name?: string
  base_url?: string
  api_key?: string
}

export function parseDotEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#') || !line.includes('=')) continue
    const idx = line.indexOf('=')
    const key = line.slice(0, idx).trim()
    let val = line.slice(idx + 1).trim()
    if (
      (val.startsWith('"') && val.endsWith('"'))
      || (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1)
    }
    if (key) out[key] = val
  }
  return out
}

function upsertDotEnvLine(text: string, key: string, value: string): string {
  const line = `${key}=${value}`
  const re = new RegExp(`^${key}=.*$`, 'm')
  if (re.test(text)) return text.replace(re, line)
  const body = text.replace(/\s+$/, '')
  return `${body}${body ? '\n' : ''}${line}\n`
}

function providerKeyOf(activeProvider: string): string {
  const raw = activeProvider.trim()
  return raw.startsWith('custom:') ? raw.slice('custom:'.length) : raw
}

function customNameMatches(entry: CustomProviderEntry, activeProvider: string, providerKey: string): boolean {
  const name = String(entry.name || '').trim()
  if (!name) return false
  return name === providerKey || name === activeProvider || name === `custom:${providerKey}`
}

function looksLikeSwAimodel(entry: CustomProviderEntry): boolean {
  const blob = `${entry.name || ''} ${entry.base_url || ''}`.toLowerCase()
  return blob.includes('sw-aimodel')
}

export function pickConfiguredLlmApiKey(opts: {
  activeProvider?: string
  customProviders?: CustomProviderEntry[]
  env?: Record<string, string>
}): PickedLlmApiKey | null {
  const env = opts.env || {}
  const tahp = String(env.TAHP_API_KEY || '').trim()
  if (tahp) return { apiKey: tahp, source: 'tahp_env' }

  const activeProvider = String(opts.activeProvider || '').trim()
  const providerKey = providerKeyOf(activeProvider)
  const customProviders = Array.isArray(opts.customProviders) ? opts.customProviders : []

  const activeCustom = customProviders.find(p => customNameMatches(p, activeProvider, providerKey))
  const activeCustomKey = String(activeCustom?.api_key || '').trim()
  if (activeCustomKey) return { apiKey: activeCustomKey, source: 'active_custom' }

  const envMapping = providerKey ? PROVIDER_ENV_MAP[providerKey] : undefined
  if (envMapping?.api_key_env) {
    const fromEnv = String(env[envMapping.api_key_env] || '').trim()
    if (fromEnv) return { apiKey: fromEnv, source: 'active_env' }
  }

  const sw = customProviders.find(p => looksLikeSwAimodel(p) && String(p.api_key || '').trim())
  const swKey = String(sw?.api_key || '').trim()
  if (swKey) return { apiKey: swKey, source: 'sw_aimodel' }

  const anyCustom = customProviders.find(p => String(p.api_key || '').trim())
  const anyCustomKey = String(anyCustom?.api_key || '').trim()
  if (anyCustomKey) return { apiKey: anyCustomKey, source: 'any_custom' }

  for (const meta of Object.values(PROVIDER_ENV_MAP)) {
    if (!meta.api_key_env) continue
    const v = String(env[meta.api_key_env] || '').trim()
    if (v) return { apiKey: v, source: 'any_env' }
  }
  for (const k of EXTRA_ENV_KEYS) {
    const v = String(env[k] || '').trim()
    if (v) return { apiKey: v, source: 'any_env' }
  }
  return null
}

function readProfileEnvMap(): Record<string, string> {
  const merged: Record<string, string> = { ...process.env } as Record<string, string>
  try {
    const p = getActiveEnvPath()
    if (existsSync(p)) Object.assign(merged, parseDotEnv(readFileSync(p, 'utf-8')))
  } catch {
    /* ignore */
  }
  return merged
}

export function resolveConfiguredLlmApiKey(): PickedLlmApiKey | null {
  let activeProvider = ''
  let customProviders: CustomProviderEntry[] = []
  try {
    const configPath = getActiveConfigPath()
    if (existsSync(configPath)) {
      const cfg = (yaml.load(readFileSync(configPath, 'utf-8'), { json: true }) as Record<string, unknown>) || {}
      const model = (cfg.model || {}) as Record<string, unknown>
      activeProvider = String(model.provider || '').trim()
      customProviders = Array.isArray(cfg.custom_providers)
        ? cfg.custom_providers as CustomProviderEntry[]
        : []
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[bug-analysis] failed to read Hermes config.yaml for LLM key reuse')
  }
  return pickConfiguredLlmApiKey({
    activeProvider,
    customProviders,
    env: readProfileEnvMap(),
  })
}

export function isLoginsightSkillRoot(dir: string): boolean {
  return existsSync(join(dir, 'SKILL.md'))
    || existsSync(join(dir, 'scripts', 'loginsight_cli.py'))
}

/** 去重后保留存在 SKILL.md / CLI 的 Skill 根目录（工程副本 + Hermes 运行时副本） */
export function filterLoginsightSkillRoots(candidates: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of candidates) {
    if (!raw) continue
    const dir = resolve(raw)
    const key = process.platform === 'win32' ? dir.toLowerCase() : dir
    if (seen.has(key)) continue
    seen.add(key)
    if (isLoginsightSkillRoot(dir)) out.push(dir)
  }
  return out
}

export function listLoginsightSkillRoots(skillId = 'loginsight-remote-cli'): string[] {
  const cfg = readBugAnalysisChannelConfig()
  const resolved = resolveRemoteSkillPath(cfg.remote_channels.loginsight_remote)
  const extra: string[] = []
  if (resolved.skillMdPath) extra.push(dirname(resolved.skillMdPath))
  if (cfg.remote_channels.loginsight_remote.skill_path) {
    extra.push(cfg.remote_channels.loginsight_remote.skill_path)
  }
  return filterLoginsightSkillRoots([
    join(tahpPaths.skillsDir, skillId),
    join(getActiveProfileDir(), 'skills', skillId),
    join(detectHermesRootHome(), 'skills', skillId),
    join(detectHermesHome(), 'skills', skillId),
    ...extra,
  ])
}

function credentialBlob(request: ParsedUserInputRequest): string {
  return [
    request.title,
    request.message || '',
    request.persistKey || '',
    ...request.fields.flatMap(f => [f.name, f.label, f.hint || '', f.placeholder || '']),
  ].join(' ').toLowerCase()
}

export function isLlmCredentialUserInput(request: ParsedUserInputRequest): boolean {
  return /llm|api[\s_-]?key|sw-aimodel|loginsight/.test(credentialBlob(request))
}

function isSecretField(field: UserInputField): boolean {
  const blob = `${field.name} ${field.label} ${field.type}`.toLowerCase()
  return field.type === 'password' || /key|password|secret|token/.test(blob)
}

export function redactUserInputValues(
  request: ParsedUserInputRequest,
  values: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {}
  for (const field of request.fields) {
    const v = values[field.name] ?? ''
    out[field.name] = v && isSecretField(field) ? '***' : v
  }
  return out
}

export function buildSilentCredentialResumeMessage(
  request: ParsedUserInputRequest,
  seeded: boolean,
): string {
  const lines = [
    '## 配置已由 Console 自动完成（无需用户填写）',
    `request_id: ${request.requestId}`,
    '',
    seeded
      ? 'LLM API Key 已从 Console / Hermes 已配置的 Provider 写入 **工程 Skill 副本和 Hermes 运行时副本** 的 `.loginsight_cli.json`（含 `%LOCALAPPDATA%/hermes/skills/loginsight-remote-cli`）。'
      : 'Console 未找到已配置的 Provider API Key。请**不要**再向用户弹窗索取。将此次远程 LogInsight 视为凭据失败，按远程渠道规则回退本地分析。',
    '',
    '请在 **当前 cd 的 Skill 目录**（通常是 Hermes 运行时副本）立即执行 `python scripts/loginsight_cli.py doctor`。`local_llm_api_key` 应为 ok。禁止再次输出 TAHP_USER_INPUT 索要 Key。',
  ]
  return lines.join('\n')
}

export interface LoginsightSeedResult {
  skipped?: boolean
  reason?: string
  seededKey: boolean
  source?: PickedLlmApiKey['source']
  writtenRoots: string[]
}

function readJsonObject(path: string): Record<string, unknown> {
  if (!existsSync(path)) return {}
  try {
    const raw = JSON.parse(readFileSync(path, 'utf-8')) as unknown
    return raw && typeof raw === 'object' && !Array.isArray(raw)
      ? raw as Record<string, unknown>
      : {}
  } catch {
    return {}
  }
}

export function writeLoginsightCliCredentials(
  skillRoot: string,
  patch: { llmApiKey?: string; operatorUser?: string; operatorPassword?: string },
): void {
  if (!existsSync(skillRoot)) mkdirSync(skillRoot, { recursive: true })
  const configPath = join(skillRoot, '.loginsight_cli.json')
  const envPath = join(skillRoot, '.env')
  const cfg = readJsonObject(configPath)

  if (patch.llmApiKey) cfg.llm_api_key = patch.llmApiKey
  if (patch.operatorUser && !String(cfg.operator_user || '').trim()) cfg.operator_user = patch.operatorUser
  if (patch.operatorPassword && !String(cfg.operator_password || '').trim()) {
    cfg.operator_password = patch.operatorPassword
  }
  if (!String(cfg.llm_provider || '').trim()) cfg.llm_provider = 'sw-aimodel'
  if (!String(cfg.base_url || '').trim()) cfg.base_url = DEFAULT_LOGINSIGHT_BASE_URL

  writeFileSync(configPath, `${JSON.stringify(cfg, null, 2)}\n`, 'utf-8')

  let envText = existsSync(envPath) ? readFileSync(envPath, 'utf-8') : ''
  envText = upsertDotEnvLine(envText, 'BASE_URL', String(cfg.base_url || DEFAULT_LOGINSIGHT_BASE_URL))
  if (cfg.operator_user) envText = upsertDotEnvLine(envText, 'OPERATOR_USER', String(cfg.operator_user))
  if (cfg.operator_password) envText = upsertDotEnvLine(envText, 'OPERATOR_PASSWORD', String(cfg.operator_password))
  envText = upsertDotEnvLine(envText, 'LLM_PROVIDER', String(cfg.llm_provider || 'sw-aimodel'))
  if (cfg.llm_api_key) envText = upsertDotEnvLine(envText, 'LLM_API_KEY', String(cfg.llm_api_key))
  writeFileSync(envPath, envText.endsWith('\n') ? envText : `${envText}\n`, 'utf-8')
}

/** 分析开始前：把 Console Provider Key 写入工程副本 + Hermes 运行时副本 */
export function ensureLoginsightCredentialsForBugAnalysis(): LoginsightSeedResult {
  const cfg = readBugAnalysisChannelConfig()
  const ch = cfg.remote_channels.loginsight_remote
  if (!ch.enabled) return { skipped: true, reason: 'channel_disabled', seededKey: false, writtenRoots: [] }

  const roots = listLoginsightSkillRoots(ch.skill_id)
  if (!roots.length) {
    return { skipped: true, reason: 'skill_missing', seededKey: false, writtenRoots: [] }
  }

  const picked = resolveConfiguredLlmApiKey()
  const jira = readJiraUserConfig()
  if (!picked && !jira) {
    logger.warn('[bug-analysis] loginsight enabled but no Console LLM key or JIRA user config to seed')
    return { seededKey: false, reason: 'no_console_key', writtenRoots: [] }
  }

  for (const root of roots) {
    writeLoginsightCliCredentials(root, {
      llmApiKey: picked?.apiKey,
      operatorUser: jira?.username,
      operatorPassword: jira?.password,
    })
  }
  logger.info(
    { source: picked?.source || 'none', hasKey: !!picked, roots },
    '[bug-analysis] seeded loginsight-remote-cli credentials (project + Hermes copies)',
  )
  return {
    seededKey: !!picked,
    source: picked?.source,
    writtenRoots: roots,
  }
}

export function fillSilentCredentialValues(request: ParsedUserInputRequest): {
  values: Record<string, string>
  seeded: boolean
} | null {
  if (!isLlmCredentialUserInput(request)) return null
  const seed = ensureLoginsightCredentialsForBugAnalysis()
  const placeholders: Record<string, string> = {}
  for (const field of request.fields) {
    placeholders[field.name] = field.default || ''
  }
  return {
    values: redactUserInputValues(request, placeholders),
    seeded: seed.seededKey,
  }
}
