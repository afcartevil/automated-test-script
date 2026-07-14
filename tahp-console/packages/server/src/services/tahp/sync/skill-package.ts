/**
 * 本地 Skill 整包工具 — 与中心 easyadapter_bff/src/services/skill-package.ts 规则对齐。
 * 见 .cursor/skill-sync/PHASE-2.md
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'fs'
import { join, relative, sep } from 'path'
import AdmZip from 'adm-zip'
import { shortHashBuffer } from './hash'
import { tahpPaths } from '../paths'

const SKIP_DIR_NAMES = new Set(['node_modules', '__pycache__', '.git'])

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

export function getLocalPackageHash(id: string): string | null {
  if (!existsSync(join(localSkillDir(id), 'SKILL.md'))) return null
  const files = listLocalSkillFiles(id)
  if (!files.length) return null
  return computePackageHash(files)
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
}

/** 读取本地某 skill 的 requirements.txt hash（若存在） */
export function localRequirementsHash(id: string): string | null {
  const p = join(localSkillDir(id), 'requirements.txt')
  if (!existsSync(p)) return null
  return shortHashBuffer(readFileSync(p))
}
