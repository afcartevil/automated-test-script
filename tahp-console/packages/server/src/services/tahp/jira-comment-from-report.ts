/**
 * 从报告「§9 Jira 备注」结构化区块提取 Jira comment 三部分（分析阶段已写好，此处只解析）。
 */

import { enrichLogEvidenceFromReport } from './log-evidence-extract'

export interface JiraCommentBlocks {
  conclusion: string
  evidence: string[]
  suggestions: string[]
}

const SECTION9_HEADING_RE = /^#{1,4}\s*9\.\s*[^\n]*Jira\s*备注/i
const PLAIN_SECTION9_HEADING_RE = /^【\s*9\.\s*[^\n]*Jira\s*备注/i
const NEXT_SECTION_RE = /^#{1,4}\s*(?!9\.)[\d]+\.\s/
const SECTION6_HEADING_RE = /^#{1,4}\s*6\.\s*修复建议/i
const TOOLS_END_RE = /^===\s*TOOLS_INVOKED/i
const BLOCK_KEY = '分析结论|结论依据|建议|修复建议'
const BLOCK_BRACKET_RE = new RegExp(`^【\\s*(${BLOCK_KEY})\\s*】\\s*(.*)$`)
const BLOCK_MARKUP_RE = new RegExp(`^(?:\\*{1,2}|#{1,4}\\s+)(${BLOCK_KEY})(?:\\*{1,2})?[：:]?\\s*(.*)$`)
const BLOCK_COLON_RE = new RegExp(`^(${BLOCK_KEY})[：:]\\s*(.*)$`)
const BLOCK_BARE_RE = new RegExp(`^(${BLOCK_KEY})$`)

export function isMarkdownJunkLine(line: string): boolean {
  const t = line.trim()
  if (!t) return false
  if (/^`{3,}[\w-]*\s*$/.test(t)) return true
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
  let t = text.trim()
  if (!t.startsWith('```')) return stripMarkdownJunk(t)
  t = t.replace(/^```[\w-]*[ \t]*\n?/, '')
  t = t.replace(/\n```[\w-]*[ \t]*$/, '')
  return stripMarkdownJunk(t)
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
    const numbered = t.match(/^(?:\d+[.)、．]|\(\d+\)|（\d+）|[-*•])\s*(.*)$/)
    if (numbered) {
      flush()
      buf.push(numbered[1].trim())
      continue
    }
    if (buf.length) buf.push(line.replace(/^\s{2,}/, ''))
  }
  flush()
  if (!items.length) {
    const plain = stripMarkdownJunk(text)
    if (plain) items.push(plain)
  }
  return items
}

function normalizeBlockKey(raw: string): '分析结论' | '结论依据' | '建议' | null {
  if (raw === '建议' || raw === '修复建议') return '建议'
  if (raw === '分析结论' || raw === '结论依据') return raw
  return null
}

function matchBlockHeader(line: string): { key: string; rest: string } | null {
  const t = line.trim()
  const matched = t.match(BLOCK_BRACKET_RE) || t.match(BLOCK_MARKUP_RE) || t.match(BLOCK_COLON_RE) || t.match(BLOCK_BARE_RE)
  if (!matched) return null
  const key = normalizeBlockKey(matched[1] || '')
  if (!key) return null
  return { key, rest: (matched[2] || '').trim() }
}

function splitRemarkBlocks(body: string): Record<string, string> {
  const out: Record<string, string> = {}
  const lines = body.split(/\r?\n/)
  let currentKey: string | null = null
  let buf: string[] = []

  const flush = () => {
    if (!currentKey) return
    out[currentKey] = stripMarkdownJunk(buf.join('\n').trim())
    buf = []
  }

  for (const line of lines) {
    const header = matchBlockHeader(line)
    if (header) {
      flush()
      currentKey = header.key
      buf = header.rest ? [header.rest] : []
      continue
    }
    if (currentKey) buf.push(line)
  }
  flush()
  return out
}

function extractSectionBody(
  reportMarkdown: string,
  headingRe: RegExp,
  extraHeadingRe?: RegExp,
): string | null {
  const lines = reportMarkdown.replace(/\r\n/g, '\n').split('\n')
  let startIdx = -1

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim()
    if (headingRe.test(line) || (extraHeadingRe && extraHeadingRe.test(line))) {
      startIdx = i + 1
      break
    }
  }
  if (startIdx < 0) return null

  const bodyLines: string[] = []
  for (let i = startIdx; i < lines.length; i += 1) {
    const trimmed = lines[i].trim()
    if (NEXT_SECTION_RE.test(trimmed)) break
    if (TOOLS_END_RE.test(trimmed)) break
    bodyLines.push(lines[i])
  }

  const body = bodyLines.join('\n').trim()
  return body || null
}

function extractSection9Body(reportMarkdown: string): string | null {
  return extractSectionBody(reportMarkdown, SECTION9_HEADING_RE, PLAIN_SECTION9_HEADING_RE)
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
  let suggestions = parseNumberedItems(blocks['建议'] || '')

  if (!suggestions.length) {
    const section6 = extractSectionBody(reportMarkdown, SECTION6_HEADING_RE)
    if (section6) {
      const s6 = prepareSection9Body(section6)
      suggestions = parseNumberedItems(s6)
    }
  }

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
