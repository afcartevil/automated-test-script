/** 'Android 16' | '16' | 'tOS16' | '16.0' → 16。不要拿整段 project_code 调用。 */
export function parseTosMajor(raw?: string | null): number | null {
  const s = String(raw ?? '').trim()
  if (!s) return null
  const m = s.match(/(?:t\s*os|android)[\s._-]*(\d+)/i) ?? s.match(/^(\d+)/)
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) ? n : null
}

export function formatTosLabel(raw?: string | null): string {
  const major = parseTosMajor(raw)
  return major == null ? '' : `tOS${major}`
}

export function formatOsRange(fromOs?: string | null, toOs?: string | null): string {
  const from = formatTosLabel(fromOs)
  const to = formatTosLabel(toOs)
  if (from && to) return `${from} → ${to}`
  return from || to
}

const PROJECT_OS_SUFFIX = /[-_]?(?:android|t\s*os)[\s._-]*(\d+)(?:\.\d+)*$/i

/** X6879Android17 / X6879 + Android 17 → X6879-tOS17 */
export function formatPipelineProjectTitle(
  projectCode?: string | null,
  toOs?: string | null,
): string {
  const raw = String(projectCode ?? '').trim()
  if (!raw) return ''
  const suffix = raw.match(PROJECT_OS_SUFFIX)
  const code = suffix
    ? raw.slice(0, suffix.index).replace(/[-_]+$/, '') || raw
    : raw
  const fromSuffix = suffix ? Number(suffix[1]) : null
  const major = parseTosMajor(toOs) ?? (fromSuffix != null && Number.isFinite(fromSuffix) ? fromSuffix : null)
  if (major != null) return `${code}-tOS${major}`
  return code
}
