/**
 * 本地 Skill 整包工具 — 与中心 easyadapter_bff/src/services/skill-package.ts 规则对齐。
 * 见 .cursor/skill-sync/PHASE-2.md
 *
 * 包 hash 使用 mtime+size 指纹缓存，避免 sync-status 每次全量读盘。
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'fs'
import { join, relative, sep } from 'path'
import AdmZip from 'adm-zip'
import { shortHashBuffer } from './hash'
import { tahpPaths } from '../paths'

/** 运行时/依赖目录不参与整包 hash 与 ZIP（含 jira-ops 本机工作区，可达数 GB） */
const SKIP_DIR_NAMES = new Set(['node_modules', '__pycache__', '.git', 'jira_workspace'])

export interface SkillFileMeta {
  rel_path: string
  hash: string
  size: number
}

function shouldSkipName(name: string): boolean {
  if (SKIP_DIR_NAMES.has(name)) return true
  if (name === '.env' || name.startsWith('.env.')) return true
  if (name.endsWith('.pyc')) return true
  return false
}

function toPosix(p: string): string {
  return p.split(sep).join('/')
}

export function localSkillDir(id: string): string {
  return join(tahpPaths.skillsDir, id)
}

export function listLocalSkillFiles(id: string): SkillFileMeta[] {
  const root = localSkillDir(id)
  if (!existsSync(root)) return []
  const out: SkillFileMeta[] = []
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (shouldSkipName(entry.name)) continue
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        walk(full)
        continue
      }
      if (!entry.isFile()) continue
      const buf = readFileSync(full)
      out.push({
        rel_path: toPosix(relative(root, full)),
        hash: shortHashBuffer(buf),
        size: buf.length,
      })
    }
  }
  walk(root)
  out.sort((a, b) => a.rel_path.localeCompare(b.rel_path))
  return out
}

export function computePackageHash(files: SkillFileMeta[]): string {
  const payload = files.map(f => `${f.rel_path}\0${f.hash}\n`).join('')
  return shortHashBuffer(Buffer.from(payload, 'utf-8'))
}

interface PkgHashCacheEntry {
  fingerprint: string
  hash: string
}

type PkgHashCacheFile = Record<string, PkgHashCacheEntry>

const memPkgHash = new Map<string, PkgHashCacheEntry>()
let diskCacheLoaded = false

function pkgHashCachePath(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return join(d, 'skill-pkg-hash-cache.json')
}

function loadDiskPkgHashCache(): void {
  if (diskCacheLoaded) return
  diskCacheLoaded = true
  try {
    const p = pkgHashCachePath()
    if (!existsSync(p)) return
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as PkgHashCacheFile
    for (const [id, ent] of Object.entries(raw || {})) {
      if (ent?.fingerprint && ent?.hash) memPkgHash.set(id, ent)
    }
  } catch { /* ignore */ }
}

let persistTimer: ReturnType<typeof setTimeout> | null = null
function schedulePersistPkgHashCache(): void {
  if (persistTimer) return
  persistTimer = setTimeout(() => {
    persistTimer = null
    try {
      const obj: PkgHashCacheFile = {}
      for (const [id, ent] of memPkgHash) obj[id] = ent
      writeFileSync(pkgHashCachePath(), JSON.stringify(obj), 'utf-8')
    } catch { /* ignore */ }
  }, 500)
}

/** 仅扫目录元数据（不读文件内容）生成指纹 */
export function getLocalPackageFingerprint(id: string): string | null {
  const root = localSkillDir(id)
  if (!existsSync(join(root, 'SKILL.md'))) return null
  const parts: string[] = []
  const walk = (dir: string) => {
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      return
    }
    entries.sort((a, b) => a.name.localeCompare(b.name))
    for (const entry of entries) {
      if (shouldSkipName(entry.name)) continue
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        walk(full)
        continue
      }
      if (!entry.isFile()) continue
      try {
        const st = statSync(full)
        const rel = toPosix(relative(root, full))
        parts.push(`${rel}\0${st.size}\0${Math.floor(st.mtimeMs)}`)
      } catch { /* skip */ }
    }
  }
  walk(root)
  if (!parts.length) return null
  parts.sort()
  return shortHashBuffer(Buffer.from(parts.join('\n'), 'utf-8'))
}

