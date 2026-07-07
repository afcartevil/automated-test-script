/**
 * 从报告 §9 组装 Jira comment（小节标题用 Jira Wiki 加粗，正文无 Markdown 垃圾）。
 */

import { extractJiraCommentBlocks, isMarkdownJunkLine, stripMarkdownJunk } from './jira-comment-from-report'
import { enrichLogEvidenceFromReport } from './log-evidence-extract'

function formatEvidenceItems(evidence: string[]): string[] {
  const lines: string[] = []
  evidence.forEach((item, i) => {
    const parts = item.split('\n')
    lines.push(`${i + 1}. ${parts[0]}`)
    for (let j = 1; j < parts.length; j += 1) {
      lines.push(`   ${parts[j]}`)
    }
  })
  return lines
}

function assembleComment(conclusion: string, evidence: string[], suggestions: string[]): string {
  const lines: string[] = []

  lines.push(`*分析结论：*`)
  lines.push(conclusion || '（报告 §9 未填写分析结论）')
  lines.push('')
  lines.push('*结论依据：*')
  if (evidence.length) {
    lines.push(...formatEvidenceItems(evidence))
  } else {
    lines.push('1. （报告 §9 未填写结论依据）')
  }

  lines.push('')
  lines.push('*建议：*')
  if (suggestions.length) {
    suggestions.forEach((item, i) => lines.push(`${i + 1}. ${item}`))
  } else {
    lines.push('1. （报告 §9 未填写建议）')
  }

  return stripMarkdownJunk(lines.join('\n'))
}

export function composeJiraCommentFromReport(reportMarkdown: string): string {
  const blocks = extractJiraCommentBlocks(reportMarkdown)
  if (!blocks) return ''
  return assembleComment(blocks.conclusion, blocks.evidence, blocks.suggestions)
}

/** 提交前去除 Markdown 残留（保留 Jira Wiki 小节标题 *...*）与无意义分隔行 */
export function sanitizeJiraCommentText(comment: string): string {
  let text = comment.replace(/\r\n/g, '\n')
  text = text.replace(/```[\s\S]*?```/g, '')
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '$1')
  const lines = text.split('\n').filter(line => !isMarkdownJunkLine(line))
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

export function preprocessJiraCommentForSubmit(comment: string, reportMarkdown?: string): string {
  const polished = sanitizeJiraCommentText(comment)
  if (!reportMarkdown?.trim()) return polished

  const lines = polished.split('\n')
  const out: string[] = []
  let inEvidence = false
  let evidenceItems: string[] = []

  const flushEvidence = () => {
    if (!evidenceItems.length) return
    const enriched = enrichLogEvidenceFromReport(evidenceItems, reportMarkdown)
    enriched.forEach((item, i) => {
      const parts = item.split('\n')
      out.push(`${i + 1}. ${parts[0]}`)
      for (let j = 1; j < parts.length; j += 1) {
        out.push(`   ${parts[j]}`)
      }
    })
    evidenceItems = []
  }

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const trimmed = line.trim()
    if (/^\*?结论依据：\*?$/.test(trimmed)) {
      inEvidence = true
      out.push('*结论依据：*')
      continue
    }
    if (inEvidence && /^\*?建议：\*?$/.test(trimmed)) {
      flushEvidence()
      inEvidence = false
      out.push('*建议：*')
      continue
    }
    if (!inEvidence) {
      if (!isMarkdownJunkLine(line)) out.push(line)
      continue
    }
    const numbered = line.match(/^\d+\.\s*(.+)$/)
    if (numbered) {
      const buf = [numbered[1]]
      while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1])) {
        i += 1
        buf.push(lines[i].trim())
      }
      evidenceItems.push(buf.join('\n'))
      continue
    }
    if (trimmed && !isMarkdownJunkLine(line)) evidenceItems.push(trimmed)
  }
  if (inEvidence) flushEvidence()
  return stripMarkdownJunk(out.join('\n'))
}
