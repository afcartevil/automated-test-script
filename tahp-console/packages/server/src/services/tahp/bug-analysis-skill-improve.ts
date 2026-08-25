/**
 * 从 Agent 工具调用中识别「自改进 Skill」写入（skill_manage 或直接改 skills 目录）。
 * 纯函数，供单测与 bug-analysis 落盘共用。
 */
import { taskIdFromSessionId, type CuratorLedgerEntry } from '../hermes/skill-improve-registry'

export interface SkillImproveRecord {
  name: string
  actions: string[]
  snapshot_dir?: string
  snapshot_source?: 'runtime' | 'backfill'
}

const MANAGE_WRITE_ACTIONS = new Set([
  'create',
  'edit',
  'patch',
  'write_file',
  'remove_file',
  'delete',
])

const FILE_WRITE_TOOLS = new Set(['write_file', 'patch'])

const SKILL_NAME_RE = /^[a-z0-9][a-z0-9._-]*$/i

function isSkillDirName(name: string | undefined): name is string {
  return !!name && !name.startsWith('.') && SKILL_NAME_RE.test(name)
}

export const SKILL_IMPROVE_ACTION_LABELS: Record<string, string> = {
  create: '新建',
  edit: '整篇改写',
  patch: '局部补丁',
  write_file: '附属文件',
  remove_file: '删除文件',
  delete: '删除',
  file_write: '直接改文件',
}

/**
 * Skill 目录布局有两种：扁平（`skills/<name>/`，TAHP 注入与 profile 目录）
 * 与分类（`skills/<category>/<name>/`，Hermes 内置）。SKILL.md 的父目录才是
 * Skill 本体，优先据此判定，避免把分类名当成 Skill 名。
 */
export function skillNameFromPath(rawPath: string): string | null {
  if (!rawPath) return null
  const parts = rawPath.replace(/\\/g, '/').split('/').filter(Boolean)
  const hasSkillsSegment = parts.some((p, i) => p === 'skills' && i < parts.length - 1)
  if (!hasSkillsSegment) return null

  const last = parts[parts.length - 1]
  if (last?.toLowerCase() === 'skill.md' && parts.length >= 2) {
    const owner = parts[parts.length - 2]
    if (owner !== 'skills' && isSkillDirName(owner)) return owner
  }

  for (let i = parts.length - 2; i >= 0; i -= 1) {
    if (parts[i] !== 'skills') continue
    if (isSkillDirName(parts[i + 1])) return parts[i + 1]
  }
  return null
}

export function detectSkillImprove(
  toolName: string,
  args: unknown,
): { name: string; action: string } | null {
  if (!toolName) return null
  const obj = args && typeof args === 'object' ? args as Record<string, unknown> : {}

  if (toolName === 'skill_manage') {
    const action = String(obj.action || '').trim()
    if (!MANAGE_WRITE_ACTIONS.has(action)) return null
    const name = String(obj.name || '').trim()
    if (!name || !SKILL_NAME_RE.test(name) || name.startsWith('.')) return null
    return { name, action }
  }

  if (FILE_WRITE_TOOLS.has(toolName)) {
    const path = String(obj.path || obj.file_path || obj.file || '')
    const name = skillNameFromPath(path)
    if (!name) return null
    return { name, action: 'file_write' }
  }

  return null
}

export function upsertSkillImprove(
  existing: SkillImproveRecord[],
  hit: { name: string; action: string },
): SkillImproveRecord[] {
  const idx = existing.findIndex(e => e.name === hit.name)
  if (idx < 0) return [...existing, { name: hit.name, actions: [hit.action] }]
  const rec = existing[idx]
  if (rec.actions.includes(hit.action)) return existing
  const next = existing.slice()
  next[idx] = { ...rec, actions: [...rec.actions, hit.action] }
  return next
}

/**
 * 任务结束时用 curator ledger 补齐本 session 改过的 Skill。
 * tool.started 可能丢事件，ledger 是徽章/快照的权威源；已有实时命中保留并合并 action。
 */
export function mergeLedgerSkillImproves(
  existing: SkillImproveRecord[],
  taskId: string,
  entries: CuratorLedgerEntry[],
): SkillImproveRecord[] {
  const tid = String(taskId || '').trim()
  if (!tid || !entries.length) return existing
  let next = existing
  for (const entry of entries) {
    const entryTid = taskIdFromSessionId(entry.evidence?.session_id || '')
    if (entryTid !== tid) continue
    const action = String(entry.action || '').trim() || 'create'
    next = upsertSkillImprove(next, { name: entry.skill, action })
  }
  return next
}

export function parseSkillImproves(raw: unknown): SkillImproveRecord[] {
  if (!Array.isArray(raw)) return []
  const out: SkillImproveRecord[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const rec = item as Record<string, unknown>
    const name = String(rec.name || '').trim()
    if (!name || !SKILL_NAME_RE.test(name)) continue
    const actions = Array.isArray(rec.actions)
      ? rec.actions.map(a => String(a)).filter(Boolean)
      : []
    const snapshotDir = typeof rec.snapshot_dir === 'string' ? rec.snapshot_dir.trim() : ''
    const snapshotSource = rec.snapshot_source === 'backfill' || rec.snapshot_source === 'runtime'
      ? rec.snapshot_source
      : undefined
    const parsed: SkillImproveRecord = { name, actions: actions.length ? actions : ['patch'] }
    if (snapshotDir) parsed.snapshot_dir = snapshotDir
    if (snapshotSource) parsed.snapshot_source = snapshotSource
    out.push(parsed)
  }
  return out
}

export function formatSkillImproveSummary(records: SkillImproveRecord[]): string {
  return records
    .map(r => {
      const labels = r.actions
        .map(a => SKILL_IMPROVE_ACTION_LABELS[a] || a)
        .join('、')
      return labels ? `${r.name}（${labels}）` : r.name
    })
    .join('、')
}
