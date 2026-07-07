/**
 * 从报告「§9 Jira 备注」结构化区块提取 Jira comment 三部分（分析阶段已写好，此处只解析）。
 */

import { enrichLogEvidenceFromReport } from './log-evidence-extract'

export interface JiraCommentBlocks {
  conclusion: string
  evidence: string[]
  suggestions: string[]
}

const BLOCK_SPLIT_RE = /【\s*(分析结论|结论依据|建议)\s*】/
const SECTION9_HEADING_RE = /^#{1,4}\s*9\.\s*[^\n]*Jira\s*备注/i
const PLAIN_SECTION9_HEADING_RE = /^【\s*9\.\s*[^\n]*Jira\s*备注/i
const NEXT_SECTION_RE = /^#{1,4}\s*(?!9\.)[\d]+\.\s/
const TOOLS_END_RE = /^===\s*TOOLS_INVOKED/i

export function isMarkdownJunkLine(line: string): boolean {
  const t = line.trim()
  if (!t) return false
  if (/^`{3,}\s*$/.test(t)) return true
  if (/^[-─_]{3,}$/.test(t)) return true
  if (/^[│｜|….\s]+$/.test(t)) return true
  if (t === '...' || t === '…' || t === '|') return true
  return false
}

export function stripMarkdownJunk(text: string): string {
  const lines = text.split('\n').filter(line => !isMarkdownJunkLine(line))
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop()
  return lines.join('\n').trim()
}

function unwrapCodeFence(text: string): string {
  const t = text.trim()
  if (!t.startsWith('```')) return stripMarkdownJunk(t)

  const openEnd = t.indexOf('\n')
  if (openEnd < 0) return stripMarkdownJunk(t.replace(/^```[\w-]*\s*/, ''))

  const closeIdx = t.indexOf('\n```', openEnd)
  if (closeIdx >= 0) {
    return stripMarkdownJunk(t.slice(openEnd + 1, closeIdx).trim())
  }
  return stripMarkdownJunk(t.replace(/^```[\w-]*\n?/, '').replace(/\n?```[\s\S]*$/, '').trim())
}

function prepareSection9Body(content: string): string {
  let text = unwrapCodeFence(content)
  text = text.replace(/^【\s*9\.\s*[^\n]*】\s*\n?/i, '')
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '$1')
  return stripMarkdownJunk(text.trim())
}

function parseNumberedItems(text: string): string[] {
  const items: string[] = []
  const lines = text.split(/\r?\n/)
  let buf: string[] = []

  const flush = () => {
    if (!buf.length) return
    const joined = stripMarkdownJunk(buf.join('\n'))
    if (joined) items.push(joined)
    buf = []
  }

  for (const line of lines) {
    const t = line.trim()
    if (!t) {
      if (buf.length) buf.push('')
      continue
    }
    if (isMarkdownJunkLine(line)) {
      flush()
      continue
    }
    const numbered = t.match(/^\d+[.)]\s+([\s\S]*)$/)
    if (numbered) {
      flush()
      buf.push(numbered[1].trim())
      continue
    }
    if (buf.length) buf.push(line.replace(/^\s{2,}/, ''))
  }
  flush()
  return items
}

function splitRemarkBlocks(body: string): Record<string, string> {
  const out: Record<string, string> = {}
  const parts = body.split(BLOCK_SPLIT_RE)
  for (let i = 1; i < parts.length; i += 2) {
    out[parts[i]] = stripMarkdownJunk((parts[i + 1] || '').trim())
  }
  return out
}

function extractSection9Body(reportMarkdown: string): string | null {
  const lines = reportMarkdown.replace(/\r\n/g, '\n').split('\n')
  let startIdx = -1

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim()
    if (SECTION9_HEADING_RE.test(line) || PLAIN_SECTION9_HEADING_RE.test(line)) {
      startIdx = i + 1
      break
    }
  }
  if (startIdx < 0) return null

  const bodyLines: string[] = []
  let inFence = false

  for (let i = startIdx; i < lines.length; i += 1) {
    const line = lines[i]
    const trimmed = line.trim()

    if (!inFence && NEXT_SECTION_RE.test(trimmed)) break
    if (TOOLS_END_RE.test(trimmed)) break

    if (/^```/.test(trimmed)) {
      if (!inFence) {
        inFence = true
        continue
      }
      break
    }
    if (inFence || !isMarkdownJunkLine(line)) {
      bodyLines.push(line)
    }
  }

  const body = bodyLines.join('\n').trim()
  return body || null
}

export function extractJiraCommentBlocks(reportMarkdown: string): JiraCommentBlocks | null {
  const raw = extractSection9Body(reportMarkdown)
  if (!raw) return null

  const body = prepareSection9Body(raw)
  const blocks = splitRemarkBlocks(body)

  const conclusion = stripMarkdownJunk(
    (blocks['分析结论'] || '').replace(/^分析结论[：:]\s*/i, '').trim(),
  )
  const evidence = parseNumberedItems(blocks['结论依据'] || '')
  const suggestions = parseNumberedItems(blocks['建议'] || '')

  if (!conclusion && !evidence.length && !suggestions.length) return null

  return {
    conclusion,
    evidence: enrichLogEvidenceFromReport(evidence, reportMarkdown),
    suggestions,
  }
}

export function hasJiraRemarkSection(reportMarkdown: string): boolean {
  return /^#{1,4}\s*9\.\s*[^\n]*Jira\s*备注/im.test(reportMarkdown)
    || /^【\s*9\.\s*[^\n]*Jira\s*备注/im.test(reportMarkdown)
}
