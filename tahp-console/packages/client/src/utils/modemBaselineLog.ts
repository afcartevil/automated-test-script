/** Keep modem run logs bounded so opening a task does not freeze the UI. */
export const MODEM_LOG_TAIL_LINES = 800
export const MODEM_LOG_MAX_CHARS = 512 * 1024

export function takeModemLogTail(
  text: string,
  maxLines = MODEM_LOG_TAIL_LINES,
  maxChars = MODEM_LOG_MAX_CHARS,
): string {
  let raw = String(text || '')
  if (!raw) return ''

  if (raw.length > maxChars) {
    raw = raw.slice(raw.length - maxChars)
    const firstNl = raw.indexOf('\n')
    if (firstNl >= 0 && firstNl + 1 < raw.length) {
      raw = raw.slice(firstNl + 1)
    }
  }

  let idx = raw.length
  let lines = 0
  while (lines < maxLines) {
    const prev = raw.lastIndexOf('\n', idx - 1)
    if (prev < 0) return raw
    lines += 1
    idx = prev
  }

  return `… 已省略较早日志，仅展示最近 ${maxLines} 行 …\n\n${raw.slice(idx + 1)}`
}

export function appendModemLogTail(
  current: string,
  chunk: string,
  maxLines = MODEM_LOG_TAIL_LINES,
  maxChars = MODEM_LOG_MAX_CHARS,
): string {
  if (!chunk) return current
  const next = `${current || ''}${chunk}`
  // Cheap path: stay under byte budget; trim only when needed.
  if (next.length <= maxChars) return next
  return takeModemLogTail(next, maxLines, maxChars)
}

/** 「只看错误」：覆盖 Gerrit / Change-Id / remote rejected，避免只剩 final_status=failed。 */
export function isModemErrorLogLine(line: string): boolean {
  const text = String(line || '')
  if (!text.trim()) return false
  // Post-process noise alone is not helpful as the "root" error.
  if (/\[conflicts\]\s*final_status=failed\b/i.test(text)) return false
  if (/\[run\]\s*phase=\S+\s+status=failed\b/i.test(text) && !/FAILURE:/i.test(text)) return false
  if (/summary=post_process_failed\b/i.test(text)) return false
  return (
    /\berror\b/i.test(text)
    || /\bfailed\b/i.test(text)
    || /\bFAILURE\b/.test(text)
    || /remote rejected/i.test(text)
    || /missing\s+Change-Id/i.test(text)
    || /failed to push/i.test(text)
    || /\[Harness ERROR/i.test(text)
    || /exit_code:\s*[1-9]\d*/i.test(text)
    || /inferred_error=/i.test(text)
  )
}

export function isModemConflictLogLine(line: string): boolean {
  const text = String(line || '')
  return /\bconflict\b/i.test(text) || /\[conflicts\]/i.test(text)
}
