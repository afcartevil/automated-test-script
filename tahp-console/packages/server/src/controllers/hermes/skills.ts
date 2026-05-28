import { readdir, readFile, cp, stat, writeFile } from 'fs/promises'
import { join, resolve, dirname, basename, relative } from 'path'
import { existsSync, mkdirSync, writeFileSync, rmSync } from 'fs'
import { createHash } from 'crypto'
import { execFile } from 'child_process'
import { promisify } from 'util'
import {
  readConfigYaml, updateConfigYaml,
  safeReadFile, extractDescription, listFilesRecursive, getHermesDir,
} from '../../services/config-helpers'
import { pinSkill } from '../../services/hermes/hermes-cli'
import { isPathWithin } from '../../services/hermes/hermes-path'
import { getSkillUsageStatsFromDb } from '../../db/hermes/sessions-db'
import { tahpPaths, hasTahpProject } from '../../services/tahp/paths'

const execFileAsync = promisify(execFile)

/** 动态加载 adm-zip（避免未 npm install 时模块整体崩溃） */
function requireAdmZip(): any {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require('adm-zip')
  } catch {
    throw new Error('adm-zip 依赖未安装，请在 tahp-console 目录运行: npm install')
  }
}

/** 解析 SKILL.md 顶部 YAML frontmatter（--- ... ---） */
function parseFrontmatter(content: string): Record<string, string> {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) return {}
  const result: Record<string, string> = {}
  for (const line of match[1].split(/\r?\n/)) {
    const colonIdx = line.indexOf(':')
    if (colonIdx === -1) continue
    const key = line.slice(0, colonIdx).trim()
    const value = line.slice(colonIdx + 1).trim().replace(/^["']|["']$/g, '')
    if (key) result[key] = value
  }
  return result
}

/**
 * 向 SKILL.md 的 frontmatter 中注入指定字段（如已存在则覆盖），不存在 frontmatter 则新建
 */
async function injectFrontmatterFields(filePath: string, fields: Record<string, string>): Promise<void> {
  let content = ''
  try { content = await readFile(filePath, 'utf-8') } catch { return }
  const fmMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---(\r?\n|$)/)
  let body = content
  let fmLines: string[] = []
  let rest = content
  if (fmMatch) {
    fmLines = fmMatch[1].split(/\r?\n/)
    rest = content.slice(fmMatch[0].length)
  }
  // 替换已有字段或追加
  for (const [key, value] of Object.entries(fields)) {
    const idx = fmLines.findIndex(l => l.startsWith(key + ':'))
    const line = `${key}: "${value.replace(/"/g, '\\"')}"`
    if (idx >= 0) fmLines[idx] = line
    else fmLines.push(line)
  }
  body = `---\n${fmLines.join('\n')}\n---\n${rest}`
  await writeFile(filePath, body, 'utf-8')
}

/** 运行 git 命令，失败时返回 null */
async function gitExec(cwd: string, args: string[]): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync('git', args, { cwd, timeout: 15000, windowsHide: true })
    return stdout.trim()
  } catch {
    return null
  }
}

/** TAHP 工程技能目录（skills/.claude/skills/） */
function getTahpSkillsDir(): string {
  return join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
}

/**
 * 一次性批量获取 skills 目录下所有子目录的最后 commit 时间戳（ms）。
 * 只跑一次 git log，解析输出得到 name → timestamp 映射，避免 N 次 git 进程。
 * 格式: git log --format="COMMIT %at" --name-only skills/.claude/skills/
 */
async function batchGetSkillUpdatedAt(tahpDir: string): Promise<Map<string, number>> {
  const projectRoot = tahpPaths.projectRoot
  const relBase = relative(projectRoot, tahpDir).replace(/\\/g, '/') + '/'
  const map = new Map<string, number>()

  // 单次 git log：最近 1000 条 commit 里找每个 skill 的最新修改时间
  // --max-count 防止大仓历史过长导致超时
  const output = await gitExec(projectRoot, [
    'log', '--format=COMMIT %at', '--name-only', '--max-count=1000', '--', relBase,
  ])

  if (output) {
    let currentTs = 0
    for (const line of output.split(/\r?\n/)) {
      if (line.startsWith('COMMIT ')) {
        currentTs = parseInt(line.slice(7), 10) * 1000
      } else if (line.startsWith(relBase)) {
        // 取 relBase 后的第一段路径作为 skill name
        const rest = line.slice(relBase.length)
        const skillName = rest.split('/')[0]
        if (skillName && !map.has(skillName)) {
          // 第一次出现的 commit 就是最新的（git log 是从新到旧）
          map.set(skillName, currentTs)
        }
      }
    }
  }

  return map
}

