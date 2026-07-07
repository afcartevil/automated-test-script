/**
 * 将 Agent Markdown 报告转为适合 Jira comment / 知识库条目的纯文本。
 */

export function formatBugReportPlainText(markdown: string): string {
  if (!markdown?.trim()) return ''

  let text = markdown.replace(/\r\n/g, '\n')

  text = text.replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, code: string) => code.trim())
  text = text.replace(/^#{1,6}\s+(.+)$/gm, (_, title: string) => `【${title.trim()}】`)
  text = text.replace(/\*\*([^*\n]+)\*\*[：:]\s*/g, '$1: ')
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '$1')
  text = text.replace(/^-{3,}$/gm, '────────────────────────────────')

  const lines = text.split('\n')
  const out: string[] = []
  for (const line of lines) {
    const t = line.trim()
    if (/^\|.+\|$/.test(t) && t.includes('|')) {
      out.push(t.replace(/^\|/, '').replace(/\|$/, '').replace(/\s*\|\s*/g, ' | ').trim())
      continue
    }
    out.push(line)
  }

  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}
