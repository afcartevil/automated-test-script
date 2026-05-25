import { readdir, readFile, cp } from 'fs/promises'
import { join, resolve, dirname, basename, relative } from 'path'
import { existsSync, mkdirSync, writeFileSync, rmSync } from 'fs'
import { createHash } from 'crypto'
import {
  readConfigYaml, updateConfigYaml,
  safeReadFile, extractDescription, listFilesRecursive, getHermesDir,
} from '../../services/config-helpers'
import { pinSkill } from '../../services/hermes/hermes-cli'
import { isPathWithin } from '../../services/hermes/hermes-path'
import { getSkillUsageStatsFromDb } from '../../db/hermes/sessions-db'
import { tahpPaths, hasTahpProject } from '../../services/tahp/paths'

/** 动态加载 adm-zip（避免未 npm install 时模块整体崩溃） */
function requireAdmZip(): any {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require('adm-zip')
  } catch {
    throw new Error('adm-zip 依赖未安装，请在 tahp-console 目录运行: npm install')
  }
}

/** TAHP 工程技能目录（skills/.claude/skills/） */
function getTahpSkillsDir(): string {
  return join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
}

/** 扫描 TAHP 工程技能目录，返回技能对象数组 */
async function scanTahpSkills(): Promise<any[]> {
  const tahpDir = getTahpSkillsDir()
  if (!hasTahpProject() || !existsSync(tahpDir)) return []
  const skills: any[] = []
  let entries: import('fs').Dirent[]
  try {
    entries = await readdir(tahpDir, { withFileTypes: true })
  } catch { return [] }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    const skillMd = await safeReadFile(join(tahpDir, entry.name, 'SKILL.md'))
    if (!skillMd) continue
    skills.push({
      name: entry.name,
      description: extractDescription(skillMd),
      enabled: true,
      source: 'tahp',
    })
  }
  skills.sort((a, b) => a.name.localeCompare(b.name))
  return skills
}

/** Read bundled manifest as a name→hash map from ~/.hermes/skills/.bundled_manifest */
function readBundledManifest(manifestContent: string | null): Map<string, string> {
  const map = new Map<string, string>()
  if (!manifestContent) return map
  for (const line of manifestContent.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const idx = trimmed.indexOf(':')
    if (idx === -1) continue
    const name = trimmed.slice(0, idx).trim()
    const hash = trimmed.slice(idx + 1).trim()
    if (name && hash) map.set(name, hash)
  }
  return map
}

/** Read hub-installed skill names from ~/.hermes/skills/.hub/lock.json */
function readHubInstalledNames(lockContent: string | null): Set<string> {
  if (!lockContent) return new Set()
  try {
    const data = JSON.parse(lockContent)
    if (data?.installed && typeof data.installed === 'object') {
      return new Set(Object.keys(data.installed))
    }
  } catch { /* ignore */ }
  return new Set()
}

/** Compute md5 hash of all files in a directory (mirrors Hermes _dir_hash), with in-memory cache */
const hashCache = new Map<string, { hash: string; mtime: number }>()
const HASH_CACHE_TTL = 60_000 // 1 minute

async function dirHash(directory: string): Promise<string> {
  const cached = hashCache.get(directory)
  if (cached && Date.now() - cached.mtime < HASH_CACHE_TTL) return cached.hash

  const hasher = createHash('md5')
  const files = await listFilesRecursive(directory, '')
  files.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
  for (const f of files) {
    hasher.update(f.path)
    const content = await readFile(join(directory, f.path))
    hasher.update(content)
  }
  const hash = hasher.digest('hex')
  hashCache.set(directory, { hash, mtime: Date.now() })
  return hash
}

/** Determine the source type of a skill */
function getSkillSource(
  dirName: string,
  bundledManifest: Map<string, string>,
  hubNames: Set<string>,
): 'builtin' | 'hub' | 'local' {
  if (bundledManifest.has(dirName)) return 'builtin'
  if (hubNames.has(dirName)) return 'hub'
  return 'local'
}

/** Read .usage.json as a name→stats map */
interface UsageStats { patch_count: number; use_count: number; view_count: number; pinned: boolean }
function readUsageStats(usageContent: string | null): Map<string, UsageStats> {
  const map = new Map<string, UsageStats>()
  if (!usageContent) return map
  try {
    const data = JSON.parse(usageContent)
    for (const [name, stats] of Object.entries(data)) {
      const s = stats as any
      map.set(name, { patch_count: s.patch_count ?? 0, use_count: s.use_count ?? 0, view_count: s.view_count ?? 0, pinned: !!s.pinned })
    }
  } catch { /* ignore */ }
  return map
}

