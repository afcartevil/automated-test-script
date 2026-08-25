import { composeJiraCommentFromReport } from './compose-jira-comment'
import { formatBugReportPlainText } from './format-bug-report-plain'
import { isJiraRemarkTitle, splitReportIntoSections } from './bug-analysis-report'

export interface JiraCommentSection {
  id: string
  title: string
  snippet: string
  defaultSelected: boolean
}

function slugTitle(title: string, index: number): string {
  const slug = title.replace(/\s+/g, '-').replace(/[（）()]/g, '').slice(0, 40)
  return `sec-${index}-${slug || 'section'}`
}

export function buildJiraCommentSections(reportMarkdown: string): JiraCommentSection[] {
  const remarkSnippet = composeJiraCommentFromReport(reportMarkdown).trim()
  return splitReportIntoSections(reportMarkdown)
    .map((block, index) => {
      const isRemark = isJiraRemarkTitle(block.title)
      const snippet = isRemark
        ? (remarkSnippet || formatBugReportPlainText(block.content))
        : formatBugReportPlainText(block.content)
      return {
        id: slugTitle(block.title, index),
        title: block.title,
        snippet: snippet.trim(),
        defaultSelected: isRemark,
      }
    })
    .filter(section => section.snippet)
}

export function joinSelectedSnippets(sections: JiraCommentSection[], selectedIds: string[]): string {
  const picked = new Set(selectedIds)
  return sections
    .filter(section => picked.has(section.id))
    .map(section => section.snippet.trim())
    .filter(Boolean)
    .join('\n\n')
    .trim()
}

export function appendJiraCommentSnippet(preview: string, snippet: string): string {
  const snip = snippet.trim()
  if (!snip) return preview.trim()
  const base = preview.trim()
  if (!base) return snip
  if (base.includes(snip)) return base
  return `${base}\n\n${snip}`
}

export function removeJiraCommentSnippet(preview: string, snippet: string): string {
  const snip = snippet.trim()
  if (!snip) return preview.trim()
  const idx = preview.indexOf(snip)
  if (idx < 0) return preview.trim()
  const before = preview.slice(0, idx).trimEnd()
  const after = preview.slice(idx + snip.length).trimStart()
  return [before, after].filter(Boolean).join('\n\n').trim()
}

export function toggleJiraCommentSection(input: {
  preview: string
  snippet: string
  selected: boolean
  inserted?: string
}): { preview: string; inserted?: string } {
  if (input.selected) {
    const snip = input.snippet.trim()
    return {
      preview: appendJiraCommentSnippet(input.preview, snip),
      inserted: snip || undefined,
    }
  }
  const toRemove = (input.inserted || input.snippet).trim()
  return {
    preview: removeJiraCommentSnippet(input.preview, toRemove),
    inserted: undefined,
  }
}
