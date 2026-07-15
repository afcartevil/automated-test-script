/**
 * Skill 同步状态 — 本地 vs 中心 manifest 比对。
 * 性能：包 hash 指纹缓存 + 结果短 TTL + 中心请求并行。
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { config } from '../../../config'
import { logger } from '../../logger'
import { tahpPaths } from '../paths'
import { getRuntimeModeInfo, isCentralConfigured } from '../runtime-mode'
import { centralClient } from './central-client'
import { getLocalPackageHash } from './skill-package'
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
  /** 是否来自短 TTL 内存缓存 */
  from_cache?: boolean
  checked_at?: string
}

interface PersistedSyncState {
  last_pulled_at?: string
  skills?: Record<string, { central_hash?: string; local_hash?: string; state?: string }>
  /** 最近一次完整 status 快照（供首屏秒开） */
  last_status?: SkillSyncStatusResult
}

const STATUS_TTL_MS = 30_000
let memStatus: { at: number; key: string; data: SkillSyncStatusResult } | null = null

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

export function invalidateSkillSyncStatusCache(): void {
  memStatus = null
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

function listLocalSkills(forceHash = false): Map<string, { hash: string; meta: ReturnType<typeof parseSkillMeta> }> {
  const root = tahpPaths.skillsDir
  const out = new Map<string, { hash: string; meta: ReturnType<typeof parseSkillMeta> }>()
  if (!existsSync(root)) return out
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    const md = join(root, entry.name, 'SKILL.md')
    if (!existsSync(md)) continue
    try {
      const raw = readFileSync(md, 'utf-8')
      const pkgHash = getLocalPackageHash(entry.name, forceHash)
      out.set(entry.name, {
        hash: pkgHash || shortHash(raw),
        meta: parseSkillMeta(raw),
      })
    } catch {
      out.set(entry.name, { hash: '', meta: {} })
    }
  }
  return out
}

