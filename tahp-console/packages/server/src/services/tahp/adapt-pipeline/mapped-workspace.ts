/**
 * 映射盘 discover → Windows / Linux 路径对照。
 * 供前置、编译、Gerrit 共用，避免各阶段各自猜 Z:\ / /work/code/<user>。
 */
import { pickMappedRootFromDiscover } from '../code-pull'
import { normalizeMappedRoot } from '../code-pull/result-parse'
import { winMappedPathToLinuxWorkCode } from './win-path-to-linux'
import type { BuildContext } from './types'

export const DEFAULT_LINUX_MAPPED_ROOT = '/work/code/$(whoami)'

function asRecord(v: unknown): Record<string, unknown> | undefined {
  return v && typeof v === 'object' ? v as Record<string, unknown> : undefined
}

function linuxRootFromRecord(rec: Record<string, unknown>): string {
  return String(
    rec.inferred_remote_workspace
    || rec.inferredRemoteWorkspace
    || rec.linux_root
    || rec.linuxRoot
    || rec.remote_workspace
    || rec.remoteWorkspace
    || '',
  ).trim()
}

function mappedRootFromRecord(rec: Record<string, unknown>): string {
  return String(rec.mapped_root || rec.mappedRoot || rec.drive || rec.root || rec.path || '').trim()
}

function walkCandidates(raw: unknown): Record<string, unknown>[] {
  const obj = asRecord(raw)
  if (!obj) return []
  const nested = asRecord(obj.data)
  const lists = [
    obj.mapped_roots, obj.mappedRoots, obj.candidates, obj.runners,
    obj.approved_mapped_roots, obj.approvedMappedRoots,
    nested?.mapped_roots, nested?.mappedRoots, nested?.candidates, nested?.runners,
  ]
  const out: Record<string, unknown>[] = []
  for (const list of lists) {
    if (!Array.isArray(list)) continue
    for (const item of list) {
      if (typeof item === 'string' && item.trim()) {
        out.push({ mapped_root: item })
      } else {
        const rec = asRecord(item)
        if (rec) out.push(rec)
      }
    }
  }
  if (mappedRootFromRecord(obj) || linuxRootFromRecord(obj)) out.push(obj)
  if (nested && (mappedRootFromRecord(nested) || linuxRootFromRecord(nested))) out.push(nested)
  return out
}

/** 与 mapped_root 同一候选上的 Linux 映射根 */
export function pickLinuxRootFromDiscover(raw: unknown, mappedRoot?: string): string | undefined {
  const want = mappedRoot?.trim() ? normalizeMappedRoot(mappedRoot.trim()) : ''
  for (const rec of walkCandidates(raw)) {
    if (rec.approved_for_runner === false || rec.suspicious_runner_root === true) continue
    const mapped = mappedRootFromRecord(rec)
    const linux = linuxRootFromRecord(rec)
    if (!linux) continue
    if (!want || !mapped || normalizeMappedRoot(mapped) === want) return linux.replace(/\/+$/, '')
  }
  const obj = asRecord(raw)
  const direct = obj ? linuxRootFromRecord(obj) : ''
  return direct ? direct.replace(/\/+$/, '') : undefined
}

function slashPath(p: string): string {
  return p.replace(/\\/g, '/').replace(/\/+/g, '/')
}

function stripMappedPrefix(winPath: string, mappedRoot: string): string | null {
  const src = slashPath(winPath).replace(/^\/+/, '')
  const root = slashPath(normalizeMappedRoot(mappedRoot)).replace(/\/+$/, '')
  if (!root) return null
  if (src.toLowerCase().startsWith(root.toLowerCase())) {
    return src.slice(root.length).replace(/^\/+/, '')
  }
  return null
}