async function findSkillDirByName(rootDir: string, skillName: string): Promise<string | null> {
  let entries: import('fs').Dirent[]
  try {
    entries = await readdir(rootDir, { withFileTypes: true })
  } catch {
    return null
  }

  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue

    const entryPath = join(rootDir, entry.name)
    const skillMd = await safeReadFile(join(entryPath, 'SKILL.md'))
    if (skillMd !== null) {
      if (entry.name === skillName) return entryPath
      // This is another skill root. Do not search inside its references/scripts.
      continue
    }

    const found = await findSkillDirByName(entryPath, skillName)
    if (found) return found
  }

  return null
}

/**
 * Scan for skills at different directory depths.
 *
 * Supports both:
 *   - Three-level: skills/<category>/<skill-name>/SKILL.md  (category is a container)
 *   - Two-level:   skills/<skill-name>/SKILL.md            (flat skill under "misc" category)
 *
 * Categories are identified by having a DESCRIPTION.md at the category level
 * or by containing subdirectories with SKILL.md (three-level pattern).
 * Skills without a parent category (flat skills) are grouped under the "misc" category.
 */
async function scanSkillsDir(skillsDir: string, bundledManifest: Map<string, string>, hubNames: Set<string>, disabledList: string[], usageStats: Map<string, UsageStats>) {
  const allEntries = await readdir(skillsDir, { withFileTypes: true })
  const dirNames = allEntries
    .filter(e => e.isDirectory() && !e.name.startsWith('.'))
    .map(e => e.name)

  // Classify directories: categories vs. flat skills
  const categoryDirs: { name: string; description: string }[] = []
  const flatSkills: { name: string; skillMd: string; source: string }[] = []

  for (const dirName of dirNames) {
    const catDir = join(skillsDir, dirName)
    const hasDesc = await safeReadFile(join(catDir, 'DESCRIPTION.md'))
    const hasSkillMd = await safeReadFile(join(catDir, 'SKILL.md'))
    const subEntries = await readdir(catDir, { withFileTypes: true })
    const subDirs = subEntries.filter(se => se.isDirectory())

    // Priority: SKILL.md at top level → flat skill
    //           DESCRIPTION.md or subdirs (without SKILL.md) → category
    if (hasSkillMd) {
      // Flat skill: has SKILL.md at the top level (two-level pattern)
      // Could also have subdirectories (references/, scripts/, etc.)
      flatSkills.push({
        name: dirName,
        skillMd: hasSkillMd,
        source: getSkillSource(dirName, bundledManifest, hubNames),
      })
    } else if (!!hasDesc || subDirs.length > 0) {
      // True category: has DESCRIPTION.md or subdirs, but no SKILL.md at top level
      const catDescription = hasDesc ? hasDesc.trim().split('\n')[0].replace(/^#+\s*/, '').slice(0, 100) : ''
      categoryDirs.push({ name: dirName, description: catDescription })
    }
  }

  // Build categories with their nested skills
  const categories: any[] = []

  for (const cat of categoryDirs) {
    const catDir = join(skillsDir, cat.name)
    const subEntries = await readdir(catDir, { withFileTypes: true })
    const skills: any[] = []
    // Recursively collect skills from subdirectories (supports nested sub-categories)
    async function collectSkills(dir: string): Promise<any[]> {
      const entries = await readdir(dir, { withFileTypes: true })
      const results: any[] = []
      for (const entry of entries) {
        if (!entry.isDirectory() || entry.name.startsWith('.')) continue
        const entryPath = join(dir, entry.name)
        const skillMd = await safeReadFile(join(entryPath, 'SKILL.md'))
        if (skillMd) {
          const source = getSkillSource(entry.name, bundledManifest, hubNames)
          let modified = false
          if (source === 'builtin') {
            const manifestHash = bundledManifest.get(entry.name)
            if (manifestHash) {
              const currentHash = await dirHash(entryPath)
              modified = currentHash !== manifestHash
            }
          }
          const usage = usageStats.get(entry.name)
          results.push({
            name: entry.name,
            description: extractDescription(skillMd),
            enabled: !disabledList.includes(entry.name),
            source,
            modified: modified || undefined,
            patchCount: usage?.patch_count,
            useCount: usage?.use_count,
            viewCount: usage?.view_count,
            pinned: usage?.pinned || undefined,
          })
        } else {
          // No SKILL.md — might be a sub-category container, recurse deeper
          const subResults = await collectSkills(entryPath)
          results.push(...subResults)
        }
      }
      return results
    }
    skills.push(...await collectSkills(catDir))
    if (skills.length > 0) {
      categories.push({ name: cat.name, description: cat.description, skills })
    }
  }

  // Group flat skills into a "misc" (雜項) category
  if (flatSkills.length > 0) {
    const miscSkills: any[] = []
    for (const fs of flatSkills) {
      const usage = usageStats.get(fs.name)
      miscSkills.push({
        name: fs.name,
        description: extractDescription(fs.skillMd),
        enabled: !disabledList.includes(fs.name),
        source: fs.source,
        modified: undefined,
        patchCount: usage?.patch_count,
        useCount: usage?.use_count,
        viewCount: usage?.view_count,
        pinned: usage?.pinned || undefined,
      })
    }
    miscSkills.sort((a: any, b: any) => a.name.localeCompare(b.name))
    categories.push({
      name: 'misc',
      description: '雜項',
      skills: miscSkills,
    })
  }

  categories.sort((a, b) => a.name.localeCompare(b.name))
  for (const cat of categories) { cat.skills.sort((a: any, b: any) => a.name.localeCompare(b.name)) }
  return categories
}

export async function list(ctx: any) {
  // TAHP Console 只展示工程技能（skills/.claude/skills/），不再使用 Hermes ~/.hermes/skills/。
  try {
    const tahpSkills = await scanTahpSkills()
    const categories = tahpSkills.length > 0
      ? [{ name: 'tahp-project', description: 'TAHP 工程技能', skills: tahpSkills }]
      : []
    ctx.body = { categories, archived: [] }
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { error: `Failed to read TAHP skills: ${err.message}` }
  }
}

export async function usageStats(ctx: any) {
  const rawDays = parseInt(String(ctx.query?.days ?? '7'), 10)
  const days = Number.isFinite(rawDays) && rawDays > 0 ? Math.min(rawDays, 365) : 7

  try {
    ctx.body = await getSkillUsageStatsFromDb(days)
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { error: `Failed to read skill usage stats: ${err.message}` }
  }
}

export async function toggle(ctx: any) {
  const { name, enabled } = ctx.request.body as { name?: string; enabled?: boolean }
  if (!name || typeof enabled !== 'boolean') {
    ctx.status = 400
    ctx.body = { error: 'Missing name or enabled flag' }
    return
  }
  try {
    await updateConfigYaml((config) => {
      if (!config.skills) config.skills = {}
      if (!Array.isArray(config.skills.disabled)) config.skills.disabled = []
      const disabled = config.skills.disabled as string[]
      const idx = disabled.indexOf(name)
      if (enabled) { if (idx !== -1) disabled.splice(idx, 1) }
      else { if (idx === -1) disabled.push(name) }
      return config
    })
    ctx.body = { success: true }
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { error: err.message }
  }
}

export async function listFiles(ctx: any) {
  const { category, skill } = ctx.params
  const hd = getHermesDir()

  // ── TAHP 工程技能：从工程目录读取 ──────────────────────────────────────────
  if (category === 'tahp-project') {
    const skillDir = join(getTahpSkillsDir(), skill)
    try {
      const allFiles = await listFilesRecursive(skillDir, '')
      const files = allFiles.filter((f: any) => f.path !== 'SKILL.md')
      ctx.body = { files }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { error: err.message }
    }
    return
  }

  const skillsDir = join(hd, 'skills', category)
  if (category === 'misc') {
    const skillDir = join(hd, 'skills', skill)
    try {
      const allFiles = await listFilesRecursive(skillDir, '')
      const files = allFiles.filter((f: any) => f.path !== 'SKILL.md')
      ctx.body = { files }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { error: err.message }
    }
    return
  }
  // Recursively find the actual skill directory (supports nested sub-categories like mlops/evaluation/lm-evaluation-harness)
  try {
    const skillDir = await findSkillDirByName(skillsDir, skill)
    if (!skillDir) {
      ctx.status = 404
      ctx.body = { error: 'Skill not found' }
      return
    }
    const allFiles = await listFilesRecursive(skillDir, '')
    const files = allFiles.filter((f: any) => f.path !== 'SKILL.md')
    ctx.body = { files }
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { error: err.message }
  }
}

export async function readFile_(ctx: any) {
  const filePath = (ctx.params as any).path
  const hd = getHermesDir()

  // ── TAHP 工程技能：从工程目录读取 ──────────────────────────────────────────
  if (filePath.startsWith('tahp-project/')) {
    const relativePath = filePath.slice('tahp-project/'.length)
    const tahpBase = getTahpSkillsDir()
    const fullPath = resolve(join(tahpBase, relativePath))
    if (!isPathWithin(fullPath, tahpBase)) {
      ctx.status = 403
      ctx.body = { error: 'Access denied' }
      return
    }
    const content = await safeReadFile(fullPath)
    if (content === null) {
      ctx.status = 404
      ctx.body = { error: 'File not found' }
      return
    }
    ctx.body = { content }
    return
  }

  // Handle 'misc' category: real skill dir is skills/<skill>, not skills/misc/<skill>
  let realPath = filePath
  if (filePath.startsWith('misc/')) {
    realPath = filePath.slice(5)
  }
  const fullPath = resolve(join(hd, 'skills', realPath))
  if (!isPathWithin(fullPath, join(hd, 'skills'))) {
    ctx.status = 403
    ctx.body = { error: 'Access denied' }
    return
  }
  let content = await safeReadFile(fullPath)
  if (content === null) {
    // Fallback: recursive search for nested skills (e.g., mlops/lm-evaluation-harness/SKILL.md
    // where actual path is mlops/evaluation/lm-evaluation-harness/SKILL.md)
    const parts = filePath.split('/')
    if (parts.length >= 2) {
      const category = parts[0]
      const skillName = parts[1]
      const restPath = parts.slice(2).join('/')
      const catDir = join(hd, 'skills', category)
      const skillDir = await findSkillDirByName(catDir, skillName)
      if (skillDir) {
        const resolvedPath = resolve(join(skillDir, restPath))
        if (isPathWithin(resolvedPath, skillDir)) {
          const nestedContent = await safeReadFile(resolvedPath)
          if (nestedContent !== null) {
            ctx.body = { content: nestedContent }
            return
          }
        }
      }
    }
    ctx.status = 404
    ctx.body = { error: 'File not found' }
    return
  }
  ctx.body = { content }
}

export async function pin_(ctx: any) {
  const { name, pinned } = ctx.request.body as { name?: string; pinned?: boolean }
  if (!name || typeof pinned !== 'boolean') {
    ctx.status = 400
    ctx.body = { error: 'Missing name or pinned flag' }
    return
  }
  try {
    await pinSkill(name, pinned)
    ctx.body = { success: true }
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { error: err.message }
  }
}

// ---------------------------------------------------------------------------
// ZIP 批量导入 — 通用 ZIP 结构检测算法
//
// 支持三种 ZIP 结构：
//   A. 多 skill 并排：  skill-a/SKILL.md  skill-b/SKILL.md
//   B. 单 skill 打包：  SKILL.md（skill 名来自 zipFilename）
//   C. 顶层包装目录：   all/skill-a/SKILL.md  all/skill-b/SKILL.md
//
// 检测逻辑：找所有 SKILL.md 路径 → 其父目录即为 skill 根，
// 提取时复制该目录下所有文件。
// ---------------------------------------------------------------------------

interface SkillPreviewItem {
  name: string
  description: string
  zipPrefix: string   // ZIP 内该 skill 目录的路径前缀（含末尾 /）
  exists: boolean     // 目标目录中是否已存在同名 skill
}

function detectSkillsInZip(zip: any, zipFilename: string): SkillPreviewItem[] {
  const tahpDir = getTahpSkillsDir()
  const items: SkillPreviewItem[] = []

  for (const entry of zip.getEntries()) {
    const name = entry.entryName.replace(/\\/g, '/')
    if (!name.endsWith('/SKILL.md') && name !== 'SKILL.md') continue

    let zipPrefix: string
    let skillName: string

    if (name === 'SKILL.md') {
      // 结构 B：SKILL.md 在 ZIP 根，用文件名（去 .zip 后缀）作为 skill 名
      zipPrefix = ''
      skillName = zipFilename.replace(/\.zip$/i, '').trim() || 'unnamed-skill'
    } else {
      // 结构 A / C：取 SKILL.md 的父目录
      const parts = name.split('/')
      // 去掉末尾的 SKILL.md，剩余是 skill 路径段
      parts.pop()
      skillName = parts[parts.length - 1]
      zipPrefix = parts.join('/') + '/'
    }

    const skillMd = entry.getData().toString('utf-8')
    items.push({
      name: skillName,
      description: extractDescription(skillMd),
      zipPrefix,
      exists: existsSync(join(tahpDir, skillName)),
    })
  }

  return items
}

/**
 * POST /api/hermes/skills/preview-import
 * Body: { zipData: string (base64), zipFilename: string }
 * Returns: { skills: SkillPreviewItem[] }
 */
export async function previewImport(ctx: any) {
  const { zipData, zipFilename = 'skills.zip' } = ctx.request.body as { zipData?: string; zipFilename?: string }
  if (!zipData) {
    ctx.status = 400
    ctx.body = { error: '缺少 zipData' }
    return
  }
  try {
    const AdmZip = requireAdmZip()
    const buffer = Buffer.from(zipData, 'base64')
    const zip = new AdmZip(buffer)
    const skills = detectSkillsInZip(zip, zipFilename)
    ctx.body = { skills }
  } catch (err: any) {
    ctx.status = 400
    ctx.body = { error: `ZIP 解析失败: ${err.message}` }
  }
}

/**
 * POST /api/hermes/skills/import
 * Body: { zipData: string (base64), zipFilename: string, overwrite: boolean }
 * Returns: { imported: string[], skipped: string[], errors: { name: string; error: string }[] }
 */
export async function importSkills(ctx: any) {
  const {
    zipData,
    zipFilename = 'skills.zip',
    overwrite = false,
  } = ctx.request.body as { zipData?: string; zipFilename?: string; overwrite?: boolean }

  if (!zipData) {
    ctx.status = 400
    ctx.body = { error: '缺少 zipData' }
    return
  }

  const tahpDir = getTahpSkillsDir()
  const imported: string[] = []
  const skipped: string[] = []
  const errors: { name: string; error: string }[] = []

  try {
    const AdmZip = requireAdmZip()
    const buffer = Buffer.from(zipData, 'base64')
    const zip = new AdmZip(buffer)
    const skillDefs = detectSkillsInZip(zip, zipFilename)

    // 确保目标目录存在
    mkdirSync(tahpDir, { recursive: true })

    for (const def of skillDefs) {
      const targetDir = join(tahpDir, def.name)
      if (def.exists && !overwrite) {
        skipped.push(def.name)
        continue
      }
      try {
        // 提取该 skill 对应的所有文件
        mkdirSync(targetDir, { recursive: true })
        for (const entry of zip.getEntries()) {
          if (entry.isDirectory) continue
          const entryPath = entry.entryName.replace(/\\/g, '/')
          // 对于 zipPrefix == '' 的单 skill，直接取所有文件
          if (def.zipPrefix !== '' && !entryPath.startsWith(def.zipPrefix)) continue
          const relativePath = def.zipPrefix === ''
            ? entryPath
            : entryPath.slice(def.zipPrefix.length)
          if (!relativePath) continue
          const targetFile = join(targetDir, relativePath)
          mkdirSync(dirname(targetFile), { recursive: true })
          writeFileSync(targetFile, entry.getData())
        }
        imported.push(def.name)
      } catch (err: any) {
        errors.push({ name: def.name, error: err.message })
      }
    }

    ctx.body = { imported, skipped, errors }
  } catch (err: any) {
    ctx.status = 400
    ctx.body = { error: `导入失败: ${err.message}` }
  }
}

// ---------------------------------------------------------------------------
// 本地路径扫描导入
//
// 递归扫描指定目录，找到所有包含 SKILL.md 的子目录（即 skill 根目录）。
// category = skill 目录相对于扫描根目录的父路径，支持多层嵌套：
//   root/skill-a/SKILL.md          → category=""
//   root/telephony/bug-analyzer/SKILL.md → category="telephony"
//   root/a/b/skill-x/SKILL.md      → category="a/b"
// ---------------------------------------------------------------------------

export interface PathScanItem {
  name: string
  description: string
  sourcePath: string  // 该 skill 目录在磁盘上的绝对路径
  category: string    // 相对于扫描根目录的父路径层级，空字符串=根级别
  exists: boolean     // TAHP skills 目录中是否已存在同名 skill
}

async function walkForSkills(
  dir: string,
  rootPath: string,
  tahpDir: string,
  results: PathScanItem[],
  depth = 0,
  maxDepth = 10,
): Promise<void> {
  if (depth > maxDepth) return
  let entries: import('fs').Dirent[]
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch { return }

  // 如果当前目录本身是一个 skill（含 SKILL.md），记录并停止递归
  const hasSkillMd = entries.some(e => e.isFile() && e.name === 'SKILL.md')
  if (hasSkillMd && depth > 0) {
    const skillName = basename(dir)
    const rel = relative(rootPath, dir).replace(/\\/g, '/')
    const parts = rel.split('/')
    const category = parts.length > 1 ? parts.slice(0, -1).join('/') : ''
    const skillMd = await safeReadFile(join(dir, 'SKILL.md'))
    results.push({
      name: skillName,
      description: skillMd ? extractDescription(skillMd) : '',
      sourcePath: resolve(dir),
      category,
      exists: existsSync(join(tahpDir, skillName)),
    })
    return
  }

  // 否则递归进入子目录
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.') || entry.name === 'node_modules') continue
    await walkForSkills(join(dir, entry.name), rootPath, tahpDir, results, depth + 1, maxDepth)
  }
}

