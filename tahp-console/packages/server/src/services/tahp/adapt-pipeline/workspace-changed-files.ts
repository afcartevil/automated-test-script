/**
 * 适配变更文件：绝对路径归一化 + 限制在 AOSP workspace 树下
 */
import { isAbsolute, join, normalize } from 'path'

/** mapped_root + workspace → AOSP 源码树绝对路径 */
export function resolveAospWorkspaceRoot(mappedRoot: string, workspace: string): string {
  const root = mappedRoot.trim()
  const ws = workspace.trim()
  if (!root) return ''
  if (!ws) return normalize(root)
  if (isAbsolute(ws)) return normalize(ws)
  return normalize(join(root, ws))
}

function normKey(p: string): string {
  return normalize(p).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

/** 判断 abs 是否落在 root 下（含 root 自身） */
export function isPathUnderRoot(absPath: string, root: string): boolean {
  const a = normKey(absPath)
  const r = normKey(root)
  if (!a || !r) return false
  return a === r || a.startsWith(`${r}/`)
}

/** 相对路径按 workspace 根解析；已是绝对路径则 normalize */
export function toAbsolutePath(file: string, workspaceRoot: string): string {
  const t = file.trim().replace(/^["']|["']$/g, '')
  if (!t) return ''
  if (isAbsolute(t)) return normalize(t)
  if (workspaceRoot.trim()) return normalize(join(workspaceRoot, t))
  return normalize(t)
}

export function mergeAbsolutePaths(
  paths: string[],
  workspaceRoot: string,
): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of paths) {
    const abs = toAbsolutePath(raw, workspaceRoot)
    if (!abs) continue
    const key = normKey(abs)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(abs)
  }
  return out
}

/**
 * 保留落在 AOSP workspace 树下的绝对路径（相对路径先按 workspace 解析）。
 * workspace 为空时退回 mapped_root。
 */
export function filterFilesUnderWorkspace(
  files: string[],
  mappedRoot: string,
  workspace: string,
): string[] {
  const tree = resolveAospWorkspaceRoot(mappedRoot, workspace)
  if (!tree) return []
  const abs = mergeAbsolutePaths(files, tree)
  return abs.filter(f => isPathUnderRoot(f, tree))
}

export function domainsWithWorkspaceChanges<T extends {
  domain_id: string
  enabled?: boolean
  status?: string
  changed_files?: string[]
}>(
  domains: T[],
  mappedRoot: string,
  workspace: string,
): Array<T & { changed_files: string[] }> {
  return domains
    .filter(d => d.enabled !== false && (!d.status || d.status === 'done'))
    .map(d => ({
      ...d,
      changed_files: filterFilesUnderWorkspace(d.changed_files ?? [], mappedRoot, workspace),
    }))
    .filter(d => d.changed_files.length > 0)
}
