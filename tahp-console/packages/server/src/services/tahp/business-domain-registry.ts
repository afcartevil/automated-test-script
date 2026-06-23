/**
 * 业务子域配置加载 — 从 knowledge-base/business-domains.yaml 读取，支持多部门扩展。
 */
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import { load as yamlLoad } from 'js-yaml'
import { tahpPaths } from './paths'
import { logger } from '../logger'

export interface BusinessDomainDef {
  id: string
  label: string
  modules: string[]
  keywords: string[]
  jiraHints: RegExp[]
  aliases: string[]
}

interface YamlDomainRow {
  id: string
  label: string
  modules?: string[]
  keywords?: string[]
  jira_hints?: string[]
  aliases?: string[]
}

interface YamlConfig {
  version?: number
  domains?: YamlDomainRow[]
}

let cachedDomains: BusinessDomainDef[] | null = null
let cachedAliasMap: Map<string, string> | null = null
let cachedConfigPath: string | null = null

function compileHint(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern)
  } catch {
    logger.warn({ pattern }, '[business-domain] invalid jira_hint regex, skipped')
    return null
  }
}

function parseDomainRow(row: YamlDomainRow): BusinessDomainDef | null {
  if (!row.id || !row.label) return null
  const jiraHints = (row.jira_hints || [])
    .map(compileHint)
    .filter((r): r is RegExp => r !== null)
  return {
    id: row.id,
    label: row.label,
    modules: row.modules?.length ? [...row.modules] : ['shared'],
    keywords: row.keywords || [],
    jiraHints,
    aliases: row.aliases || [],
  }
}

function buildAliasMap(domains: BusinessDomainDef[]): Map<string, string> {
  const map = new Map<string, string>()
  for (const d of domains) {
    map.set(d.label, d.id)
    map.set(d.id, d.id)
    for (const alias of d.aliases) {
      map.set(alias, d.id)
      map.set(alias.toLowerCase(), d.id)
    }
  }
  return map
}

function resolveConfigPath(): string {
  return join(tahpPaths.knowledgeDir, 'business-domains.yaml')
}

/** 从 YAML 加载业务子域表（带内存缓存） */
export function loadBusinessDomains(force = false): BusinessDomainDef[] {
  const configPath = resolveConfigPath()
  if (!force && cachedDomains && cachedConfigPath === configPath) {
    return cachedDomains
  }

  if (!existsSync(configPath)) {
    logger.warn({ configPath }, '[business-domain] config missing, using empty fallback')
    cachedDomains = []
    cachedAliasMap = new Map()
    cachedConfigPath = configPath
    return cachedDomains
  }

  const raw = readFileSync(configPath, 'utf8')
  const parsed = yamlLoad(raw) as YamlConfig
  const domains: BusinessDomainDef[] = []
  for (const row of parsed.domains || []) {
    const def = parseDomainRow(row)
    if (def) domains.push(def)
  }

  cachedDomains = domains
  cachedAliasMap = buildAliasMap(domains)
  cachedConfigPath = configPath
  logger.info({ count: domains.length, configPath }, '[business-domain] loaded domain registry')
  return domains
}

export function reloadBusinessDomains(): BusinessDomainDef[] {
  cachedDomains = null
  cachedAliasMap = null
  return loadBusinessDomains(true)
}

export function getDomainById(id: string): BusinessDomainDef | undefined {
  return loadBusinessDomains().find(d => d.id === id)
}

export function getBusinessDomainLabel(id: string): string {
  return getDomainById(id)?.label || id || '通用'
}

export function listDomainsForModule(module?: string): BusinessDomainDef[] {
  const all = loadBusinessDomains().filter(d => d.id !== 'general')
  if (!module) return all
  return all.filter(d => d.modules.includes(module) || d.modules.includes('shared'))
}

export function resolveAliasToDomainId(text: string): string | null {
  if (!cachedAliasMap || cachedConfigPath !== resolveConfigPath()) {
    loadBusinessDomains()
  }
  const map = cachedAliasMap!
  const trimmed = text.trim()
  if (map.has(trimmed)) return map.get(trimmed)!
  const lower = trimmed.toLowerCase()
  if (map.has(lower)) return map.get(lower)!
  for (const [alias, id] of map.entries()) {
    if (alias.length >= 2 && trimmed.includes(alias)) return id
  }
  return null
}