/**
 * POST /api/hermes/skills/scan-path
 * Body: { sourcePath: string }
 * 返回扫描到的技能列表（不写磁盘）
 */
export async function scanPath(ctx: any) {
  const { sourcePath } = ctx.request.body as { sourcePath?: string }
  if (!sourcePath || !sourcePath.trim()) {
    ctx.status = 400
    ctx.body = { error: '缺少 sourcePath' }
    return
  }
  const absPath = resolve(sourcePath.trim())
  if (!existsSync(absPath)) {
    ctx.status = 400
    ctx.body = { error: `路径不存在: ${absPath}` }
    return
  }

  const tahpDir = getTahpSkillsDir()
  const results: PathScanItem[] = []

  // 特殊情况：sourcePath 本身就是一个 skill 目录
  const rootEntries = await readdir(absPath, { withFileTypes: true }).catch(() => [])
  const rootHasSkillMd = rootEntries.some((e: any) => e.isFile() && e.name === 'SKILL.md')
  if (rootHasSkillMd) {
    const skillName = basename(absPath)
    const skillMd = await safeReadFile(join(absPath, 'SKILL.md'))
    results.push({
      name: skillName,
      description: skillMd ? extractDescription(skillMd) : '',
      sourcePath: absPath,
      category: '',
      exists: existsSync(join(tahpDir, skillName)),
    })
  } else {
    await walkForSkills(absPath, absPath, tahpDir, results)
  }

  if (results.length === 0) {
    ctx.body = { skills: [], message: '未在该路径下检测到任何技能（需包含 SKILL.md 文件）' }
    return
  }
  results.sort((a, b) => `${a.category}/${a.name}`.localeCompare(`${b.category}/${b.name}`))
  ctx.body = { skills: results }
}

