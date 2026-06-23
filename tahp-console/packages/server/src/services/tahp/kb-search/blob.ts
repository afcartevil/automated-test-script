import type { KbEntryLike } from './types'

const JIRA_IN_CONTENT_RE = /\b([A-Z][A-Z0-9]+-\d+)\b/

/** 从沉淀报告抽取 TL;DR / 摘要段 */
export function extractTldr(content: string, maxLen = 500): string {
  const lines = content.split('\n')
  const tldrIdx = lines.findIndex(l => /##\s*1\.\s*摘要|TL;DR|摘要\s*\/\s*TL/i.test(l))
  const start = tldrIdx >= 0 ? tldrIdx : 0
  const slice = lines.slice(start, start + 30).join('\n')
  return slice.replace(/^#{1,6}\s+/gm, '').trim().slice(0, maxLen)
}

export function inferSourceType(entry: KbEntryLike): KbEntryLike['source_type'] {
  if (entry.source_type) return entry.source_type
  if (entry.source_task_id) return 'bug_distill'
  if (entry.source_document_id) return 'doc_chunk'
  return 'manual'
}

export function inferJiraKey(entry: KbEntryLike): string | undefined {
  if (entry.jira_key) return entry.jira_key
  const fromFile = entry.source_file?.match(JIRA_IN_CONTENT_RE)
  if (fromFile) return fromFile[1]
  const fromContent = entry.content.match(JIRA_IN_CONTENT_RE)
  return fromContent?.[1]
}

/** 从报告复现路径/症状描述抽取可检索短语（用户常粘贴标题或步骤描述来搜） */
export function extractSymptomPhrases(content: string, maxLen = 600): string {
  const phrases: string[] = []
  for (const line of content.split('\n')) {
    const clean = line.replace(/^#{1,6}\s+/, '').replace(/\|/g, ' ').trim()
    if (!clean || clean.length < 6) continue
    if (/通知栏|端口防烧|防烧|NTC|70|不显示|充电|插入|小板|触发|复现|预期|实际/.test(clean)) {
      phrases.push(clean)
    }
  }
  return [...new Set(phrases)].join(' ').slice(0, maxLen)
}

export function buildSearchBlob(entry: KbEntryLike): string {
  const tags = (entry.tags || []).join(' ')
  const keywords = (entry.keywords || []).join(' ')
  const tldr = entry.symptom_summary || extractTldr(entry.content)
  const symptoms = extractSymptomPhrases(entry.content)
  const jira = inferJiraKey(entry) || ''
  const title = entry.source_file || entry.id
  return [title, jira, tags, keywords, tldr, symptoms].filter(Boolean).join('\n').trim()
}

export function buildTags(entry: KbEntryLike): string[] {
  const base = new Set<string>([
    ...(entry.tags || []),
    ...(entry.keywords || []).filter(k => k.length >= 2 && k.length <= 32),
  ])
  const jira = inferJiraKey(entry)
  if (jira) base.add(jira)
  return [...base].slice(0, 20)
}
