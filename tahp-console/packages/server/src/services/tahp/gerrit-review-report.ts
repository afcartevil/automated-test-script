/**
 * 从 Gerrit Code Review 报告 Markdown 中提取 P0 测试建议。
 */

export interface P0ExtractionResult {
  items: string[]
  rawSection: string
}

const P0_START_PATTERNS: RegExp[] = [
  /^#{2,4}\s*P0\s*[-–—]\s*必须测试\s*$/im,
  /^#{2,4}\s*<span[^>]*>\s*P0\s*<\/span>\s*必须测试\s*$/im,
  /^\*\*P0\s*[-–—]\s*必须测试\*\*\s*$/im,
  /^#{2,4}\s*P0\s*[-–—]\s*必须测试/im,
]

const MERGED_TEST_HEADING_RE = /^#{2,4}\s*合并测试建议\s*$/im

const SECTION_END_PATTERNS: RegExp[] = [
  /^#{2,4}\s*P[12]\s*[-–—]/m,
  /^#{2,4}\s*<span[^>]*>\s*P[12]\s*<\/span>/m,
  /^\*\*P[12]\s*[-–—]/m,
  /^#{2,4}\s*合并测试建议/m,
  /^---\s*$/m,
  /^\*\*HTML Report\*\*/m,
  /^#{2,4}\s*5\.\s*查看报告/m,
]

function parseListItems(section: string): string[] {
  const items: string[] = []
  for (const line of section.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    if (/^P[12]\s*[-–—]/i.test(trimmed)) continue
    if (/^#{1,4}\s/.test(trimmed)) continue
    const numbered = trimmed.match(/^\d+\.\s+(.+)$/)
    const bulleted = trimmed.match(/^[-*•]\s+(.+)$/)
    const text = numbered?.[1] ?? bulleted?.[1]
    if (text) items.push(text.trim())
  }
  return items
}

function findP0ContentStart(text: string): number {
  for (const re of P0_START_PATTERNS) {
    const match = re.exec(text)
    if (match?.index !== undefined) {
      return match.index + match[0].length
    }
  }
  return -1
}

function sliceUntilSectionEnd(rest: string): string {
  let end = rest.length
  for (const re of SECTION_END_PATTERNS) {
    const match = re.exec(rest)
    if (match?.index !== undefined && match.index < end) {
      end = match.index
    }
  }
  return rest.slice(0, end).trim()
}

function extractP0FromText(text: string): string {
  const start = findP0ContentStart(text)
  if (start < 0) return ''
  return sliceUntilSectionEnd(text.slice(start))
}

/**
 * 从 Agent 完整输出或报告 Markdown 中提取 P0 - 必须测试 列表。
 */
export function extractP0TestSuggestions(markdown: string): P0ExtractionResult {
  if (!markdown?.trim()) {
    return { items: [], rawSection: '' }
  }

  let rawSection = extractP0FromText(markdown)

  if (!rawSection) {
    const mergedIdx = MERGED_TEST_HEADING_RE.exec(markdown)
    if (mergedIdx?.index !== undefined) {
      rawSection = extractP0FromText(markdown.slice(mergedIdx.index))
    }
  }

  const items = parseListItems(rawSection)
  return { items, rawSection }
}