/**
 * POST /api/hermes/skills/import-from-path
 * Body: { skills: { name: string; sourcePath: string }[], overwrite?: boolean }
 * 将指定的 skill 目录拷贝到 TAHP skills 目录
 */
export async function importFromPath(ctx: any) {
  const { skills: skillList, overwrite = false } = ctx.request.body as {
    skills?: { name: string; sourcePath: string }[]
    overwrite?: boolean
  }
  if (!skillList || skillList.length === 0) {
    ctx.status = 400
    ctx.body = { error: '缺少 skills 列表' }
    return
  }

  const tahpDir = getTahpSkillsDir()
  mkdirSync(tahpDir, { recursive: true })

  const imported: string[] = []
  const skipped: string[] = []
  const errors: { name: string; error: string }[] = []

  for (const skill of skillList) {
    const srcAbs = resolve(skill.sourcePath)
    const targetDir = join(tahpDir, skill.name)

    if (existsSync(targetDir) && !overwrite) {
      skipped.push(skill.name)
      continue
    }
    if (!existsSync(srcAbs)) {
      errors.push({ name: skill.name, error: `源路径不存在: ${srcAbs}` })
      continue
    }
    try {
      if (existsSync(targetDir)) {
        rmSync(targetDir, { recursive: true, force: true })
      }
      await cp(srcAbs, targetDir, { recursive: true })
      imported.push(skill.name)
    } catch (err: any) {
      errors.push({ name: skill.name, error: err.message })
    }
  }

  ctx.body = { imported, skipped, errors }
}