// ─── 规范化映射：英文 key → 中文 display（skill 系统内 canonical 值为中文） ──────
const FUNC_TYPE_NORMALIZE: Record<string, string> = {
  'bug_analysis':       'AI故障分析',
  'code_adaptation':    'AI自动化适配',
  'version_adaptation': 'AI自动化适配',
  'carrier_porting':    'AI自动化适配',
  'self_check':         'AI自检工具',
  'ai_self_check':      'AI自检工具',
  // 以下已是中文 canonical，透传
  'AI故障分析':    'AI故障分析',
  'AI自动化适配':  'AI自动化适配',
  'AI自检工具':    'AI自检工具',
}
const MODULE_NORMALIZE: Record<string, string> = {
  'telephony':     '通信',
  'kernel-driver': '驱动',
  'kernel_driver': '驱动',
  'power-mgmt':    '功耗',
  'power_mgmt':    '功耗',
  'shared':        '通用',
  'common':        '通用',
  // 以下已是中文 canonical，透传
  '通信': '通信', '驱动': '驱动', '内核': '内核', '功耗': '功耗', '通用': '通用',
}

/** 将 funcType 原始值规范化为中文 display 名（不命中则原样返回） */
export function normalizeFuncType(raw: string): string {
  return FUNC_TYPE_NORMALIZE[raw.trim()] ?? raw.trim()
}

/** 将 module/group 原始值规范化为中文 display 名（不命中则原样返回） */
export function normalizeModule(raw: string): string {
  return MODULE_NORMALIZE[raw.trim()] ?? raw.trim()
}

/**
 * 根据 skill 目录名推断 funcType 和 category。
 * 先查精准映射表，再用前缀规则兜底。
 * 返回 null 表示未命中，调用方应保留 frontmatter 已有值。
 */
function inferSkillClassification(name: string): { funcType: string; category: string } | null {
  if (SKILL_CLASSIFY_MAP[name]) {
    const [ft, cat] = SKILL_CLASSIFY_MAP[name]
    return { funcType: ft, category: cat }
  }
  for (const [prefix, ft, cat] of SKILL_PREFIX_RULES) {
    if (name.startsWith(prefix)) return { funcType: ft, category: cat }
  }
  return null
}

// ── 扫描结果内存缓存（TTL = 30s，避免重复扫描） ─────────────────────────────
let _skillsCache: { data: any[]; ts: number } | null = null
const SKILLS_CACHE_TTL = 30_000

function invalidateSkillsCache() { _skillsCache = null }

/**
 * 技能描述文件的候选名称，按优先级依次尝试。
 * 不同 skill 目录使用不同文件名作为主文档：
 *   - SKILL.md (含 YAML frontmatter，最规范)
 *   - ANALYSIS_STEPS.md (故障分析类)
 *   - README.md
 *   - reference.md
 */
const SKILL_MAIN_FILES = ['SKILL.md', 'ANALYSIS_STEPS.md', 'README.md', 'reference.md']

/** 在 skill 目录中查找第一个存在的主文档，返回 { file, content } 或 null */
async function findSkillMainFile(
  skillDir: string,
): Promise<{ file: string; content: string } | null> {
  for (const fname of SKILL_MAIN_FILES) {
    const content = await safeReadFile(join(skillDir, fname))
    if (content) return { file: fname, content }
  }
  return null
}

