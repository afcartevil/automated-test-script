/**
 * 审计日志服务 — JSONL 追加写入，不可逆
 *
 * 存储路径: knowledge-base/.kb-data/audit-log.jsonl
 * 按天自动轮转文件名: audit-log-{YYYY-MM-DD}.jsonl
 */
import { existsSync, mkdirSync, appendFileSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import { randomUUID } from 'crypto'
import { tahpPaths } from './paths'
import { logger } from '../logger'

// ─── 审计事件类型 ────────────────────────────────────────────────────────────

export type AuditAction =
  | 'skill_draft_deleted'
  | 'skill_draft_deprecated'
  | 'skill_draft_deactivated'
  | 'skill_draft_archived'
  | 'skill_draft_restored'
  | 'skill_bulk_cleanup'
  | 'skill_bulk_deprecate'
  | 'skill_bulk_approved'
  | 'skill_bulk_rejected'
  | 'skill_bulk_deleted'
  | 'skill_bulk_archived'
  | 'entry_hard_deleted'
  | 'entry_bulk_archived'
  | 'entry_bulk_deleted'

export interface AuditLogEntry {
  id: string
  timestamp: string
  action: AuditAction
  actor: string
  target_type: 'skill_draft' | 'knowledge_entry' | 'document'
  target_id: string
  target_name?: string
  details?: Record<string, unknown>
  reason?: string
}

// ─── 路径工具 ───────────────────────────────────────────────────────────────

function getKbDataDir(): string {
  return join(tahpPaths.knowledgeDir, '.kb-data')
}

function getAuditLogPath(): string {
  const dateStr = new Date().toISOString().slice(0, 10) // YYYY-MM-DD
  return join(getKbDataDir(), `audit-log-${dateStr}.jsonl`)
}

function getAuditLogBasePath(): string {
  return join(getKbDataDir(), 'audit-log.jsonl')
}

// ─── 写入审计日志 ───────────────────────────────────────────────────────────

/**
 * 追加一条审计日志（JSONL 格式，不可逆）
 * 同时写入当日轮转文件和主文件（兼容）
 */
export function writeAuditLog(entry: Omit<AuditLogEntry, 'id' | 'timestamp'>): AuditLogEntry {
  const fullEntry: AuditLogEntry = {
    id: `al-${Date.now()}-${randomUUID().slice(0, 6)}`,
    timestamp: new Date().toISOString(),
    ...entry,
  }

  const kbDataDir = getKbDataDir()
  if (!existsSync(kbDataDir)) {
    mkdirSync(kbDataDir, { recursive: true })
  }

  const line = JSON.stringify(fullEntry) + '\n'

  try {
    // 写入当日轮转文件
    appendFileSync(getAuditLogPath(), line, 'utf-8')
    // 同时写入主文件（向后兼容）
    appendFileSync(getAuditLogBasePath(), line, 'utf-8')
  } catch (err) {
    logger.error({ err: (err as Error).message, action: entry.action }, '[audit] failed to write audit log')
  }

  return fullEntry
}

// ─── 读取审计日志 ───────────────────────────────────────────────────────────

/**
 * 读取审计日志（最近 N 条，默认100）
 * 从所有轮转文件 + 主文件中合并、去重、按时间倒序
 */
export function readAuditLog(limit = 100, actionFilter?: AuditAction): AuditLogEntry[] {
  const kbDataDir = getKbDataDir()
  if (!existsSync(kbDataDir)) return []

  const entries: AuditLogEntry[] = []
  const seenIds = new Set<string>()

  try {
    const files = readdirSync(kbDataDir).filter(f => f.startsWith('audit-log') && f.endsWith('.jsonl'))
    for (const file of files) {
      try {
        const content = readFileSync(join(kbDataDir, file), 'utf-8')
        for (const line of content.split('\n')) {
          if (!line.trim()) continue
          try {
            const entry = JSON.parse(line) as AuditLogEntry
            if (!seenIds.has(entry.id)) {
              seenIds.add(entry.id)
              entries.push(entry)
            }
          } catch { /* skip malformed line */ }
        }
      } catch { /* skip unreadable file */ }
    }
  } catch { /* dir not found */ }

  // 按时间倒序
  entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp))

  // 按 action 过滤
  const filtered = actionFilter ? entries.filter(e => e.action === actionFilter) : entries

  return filtered.slice(0, limit)
}
