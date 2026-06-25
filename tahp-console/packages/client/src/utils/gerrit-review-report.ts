/**
 * 从 Gerrit Code Review 报告 Markdown 中提取「必须测试」建议（与 server 逻辑一致）。
 */

export interface P0ExtractionResult {
  items: string[]
  rawSection: string
}

const MUST_TEST_START_PATTERNS: RegExp[] = [
  /^\s*(?:#{1,4}\s*)+(?:P0\s*[-–—]?\s*|P0\s+)?(?:必须测试|必现测试)\s*$/im,
  /^\s*\*\*(?:P0\s*[-–—]?\s*)?(?:必须测试|必现测试)\*\*\s*$/im,
  /^\s*(?:#{1,4}\s*)+(?:必须测试|必现测试)/im,
  /^\s*<span[^>]*>\s*P0\s*<\/span>\s*必须测试\s*$/im,
]

const TEST_SUGGESTION_SECTION_RE = /^\s*#{1,4}\s*(?:\d+\.\s*)?测试建议/m
const MERGED_TEST_HEADING_RE = /^\s*#{1,4}\s*合并测试建议\s*$/im

const SECTION_END_PATTERNS: RegExp[] = [
  /^\s*(?:#{1,4}\s*)+(?:P[12]\s*[-–—]?\s*)?(?:强烈建议|建议测试)/m,
  /^\s*\*\*(?:P[12]\s*[-–—]?\s*)?(?:强烈建议|建议测试)\*\*/m,
  /^\s*P[12]\s*[-–—]/m,
  /^\s*#{1,4}\s*<span[^>]*>\s*P[12]\s*<\/span>/m,
  /^\s*#{1,4}\s*合并测试建议/m,
  /^\s*#{1,4}\s*报告链接/m,
  /^\s*#{1,4}\s*5\.\s*(?:Report|查看报告|报告)/m,
  /^\s*---\s*$/m,
  /^\s*\*\*HTML Report\*\*/m,
  /<h3[^>]*>[\s\S]*?P[12][\s\S]*?<\/h3>/m,
  /<div[^>]*id="test-p[12]"/m,
]

function normalizeAgentMarkdown(text: string): string {
  let t = text
  t = t.replace(
    /<h3[^>]*>\s*<span[^>]*>\s*P0\s*<\/span>\s*必须测试\s*<\/h3>/gi,
    '### 必须测试',
  )
  t = t.replace(/^(\s*(?:#{1,4}\s*)+)(?:P0\s*[-–—]?\s*|P0\s+)?(必须测试|必现测试)\s*$/gim, '### 必须测试')
  t = t.replace(/^(\s*(?:#{1,4}\s*)+)(?:P[12]\s*[-–—]?\s*)?(强烈建议|建议测试)\s*$/gim, '### $2')
  t = t.replace(/^#{2,4}\s*<span[^>]*>\s*P0\s*<\/span>\s*必须测试\s*$/gim, '### 必须测试')
  t = t.replace(/^#{2,4}\s*<span[^>]*>\s*P1\s*<\/span>[^\n]*/gim, '### 强烈建议')
  t = t.replace(/^#{2,4}\s*<span[^>]*>\s*P2\s*<\/span>[^\n]*/gim, '### 建议测试')
  t = t.replace(/\*\*(#{1,4}\s*(?:P0\s*[-–—]?\s*)?(?:必须测试|必现测试))\*\*/gi, '### 必须测试')
  t = t.replace(/\*\*(#{1,4}\s*P[12][^*]+)\*\*/gi, '$1')
  t = t.replace(/^\s*\*\*(?:P0\s*[-–—]?\s*)?(必须测试|必现测试)\*\*\s*$/gim, '### 必须测试')
  t = t.replace(/^\s*\*\*(?:P1\s*[-–—]?\s*)?强烈建议\*\*\s*$/gim, '### 强烈建议')
  t = t.replace(/^\s*\*\*(?:P2\s*[-–—]?\s*)?建议测试\*\*\s*$/gim, '### 建议测试')
  t = t.replace(/^#{2,4}\s*[^\n]*关键测试项\s*\(P0\)\s*$/gim, '### 必须测试')
  t = t.replace(/^\s*\d+\.\s*\*\*测试建议\*\*\s*[:：]?\s*$/gim, '### 测试建议')
  t = t.replace(/<ol[^>]*>/gi, '\n')
  t = t.replace(/<\/ol>/gi, '\n')
  t = t.replace(/<li[^>]*>/gi, '\n- ')
  t = t.replace(/<\/li>/gi, '\n')
  t = t.replace(/<strong>(.*?)<\/strong>/gi, '**$1**')
  t = t.replace(/<br\s*\/?>/gi, '\n')
  t = t.replace(/<[^>]+>/g, '')
  return t
}

function isSectionEndLine(trimmed: string): boolean {
  if (/^#{1,4}\s*P[12]\b/i.test(trimmed)) return true
  if (/^\*\*(?:P[12]\s*[-–—]?\s*)?(?:强烈建议|建议测试)\*\*/i.test(trimmed)) return true
  if (/^P[12]\s*[-–—]/i.test(trimmed)) return true
  if (/^#{1,4}\s*(?:强烈建议|建议测试)\s*$/i.test(trimmed)) return true
  if (/^(?:强烈建议|建议测试)$/.test(trimmed)) return true
  if (/^#{1,4}\s*报告链接/i.test(trimmed)) return true
  return false
}

function parseListItems(section: string): string[] {
  const items: string[] = []
  for (const line of section.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    if (isSectionEndLine(trimmed)) break
    if (/^P[12]\s*[-–—]/i.test(trimmed)) break
    if (/^#{1,4}\s/.test(trimmed)) continue
    if (/^\d+\.\s*\*\*Report\*\*/i.test(trimmed)) break
    const numbered = trimmed.match(/^\d+\.\s+(.+)$/)
    const bulleted = trimmed.match(/^[-*•]\s+(.+)$/)
    const text = numbered?.[1] ?? bulleted?.[1]
    if (text && !/^\*\*Report\*\*/i.test(text)) items.push(text.trim())
  }
  return items
}

function findMustTestContentStart(text: string): number {
  for (const re of MUST_TEST_START_PATTERNS) {
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

function extractMustTestFromText(text: string): string {
  const start = findMustTestContentStart(text)
  if (start < 0) return ''
  return sliceUntilSectionEnd(text.slice(start))
}

function extractFromTestSuggestionSection(normalized: string): string {
  const match = TEST_SUGGESTION_SECTION_RE.exec(normalized)
  if (match?.index === undefined) return ''
  return extractMustTestFromText(normalized.slice(match.index))
}

export function extractP0TestSuggestions(markdown: string): P0ExtractionResult {
  if (!markdown?.trim()) {
    return { items: [], rawSection: '' }
  }

  const normalized = normalizeAgentMarkdown(markdown)
  let rawSection = extractMustTestFromText(normalized)

  if (!rawSection) {
    rawSection = extractFromTestSuggestionSection(normalized)
  }

  if (!rawSection) {
    const mergedIdx = MERGED_TEST_HEADING_RE.exec(normalized)
    if (mergedIdx?.index !== undefined) {
      rawSection = extractMustTestFromText(normalized.slice(mergedIdx.index))
    }
  }

  const items = parseListItems(rawSection)
  return { items, rawSection }
}

export interface ModuleExtractionResult {
  modules: string[]
  display: string
}

const MODULE_DISPLAY_UNKNOWN = '未识别'

const MODULE_LINE_PATTERNS: RegExp[] = [
  /\*\*模块\*\*\s*[:：]\s*([^\n]+)/i,
  /^\|\s*模块\s*\|\s*([^|\n]+)\s*\|/im,
  /<td[^>]*>\s*模块\s*<\/td>\s*<td[^>]*>\s*([^<]+)\s*<\/td>/i,
]

function parseModulesDisplay(display: string): string[] {
  const trimmed = display.trim()
  if (!trimmed || trimmed === MODULE_DISPLAY_UNKNOWN) return []
  return trimmed
    .split(/[/／、,，]/)
    .map(part => part.trim())
    .filter(Boolean)
}

export function extractModules(markdown: string): ModuleExtractionResult {
  if (!markdown?.trim()) {
    return { modules: [], display: MODULE_DISPLAY_UNKNOWN }
  }

  for (const re of MODULE_LINE_PATTERNS) {
    const match = re.exec(markdown)
    if (match?.[1]) {
      const display = match[1].replace(/<[^>]+>/g, '').trim()
      const modules = parseModulesDisplay(display)
      return {
        modules,
        display: modules.length ? display : MODULE_DISPLAY_UNKNOWN,
      }
    }
  }

  return { modules: [], display: MODULE_DISPLAY_UNKNOWN }
}
