import { inferJiraKey } from './kb-search/blob'

export interface DistillDedupEntryLike {
  id: string
  content: string
  status: string
  created_at?: string
  updated_at?: string
  jira_key?: string
  source_file?: string
  source_task_id?: string
  source_type?: string
}

export type DepositDedupAction = 'created' | 'updated' | 'unchanged'

export function normalizeEntryContent(content: string): string {
  return content.replace(/\s+/g, ' ').trim()
}

export function isActiveKbEntry(status: string): boolean {
  return status !== 'deleted' && status !== 'rejected'
}

/** 多条重复时保留最早创建、且非 archived 优先的那条 */
export function pickCanonicalDistillEntry<T extends DistillDedupEntryLike>(entries: T[]): T {
  const sorted = [...entries].sort((a, b) => {
    const rank = (s: string) => (s === 'archived' ? 1 : 0)
    if (rank(a.status) !== rank(b.status)) return rank(a.status) - rank(b.status)
    return (a.created_at || '').localeCompare(b.created_at || '')
  })
  return sorted[0]
}

export function resolveDistillJiraKey(params: {
  jira_key?: string
  content: string
  source_file?: string
}): string | undefined {
  const explicit = params.jira_key?.trim()
  if (explicit) return explicit.toUpperCase()
  return inferJiraKey({
    id: 'x',
    content: params.content,
    category: '',
    module: '',
    func_type: '',
    status: 'pending_review',
    source_file: params.source_file,
  })?.toUpperCase()
}

function entryJiraKey(entry: DistillDedupEntryLike): string | undefined {
  if (entry.jira_key?.trim()) return entry.jira_key.trim().toUpperCase()
  const fromFile = entry.source_file?.match(/\b([A-Z][A-Z0-9]+-\d+)\b/i)
  if (fromFile) return fromFile[1].toUpperCase()
  const fromContent = entry.content.match(/\b([A-Z][A-Z0-9]+-\d+)\b/)
  return fromContent?.[1]?.toUpperCase()
}

/**
 * 查找可合并的已有沉淀条目：JIRA > source_task_id > 正文完全一致。
 */
export function findDuplicateDistillEntry<T extends DistillDedupEntryLike>(
  entries: T[],
  params: { jira_key?: string; source_task_id?: string; content: string },
): T | null {
  const active = entries.filter(e => isActiveKbEntry(e.status))
  if (active.length === 0) return null

  const targetJira = resolveDistillJiraKey(params)
  if (targetJira) {
    const byJira = active.filter(e => entryJiraKey(e) === targetJira)
    if (byJira.length > 0) return pickCanonicalDistillEntry(byJira)
  }

  if (params.source_task_id) {
    const byTask = active.filter(e => e.source_task_id === params.source_task_id)
    if (byTask.length > 0) return pickCanonicalDistillEntry(byTask)
  }

  const norm = normalizeEntryContent(params.content)
  if (norm.length >= 80) {
    const byContent = active.filter(e => {
      const isDistill = e.source_type === 'bug_distill' || !!e.source_task_id
      return isDistill && normalizeEntryContent(e.content) === norm
    })
    if (byContent.length > 0) return pickCanonicalDistillEntry(byContent)
  }

  return null
}
