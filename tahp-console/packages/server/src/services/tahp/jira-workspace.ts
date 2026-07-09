/**
 * JIRA 日志工作区 — 固定为 {TAHP 工程根}/jira_workspace/（盘符与 clone 路径自动解析）。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { getActiveProfileDir } from '../hermes/hermes-profile'
import { logger } from '../logger'
import { tahpPaths } from './paths'

export function getJiraWorkspaceRoot(): string {
  return tahpPaths.jiraWorkspaceDir
}

function normalizeEnvPath(p: string): string {
  return p.replace(/\\/g, '/').toLowerCase()
}

/** 是否应将 WORKSPACE_ROOT 改写到工程目录 jira_workspace/ */
export function shouldRewriteWorkspaceRoot(current: string | undefined, canonical = getJiraWorkspaceRoot()): boolean {
  const v = (current || '').trim()
  if (!v) return true
  const norm = normalizeEnvPath(resolve(v))
  const canon = normalizeEnvPath(resolve(canonical))
  if (norm === canon || norm.startsWith(`${canon}/`)) return false
  return true
}

function upsertEnvVar(envPath: string, key: string, value: string): void {
  const lines = existsSync(envPath) ? readFileSync(envPath, 'utf-8').split(/\r?\n/) : [
    '# jira-ops runtime configuration (auto-managed; do not commit secrets)',
    '',
  ]
  let found = false
  const out = lines.map((line) => {
    const trimmed = line.trim()
    if (trimmed.startsWith(`${key}=`) || trimmed.startsWith(`${key} =`)) {
      found = true
      return `${key}=${value}`
    }
    return line
  })
  if (!found) {
    if (out.length && out[out.length - 1] !== '') out.push('')
    out.push(`${key}=${value}`)
  }
  mkdirSync(dirname(envPath), { recursive: true })
  writeFileSync(envPath, `${out.join('\n').replace(/\n*$/, '')}\n`, 'utf-8')
}

function readEnvVar(envPath: string, key: string): string {
  if (!existsSync(envPath)) return ''
  for (const rawLine of readFileSync(envPath, 'utf-8').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq <= 0) continue
    if (line.slice(0, eq).trim() === key) {
      let val = line.slice(eq + 1).trim()
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1)
      }
      return val
    }
  }
  return ''
}

function skillEnvTargets(): string[] {
  const rels = [
    'jira-ops/.env',
    'modem-analysis-local/.env',
    'modem-analysis-local/log-pipeline/.env',
  ]
  const bases = [tahpPaths.skillsDir, join(getActiveProfileDir(), 'skills')]
  const paths: string[] = []
  for (const base of bases) {
    for (const rel of rels) {
      paths.push(join(base, rel))
    }
  }
  return [...new Set(paths)]
}

function unifiedConfigPath(): string {
  return join(tahpPaths.projectRoot, '.tahp', 'unified-config.json')
}

/** 将一键配置中的 workspace_root 对齐到工程 jira_workspace/（若曾指向 .tahp/jira_workspace 等旧路径） */
function syncUnifiedConfigWorkspaceRoot(workspaceRoot: string): void {
  const p = unifiedConfigPath()
  if (!existsSync(p)) return
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const current = typeof raw.workspace_root === 'string' ? raw.workspace_root.trim() : ''
    if (!shouldRewriteWorkspaceRoot(current, workspaceRoot)) return
    raw.workspace_root = workspaceRoot.replace(/\\/g, '/')
    raw.__updated_at = new Date().toISOString()
    mkdirSync(dirname(p), { recursive: true })
    writeFileSync(p, JSON.stringify(raw, null, 2), 'utf-8')
    logger.info({ workspaceRoot }, '[jira-workspace] 已同步 unified-config workspace_root')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[jira-workspace] 同步 unified-config 失败')
  }
}

/**
 * 确保 {工程根}/jira_workspace 存在，并将 WORKSPACE_ROOT 同步到 Skill .env 与 unified-config。
 */
export function ensureJiraWorkspaceLayout(options?: { workspaceRoot?: string }): string {
  const workspaceRoot = resolve(options?.workspaceRoot?.trim() || getJiraWorkspaceRoot())
  mkdirSync(workspaceRoot, { recursive: true })

  const envValue = workspaceRoot.replace(/\\/g, '/')
  let updated = 0
  for (const envPath of skillEnvTargets()) {
    const current = readEnvVar(envPath, 'WORKSPACE_ROOT')
    if (!shouldRewriteWorkspaceRoot(current, workspaceRoot)) continue
    try {
      upsertEnvVar(envPath, 'WORKSPACE_ROOT', envValue)
      updated += 1
    } catch (err) {
      logger.warn({ err: (err as Error).message, envPath }, '[jira-workspace] 写入 WORKSPACE_ROOT 失败')
    }
  }
  syncUnifiedConfigWorkspaceRoot(workspaceRoot)
  if (updated > 0) {
    logger.info({ workspaceRoot, updated }, '[jira-workspace] 已同步 WORKSPACE_ROOT 到 Skill .env')
  }
  return workspaceRoot
}