export function invalidateLocalPackageHashCache(id?: string): void {
  loadDiskPkgHashCache()
  if (id) memPkgHash.delete(id)
  else memPkgHash.clear()
  schedulePersistPkgHashCache()
}

/**
 * 整包 hash；指纹未变时直接复用缓存（status 热路径）。
 * force=true 时忽略缓存重算。
 */
export function getLocalPackageHash(id: string, force = false): string | null {
  if (!existsSync(join(localSkillDir(id), 'SKILL.md'))) return null
  loadDiskPkgHashCache()
  const fingerprint = getLocalPackageFingerprint(id)
  if (!fingerprint) return null
  if (!force) {
    const hit = memPkgHash.get(id)
    if (hit && hit.fingerprint === fingerprint) return hit.hash
  }
  const files = listLocalSkillFiles(id)
  if (!files.length) return null
  const hash = computePackageHash(files)
  memPkgHash.set(id, { fingerprint, hash })
  schedulePersistPkgHashCache()
  return hash
}

export function buildLocalSkillZipBuffer(id: string): Buffer {
  const root = localSkillDir(id)
  if (!existsSync(join(root, 'SKILL.md'))) throw new Error(`本地 Skill 不存在: ${id}`)
  const zip = new AdmZip()
  for (const f of listLocalSkillFiles(id)) {
    zip.addFile(f.rel_path, readFileSync(join(root, ...f.rel_path.split('/'))))
  }
  return zip.toBuffer()
}

export function applySkillZipToLocal(id: string, zipBuffer: Buffer): void {
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error('无效 skill id')
  const zip = new AdmZip(zipBuffer)
  const entries = zip.getEntries().filter(e => !e.isDirectory)
  const root = localSkillDir(id)
  if (existsSync(root)) rmSync(root, { recursive: true, force: true })
  mkdirSync(root, { recursive: true })

  for (const entry of entries) {
    let rel = toPosix(entry.entryName)
    if (rel.startsWith(`${id}/`)) rel = rel.slice(id.length + 1)
    if (!rel || rel.includes('..')) continue
    const parts = rel.split('/')
    if (parts.some(p => SKIP_DIR_NAMES.has(p) || shouldSkipName(p))) continue
    const dest = join(root, ...parts)
    mkdirSync(join(dest, '..'), { recursive: true })
    writeFileSync(dest, entry.getData())
  }
  if (!existsSync(join(root, 'SKILL.md'))) {
    throw new Error(`解压后缺少 SKILL.md: ${id}`)
  }
  invalidateLocalPackageHashCache(id)
}

export function applyInlineFilesToLocal(
  id: string,
  files: Array<{ rel_path: string; content_b64: string }>,
): void {
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error('无效 skill id')
  if (!files.some(f => f.rel_path === 'SKILL.md')) throw new Error('缺少 SKILL.md')
  const root = localSkillDir(id)
  if (existsSync(root)) rmSync(root, { recursive: true, force: true })
  mkdirSync(root, { recursive: true })
  for (const f of files) {
    if (!f.rel_path || f.rel_path.includes('..')) continue
    const parts = f.rel_path.split('/')
    if (parts.some(p => shouldSkipName(p))) continue
    const dest = join(root, ...parts)
    mkdirSync(join(dest, '..'), { recursive: true })
    writeFileSync(dest, Buffer.from(f.content_b64, 'base64'))
  }
  invalidateLocalPackageHashCache(id)
}

/** 读取本地某 skill 的 requirements.txt hash（若存在） */
export function localRequirementsHash(id: string): string | null {
  const p = join(localSkillDir(id), 'requirements.txt')
  if (!existsSync(p)) return null
  return shortHashBuffer(readFileSync(p))
}
