/** 与 server distill-jira-header 保持一致：沉淀知识条目时前置 JIRA 信息（纯文本） */

export interface DistillJiraInfo {
  key?: string
  summary?: string
  description?: string
}

export function buildDistillJiraHeader(jira: DistillJiraInfo): string {
  const key = jira.key?.trim()
  const summary = jira.summary?.trim()
  const description = jira.description?.trim()
  if (!key && !summary && !description) return ''

  const lines = ['【JIRA 信息】', '']
  if (key) lines.push(`KEY: ${key}`)
  if (summary) lines.push(`标题: ${summary}`)
  if (description) lines.push(`描述: ${description}`)
  lines.push('', '────────────────────────────────', '')
  return lines.join('\n')
}

export function prependDistillJiraHeader(content: string, jira: DistillJiraInfo): string {
  const trimmed = content.trim()
  if (!trimmed) return buildDistillJiraHeader(jira).trimEnd()
  if (trimmed.startsWith('【JIRA 信息】')) return trimmed

  const header = buildDistillJiraHeader(jira)
  if (!header) return trimmed
  return `${header}${trimmed}`
}
