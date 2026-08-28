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
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'fs'
import { join, relative, sep } from 'path'
import AdmZip from 'adm-zip'
import { shortHashBuffer, shortHashBufferNormalized } from './hash'
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

/** 删除本机 Skill 目录（仅本机删除 / pull tombstone） */
export function removeLocalSkill(id: string): boolean {
  if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
    throw new Error('无效 skill id')
  }
  const root = localSkillDir(id)
  if (!existsSync(root)) return false
  rmSync(root, { recursive: true, force: true })
  return true
}

export function listLocalSkillFiles(id: string): SkillFileMeta[] {
  return listLocalSkillHashRows(id).map(f => ({
    rel_path: f.rel_path,
    hash: f.raw,
    size: f.size,
  }))
}

interface SkillHashRow {
  rel_path: string
  raw: string
  norm: string
  size: number
}

function listLocalSkillHashRows(id: string): SkillHashRow[] {
  const root = localSkillDir(id)
  if (!existsSync(root)) return []
  const out: SkillHashRow[] = []
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
        raw: shortHashBuffer(buf),
        norm: shortHashBufferNormalized(buf),
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
  norm?: string
}

type PkgHashCacheFile = {
  v: number
  entries: Record<string, PkgHashCacheEntry>
}

const PKG_HASH_CACHE_VERSION = 3

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
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as PkgHashCacheFile | Record<string, PkgHashCacheEntry>
    const entries = (raw as PkgHashCacheFile)?.v === PKG_HASH_CACHE_VERSION
      ? (raw as PkgHashCacheFile).entries
      : null
    if (!entries) return
    for (const [id, ent] of Object.entries(entries)) {
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
      const entries: Record<string, PkgHashCacheEntry> = {}
      for (const [id, ent] of memPkgHash) entries[id] = ent
      writeFileSync(pkgHashCachePath(), JSON.stringify({ v: PKG_HASH_CACHE_VERSION, entries }), 'utf-8')
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

export interface LocalPackageHashes {
  raw: string
  norm: string
}

/**
 * 整包 hash（原始字节 + 换行归一）。指纹未变时复用缓存。
 * raw 与中心 manifest 对齐；norm 用于仅换行不同时视为已对齐。
 */
export function getLocalPackageHashPair(id: string, force = false): LocalPackageHashes | null {
  if (!existsSync(join(localSkillDir(id), 'SKILL.md'))) return null
  loadDiskPkgHashCache()
  const fingerprint = getLocalPackageFingerprint(id)
  if (!fingerprint) return null
  if (!force) {
    const hit = memPkgHash.get(id)
    if (hit && hit.fingerprint === fingerprint && hit.norm) {
      return { raw: hit.hash, norm: hit.norm }
    }
  }
  const rows = listLocalSkillHashRows(id)
  if (!rows.length) return null
  const raw = computePackageHash(rows.map(f => ({ rel_path: f.rel_path, hash: f.raw, size: f.size })))
  const norm = computePackageHash(rows.map(f => ({ rel_path: f.rel_path, hash: f.norm, size: f.size })))
  memPkgHash.set(id, { fingerprint, hash: raw, norm })
  schedulePersistPkgHashCache()
  return { raw, norm }
}

export function getLocalPackageHash(id: string, force = false): string | null {
  return getLocalPackageHashPair(id, force)?.raw ?? null
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
  const zip = new AdmZip(zipBuffer)
  const entries = zip.getEntries().filter(e => !e.isDirectory)
  replaceSkillDir(id, staging => {
    for (const entry of entries) {
      let rel = toPosix(entry.entryName)
      if (rel.startsWith(`${id}/`)) rel = rel.slice(id.length + 1)
      if (!rel || rel.includes('..')) continue
      const parts = rel.split('/')
      if (parts.some(p => SKIP_DIR_NAMES.has(p) || shouldSkipName(p))) continue
      const dest = join(staging, ...parts)
      mkdirSync(join(dest, '..'), { recursive: true })
      writeFileSync(dest, entry.getData())
    }
  })
}

export function applyInlineFilesToLocal(
  id: string,
  files: Array<{ rel_path: string; content_b64: string }>,
): void {
  if (!files.some(f => f.rel_path === 'SKILL.md')) throw new Error('缺少 SKILL.md')
  replaceSkillDir(id, staging => {
    for (const f of files) {
      if (!f.rel_path || f.rel_path.includes('..')) continue
      const parts = f.rel_path.split('/')
      if (parts.some(p => shouldSkipName(p))) continue
      const dest = join(staging, ...parts)
      mkdirSync(join(dest, '..'), { recursive: true })
      writeFileSync(dest, Buffer.from(f.content_b64, 'base64'))
    }
  })
}

/** 先写入临时目录再替换，失败时尽量还原旧目录，避免先删后写丢稿。 */
function replaceSkillDir(id: string, populate: (staging: string) => void): void {
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error('无效 skill id')
  const root = localSkillDir(id)
  const staging = `${root}.incoming`
  const backup = `${root}.bak`
  try {
    if (existsSync(staging)) rmSync(staging, { recursive: true, force: true })
    mkdirSync(staging, { recursive: true })
    populate(staging)
    if (!existsSync(join(staging, 'SKILL.md'))) {
      throw new Error(`解压后缺少 SKILL.md: ${id}`)
    }
    if (existsSync(backup)) rmSync(backup, { recursive: true, force: true })
    if (existsSync(root)) renameSync(root, backup)
    try {
      renameSync(staging, root)
    } catch (err) {
      if (existsSync(backup) && !existsSync(root)) {
        try { renameSync(backup, root) } catch { /* 继续抛出原错误 */ }
      }
      throw err
    }
    if (existsSync(backup)) rmSync(backup, { recursive: true, force: true })
  } catch (err) {
    if (existsSync(staging)) {
      try { rmSync(staging, { recursive: true, force: true }) } catch { /* ignore */ }
    }
    throw err
  }
  invalidateLocalPackageHashCache(id)
}

/** 读取本地某 skill 的 requirements.txt hash（若存在） */
export function localRequirementsHash(id: string): string | null {
  const p = join(localSkillDir(id), 'requirements.txt')
  if (!existsSync(p)) return null
  return shortHashBuffer(readFileSync(p))
}