function stripUncShare(winPath: string): string | null {
  const n = winPath.replace(/\//g, '\\')
  const m = n.match(/^\\\\[^\\]+\\[^\\]+\\(.+)$/)
  return m ? slashPath(m[1]).replace(/^\/+/, '') : null
}

function stripLinuxUserRoot(linuxPath: string): string | null {
  const p = slashPath(linuxPath)
  const m = p.match(/^\/work\/code\/[^/]+\/(.+)$/)
  return m ? m[1] : null
}

/**
 * 把 Windows / UNC / 已是 Linux 的文件路径变成相对映射根的 POSIX 相对路径。
 */
export function winPathRelativeToMappedRoot(winPath: string, mappedRoot?: string): string {
  const raw = String(winPath ?? '').trim()
  if (!raw) throw new Error('路径为空')
  if (raw.startsWith('/work/code/')) {
    return stripLinuxUserRoot(raw) || raw.replace(/^\/+/, '')
  }
  if (mappedRoot?.trim()) {
    const stripped = stripMappedPrefix(raw, mappedRoot)
    if (stripped) return stripped
  }
  const unc = stripUncShare(raw)
  if (unc) return unc
  const drive = raw.match(/^([A-Za-z]):[\\/](.*)$/)
  if (drive) {
    return slashPath(drive[2]).replace(/^\/+|\/+$/g, '')
  }
  throw new Error(`无法换算为映射根相对路径：${raw}`)
}

export function joinLinuxWorkCode(linuxRoot: string, rel: string): string {
  const root = (linuxRoot.trim() || DEFAULT_LINUX_MAPPED_ROOT).replace(/\/+$/, '')
  const rest = slashPath(rel).replace(/^\/+/, '')
  return `${root}/${rest}`
}

/** Windows / UNC → Linux `/work/code/...`（$USER / $(whoami) 由远端展开） */
export function toLinuxWorkCodePath(
  winPath: string,
  opts?: { mappedRoot?: string; linuxRoot?: string },
): string {
  const raw = String(winPath ?? '').trim()
  if (raw.startsWith('/work/code/')) return slashPath(raw)
  const linuxRoot = opts?.linuxRoot?.trim() || DEFAULT_LINUX_MAPPED_ROOT
  try {
    const rel = winPathRelativeToMappedRoot(raw, opts?.mappedRoot)
    return joinLinuxWorkCode(linuxRoot, rel)
  } catch {
    return winMappedPathToLinuxWorkCode(raw).replace('/work/code/$USER/', `${linuxRoot.replace(/\/+$/, '')}/`)
  }
}

export function mapWinFilesToLinux(
  files: string[],
  opts?: { mappedRoot?: string; linuxRoot?: string },
): Array<{ win: string; linux: string; rel: string }> {
  const out: Array<{ win: string; linux: string; rel: string }> = []
  for (const win of files) {
    const t = String(win || '').trim()
    if (!t) continue
    const rel = winPathRelativeToMappedRoot(t, opts?.mappedRoot)
    out.push({
      win: t,
      rel,
      linux: joinLinuxWorkCode(opts?.linuxRoot || DEFAULT_LINUX_MAPPED_ROOT, rel),
    })
  }
  return out
}

/**
 * 补全 mapped_root / linux_root。discover JSON 可选；已有 mapped_root 时不再覆盖。
 */
export function fillMappedWorkspaceIfMissing(
  bc: BuildContext | undefined,
  disc?: Record<string, unknown> | null,
): BuildContext {
  const next: BuildContext = {
    mapped_root: '',
    workspace: '',
    variant: 'userdebug',
    ...(bc ?? {}),
  }
  if (!next.linux_root?.trim()) {
    const fromDisc = pickLinuxRootFromDiscover(disc ?? null, next.mapped_root)
    next.linux_root = fromDisc || DEFAULT_LINUX_MAPPED_ROOT
  }
  if (next.mapped_root?.trim()) return next
  const mapped = pickMappedRootFromDiscover(disc ?? null)
  if (mapped) {
    next.mapped_root = mapped
    const linux = pickLinuxRootFromDiscover(disc ?? null, mapped)
    if (linux) next.linux_root = linux
  }
  return next
}
