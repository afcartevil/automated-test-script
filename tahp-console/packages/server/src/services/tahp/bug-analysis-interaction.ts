/**
 * 智能诊断 — 人机协同交互协议
 *
 * 场景 A：危险命令审批（Bridge approval.requested → task.approval_requested）
 * 场景 D：结构化用户配置输入（Agent 输出 TAHP_USER_INPUT 标记块）
 */

export const APPROVAL_AUTO_ONCE_MS = 60_000

export interface UserInputField {
  name: string
  label: string
  type: 'text' | 'textarea' | 'password' | 'number'
  required?: boolean
  placeholder?: string
  default?: string
  hint?: string
}

export interface ParsedUserInputRequest {
  requestId: string
  title: string
  message?: string
  timeoutSec: number
  persistKey?: string
  fields: UserInputField[]
  rawBlock: string
  startIndex: number
}

const USER_INPUT_BLOCK_RE = /=== TAHP_USER_INPUT ===\r?\n([\s\S]*?)=== END_TAHP_USER_INPUT ===/g

function parseKeyValueBody(body: string): Record<string, string> {
  const fields: Record<string, string> = {}
  for (const line of body.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const idx = trimmed.indexOf(':')
    if (idx <= 0) continue
    const key = trimmed.slice(0, idx).trim()
    const value = trimmed.slice(idx + 1).trim()
    if (key) fields[key] = value
  }
  return fields
}

function parseFieldDefs(kv: Record<string, string>): UserInputField[] {
  const byName = new Map<string, Partial<UserInputField>>()

  for (const [key, value] of Object.entries(kv)) {
    if (!key.startsWith('field.')) continue
    const rest = key.slice('field.'.length)
    const dot = rest.indexOf('.')
    if (dot <= 0) continue
    const name = rest.slice(0, dot)
    const prop = rest.slice(dot + 1)
    const existing = byName.get(name) || { name }
    if (prop === 'type') {
      const t = value.toLowerCase()
      existing.type = (t === 'textarea' || t === 'password' || t === 'number' ? t : 'text') as UserInputField['type']
    } else if (prop === 'label') existing.label = value
    else if (prop === 'required') existing.required = value === 'true' || value === '1' || value === 'yes'
    else if (prop === 'placeholder') existing.placeholder = value
    else if (prop === 'default') existing.default = value
    else if (prop === 'hint') existing.hint = value
    byName.set(name, existing)
  }

  return Array.from(byName.values())
    .filter((f): f is UserInputField => !!f.name && !!f.label)
    .map((f) => ({
      name: f.name!,
      label: f.label!,
      type: f.type || 'text',
      required: f.required,
      placeholder: f.placeholder,
      default: f.default,
      hint: f.hint,
    }))
}

export function findUserInputMarkers(text: string, fromIndex = 0): ParsedUserInputRequest[] {
  const hits: ParsedUserInputRequest[] = []
  USER_INPUT_BLOCK_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = USER_INPUT_BLOCK_RE.exec(text)) !== null) {
    if (m.index < fromIndex) continue
    const kv = parseKeyValueBody(m[1])
    const requestId = kv.request_id || kv.requestid || `req-${m.index}`
    const title = kv.title || '请提供配置信息'
    const timeoutRaw = Number(kv.timeout_sec || kv.timeout || '300')
    const timeoutSec = Number.isFinite(timeoutRaw) && timeoutRaw > 0 ? timeoutRaw : 300
    const fields = parseFieldDefs(kv)
    if (fields.length === 0) continue

    hits.push({
      requestId,
      title,
      message: kv.message,
      timeoutSec,
      persistKey: kv.persist_key || kv.persistkey,
      fields,
      rawBlock: m[0],
      startIndex: m.index,
    })
  }
  return hits
}

export function buildUserInputResumeMessage(
  request: ParsedUserInputRequest,
  values: Record<string, string>,
): string {
  const lines: string[] = [
    '## 用户已提交配置',
    `request_id: ${request.requestId}`,
    '',
  ]
  if (request.persistKey) {
    lines.push(`persist_key: ${request.persistKey}`)
    lines.push('')
  }
  for (const field of request.fields) {
    const v = values[field.name] ?? ''
    lines.push(`- **${field.label}** (\`${field.name}\`): ${v || '(空)'}`)
  }
  lines.push('')
  lines.push('请根据以上配置继续执行后续步骤（含必要的配置持久化），并继续 Bug 分析流程。')
  return lines.join('\n')
}

export interface UserInputResponseRecord {
  request_id: string
  title: string
  persist_key?: string
  values: Record<string, string>
  submitted_at: string
}

export interface ApprovalRequestPayload {
  approval_id: string
  command: string
  description: string
  choices: string[]
  allow_permanent?: boolean
  timeout_ms?: number
}
