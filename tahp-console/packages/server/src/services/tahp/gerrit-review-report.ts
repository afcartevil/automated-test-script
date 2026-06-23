/**
 * 从 Gerrit Code Review 报告 Markdown 中提取 P0 测试建议。
 */

export interface P0ExtractionResult {
  items: string[]
  rawSection: string
}

const P0_HEADING_RE = /^#{2,4}\s*P0\s*[-–—]\s*必须测试\s*$/im
const MERGED_TEST_HEADING_RE = /^#{2,4}\s*合并测试建议\s*$/im
const SECTION_END_RE = /^#{2,4}\s*(?:P[12]\s*[-–—]|合并测试建议|\d+\.)/m

function parseListItems(section: string): string[] {
  const items: string[] = []
  for (const line of section.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const numbered = trimmed.match(/^\d+\.\s+(.+)$/)
    const bulleted = trimmed.match(/^[-*]\s+(.+)$/)
    const text = numbered?.[1] ?? bulleted?.[1]
    if (text) items.push(text.trim())
  }
  return items
}

function extractSectionAfterHeading(text: string, headingRe: RegExp): string {
  const match = headingRe.exec(text)
  if (!match || match.index === undefined) return ''

  const start = match.index + match[0].length
  const rest = text.slice(start)
  const endMatch = SECTION_END_RE.exec(rest)
  const section = endMatch ? rest.slice(0, endMatch.index) : rest
  return section.trim()
}

/**
 * 从 Agent 完整输出或报告 Markdown 中提取 P0 - 必须测试 列表。
 */
export function extractP0TestSuggestions(markdown: string): P0ExtractionResult {
  if (!markdown?.trim()) {
    return { items: [], rawSection: '' }
  }

  let rawSection = extractSectionAfterHeading(markdown, P0_HEADING_RE)

  if (!rawSection) {
    const mergedIdx = MERGED_TEST_HEADING_RE.exec(markdown)
    if (mergedIdx?.index !== undefined) {
      const afterMerged = markdown.slice(mergedIdx.index)
      rawSection = extractSectionAfterHeading(afterMerged, P0_HEADING_RE)
    }
  }

  const items = parseListItems(rawSection)
  return { items, rawSection }
}
