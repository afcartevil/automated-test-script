import type { ChecklistScmpJsonlEvent, ChecklistScmpRun, ChecklistScmpSummary } from './types'

const MAX_LOG = 200

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function clampProgress(value: number): number {
  if (value < 0) return 0
  if (value > 100) return 100
  return Math.round(value)
}

function pushLog(run: ChecklistScmpRun, message: string) {
  const text = message.trim()
  if (!text) return
  run.log_tail = [...run.log_tail, text].slice(-MAX_LOG)
  run.message = text
}

function sheetProgress(index: number, total: number, started: boolean): number {
  if (total <= 0) return started ? 20 : 18
  const ratio = started ? Math.max(0, index - 1) / total : index / total
  return clampProgress(20 + ratio * 80)
}

function parseSummary(raw: unknown): ChecklistScmpSummary | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const s = raw as Record<string, unknown>
  const failed = Array.isArray(s.failed_sheets)
    ? s.failed_sheets.map(item => String(item)).filter(Boolean)
    : []
  return {
    sheet_count: asNumber(s.sheet_count) ?? 0,
    feature_count: asNumber(s.feature_count) ?? 0,
    supported: asNumber(s.supported) ?? 0,
    unsupported: asNumber(s.unsupported) ?? 0,
    partial: asNumber(s.partial) ?? 0,
    missing: asNumber(s.missing) ?? 0,
    failed_sheets: failed,
  }
}

export function parseChecklistScmpLine(line: string): ChecklistScmpJsonlEvent | null {
  const text = line.trim()
  if (!text) return null
  const start = text.indexOf('{')
  if (start < 0) return null
  try {
    const parsed = JSON.parse(text.slice(start)) as ChecklistScmpJsonlEvent
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function applyChecklistScmpEvent(run: ChecklistScmpRun, event: ChecklistScmpJsonlEvent): ChecklistScmpRun {
  const next: ChecklistScmpRun = {
    ...run,
    log_tail: [...run.log_tail],
    updated_at: new Date().toISOString(),
  }
  const name = asString(event.event) || 'log'
  const message = asString(event.message)
  if (message) pushLog(next, message)
  next.phase = name

  switch (name) {
    case 'start':
      next.status = 'running'
      next.progress = Math.max(next.progress, 2)
      break
    case 'workbook':
      next.title = asString(event.title) || next.title
      next.progress = Math.max(next.progress, 8)
      break
    case 'parsed':
      next.project = asString(event.project) || next.project
      next.tos_version = asString(event.tos_version) || next.tos_version
      next.progress = Math.max(next.progress, 12)
      break
    case 'scmp_login':
    case 'scmp_resolve':
    case 'scmp_resolved':
      next.progress = Math.max(next.progress, 15)
      break
    case 'scmp_loading':
    case 'scmp_loaded':
      next.progress = Math.max(next.progress, 18)
      break
    case 'plan': {
      const total = asNumber(event.sheet_count) ?? asNumber(event.total)
      if (total != null) next.sheet_total = total
      next.progress = Math.max(next.progress, 20)
      break
    }
    case 'sheet_start': {
      const index = asNumber(event.index)
      const total = asNumber(event.total) ?? next.sheet_total
      next.current_sheet = asString(event.sheet_name) || next.current_sheet
      if (index != null) next.sheet_index = index
      if (total != null) next.sheet_total = total
      if (index != null && total != null) next.progress = Math.max(next.progress, sheetProgress(index, total, true))
      break
    }
    case 'sheet_done':
    case 'sheet_error':
    case 'sheet_write': {
      const index = asNumber(event.index)
      const total = asNumber(event.total) ?? next.sheet_total
      next.current_sheet = asString(event.sheet_name) || next.current_sheet
      if (index != null) next.sheet_index = index
      if (total != null) next.sheet_total = total
      if (index != null && total != null) next.progress = Math.max(next.progress, sheetProgress(index, total, false))
      break
    }
    case 'log_file':
      next.log_file = asString(event.path) || next.log_file
      break
    case 'done': {
      next.progress = 100
      const summary = parseSummary(event.summary)
      if (summary) next.summary = summary
      const ok = event.ok !== false
      next.status = ok ? 'completed' : 'failed'
      if (!ok) next.error = message || next.error || '部分 sheet 处理失败'
      next.completed_at = next.updated_at
      break
    }
    case 'error': {
      next.status = 'failed'
      next.progress = Math.max(next.progress, 100)
      const err = event.error
      const raw = typeof err === 'string'
        ? err
        : asString(err?.message) || message || 'checklist-scmp-sync 失败'
      next.error = compactChecklistScmpError(raw)
      if (next.error && next.error !== message) pushLog(next, next.error)
      next.completed_at = next.updated_at
      break
    }
    case 'report': {
      const summary = parseSummary(event.summary) || parseSummary((event as { data?: { summary?: unknown } }).data?.summary)
      if (summary) next.summary = summary
      break
    }
    default:
      break
  }
  return next
}

export function compactChecklistScmpError(message: string): string {
  if (/No module named ['"]httpx['"]/i.test(message)) {
    return 'tones-scmp 缺少 Python 包 httpx。请重启 Console 后端后再点「开始」；仍失败时在 tahp-console 执行 npm run setup:skills'
  }
  if (/No module named ['"]cryptography['"]/i.test(message)) {
    return 'tones-scmp 缺少 Python 包 cryptography。请重启 Console 后端，或在 tahp-console 执行 npm run setup:skills'
  }
  return message
}

export function validateFeishuUrl(url: string): string | null {
  const text = url.trim()
  if (!text) return '请填写飞书文档链接'
  if (!/^https?:\/\//i.test(text)) return '请输入完整的 http(s) 链接'
  if (!/feishu\.cn|larksuite\.com/i.test(text)) return '请使用飞书 Wiki 或电子表格链接'
  return null
}