/** 扫描 TAHP 工程技能目录，返回技能对象数组（并发读取 + 批量 git 查询） */
async function scanTahpSkills(): Promise<any[]> {
  // 命中缓存直接返回
  if (_skillsCache && Date.now() - _skillsCache.ts < SKILLS_CACHE_TTL) {
    return _skillsCache.data
  }
  const tahpDir = getTahpSkillsDir()
  if (!hasTahpProject() || !existsSync(tahpDir)) return []

  let entries: import('fs').Dirent[]
  try {
    entries = await readdir(tahpDir, { withFileTypes: true })
  } catch { return [] }

  const skillEntries = entries.filter(e => e.isDirectory() && !e.name.startsWith('.'))

  // ── 1. 并发读取主文档 + 批量 git 时间戳 ──────────────────────────────────
  // 每个 skill 按 SKILL_MAIN_FILES 优先级找到第一个存在的文件
  const [mainFileResults, updatedAtMap] = await Promise.all([
    Promise.all(skillEntries.map(entry => findSkillMainFile(join(tahpDir, entry.name)))),
    // ── 2. 一次性批量 git 查询（替代 N 次 git log）───────────────────────
    batchGetSkillUpdatedAt(tahpDir),
  ])

  const skills: any[] = []

  for (let i = 0; i < skillEntries.length; i++) {
    const entry = skillEntries[i]
    const mainFile = mainFileResults[i]

    // 没有任何主文档的目录（如纯资源目录）仍保留，只是描述为空
    const fm = mainFile ? parseFrontmatter(mainFile.content) : {}
    const rawDescription = mainFile ? (fm.description || extractDescription(mainFile.content)) : ''

    // ── 3. 分类：frontmatter > 精准映射表 > 前缀规则 ─────────────────────
    let funcType = fm.funcType || fm.func_type || ''
    let group    = fm.category || fm.group || fm.module || ''
    if (!funcType || !group) {
      const inferred = inferSkillClassification(entry.name)
      if (inferred) {
        if (!funcType) funcType = inferred.funcType
        if (!group)    group    = inferred.category
      }
    }
    // normalize 英文 key → 中文 display（统一 canonical 值）
    if (funcType) funcType = normalizeFuncType(funcType)
    if (group)    group    = normalizeModule(group)

    // ── 4. 时间戳：git 批量结果 > 文件 mtime ─────────────────────────────
    let updatedAt = updatedAtMap.get(entry.name) ?? 0
    if (!updatedAt && mainFile) {
      try {
        const s = await stat(join(tahpDir, entry.name, mainFile.file))
        updatedAt = s.mtimeMs
      } catch { /* ignore */ }
    }

    skills.push({
      name: entry.name,
      description: rawDescription,
      funcType,
      group,
      version: fm.version || '',
      updatedAt,
      enabled: true,
      source: 'tahp',
    })
  }

  skills.sort((a, b) => a.name.localeCompare(b.name))
  _skillsCache = { data: skills, ts: Date.now() }
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
  // TAHP Console 技能统一归入 'tahp-project' 分类（供 SkillDetail 路径解析），
  // group / funcType 字段供客户端侧边栏分组展示
  try {
    const tahpSkills = await scanTahpSkills()

    // 所有 TAHP 技能统一放在 tahp-project category 下，保证 readFile_ 路径正确
    const categories = tahpSkills.length > 0 ? [{
      name: 'tahp-project',
      description: 'TAHP 工程技能',
      skills: tahpSkills,
    }] : []

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

    if (imported.length > 0) invalidateSkillsCache()
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
    skills?: { name: string; sourcePath: string; category?: string }[]
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

      // 把来源目录层级（funcType / group）注入到目标 SKILL.md
      // skill.category 形如 "AI故障分析/内核"，第一段=功能类型，第二段=业务模块
      if (skill.category) {
        const parts = skill.category.split('/')
        const funcType = parts[0] || ''
        const group = parts[1] || ''
        const targetSkillMd = join(targetDir, 'SKILL.md')
        if (existsSync(targetSkillMd)) {
          const fields: Record<string, string> = {}
          if (funcType) fields.funcType = funcType
          if (group) fields.category = group
          await injectFrontmatterFields(targetSkillMd, fields)
        }
      }

      imported.push(skill.name)
    } catch (err: any) {
      errors.push({ name: skill.name, error: err.message })
    }
  }

  if (imported.length > 0) invalidateSkillsCache()
  ctx.body = { imported, skipped, errors }
}

// ---------------------------------------------------------------------------
// 一键回填分类（backfill funcType / category）
// ---------------------------------------------------------------------------

/**
 * 精准映射表：skill 目录名 → (funcType, category)
 * 直接从 E:\底软集成skills\skills 三级目录结构提取，覆盖所有已知 skill。
 */
