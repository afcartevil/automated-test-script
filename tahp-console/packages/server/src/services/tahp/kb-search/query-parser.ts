import { tokenize } from './bm25'

const JIRA_KEY_RE = /\b([A-Z][A-Z0-9]+-\d+)\b/g
const ENTRY_ID_RE = /\b(kb-[a-f0-9]{8})\b/i
const DOC_ID_RE = /\b(doc-[a-f0-9]{8})\b/i

const MODULE_HINTS: Array<{ module: string; patterns: RegExp[] }> = [
  { module: 'telephony', patterns: [/通信|通话|语音|拨号|来电|modem|vowifi|vozwifi|sim\b|rat\b|运营商|telephony/i] },
  { module: 'power-mgmt', patterns: [/功耗|背光|充电|电池|hbm|power/i] },
  { module: 'kernel-driver', patterns: [/驱动|指纹|sensor|driver/i] },
  { module: 'kernel', patterns: [/内核|kernel|panic|dump/i] },
]

export interface ParsedKbQuery {
  jira_key?: string
  entry_id?: string
  document_id?: string
  module_hint?: string
  tokens: string[]
  raw: string
}

export function parseJiraKey(text: string): string | undefined {
  JIRA_KEY_RE.lastIndex = 0
  const m = JIRA_KEY_RE.exec(text)
  return m?.[1]
}

export function tokenizeQuery(text: string): string[] {
  return tokenize(text)
}

export function parseKbQuery(query: string): ParsedKbQuery {
  const raw = query.trim()
  const jira_key = parseJiraKey(raw)
  const entryMatch = ENTRY_ID_RE.exec(raw)
  const docMatch = DOC_ID_RE.exec(raw)
  let module_hint: string | undefined
  for (const { module, patterns } of MODULE_HINTS) {
    if (patterns.some(p => p.test(raw))) {
      module_hint = module
      break
    }
  }
  return {
    jira_key,
    entry_id: entryMatch?.[1],
    document_id: docMatch?.[1],
    module_hint,
    tokens: tokenizeQuery(raw),
    raw,
  }
}
