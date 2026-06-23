/** 智能诊断沉淀为知识库时，在正文开头附带的 JIRA 元信息 */

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

  const lines = ['## JIRA 信息', '']
  if (key) lines.push(`- **KEY**: ${key}`)
  if (summary) lines.push(`- **标题**: ${summary}`)
  if (description) lines.push(`- **描述**: ${description}`)
  lines.push('', '---', '')
  return lines.join('\n')
}

export function hasDistillJiraHeader(content: string): boolean {
  return content.trim().startsWith('## JIRA 信息')
}

export function prependDistillJiraHeader(content: string, jira: DistillJiraInfo): string {
  const trimmed = content.trim()
  if (!trimmed) return buildDistillJiraHeader(jira).trimEnd()
  if (hasDistillJiraHeader(trimmed)) return trimmed

  const header = buildDistillJiraHeader(jira)
  if (!header) return trimmed
  return `${header}${trimmed}`
}

export function extractJiraFromBugReport(report: Record<string, unknown>): DistillJiraInfo {
  const jira = (report.jira && typeof report.jira === 'object')
    ? report.jira as Record<string, unknown>
    : {}

  const description = [
    typeof jira.description === 'string' ? jira.description : '',
    typeof jira.description_preview === 'string' ? jira.description_preview : '',
  ].find(s => s.trim())?.trim()

  return {
    key: typeof report.jira_key === 'string' ? report.jira_key.trim()
      : typeof jira.key === 'string' ? jira.key.trim() : undefined,
    summary: typeof report.title === 'string' ? report.title.trim()
      : typeof jira.summary === 'string' ? jira.summary.trim() : undefined,
    description,
  }
}