const SKILL_CLASSIFY_MAP: Record<string, [string, string]> = {
  // AI 故障分析 / 内核
  'android-bootup-issue-log-analysis':          ['AI故障分析', '内核'],
  'android-hang-log-analysis':                  ['AI故障分析', '内核'],
  'android-hwr-hwt-log-analysis':               ['AI故障分析', '内核'],
  'android-ke-log-analysis':                    ['AI故障分析', '内核'],
  'android-kernel-api-dump-log-analysis':       ['AI故障分析', '内核'],
  'android-kerneldb-extract':                   ['AI故障分析', '内核'],
  'android-kerneltne-extract':                  ['AI故障分析', '内核'],
  'android-unisoc-kernel-crash-log-analysis':   ['AI故障分析', '内核'],
  // AI 故障分析 / 驱动
  'DRV_TP_LargeArea':                           ['AI故障分析', '驱动'],
  'DRV_Vibrator_VibrationFault':                ['AI故障分析', '驱动'],
  'BSP_sensor_ps_anti_touch':                   ['AI故障分析', '驱动'],
  'android-fingerprint-log-analysis':           ['AI故障分析', '驱动'],
  'android-sys-usb-config-gadget':              ['AI故障分析', '驱动'],
  'audio-bug-solver':                           ['AI故障分析', '驱动'],
  'mediatek-mtu3-xhci-host':                    ['AI故障分析', '驱动'],
  'mediatek-pd-typec-analysis':                 ['AI故障分析', '驱动'],
  'mediatek-pd-typec-protocol-6-1':             ['AI故障分析', '驱动'],
  'mediatek-pd-typec-protocol-6-12':            ['AI故障分析', '驱动'],
  'mtk-backlight-abnormal-log-analysis':        ['AI故障分析', '驱动'],
  'mtk-battery-gauge-stack':                    ['AI故障分析', '驱动'],
  'mtk-panel-load-abnormal-log-analysis':       ['AI故障分析', '驱动'],
  'mtk-screen-tearing-abnormal-log-analysis':   ['AI故障分析', '驱动'],
  'mtk-suspend-resume-abnormal-log-analysis':   ['AI故障分析', '驱动'],
  'mtk-tp-fod-log-analysis':                    ['AI故障分析', '驱动'],
  'mtk-tp-gesture-log-analysis':                ['AI故障分析', '驱动'],
  'mtk-tp-touch-log-analysis':                  ['AI故障分析', '驱动'],
  'mtk-usb20-musb-otg-core':                    ['AI故障分析', '驱动'],
  'mtu3-usb-device-core':                       ['AI故障分析', '驱动'],
  'power-usb-cross-stack-triage':               ['AI故障分析', '驱动'],
  'qualcomm-adsp-charging-analysis':            ['AI故障分析', '驱动'],
  'qualcomm-adsp-power-usb-triage':             ['AI故障分析', '驱动'],
  'qualcomm-adsp-usb-pd-analysis':              ['AI故障分析', '驱动'],
  'qualcomm-kernel-adsp-bridge':                ['AI故障分析', '驱动'],
  'qualcomm-msm-kernel-charging-supply-analysis':     ['AI故障分析', '驱动'],
  'qualcomm-msm-kernel-dwc3-role-gadget-analysis':    ['AI故障分析', '驱动'],
  'qualcomm-msm-kernel-usb-ucsi-analysis':      ['AI故障分析', '驱动'],
  'sensor-als-autobrightness':                  ['AI故障分析', '驱动'],
  'sensor-als-first-report':                    ['AI故障分析', '驱动'],
  'transsion-batt-high-temp-low-cv-eoc':        ['AI故障分析', '驱动'],
  'transsion-bc12-type-detect':                 ['AI故障分析', '驱动'],
  'transsion-charger-orchestrator':             ['AI故障分析', '驱动'],
  'transsion-dcp-fastcharge-probe':             ['AI故障分析', '驱动'],
  'transsion-extcon-usb-role-bridge':           ['AI故障分析', '驱动'],
  'transsion-pe5-vi-tuning':                    ['AI故障分析', '驱动'],
  'transsion-tcpc-adapter':                     ['AI故障分析', '驱动'],
  'transsion-wireless-bypass-fan':              ['AI故障分析', '驱动'],
  'usb-pd-platform-router':                     ['AI故障分析', '驱动'],
  'video-playback-log-analysis':                ['AI故障分析', '驱动'],
  // AI 故障分析 / 功耗
  'bug-scenario-power-standby':                 ['AI故障分析', '功耗'],
  'power-leak-detector':                        ['AI故障分析', '功耗'],
  'power-backlight-app-optimization':           ['AI故障分析', '功耗'],
  'power-backlight-auto-anomaly':               ['AI故障分析', '功耗'],
  'power-backlight-camera-video':               ['AI故障分析', '功耗'],
  'power-backlight-hbm-enter':                  ['AI故障分析', '功耗'],
  'power-backlight-manual-adjust':              ['AI故障分析', '功耗'],
  'power-backlight-policy-factors':             ['AI故障分析', '功耗'],
  'power-display-double-tap-wake':              ['AI故障分析', '功耗'],
  'power-display-notification-wake':            ['AI故障分析', '功耗'],
  'power-display-power-key-screen':             ['AI故障分析', '功耗'],
  'power-display-timeout-screen-off':           ['AI故障分析', '功耗'],
  'power-sensor-proximity-brightness':          ['AI故障分析', '功耗'],
  // AI 故障分析 / 通信
  'com-comm-analysis-foundation':               ['AI故障分析', '通信'],
  'com-comm-sop-source-archive':                ['AI故障分析', '通信'],
  'com-data-datasetupfail':                     ['AI故障分析', '通信'],
  'com-data-dataunstable':                      ['AI故障分析', '通信'],
  'com-data-ddsswitchfail':                     ['AI故障分析', '通信'],
  'com-data-sim-contact-add':                   ['AI故障分析', '通信'],
  'com-data-sim-recognition':                   ['AI故障分析', '通信'],
  'com-dstall-datastall':                       ['AI故障分析', '通信'],
  'com-network-roamingstate':                   ['AI故障分析', '通信'],
  'com-network-signalabnormal':                 ['AI故障分析', '通信'],
  'com-network-timezonewrong':                  ['AI故障分析', '通信'],
  'com-sim-apnchange':                          ['AI故障分析', '通信'],
  'com-sim-ussdflow':                           ['AI故障分析', '通信'],
  'com-sim-ussdwrongtext':                      ['AI故障分析', '通信'],
  'com-sms-smsappui':                           ['AI故障分析', '通信'],
  'com-voice-call-dialing':                     ['AI故障分析', '通信'],
  'com-voice-ecc-emergency':                    ['AI故障分析', '通信'],
  'mtk-call-dialfail':                          ['AI故障分析', '通信'],
  'mtk-call-emergencynumber':                   ['AI故障分析', '通信'],
  'mtk-call-incominganswerfail':                ['AI故障分析', '通信'],
  'mtk-fl16-flashcall16':                       ['AI故障分析', '通信'],
  'mtk-modem-ee-modemee':                       ['AI故障分析', '通信'],
  'mtk-network-dataslow':                       ['AI故障分析', '通信'],
  'mtk-sim-operatorname':                       ['AI故障分析', '通信'],
  'mtk-sim-simdetect':                          ['AI故障分析', '通信'],
  'mtk-sim-statusbaricon':                      ['AI故障分析', '通信'],
  'mtk-sms-mmsrecvfail':                        ['AI故障分析', '通信'],
  'mtk-sms-mmssendfail':                        ['AI故障分析', '通信'],
  'mtk-sms-smsrecvfail':                        ['AI故障分析', '通信'],
  'mtk-sms-smssendfail':                        ['AI故障分析', '通信'],
  'near-bt-device-connect':                     ['AI故障分析', '通信'],
  'near-bt-opp-transfer':                       ['AI故障分析', '通信'],
  'near-bt-switch':                             ['AI故障分析', '通信'],
  'uns-call-dialfail':                          ['AI故障分析', '通信'],
  'uns-call-flashcall15':                       ['AI故障分析', '通信'],
  'uns-call-incominganswerfail':                ['AI故障分析', '通信'],
  'uns-sim-operatorname':                       ['AI故障分析', '通信'],
  'uns-sim-simdetect':                          ['AI故障分析', '通信'],
  'uns-sim-statusbaricon':                      ['AI故障分析', '通信'],
  'uns-sms-mmsrecvfail':                        ['AI故障分析', '通信'],
  'uns-sms-mmssendfail':                        ['AI故障分析', '通信'],
  'uns-sms-smsrecvfail':                        ['AI故障分析', '通信'],
  'uns-sms-smssendfail':                        ['AI故障分析', '通信'],
  'telephony-bug-analyzer':                     ['AI故障分析', '通信'],
  // AI 自动化适配 / 通信
  'MODEM_P1_Adapt':                             ['AI自动化适配', '通信'],
  'telephony-version-adapter':                  ['AI自动化适配', '通信'],
  'carrier-porting-assistant':                  ['AI自动化适配', '通信'],
  // AI 自动化适配 / 内核
  'KRN_LK_CPU_Ddapt':                           ['AI自动化适配', '内核'],
  'KRN_LK_CPU_Adapt':                           ['AI自动化适配', '内核'],
  // AI 自动化适配 / 驱动
  'android-platform-security-upgrade-ai-debug': ['AI自动化适配', '驱动'],
  'DRV_Audio_Adapt':                            ['AI自动化适配', '驱动'],
  'audio-self-check':                           ['AI自动化适配', '驱动'],
  'drv-fp-adapt':                               ['AI自动化适配', '驱动'],
  'drv-fp-check':                               ['AI自动化适配', '驱动'],
  'lid-check':                                  ['AI自动化适配', '驱动'],
  'scp-sensor-check':                           ['AI自动化适配', '驱动'],
  'mtk-sensor-dts-config':                      ['AI自动化适配', '驱动'],
  'scp_upgrade':                                ['AI自动化适配', '驱动'],
  'tranprojects-upgrade':                       ['AI自动化适配', '驱动'],
  'aikey-adapt-dts':                            ['AI自动化适配', '驱动'],
  'bsp-adapt-holster-hall':                     ['AI自动化适配', '驱动'],
  'bsp-adapt-lk-key':                           ['AI自动化适配', '驱动'],
  'tp-adapt-dws-pin':                           ['AI自动化适配', '驱动'],
  'tp-adapt-engineering-sysfs':                 ['AI自动化适配', '驱动'],
  'tp-adapt-factory-capacitance':               ['AI自动化适配', '驱动'],
  'tp-adapt-factory-sysfs':                     ['AI自动化适配', '驱动'],
  'tp-adapt-gesture-driver':                    ['AI自动化适配', '驱动'],
  'tp-adapt-ko-order':                          ['AI自动化适配', '驱动'],
  'tp-adapt-power-sequence':                    ['AI自动化适配', '驱动'],
  'tp-adapt-selinux':                           ['AI自动化适配', '驱动'],
  'vib-adapt-dts-regulator':                    ['AI自动化适配', '驱动'],
  'vib-adapt-factory-cali':                     ['AI自动化适配', '驱动'],
  'vib-adapt-haptic-rc':                        ['AI自动化适配', '驱动'],
  'vib-adapt-lra-driver':                       ['AI自动化适配', '驱动'],
  'vib-adapt-projectconfig':                    ['AI自动化适配', '驱动'],
  'vib-adapt-rotor-driver':                     ['AI自动化适配', '驱动'],
  'fc-aikey-dts':                               ['AI自动化适配', '驱动'],
  'fc-aikey-event':                             ['AI自动化适配', '驱动'],
  'fc-template':                                ['AI自动化适配', '驱动'],
  'fc-tp-driver':                               ['AI自动化适配', '驱动'],
  'fc-tp-factory-info':                         ['AI自动化适配', '驱动'],
  'fc-tp-factory':                              ['AI自动化适配', '驱动'],
  'fc-tp-gesture':                              ['AI自动化适配', '驱动'],
  'fc-tp-selinux':                              ['AI自动化适配', '驱动'],
  'fc-tp-sysfs':                                ['AI自动化适配', '驱动'],
  'fc-tp-touch':                                ['AI自动化适配', '驱动'],
  'fc-vib-cali':                                ['AI自动化适配', '驱动'],
  'fc-vib-driver':                              ['AI自动化适配', '驱动'],
  'fc-vib-effect':                              ['AI自动化适配', '驱动'],
  'fc-vib-hal':                                 ['AI自动化适配', '驱动'],
  'fc-vib-he':                                  ['AI自动化适配', '驱动'],
  'fc-vib-rootperm':                            ['AI自动化适配', '驱动'],
  'fc-vib-rotor':                               ['AI自动化适配', '驱动'],
  'fc-vib-selinux':                             ['AI自动化适配', '驱动'],
  'mtk-adapt-template-basic-charging-capability': ['AI自动化适配', '驱动'],
  'mtk-adapt-template-device-charge-pump':      ['AI自动化适配', '驱动'],
  'mtk-adapt-template-device-charger-ic':       ['AI自动化适配', '驱动'],
  'mtk-adapt-template-device-gauge':            ['AI自动化适配', '驱动'],
  'mtk-adapt-template-device-pd-ic':            ['AI自动化适配', '驱动'],
  'mtk-adapt-template-feature-factory-mode':    ['AI自动化适配', '驱动'],
  'mtk-adapt-template-feature-kpoc-charging':   ['AI自动化适配', '驱动'],
  'mtk-adapt-template-feature-placeholder':     ['AI自动化适配', '驱动'],
  'mtk-adapt-template-router':                  ['AI自动化适配', '驱动'],
  'mtk-adapt-upgrade-branch-orchestrator':      ['AI自动化适配', '驱动'],
  'mtk-adapt-upgrade-inventory-checklist':      ['AI自动化适配', '驱动'],
  'mtk-adapt-upgrade-platform-delta-table':     ['AI自动化适配', '驱动'],
  'transsion-charger-dtsi-driver-bridge':       ['AI自动化适配', '驱动'],
  'transsion-pe5-migrate-dual-cp-k612':         ['AI自动化适配', '驱动'],
  'transsion-sunmao40-customization-features-adapt': ['AI自动化适配', '驱动'],
  'transsion-tran-battery-to-tc-charger-dtsi':  ['AI自动化适配', '驱动'],
  'tran-projects-config-migrate-dtsi-dws':      ['AI自动化适配', '驱动'],
  // AI 自检工具
  'spd-cpu-feature-check':                      ['AI自检工具', '通用'],
  'kernel-panic-tracer':                        ['AI自检工具', '内核'],
}

