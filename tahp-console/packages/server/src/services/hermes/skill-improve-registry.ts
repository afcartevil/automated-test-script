/**
 * Agent 自改进 Skill 注册表：只读解析 Hermes curator ledger + profile 落盘路径，
 * 并与仓库 skills/.claude/skills 比对，判定覆盖风险。
 */
import { existsSync, readFileSync, readdirSync, rmSync, statSync, type Dirent } from 'fs'
import { basename, join, relative } from 'path'
import { getActiveProfileDir } from './hermes-profile'
import { isPathWithin } from './hermes-path'
import { tahpPaths } from '../tahp/paths'

const SKILL_NAME_RE = /^[a-z0-9][a-z0-9._-]*$/i
const SESSION_PREFIX = 'tahp-bug-'

export type OverwriteRisk = 'none' | 'will_be_overwritten'
export type ImprovedSkillStatus = 'agent_only' | 'promoted' | 'at_risk'

export interface ImprovedSkillFile {
  path: string
  sha256: string
}

export interface ImprovedSkill {
  name: string
  profile_rel_path: string | null
  profile_abs_path: string | null
  actions: string[]
  first_seen_at: string
  last_updated_at: string
  task_ids: string[]
  files: ImprovedSkillFile[]
  exists_on_disk: boolean
  in_repo: boolean
  overwrite_risk: OverwriteRisk
  status: ImprovedSkillStatus
}

export interface SkillImproveRegistryPaths {
  profileSkillsDir: string
  repoSkillsDir: string
  ledgerPath?: string
}

export interface CuratorLedgerEntry {
  id: string
  ts: string
  actor: string
  action: string
  skill: string
  evidence?: { session_id?: string; file_path?: string }
  before?: Array<{ path?: string; sha256?: string }>
  after?: Array<{ path?: string; sha256?: string }>
}

export function defaultSkillImproveRegistryPaths(): SkillImproveRegistryPaths {
  const profileSkillsDir = join(getActiveProfileDir(), 'skills')
  return {
    profileSkillsDir,
    repoSkillsDir: tahpPaths.skillsDir,
    ledgerPath: join(profileSkillsDir, '.curator_ledger.jsonl'),
  }
}

export function isSkillImproveName(name: string): boolean {
  return !!name && !name.startsWith('.') && SKILL_NAME_RE.test(name) && !name.includes('/') && !name.includes('\\')
}

/** `tahp-bug-<taskId>` → taskId；无法识别则返回 null。 */
export function taskIdFromSessionId(sessionId: string): string | null {
  const s = String(sessionId || '').trim()
  if (!s) return null
  if (s.startsWith(SESSION_PREFIX)) {
    const rest = s.slice(SESSION_PREFIX.length)
    return rest || null
  }
  return null
}

export function loadCuratorLedger(
  paths: SkillImproveRegistryPaths = defaultSkillImproveRegistryPaths(),
): CuratorLedgerEntry[] {
  const ledgerPath = paths.ledgerPath || join(paths.profileSkillsDir, '.curator_ledger.jsonl')
  try {
    return parseCuratorLedger(readFileSync(ledgerPath, 'utf-8'))
  } catch {
    return []
  }
}

export function parseCuratorLedger(text: string): CuratorLedgerEntry[] {
  const out: CuratorLedgerEntry[] = []
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    try {
      const obj = JSON.parse(line) as Record<string, unknown>
      const skill = String(obj.skill || '').trim()
      if (!isSkillImproveName(skill)) continue
      const action = String(obj.action || '').trim()
      if (!action) continue
      const evidence = obj.evidence && typeof obj.evidence === 'object'
        ? obj.evidence as { session_id?: string; file_path?: string }
        : undefined
      out.push({
        id: String(obj.id || ''),
        ts: String(obj.ts || ''),
        actor: String(obj.actor || ''),
        action,
        skill,
        evidence,
        before: Array.isArray(obj.before) ? obj.before as CuratorLedgerEntry['before'] : [],
        after: Array.isArray(obj.after) ? obj.after as CuratorLedgerEntry['after'] : [],
      })
    } catch {
      /* skip corrupt line */
    }
  }
  return out
}

/** session_id → 该任务改过的 skill 名（去重，保持出现顺序） */
export function taskSkillsFromLedger(entries: CuratorLedgerEntry[]): Map<string, string[]> {
  const map = new Map<string, string[]>()
  for (const entry of entries) {
    const tid = taskIdFromSessionId(entry.evidence?.session_id || '')
    if (!tid) continue
    const list = map.get(tid) || []
    if (!list.includes(entry.skill)) list.push(entry.skill)
    map.set(tid, list)
  }
  return map
}

/**
 * 先试扁平 `skills/<name>/`，再扫一级分类 `skills/<cat>/<name>/`。
 * 两者都在时优先扁平（注入器只写扁平路径）。
 */
