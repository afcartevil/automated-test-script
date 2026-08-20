/**
 * ASF / Harness Skill 路径注册：本机客户端 skills 根 + 工程 skills/.claude/skills。
 * 按目录名与 capability 惯例识别 build/flash，兼容 harness-* 与 asf-*。
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import { tahpPaths } from '../paths'
import { HARNESS_HOST_SKILL_ROOTS_REL } from '../harness-host-skills'

export type HarnessSkillKind = 'build' | 'flash'

export interface HarnessSkillMeta {
  id: string
  kind: HarnessSkillKind
  label: string
  description: string
  path: string
  root: string
}

const BUILD_ID_RE = /^(harness|asf)-build/
const FLASH_ID_RE = /^(harness-device|asf-device|harness-flash-|asf-flash-)/

const BUILD_PREF = {
  native_module: ['asf-build-native', 'harness-build-native'],
  whole_device: ['asf-build-whole-device', 'harness-build-whole-device'],
  router: ['asf-build', 'harness-build'],
} as const

const FLASH_PREF = ['asf-device', 'harness-device']

/** 额外根目录：环境变量 TAHP_HARNESS_SKILL_ROOTS，用 ; 或 | 分隔 */
export function listHarnessSkillRoots(): string[] {
  const defaults = [
    ...HARNESS_HOST_SKILL_ROOTS_REL.map(rel => join(homedir(), ...rel.split('/'))),
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

export function classifySkillId(id: string): HarnessSkillKind | null {
  if (BUILD_ID_RE.test(id)) return 'build'
  if (FLASH_ID_RE.test(id)) return 'flash'
  return null
}

function labelFor(id: string): string {
  switch (id) {
    case 'harness-build':
    case 'asf-build':
      return '编译路由（自动分流）'
    case 'harness-build-whole-device':
    case 'asf-build-whole-device':
      return '整机编译（rdtool）'
    case 'harness-build-native':
    case 'asf-build-native':
      return '模块/Native 编译'
    case 'harness-device':
    case 'asf-device':
      return '设备刷机（整包）'
    case 'harness-flash-single-img':
    case 'asf-flash-single-img':
      return '单分区镜像刷入'
    default:
      return id
  }
}

export function pickPreferredSkillId(kind: HarnessSkillKind, installed: string[], buildKind?: 'whole_device' | 'native_module'): string {
  const set = new Set(installed)
  if (kind === 'flash') {
    return FLASH_PREF.find(id => set.has(id)) || installed[0] || 'asf-device'
  }
  if (buildKind === 'native_module') {
    return BUILD_PREF.native_module.find(id => set.has(id)) || 'asf-build-native'
  }
  if (buildKind === 'whole_device') {
    return BUILD_PREF.whole_device.find(id => set.has(id)) || 'asf-build-whole-device'
  }
  return BUILD_PREF.router.find(id => set.has(id)) || 'asf-build'
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
  const aliases = skillIdAliases(skillId)
  for (const id of aliases) {
    const projectPath = join(tahpPaths.skillsDir, id, 'SKILL.md')
    if (existsSync(projectPath)) return projectPath
    for (const root of listHarnessSkillRoots()) {
      const p = join(root, id, 'SKILL.md')
      if (existsSync(p)) return p
    }
  }
  return null
}

function skillIdAliases(skillId: string): string[] {
  const id = skillId.trim()
  if (!id) return []
  const out = [id]
  if (id.startsWith('harness-')) out.push(`asf-${id.slice('harness-'.length)}`)
  if (id.startsWith('asf-')) out.push(`harness-${id.slice('asf-'.length)}`)
  return [...new Set(out)]
}

/** 用户本机 skill 根（客户端 skills 与 TAHP_HARNESS_SKILL_ROOTS），不含工程 skills 目录 */
export function listUserHarnessSkillRoots(): string[] {
  const projectKey = tahpPaths.skillsDir.replace(/\\/g, '/').toLowerCase()
  return listHarnessSkillRoots().filter(
    r => r.replace(/\\/g, '/').toLowerCase() !== projectKey,
  )
}

/** 整包刷机等：优先用户目录下的官方 skill */
export function resolveUserHarnessSkillPath(skillId: string): string | null {
  const aliases = skillIdAliases(skillId)
  for (const root of listUserHarnessSkillRoots()) {
    for (const id of aliases) {
      const p = join(root, id, 'SKILL.md')
      if (existsSync(p)) return p
    }
  }
  return null
}

export function defaultBuildSkillId(buildKind: 'whole_device' | 'native_module' | undefined): string {
  const installed = listHarnessSkills('build').map(s => s.id)
  return pickPreferredSkillId('build', installed, buildKind)
}

export function defaultFlashSkillId(): string {
  const installed = listHarnessSkills('flash').map(s => s.id)
  return pickPreferredSkillId('flash', installed)
}