/** 前缀兜底规则 */
const SKILL_PREFIX_RULES: Array<[string, string, string]> = [
  ['MODEM_P1_',           'AI自动化适配', '通信'],
  ['KRN_LK_',             'AI自动化适配', '内核'],
  ['carrier-porting',     'AI自动化适配', '通信'],
  ['telephony-version',   'AI自动化适配', '通信'],
  ['tp-adapt-',           'AI自动化适配', '驱动'],
  ['vib-adapt-',          'AI自动化适配', '驱动'],
  ['fc-tp-',              'AI自动化适配', '驱动'],
  ['fc-vib-',             'AI自动化适配', '驱动'],
  ['fc-aikey-',           'AI自动化适配', '驱动'],
  ['mtk-adapt-',          'AI自动化适配', '驱动'],
  ['drv-fp-',             'AI自动化适配', '驱动'],
  ['aikey-adapt',         'AI自动化适配', '驱动'],
  ['bsp-adapt-',          'AI自动化适配', '驱动'],
  ['tran-projects-',      'AI自动化适配', '驱动'],
  ['DRV_Audio_',          'AI自动化适配', '驱动'],
  ['spd-cpu-',            'AI自检工具',   '通用'],
  ['android-bootup',      'AI故障分析',   '内核'],
  ['android-hang',        'AI故障分析',   '内核'],
  ['android-hwr',         'AI故障分析',   '内核'],
  ['android-ke-',         'AI故障分析',   '内核'],
  ['android-kernel',      'AI故障分析',   '内核'],
  ['android-kerneldb',    'AI故障分析',   '内核'],
  ['android-kerneltne',   'AI故障分析',   '内核'],
  ['android-unisoc',      'AI故障分析',   '内核'],
  ['kernel-panic',        'AI故障分析',   '内核'],
  ['BSP_sensor',          'AI故障分析',   '驱动'],
  ['DRV_',                'AI故障分析',   '驱动'],
  ['android-fingerprint', 'AI故障分析',   '驱动'],
  ['android-sys-usb',     'AI故障分析',   '驱动'],
  ['audio-bug',           'AI故障分析',   '驱动'],
  ['mediatek-mtu3',       'AI故障分析',   '驱动'],
  ['mediatek-pd',         'AI故障分析',   '驱动'],
  ['mtk-backlight',       'AI故障分析',   '驱动'],
  ['mtk-battery',         'AI故障分析',   '驱动'],
  ['mtk-panel',           'AI故障分析',   '驱动'],
  ['mtk-screen',          'AI故障分析',   '驱动'],
  ['mtk-suspend',         'AI故障分析',   '驱动'],
  ['mtk-tp-',             'AI故障分析',   '驱动'],
  ['mtk-usb',             'AI故障分析',   '驱动'],
  ['mtu3-usb',            'AI故障分析',   '驱动'],
  ['qualcomm-',           'AI故障分析',   '驱动'],
  ['sensor-als',          'AI故障分析',   '驱动'],
  ['transsion-',          'AI故障分析',   '驱动'],
  ['usb-pd-',             'AI故障分析',   '驱动'],
  ['video-playback',      'AI故障分析',   '驱动'],
  ['power-usb-',          'AI故障分析',   '驱动'],
  ['bug-scenario-power',  'AI故障分析',   '功耗'],
  ['power-backlight',     'AI故障分析',   '功耗'],
  ['power-display',       'AI故障分析',   '功耗'],
  ['power-sensor',        'AI故障分析',   '功耗'],
  ['power-leak',          'AI故障分析',   '功耗'],
  ['com-',                'AI故障分析',   '通信'],
  ['mtk-call-',           'AI故障分析',   '通信'],
  ['mtk-fl',              'AI故障分析',   '通信'],
  ['mtk-modem',           'AI故障分析',   '通信'],
  ['mtk-network',         'AI故障分析',   '通信'],
  ['mtk-sim',             'AI故障分析',   '通信'],
  ['mtk-sms',             'AI故障分析',   '通信'],
  ['near-bt',             'AI故障分析',   '通信'],
  ['uns-',                'AI故障分析',   '通信'],
  ['telephony-bug',       'AI故障分析',   '通信'],
]

