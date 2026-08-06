/**
 * Harness Skill 路径注册：默认 %USERPROFILE%\.claude\skills + 工程 skills/.claude/skills，可追加根目录。
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import { tahpPaths } from '../paths'

export type HarnessSkillKind = 'build' | 'flash'

export interface HarnessSkillMeta {
  id: string
  kind: HarnessSkillKind
  label: string
  description: string
  path: string
  root: string
}

const BUILD_ID_RE = /^harness-build/
const FLASH_ID_RE = /^(harness-device|harness-flash-)/

/** 额外根目录：环境变量 TAHP_HARNESS_SKILL_ROOTS，用 ; 或 | 分隔 */
export function listHarnessSkillRoots(): string[] {
  const defaults = [
    join(homedir(), '.claude', 'skills'),
    tahpPaths.skillsDir,
  ]
  const raw = process.env.TAHP_HARNESS_SKILL_ROOTS?.trim()
  const extra = raw ? raw.split(/[;|]/).map(s => s.trim()).filter(Boolean) : []
  const merged = [...defaults, ...extra]
  const seen = new Set<string>()
  const out: string[] = []
  for (const p of merged) {
    const key = p.replace(/\\/g, '/').toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    if (existsSync(p)) out.push(p)
  }
  return out
}

function parseFrontmatter(raw: string): { name?: string; description?: string } {
  if (!raw.startsWith('---')) return {}
  const end = raw.indexOf('---', 3)
  if (end < 0) return {}
  const block = raw.slice(3, end)
  const name = block.match(/^name:\s*(.+)$/m)?.[1]?.trim()
  const descLine = block.match(/^description:\s*(.+)$/m)?.[1]?.trim()
  return { name, description: descLine }
}

function classifySkillId(id: string): HarnessSkillKind | null {
  if (BUILD_ID_RE.test(id)) return 'build'
  if (FLASH_ID_RE.test(id)) return 'flash'
  return null
}

function labelFor(id: string): string {
  switch (id) {
    case 'harness-build': return '编译路由（自动分流）'
    case 'harness-build-whole-device': return '整机编译（rdtool）'
    case 'harness-build-native': return '模块/Native 编译'
    case 'harness-device': return '设备刷机（整包）'
    case 'harness-flash-single-img': return '单分区镜像刷入'
    default: return id
  }
}

export function listHarnessSkills(kind?: HarnessSkillKind): HarnessSkillMeta[] {
  const items: HarnessSkillMeta[] = []
  const seen = new Set<string>()

  for (const root of listHarnessSkillRoots()) {
    let entries: string[] = []
    try {
      entries = readdirSync(root)
    } catch {
      continue
    }
    for (const name of entries) {
      const dir = join(root, name)
      try {
        if (!statSync(dir).isDirectory()) continue
      } catch {
        continue
      }
      const skillMd = join(dir, 'SKILL.md')
      if (!existsSync(skillMd)) continue
      const kindGuess = classifySkillId(name)
      if (!kindGuess) continue
      if (kind && kindGuess !== kind) continue
      if (seen.has(name)) continue
      seen.add(name)
      let description = ''
      try {
        const fm = parseFrontmatter(readFileSync(skillMd, 'utf-8'))
        description = fm.description ?? ''
      } catch { /* ignore */ }
      items.push({
        id: name,
        kind: kindGuess,
        label: labelFor(name),
        description,
        path: skillMd,
        root,
      })
    }
  }

  return items.sort((a, b) => a.id.localeCompare(b.id))
}

export function resolveHarnessSkillPath(skillId: string): string | null {
  const projectPath = join(tahpPaths.skillsDir, skillId, 'SKILL.md')
  if (existsSync(projectPath)) return projectPath
  for (const root of listHarnessSkillRoots()) {
    const p = join(root, skillId, 'SKILL.md')
    if (existsSync(p)) return p
  }
  return null
}

/** 用户本机 skill 根（~/.claude/skills 与 TAHP_HARNESS_SKILL_ROOTS），不含工程 skills 目录 */
export function listUserHarnessSkillRoots(): string[] {
  const projectKey = tahpPaths.skillsDir.replace(/\\/g, '/').toLowerCase()
  return listHarnessSkillRoots().filter(
    r => r.replace(/\\/g, '/').toLowerCase() !== projectKey,
  )
}

/** 整包刷机等：优先用户目录下的 harness skill */
export function resolveUserHarnessSkillPath(skillId: string): string | null {
  for (const root of listUserHarnessSkillRoots()) {
    const p = join(root, skillId, 'SKILL.md')
    if (existsSync(p)) return p
  }
  return null
}

export function defaultBuildSkillId(buildKind: 'whole_device' | 'native_module' | undefined): string {
  if (buildKind === 'native_module') return 'harness-build-native'
  if (buildKind === 'whole_device') return 'harness-build-whole-device'
  return 'harness-build'
}

export function defaultFlashSkillId(): string {
  return 'harness-device'
}
