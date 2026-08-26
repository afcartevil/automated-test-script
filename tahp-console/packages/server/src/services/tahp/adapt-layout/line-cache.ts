/**
 * 跃迁基线布局本机缓存（V13：断网沿用上次拉取，失败不清空）
 */
import { existsSync, mkdirSync } from 'fs'
import { dirname, join } from 'path'
import { safeFileStore } from '../../safe-file-store'
import { tahpPaths } from '../paths'

export interface CachedLineField {
  key: string
  label: string
  type: string
  required?: boolean
  placeholder?: string
  options?: Array<{ label: string; value: string }>
  defaultValue?: string
}

export interface CachedLineDomain {
  workspace_id: string
  domain_id: string
  revision: number
  fields: CachedLineField[]
  related_skills: string[]
  interaction_mode?: boolean
  updated_at?: string
}

export interface CachedLine {
  line_id: string
  from_os: string
  to_os: string
  domains: CachedLineDomain[]
}

export interface LineLayoutCache {
  updated_at: string
  from_center: boolean
  lines: CachedLine[]
}

function cachePath(): string {
  return join(tahpPaths.projectRoot, '.adapt-config', 'line-layouts', 'cache.json')
}

export function getLineLayoutCachePath(): string {
  return cachePath()
}

export async function readLineLayoutCache(): Promise<LineLayoutCache | null> {
  const path = cachePath()
  if (!existsSync(path)) return null
  try {
    const parsed = JSON.parse(await safeFileStore.readText(path)) as LineLayoutCache
    if (!Array.isArray(parsed.lines)) return null
    return parsed
  } catch {
    return null
  }
}

export async function writeLineLayoutCache(cache: LineLayoutCache): Promise<void> {
  const path = cachePath()
  mkdirSync(dirname(path), { recursive: true })
  await safeFileStore.writeText(path, JSON.stringify(cache, null, 2) + '\n', { backup: true })
}

export function pickDefaultLineId(cache: LineLayoutCache | null, preferred?: string): string | undefined {
  if (!cache?.lines.length) return undefined
  if (preferred && cache.lines.some(l => l.line_id === preferred)) return preferred
  return cache.lines[cache.lines.length - 1]?.line_id
}

export function findCachedDomain(
  cache: LineLayoutCache | null,
  lineId: string | undefined,
  workspaceId: string,
  domainId: string,
): CachedLineDomain | undefined {
  if (!cache || !lineId) return undefined
  const line = cache.lines.find(l => l.line_id === lineId)
  return line?.domains.find(d => d.workspace_id === workspaceId && d.domain_id === domainId)
}

export function mapPrereqTypeToLayout(type: string): 'text' | 'select' | 'textarea' | 'checklist' {
  if (type === 'textarea' || type === 'table') return 'textarea'
  if (type === 'select' || type === 'multiselect') return 'select'
  if (type === 'checklist') return 'checklist'
  return 'text'
}

export function cachedFieldsToLayout(fields: CachedLineField[]): Array<{
  name: string
  label: string
  type: 'text' | 'select' | 'textarea' | 'checklist'
  required: boolean
  placeholder?: string
  options?: Array<{ label: string; value: string }>
  defaultValue?: string
}> {
  return fields.map(f => ({
    name: f.key,
    label: f.label,
    type: mapPrereqTypeToLayout(f.type),
    required: !!f.required,
    placeholder: f.placeholder,
    options: f.options,
    defaultValue: f.defaultValue,
  }))
}

export async function savePulledLines(lines: CachedLine[]): Promise<LineLayoutCache> {
  const cache: LineLayoutCache = {
    updated_at: new Date().toISOString(),
    from_center: true,
    lines,
  }
  await writeLineLayoutCache(cache)
  return cache
}

function asCachedLines(raw: unknown): CachedLine[] {
  if (!raw || typeof raw !== 'object') return []
  const lines = (raw as { lines?: unknown }).lines
  if (!Array.isArray(lines)) return []
  return lines.map((line) => {
    const rec = (line || {}) as Record<string, unknown>
    const domains = Array.isArray(rec.domains) ? rec.domains : []
    return {
      line_id: String(rec.line_id || ''),
      from_os: String(rec.from_os || ''),
      to_os: String(rec.to_os || ''),
      domains: domains.map((d) => {
        const domain = (d || {}) as Record<string, unknown>
        const fields = Array.isArray(domain.fields) ? domain.fields : []
        return {
          workspace_id: String(domain.workspace_id || ''),
          domain_id: String(domain.domain_id || ''),
          revision: Number(domain.revision) || 0,
          related_skills: Array.isArray(domain.related_skills) ? domain.related_skills.map(String) : [],
          interaction_mode: domain.interaction_mode === true,
          updated_at: typeof domain.updated_at === 'string' ? domain.updated_at : undefined,
          fields: fields.map((f) => {
            const field = (f || {}) as Record<string, unknown>
            return {
              key: String(field.key || field.name || ''),
              label: String(field.label || field.key || ''),
              type: String(field.type || 'text'),
              required: field.required === true,
              placeholder: typeof field.placeholder === 'string' ? field.placeholder : undefined,
              options: Array.isArray(field.options)
                ? field.options.map((o) => {
                    const opt = (o || {}) as Record<string, unknown>
                    return { label: String(opt.label || opt.value || ''), value: String(opt.value || '') }
                  })
                : undefined,
            }
          }).filter(f => f.key),
        }
      }).filter(d => d.workspace_id && d.domain_id),
    }
  }).filter(l => l.line_id)
}

export async function pullOrReadLineLayouts(fetcher?: () => Promise<unknown>): Promise<{
  cache: LineLayoutCache | null
  pulled: boolean
  error?: string
}> {
  const existing = await readLineLayoutCache()
  if (!fetcher) {
    return { cache: existing, pulled: false, error: existing ? undefined : '中心未配置' }
  }
  try {
    const raw = await fetcher()
    if (!raw || typeof raw !== 'object' || !Array.isArray((raw as { lines?: unknown }).lines)) {
      return {
        cache: existing,
        pulled: false,
        error: '中心返回的跃迁基线格式无效',
      }
    }
    const rawLines = (raw as { lines: unknown[] }).lines
    const lines = asCachedLines(raw)
    if (rawLines.length > 0 && lines.length === 0) {
      return {
        cache: existing,
        pulled: false,
        error: '中心返回的跃迁基线无法解析',
      }
    }
    const cache = await savePulledLines(lines)
    return { cache, pulled: true }
  } catch (err) {
    return {
      cache: existing,
      pulled: false,
      error: err instanceof Error ? err.message : String(err),
    }
  }
}
