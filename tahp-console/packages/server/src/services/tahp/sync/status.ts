/**
 * Skill 同步状态 — 本地 vs 中心 manifest 比对。
 * 见 .cursor/skill-sync/PHASE-1.md
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { config } from '../../../config'
import { logger } from '../../logger'
import { tahpPaths } from '../paths'
import { getRuntimeModeInfo, isCentralConfigured } from '../runtime-mode'
import { centralClient } from './central-client'
import { shortHash } from './hash'
import type { ManifestItem } from './manifest'

export type SkillSyncStateName = 'synced' | 'behind' | 'local_only' | 'unknown'

export interface SkillSyncStatusItem {
  id: string
  state: SkillSyncStateName
  central_hash?: string
  local_hash?: string
  updated_at?: string
  bundle_ids: string[]
  name?: string
  func_type?: string
  module?: string
}

export interface SkillSyncGroup {
  id: string
  label: string
  behind_count: number
  skill_ids: string[]
}

export interface SkillSyncStatusResult {
  configured: boolean
  central_url: string | null
  connected: boolean
  last_pulled_at: string | null
  behind_count: number
  skills: SkillSyncStatusItem[]
  groups: SkillSyncGroup[]
  error?: string
}

interface PersistedSyncState {
  last_pulled_at?: string
  skills?: Record<string, { central_hash?: string; local_hash?: string; state?: string }>
}

function tahpDir(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

function statePath(): string {
  return join(tahpDir(), 'skill-sync-state.json')
}

export function readPersistedSyncState(): PersistedSyncState {
  try {
    if (!existsSync(statePath())) return {}
    return JSON.parse(readFileSync(statePath(), 'utf-8')) as PersistedSyncState
  } catch {
    return {}
  }
}

export function writePersistedSyncState(patch: PersistedSyncState): void {
  try {
    const prev = readPersistedSyncState()
    const next = { ...prev, ...patch }
    writeFileSync(statePath(), JSON.stringify(next, null, 2), 'utf-8')
  } catch (e) {
    logger.warn({ err: (e as Error).message }, '[skill-sync] write state failed')
  }
}

export function setLastPulledAt(iso: string): void {
  writePersistedSyncState({ last_pulled_at: iso })
}

function parseSkillMeta(raw: string): { name?: string; func_type?: string; module?: string } {
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!m) return {}
  const fm = m[1]
  const pick = (keys: string[]): string | undefined => {
    for (const key of keys) {
      const re = new RegExp(`^${key}:\\s*(.+)$`, 'm')
      const hit = fm.match(re)
      if (hit) return hit[1].trim().replace(/^["']|["']$/g, '')
    }
    return undefined
  }
  return {
    name: pick(['domain_label', 'name']),
    func_type: pick(['funcType', 'func_type']),
    module: pick(['category', 'module', 'group']),
  }
}

function listLocalSkills(): Map<string, { hash: string; meta: ReturnType<typeof parseSkillMeta> }> {
  const root = tahpPaths.skillsDir
  const out = new Map<string, { hash: string; meta: ReturnType<typeof parseSkillMeta> }>()
  if (!existsSync(root)) return out
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    const md = join(root, entry.name, 'SKILL.md')
    if (!existsSync(md)) continue
    try {
      const raw = readFileSync(md, 'utf-8')
      out.set(entry.name, { hash: shortHash(raw), meta: parseSkillMeta(raw) })
    } catch {
      out.set(entry.name, { hash: '', meta: {} })
    }
  }
  return out
}

function buildGroups(skills: SkillSyncStatusItem[]): SkillSyncGroup[] {
  const map = new Map<string, SkillSyncGroup>()
  for (const s of skills) {
    const label = s.func_type?.trim() || '未分类'
    const id = label
    let g = map.get(id)
    if (!g) {
      g = { id, label, behind_count: 0, skill_ids: [] }
      map.set(id, g)
    }
    g.skill_ids.push(s.id)
    if (s.state === 'behind') g.behind_count++
  }
  return [...map.values()].sort((a, b) => {
    if (b.behind_count !== a.behind_count) return b.behind_count - a.behind_count
    return a.label.localeCompare(b.label, 'zh')
  })
}

export async function getSkillSyncStatus(): Promise<SkillSyncStatusResult> {
  const mode = getRuntimeModeInfo()
  const persisted = readPersistedSyncState()
  const base: SkillSyncStatusResult = {
    configured: false,
    central_url: mode.central_url,
    connected: false,
    last_pulled_at: persisted.last_pulled_at || null,
    behind_count: 0,
    skills: [],
    groups: [],
  }

  if (!isCentralConfigured()) {
    const local = listLocalSkills()
    const skills: SkillSyncStatusItem[] = [...local.entries()].map(([id, v]) => ({
      id,
      state: 'local_only' as const,
      local_hash: v.hash || undefined,
      bundle_ids: [],
      name: v.meta.name,
      func_type: v.meta.func_type,
      module: v.meta.module,
    }))
    return { ...base, skills, groups: buildGroups(skills) }
  }

  base.configured = true
  base.central_url = config.tahp.centralUrl || mode.central_url

  let manifestItems: ManifestItem[] = []
  try {
    await centralClient.ping()
    const manifest = await centralClient.manifest()
    manifestItems = manifest.items || []
    base.connected = true
  } catch (e) {
    base.connected = false
    base.error = (e as Error).message
    const local = listLocalSkills()
    const skills: SkillSyncStatusItem[] = [...local.entries()].map(([id, v]) => ({
      id,
      state: 'unknown' as const,
      local_hash: v.hash || undefined,
      bundle_ids: [],
      name: v.meta.name,
      func_type: v.meta.func_type,
      module: v.meta.module,
    }))
    return { ...base, skills, groups: buildGroups(skills) }
  }

  const local = listLocalSkills()
  const centralSkills = manifestItems.filter(i => i.type === 'skill')
  const seen = new Set<string>()
  const skills: SkillSyncStatusItem[] = []
  const skillMap: PersistedSyncState['skills'] = {}

  for (const item of centralSkills) {
    seen.add(item.id)
    const loc = local.get(item.id)
    let state: SkillSyncStateName
    if (!loc || !loc.hash) state = 'behind'
    else if (loc.hash === item.hash) state = 'synced'
    else state = 'behind'

    const row: SkillSyncStatusItem = {
      id: item.id,
      state,
      central_hash: item.hash,
      local_hash: loc?.hash,
      updated_at: item.updated_at,
      bundle_ids: Array.isArray(item.bundle_ids) ? item.bundle_ids : [],
      name: loc?.meta.name || item.id,
      func_type: loc?.meta.func_type,
      module: loc?.meta.module,
    }
    skills.push(row)
    skillMap[item.id] = {
      central_hash: item.hash,
      local_hash: loc?.hash,
      state,
    }
  }

  for (const [id, v] of local.entries()) {
    if (seen.has(id)) continue
    skills.push({
      id,
      state: 'local_only',
      local_hash: v.hash || undefined,
      bundle_ids: [],
      name: v.meta.name,
      func_type: v.meta.func_type,
      module: v.meta.module,
    })
    skillMap[id] = { local_hash: v.hash, state: 'local_only' }
  }

  skills.sort((a, b) => {
    const order = { behind: 0, unknown: 1, local_only: 2, synced: 3 }
    const d = order[a.state] - order[b.state]
    if (d !== 0) return d
    return a.id.localeCompare(b.id)
  })

  const behind_count = skills.filter(s => s.state === 'behind').length
  writePersistedSyncState({
    last_pulled_at: persisted.last_pulled_at,
    skills: skillMap,
  })

  return {
    ...base,
    behind_count,
    skills,
    groups: buildGroups(skills),
  }
}
