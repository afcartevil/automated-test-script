/**
 * 适配变更文件：只收录绝对路径（由适配 Agent 在文件修改清单中返回）。
 */
import { isAbsolute, normalize } from 'path'

function normKey(p: string): string {
  return normalize(p).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

/** Windows 盘符 / UNC 在非 win32 上也视为绝对路径（适配流水线按 Windows 盘符工作） */
export function isAbsFilePath(p: string): boolean {
  const t = p.trim()
  if (!t) return false
  if (isAbsolute(t)) return true
  if (/^[A-Za-z]:[\\/]/.test(t)) return true
  if (t.startsWith('\\\\')) return true
  return false
}

/** 去重绝对路径；相对路径丢弃（不再用 mapped_root / workspace 拼接） */
export function mergeAbsolutePaths(paths: string[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of paths) {
    const t = raw.trim().replace(/^["']|["']$/g, '')
    if (!t || !isAbsFilePath(t)) continue
    const abs = normalize(t)
    const key = normKey(abs)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(abs)
  }
  return out
}

/** 有绝对路径变更的域（供人工审核 / Gerrit） */
export function domainsWithChangedFiles<T extends {
  domain_id: string
  enabled?: boolean
  status?: string
  changed_files?: string[]
}>(
  domains: T[],
): Array<T & { changed_files: string[] }> {
  return domains
    .filter(d => d.enabled !== false && (!d.status || d.status === 'done'))
    .map(d => ({
      ...d,
      changed_files: mergeAbsolutePaths(d.changed_files ?? []),
    }))
    .filter(d => d.changed_files.length > 0)
}
