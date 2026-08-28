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

/** 工具 preview / 日志截断产生的伪路径（如 Z:\\...\\AutoDialer\\age…） */
export function isTruncatedChangedFilePath(path: string): boolean {
  const t = path.trim()
  return t.endsWith('…') || t.endsWith('...') || /\u2026/.test(t)
}

/** 去重绝对路径；相对路径丢弃（不再用 mapped_root / workspace 拼接） */
export function mergeAbsolutePaths(paths: string[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of paths) {
    const t = raw.trim().replace(/^["']|["']$/g, '')
    if (!t || !isAbsFilePath(t) || isTruncatedChangedFilePath(t)) continue
    const abs = normalize(t)
    const key = normKey(abs)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(abs)
  }
  return out
}

/** 流水线统计/Gerrit 提交候选：排除测试产物、Skill 目录、报告等不应入库的路径 */
const EXCLUDED_CHANGED_FILE_PATTERNS: RegExp[] = [
  /[\\/]AAA_TEMP[\\/]/i,
  /[\\/]reports[\\/]/i,
  /[\\/]\.tmp[\\/]/i,
  /[\\/]skills[\\/]\.claude[\\/]skills[\\/]/i,
  /[\\/]\.cursor[\\/]skills[\\/]/i,
  /[\\/]prompt-logs[\\/]/i,
  /[\\/]\.tahp[\\/]/i,
  /[\\/]et -u$/i,
  /,\s*old_string=/i,
]

export function isExcludedPipelineChangedFile(path: string): boolean {
  const norm = path.replace(/\\/g, '/')
  return EXCLUDED_CHANGED_FILE_PATTERNS.some(re => re.test(norm))
}

/** 过滤不应计入变更统计 / 提交的文件路径 */
export function filterPipelineChangedFiles(paths: string[]): string[] {
  return mergeAbsolutePaths(paths).filter(p => !isExcludedPipelineChangedFile(p))
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
      changed_files: filterPipelineChangedFiles(d.changed_files ?? []),
    }))
    .filter(d => d.changed_files.length > 0)
}