function classifySkillName(name: string): [string, string] | null {
  if (SKILL_CLASSIFY_MAP[name]) return SKILL_CLASSIFY_MAP[name]
  for (const [prefix, ft, cat] of SKILL_PREFIX_RULES) {
    if (name.startsWith(prefix)) return [ft, cat]
  }
  return null
}

/**
 * POST /api/hermes/skills/backfill-categories
 * 为所有已导入的 skill 的 SKILL.md frontmatter 批量写入 funcType / category 字段
 */
export async function backfillCategories(ctx: any) {
  const tahpDir = getTahpSkillsDir()
  if (!existsSync(tahpDir)) {
    ctx.body = { updated: 0, skipped: 0, unknown: [], message: 'skills 目录不存在' }
    return
  }

  let entries: import('fs').Dirent[]
  try {
    entries = await readdir(tahpDir, { withFileTypes: true })
  } catch (err: any) {
    ctx.status = 500
    ctx.body = { error: err.message }
    return
  }

  const updated: string[] = []
  const alreadyOk: string[] = []
  const unknown: string[] = []

  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    const skillMdPath = join(tahpDir, entry.name, 'SKILL.md')
    if (!existsSync(skillMdPath)) continue

    const classification = classifySkillName(entry.name)
    if (!classification) {
      unknown.push(entry.name)
      continue
    }
    const [funcType, category] = classification

    // 读取当前 frontmatter，检查是否已正确
    const currentContent = await safeReadFile(skillMdPath)
    if (currentContent) {
      const fm = parseFrontmatter(currentContent)
      if (fm.funcType === funcType && fm.category === category) {
        alreadyOk.push(entry.name)
        continue
      }
    }

    await injectFrontmatterFields(skillMdPath, { funcType, category })
    updated.push(entry.name)
  }

  if (updated.length > 0) invalidateSkillsCache()
  ctx.body = {
    updated,
    alreadyOk: alreadyOk.length,
    unknown,
    message: `完成：更新 ${updated.length} 个，已是正确值 ${alreadyOk.length} 个，未命中 ${unknown.length} 个`,
  }
}