export function findSkillDirInProfile(
  profileSkillsDir: string,
  name: string,
): { abs: string; rel: string } | null {
  if (!isSkillImproveName(name) || !profileSkillsDir) return null

  const flat = join(profileSkillsDir, name)
  if (isSkillDirectory(flat)) return { abs: flat, rel: name }

  let entries: Dirent[] = []
  try {
    entries = readdirSync(profileSkillsDir, { withFileTypes: true })
  } catch {
    return null
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    const nested = join(profileSkillsDir, entry.name, name)
    if (isSkillDirectory(nested)) return { abs: nested, rel: `${entry.name}/${name}` }
  }
  return null
}

function isSkillDirectory(dir: string): boolean {
  try {
    return existsSync(dir) && statSync(dir).isDirectory() && existsSync(join(dir, 'SKILL.md'))
  } catch {
    return false
  }
}

function repoHasSkill(repoSkillsDir: string, name: string): boolean {
  if (!repoSkillsDir || !isSkillImproveName(name)) return false
  const dir = join(repoSkillsDir, name)
  return existsSync(dir)
}

function relFilePath(absPath: string, skillDir: string | null): string {
  if (skillDir && isPathWithin(absPath, skillDir)) {
    const rel = relative(skillDir, absPath).replace(/\\/g, '/')
    return rel || basename(absPath)
  }
  return basename(absPath).replace(/\\/g, '/')
}

function deriveStatus(inRepo: boolean, overwriteRisk: OverwriteRisk): ImprovedSkillStatus {
  if (!inRepo) return 'agent_only'
  if (overwriteRisk === 'will_be_overwritten') return 'at_risk'
  return 'promoted'
}

export function listImprovedSkills(paths: SkillImproveRegistryPaths = defaultSkillImproveRegistryPaths()): ImprovedSkill[] {
  const ledgerPath = paths.ledgerPath || join(paths.profileSkillsDir, '.curator_ledger.jsonl')
  let text = ''
  try {
    text = readFileSync(ledgerPath, 'utf-8')
  } catch {
    return []
  }
  const entries = parseCuratorLedger(text)
  const byName = new Map<string, CuratorLedgerEntry[]>()
  for (const entry of entries) {
    const list = byName.get(entry.skill) || []
    list.push(entry)
    byName.set(entry.skill, list)
  }

  const skills: ImprovedSkill[] = []
  for (const [name, skillEntries] of byName) {
    skillEntries.sort((a, b) => String(a.ts).localeCompare(String(b.ts)))
    const first = skillEntries[0]
    const last = skillEntries[skillEntries.length - 1]
    const actions: string[] = []
    const taskIds: string[] = []
    for (const entry of skillEntries) {
      if (entry.action && !actions.includes(entry.action)) actions.push(entry.action)
      const tid = taskIdFromSessionId(entry.evidence?.session_id || '')
      if (tid && !taskIds.includes(tid)) taskIds.push(tid)
    }
    const located = findSkillDirInProfile(paths.profileSkillsDir, name)
    const files: ImprovedSkillFile[] = []
    for (const item of last?.after || []) {
      const abs = String(item.path || '').trim()
      if (!abs) continue
      files.push({
        path: relFilePath(abs, located?.abs || null),
        sha256: String(item.sha256 || ''),
      })
    }
    const inRepo = repoHasSkill(paths.repoSkillsDir, name)
    const existsOnDisk = !!located
    const isFlat = !!located && located.rel === name
    const overwriteRisk: OverwriteRisk = inRepo && existsOnDisk && isFlat
      ? 'will_be_overwritten'
      : 'none'
    skills.push({
      name,
      profile_rel_path: located?.rel || null,
      profile_abs_path: located?.abs || null,
      actions,
      first_seen_at: first?.ts || '',
      last_updated_at: last?.ts || '',
      task_ids: taskIds,
      files,
      exists_on_disk: existsOnDisk,
      in_repo: inRepo,
      overwrite_risk: overwriteRisk,
      status: deriveStatus(inRepo, overwriteRisk),
    })
  }

  skills.sort((a, b) => String(b.last_updated_at).localeCompare(String(a.last_updated_at)))
  return skills
}

/**
 * 删除已固化进仓库的 profile 原副本（分类路径或扁平路径），避免注入后出现同名双份。
 * 未固化的 Skill 拒绝删除，以免丢掉唯一副本。
 */
export function removeImprovedProfileCopy(
  name: string,
  paths: SkillImproveRegistryPaths = defaultSkillImproveRegistryPaths(),
): { ok: boolean; error?: string; removed?: string } {
  if (!isSkillImproveName(name)) return { ok: false, error: '无效的 Skill 名' }
  const skill = listImprovedSkills(paths).find(s => s.name === name)
  if (!skill) return { ok: false, error: `未在自改进记录中找到 ${name}` }
  if (!skill.in_repo) return { ok: false, error: '尚未固化进仓库，删除会丢失唯一副本' }
  if (!skill.profile_abs_path || !skill.exists_on_disk) {
    return { ok: false, error: 'profile 副本不存在' }
  }
  if (!isPathWithin(skill.profile_abs_path, paths.profileSkillsDir)) {
    return { ok: false, error: '路径非法' }
  }
  try {
    rmSync(skill.profile_abs_path, { recursive: true, force: true })
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }
  return { ok: true, removed: skill.profile_rel_path || name }
}