function buildGroupsByFuncType(skills: SkillSyncStatusItem[]): SkillSyncGroup[] {
  const map = new Map<string, SkillSyncGroup>()
  for (const s of skills) {
    const label = s.func_type?.trim() || '未分类'
    const id = `ft:${label}`
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

function cacheBundlesPath(): string {
  return join(tahpDir(), 'skill-bundles.cache.json')
}

function readBundlesCache(): { bundles: Array<{ id: string; label: string; skill_ids: string[] }> } | null {
  try {
    if (!existsSync(cacheBundlesPath())) return null
    return JSON.parse(readFileSync(cacheBundlesPath(), 'utf-8'))
  } catch {
    return null
  }
}

function writeBundlesCache(doc: unknown): void {
  try {
    writeFileSync(cacheBundlesPath(), JSON.stringify(doc, null, 2), 'utf-8')
  } catch (e) {
    logger.warn({ err: (e as Error).message }, '[skill-sync] write bundles cache failed')
  }
}

function buildGroupsFromBundles(
  skills: SkillSyncStatusItem[],
  bundles: Array<{ id: string; label: string; skill_ids: string[] }>,
): SkillSyncGroup[] {
  if (!bundles.length) return buildGroupsByFuncType(skills)
  const groups: SkillSyncGroup[] = []
  const claimed = new Set<string>()
  for (const b of bundles) {
    const members = skills.filter(s => s.bundle_ids?.includes(b.id) || (b.skill_ids || []).includes(s.id))
    const ids = members.map(s => s.id)
    for (const id of ids) claimed.add(id)
    groups.push({
      id: `bundle:${b.id}`,
      label: b.label || b.id,
      behind_count: members.filter(s => s.state === 'behind').length,
      skill_ids: ids,
    })
  }
  const rest = skills.filter(s => !claimed.has(s.id))
  if (rest.length) {
    groups.push({
      id: 'bundle:__other__',
      label: '未归包',
      behind_count: rest.filter(s => s.state === 'behind').length,
      skill_ids: rest.map(s => s.id),
    })
  }
  return groups.sort((a, b) => {
    if (b.behind_count !== a.behind_count) return b.behind_count - a.behind_count
    return a.label.localeCompare(b.label, 'zh')
  })
}

function cacheKey(opts?: { bundle_id?: string }): string {
  return opts?.bundle_id ? `b:${opts.bundle_id}` : 'all'
}

function filterByBundle(skills: SkillSyncStatusItem[], bundleId?: string): SkillSyncStatusItem[] {
  if (!bundleId) return skills
  return skills.filter(s => s.bundle_ids?.includes(bundleId))
}

export async function getSkillSyncStatus(opts?: {
  bundle_id?: string
  force?: boolean
}): Promise<SkillSyncStatusResult> {
  const key = cacheKey(opts)
  const now = Date.now()
  if (!opts?.force && memStatus && memStatus.key === key && now - memStatus.at < STATUS_TTL_MS) {
    return { ...memStatus.data, from_cache: true }
  }

  // 非强制：若有持久化快照且请求「全部」，先可被客户端使用；此处仍做完整计算，但二次进入走 mem/disk
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
    checked_at: new Date().toISOString(),
  }

  if (!isCentralConfigured()) {
    const local = listLocalSkills(!!opts?.force)
    const skills: SkillSyncStatusItem[] = [...local.entries()].map(([id, v]) => ({
      id,
      state: 'local_only' as const,
      local_hash: v.hash || undefined,
      bundle_ids: [],
      name: v.meta.name,
      func_type: v.meta.func_type,
      module: v.meta.module,
    }))
    const result = { ...base, skills, groups: buildGroupsByFuncType(skills), from_cache: false }
    memStatus = { at: now, key, data: result }
    writePersistedSyncState({ last_status: result })
    return result
  }

  base.configured = true
  base.central_url = config.tahp.centralUrl || mode.central_url

  let manifestItems: ManifestItem[] = []
  let bundlesDoc: {
    bundles: Array<{ id: string; label: string; skill_ids: string[] }>
  } | null = readBundlesCache()

  try {
    const [, manifestRes, bundlesRes] = await Promise.allSettled([
      centralClient.ping(),
      centralClient.manifest(),
      centralClient.skillBundles(),
    ])
    if (manifestRes.status !== 'fulfilled') {
      throw (manifestRes as PromiseRejectedResult).reason || new Error('拉取 manifest 失败')
    }
    manifestItems = manifestRes.value.items || []
    base.connected = true
    if (bundlesRes.status === 'fulfilled') {
      bundlesDoc = bundlesRes.value
      writeBundlesCache(bundlesDoc)
    }
  } catch (e) {
    base.connected = false
    base.error = (e as Error).message
    // 断连时优先返回持久化快照（秒开）
    if (!opts?.force && persisted.last_status?.skills?.length) {
      const snap = {
        ...persisted.last_status,
        connected: false,
        error: base.error,
        from_cache: true,
        checked_at: base.checked_at,
      }
      memStatus = { at: now, key, data: snap }
      return snap
    }
    const local = listLocalSkills(!!opts?.force)
    const skills: SkillSyncStatusItem[] = [...local.entries()].map(([id, v]) => ({
      id,
      state: 'unknown' as const,
      local_hash: v.hash || undefined,
      bundle_ids: [],
      name: v.meta.name,
      func_type: v.meta.func_type,
      module: v.meta.module,
    }))
    const result = { ...base, skills, groups: buildGroupsByFuncType(skills), from_cache: false }
    memStatus = { at: now, key, data: result }
    return result
  }

  const local = listLocalSkills(!!opts?.force)
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

  const filtered = filterByBundle(skills, opts?.bundle_id)
  const behind_count = filtered.filter(s => s.state === 'behind').length
  const groups = buildGroupsFromBundles(filtered, bundlesDoc?.bundles || [])

  const result: SkillSyncStatusResult = {
    ...base,
    behind_count,
    skills: filtered,
    groups,
    from_cache: false,
  }

  memStatus = { at: now, key, data: result }
  writePersistedSyncState({
    last_pulled_at: persisted.last_pulled_at,
    skills: skillMap,
    last_status: opts?.bundle_id ? persisted.last_status : result,
  })

  return result
}

/** 仅读持久化快照（不扫盘、不打中心）— 前端首屏用 */
export function getCachedSkillSyncStatus(): SkillSyncStatusResult | null {
  if (memStatus && Date.now() - memStatus.at < STATUS_TTL_MS * 4) {
    return { ...memStatus.data, from_cache: true }
  }
  const persisted = readPersistedSyncState()
  if (persisted.last_status?.skills) {
    return { ...persisted.last_status, from_cache: true }
  }
  return null
}

/** 解析 bundle 内 skill ids（供同步此包）— 尽量不触发全量重扫 */
export async function resolveBundleSkillIds(bundleId: string): Promise<string[]> {
  if (!isCentralConfigured()) return []
  try {
    let doc = readBundlesCache()
    if (!doc) {
      doc = await centralClient.skillBundles()
      writeBundlesCache(doc)
    }
    const b = doc.bundles.find(x => x.id === bundleId)
    const fromExplicit = new Set(b?.skill_ids || [])
    const cached = getCachedSkillSyncStatus() || await getSkillSyncStatus()
    for (const s of cached.skills) {
      if (s.bundle_ids?.includes(bundleId)) fromExplicit.add(s.id)
    }
    return [...fromExplicit]
  } catch {
    return []
  }
}