// ---------------------------------------------------------------------------
// 技能变更历史（基于 git log）
// ---------------------------------------------------------------------------

/**
 * GET /api/hermes/skills/:category/:skill/history
 * 返回该 skill 目录的 git commit 列表（最多 50 条）
 */
export async function skillHistory(ctx: any) {
  const { skill } = ctx.params as { category: string; skill: string }
  const tahpDir = getTahpSkillsDir()
  const projectRoot = tahpPaths.projectRoot
  const skillDir = join(tahpDir, skill)

  if (!existsSync(skillDir)) {
    ctx.status = 404
    ctx.body = { error: 'Skill not found' }
    return
  }

  const relPath = relative(projectRoot, skillDir).replace(/\\/g, '/') + '/'
  const output = await gitExec(projectRoot, [
    'log', '--format=%H|||%at|||%an|||%s', '-50', '--', relPath,
  ])

  if (!output) {
    ctx.body = { commits: [], message: 'git 历史不可用（可能未初始化 git 或该 skill 暂无提交）' }
    return
  }

  const commits = output.split('\n').filter(Boolean).map(line => {
    const [hash, tsStr, author, ...msgParts] = line.split('|||')
    const ts = parseInt(tsStr, 10)
    return {
      hash,
      shortHash: hash.slice(0, 7),
      date: isNaN(ts) ? tsStr : new Date(ts * 1000).toISOString(),
      author: author || '',
      message: msgParts.join('|||') || '',
    }
  })

  ctx.body = { commits }
}

