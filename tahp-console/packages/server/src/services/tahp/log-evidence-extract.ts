/** 从报告正文中提取完整异常堆栈，用于补全 §9 依据里不完整的日志行 */

const STACK_LINE_RE = /^\s*(?:at\s+|Caused by:|\.{3}\s+\d+\s+more|\.\.\.)/

function extractLogBlocks(text: string): string[] {
  const blocks: string[] = []
  const lines = text.split(/\r?\n/)
  let buf: string[] = []

  const flush = () => {
    if (!buf.length) return
    const block = buf.join('\n').trim()
    if (block.includes('at ') || block.includes('Caused by')) blocks.push(block)
    buf = []
  }

  for (const line of lines) {
    const t = line.trim()
    const isStack = STACK_LINE_RE.test(line) || /Exception|Error:|FATAL|ANR in/.test(t)
    if (isStack || (buf.length && (t.startsWith('at ') || t.includes('Caused by')))) {
      buf.push(line)
      continue
    }
    flush()
    if (/Exception|Error:|FATAL|ANR in/.test(t)) buf.push(line)
  }
  flush()
  return blocks
}

function firstLineKey(block: string): string {
  return block.split('\n')[0].trim().toLowerCase()
}

/** 若依据项只有异常头、报告中有完整堆栈，则替换为完整堆栈 */
export function enrichLogEvidenceFromReport(evidence: string[], reportMarkdown: string): string[] {
  if (!evidence.length || !reportMarkdown?.trim()) return evidence
  const blocks = extractLogBlocks(reportMarkdown)
  if (!blocks.length) return evidence

  const byHead = new Map<string, string>()
  for (const block of blocks) {
    byHead.set(firstLineKey(block), block)
  }

  return evidence.map(item => {
    const head = item.split('\n')[0].trim()
    if (item.includes('\n') && item.includes('at ')) return item
    const full = byHead.get(head.toLowerCase())
    if (full && full.length > item.length) return full
    for (const block of blocks) {
      if (block.startsWith(head) || head && block.includes(head.slice(0, Math.min(head.length, 80)))) {
        return block
      }
    }
    return item
  })
}