/**
 * GET /api/hermes/skills/:category/:skill/history/:hash
 * 返回某次 commit 的变更详情（git show）
 */
export async function skillHistoryCommit(ctx: any) {
  const { skill, hash } = ctx.params as { category: string; skill: string; hash: string }
  // 安全校验：hash 只允许十六进制字符
  if (!/^[0-9a-f]{4,40}$/i.test(hash)) {
    ctx.status = 400
    ctx.body = { error: 'Invalid commit hash' }
    return
  }

  const tahpDir = getTahpSkillsDir()
  const projectRoot = tahpPaths.projectRoot
  const skillDir = join(tahpDir, skill)
  const relPath = relative(projectRoot, skillDir).replace(/\\/g, '/') + '/'

  const output = await gitExec(projectRoot, [
    'show', '--stat', '-p', '--format=%H%n%ai%n%an%n%s%n%b%n---DIFF---', hash, '--', relPath,
  ])

  if (!output) {
    ctx.status = 404
    ctx.body = { error: 'Commit not found or git unavailable' }
    return
  }

  const diffIdx = output.indexOf('\n---DIFF---\n')
  const header = diffIdx !== -1 ? output.slice(0, diffIdx) : output
  const diff = diffIdx !== -1 ? output.slice(diffIdx + '\n---DIFF---\n'.length) : ''

  const headerLines = header.split('\n')
  ctx.body = {
    hash: headerLines[0] || hash,
    date: headerLines[1] || '',
    author: headerLines[2] || '',
    message: headerLines[3] || '',
    body: headerLines.slice(4).join('\n').trim(),
    diff,
  }
}
