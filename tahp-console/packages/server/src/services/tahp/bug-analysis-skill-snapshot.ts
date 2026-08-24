/**
 * 将 Agent 自改进 Skill 目录快照到 reports/bug-analysis/skills/<taskId>/。
 * 拷贝失败由调用方记日志，不抛到报告落盘主路径。
 */
import { createHash } from 'crypto'
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync, type Dirent } from 'fs'
import { cp } from 'fs/promises'
import { join, relative } from 'path'
import {
  findSkillDirInProfile,
  defaultSkillImproveRegistryPaths,
  isSkillImproveName,
} from '../hermes/skill-improve-registry'
import { isPathWithin } from '../hermes/hermes-path'
import type { SkillImproveRecord } from './bug-analysis-skill-improve'

export const SKILL_SNAPSHOT_MAX_BYTES = 1024 * 1024
export const SKILL_SNAPSHOT_MAX_FILES = 200

export type SkillSnapshotSource = 'runtime' | 'backfill'

export interface SkillSnapshotManifest {
  skill: string
  source_path: string
  snapshot_at: string
  snapshot_source: SkillSnapshotSource
  truncated: boolean
  files: Array<{ path: string; sha256: string; size: number }>
}

export interface SkillSnapshotRead {
  skill: string
  skill_md: string
  truncated: boolean
  snapshot_source: SkillSnapshotSource
  snapshot_at: string
  files: string[]
}

export function skillImproveSnapshotRoot(reportsDir: string, taskId: string): string {
  return join(reportsDir, 'bug-analysis', 'skills', taskId)
}

export function skillImproveSnapshotRel(taskId: string, skillName: string): string {
  return `bug-analysis/skills/${taskId}/${skillName}`
}

function collectFiles(root: string): Array<{ abs: string; rel: string; size: number }> {
  const out: Array<{ abs: string; rel: string; size: number }> = []
  const walk = (current: string) => {
    let entries: Dirent[] = []
    try {
      entries = readdirSync(current, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      if (entry.name === '.git' || entry.name === 'node_modules') continue
      const abs = join(current, entry.name)
      if (entry.isDirectory()) {
        walk(abs)
        continue
      }
      if (!entry.isFile()) continue
      if (entry.name === 'manifest.json' && current === root) continue
      try {
        const info = statSync(abs)
        out.push({
          abs,
          rel: relative(root, abs).replace(/\\/g, '/'),
          size: info.size,
        })
      } catch { /* skip unreadable */ }
    }
  }
  walk(root)
  return out
}

function sha256File(abs: string): string {
  const buf = readFileSync(abs)
  return createHash('sha256').update(buf).digest('hex')
}

function resolveDefaultSkillDir(name: string): string | null {
  const located = findSkillDirInProfile(defaultSkillImproveRegistryPaths().profileSkillsDir, name)
  return located?.abs || null
}

export async function snapshotImprovedSkills(opts: {
  reportsDir: string
  taskId: string
  records: SkillImproveRecord[]
  resolveSkillDir?: (name: string) => string | null
  source?: SkillSnapshotSource
  maxBytes?: number
  maxFiles?: number
}): Promise<SkillImproveRecord[]> {
  const resolveSkillDir = opts.resolveSkillDir || resolveDefaultSkillDir
  const source = opts.source || 'runtime'
  const maxBytes = opts.maxBytes ?? SKILL_SNAPSHOT_MAX_BYTES
  const maxFiles = opts.maxFiles ?? SKILL_SNAPSHOT_MAX_FILES
  const out: SkillImproveRecord[] = []

  for (const rec of opts.records) {
    const name = rec.name
    if (!isSkillImproveName(name)) {
      out.push(rec)
      continue
    }
    const srcDir = resolveSkillDir(name)
    if (!srcDir || !existsSync(srcDir)) {
      out.push(rec)
      continue
    }
    try {
      const destDir = join(skillImproveSnapshotRoot(opts.reportsDir, opts.taskId), name)
      const files = collectFiles(srcDir)
      const totalSize = files.reduce((sum, f) => sum + f.size, 0)
      const truncated = files.length > maxFiles || totalSize > maxBytes
      if (existsSync(destDir)) rmSync(destDir, { recursive: true, force: true })
      mkdirSync(skillImproveSnapshotRoot(opts.reportsDir, opts.taskId), { recursive: true })

      if (truncated) {
        mkdirSync(destDir, { recursive: true })
        const skillMd = join(srcDir, 'SKILL.md')
        if (existsSync(skillMd)) {
          writeFileSync(join(destDir, 'SKILL.md'), readFileSync(skillMd))
        }
      } else {
        await cp(srcDir, destDir, { recursive: true })
      }

      const copied = collectFiles(destDir)
      const manifest: SkillSnapshotManifest = {
        skill: name,
        source_path: srcDir,
        snapshot_at: new Date().toISOString(),
        snapshot_source: source,
        truncated,
        files: copied.map(f => ({
          path: f.rel,
          sha256: sha256File(f.abs),
          size: f.size,
        })),
      }
      writeFileSync(join(destDir, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf-8')
      out.push({
        ...rec,
        snapshot_dir: skillImproveSnapshotRel(opts.taskId, name),
        snapshot_source: source,
      })
    } catch {
      out.push(rec)
    }
  }
  return out
}

export function readSkillSnapshot(
  reportsDir: string,
  taskId: string,
  skillName: string,
): SkillSnapshotRead | null {
  if (!taskId || taskId.includes('..') || /[\\/]/.test(taskId)) return null
  if (!isSkillImproveName(skillName)) return null
  const destDir = join(skillImproveSnapshotRoot(reportsDir, taskId), skillName)
  if (!existsSync(destDir) || !isPathWithin(destDir, skillImproveSnapshotRoot(reportsDir, taskId))) {
    return null
  }
  let manifest: Partial<SkillSnapshotManifest> = {}
  try {
    manifest = JSON.parse(readFileSync(join(destDir, 'manifest.json'), 'utf-8')) as SkillSnapshotManifest
  } catch { /* optional */ }
  let skillMd = ''
  try {
    skillMd = readFileSync(join(destDir, 'SKILL.md'), 'utf-8')
  } catch {
    return null
  }
  const files = collectFiles(destDir).map(f => f.rel).filter(p => p !== 'manifest.json')
  return {
    skill: skillName,
    skill_md: skillMd,
    truncated: !!manifest.truncated,
    snapshot_source: manifest.snapshot_source === 'backfill' ? 'backfill' : 'runtime',
    snapshot_at: String(manifest.snapshot_at || ''),
    files,
  }
}

export interface SkillSnapshotBackfillResult {
  reports_scanned: number
  reports_updated: number
  skills_copied: number
  skipped: string[]
}

/**
 * 用 ledger 的 session_id 反解 taskId，为已有报告补事后快照（snapshot_source=backfill）。
 */
export async function backfillSkillImproveSnapshots(opts: {
  reportsDir: string
  ledgerByTask: Map<string, string[]>
  resolveSkillDir?: (name: string) => string | null
}): Promise<SkillSnapshotBackfillResult> {
  const result: SkillSnapshotBackfillResult = {
    reports_scanned: 0,
    reports_updated: 0,
    skills_copied: 0,
    skipped: [],
  }
  const reportDir = join(opts.reportsDir, 'bug-analysis')
  if (!existsSync(reportDir)) return result

  let entries: Dirent[] = []
  try {
    entries = readdirSync(reportDir, { withFileTypes: true })
  } catch {
    return result
  }

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith('.json')) continue
    const taskId = entry.name.slice(0, -5)
    result.reports_scanned += 1
    const jsonPath = join(reportDir, entry.name)
    let json: Record<string, unknown>
    try {
      json = JSON.parse(readFileSync(jsonPath, 'utf-8')) as Record<string, unknown>
    } catch {
      result.skipped.push(taskId)
      continue
    }
    const existing = Array.isArray(json.skills_improved) ? json.skills_improved as SkillImproveRecord[] : []
    const fromLedger = opts.ledgerByTask.get(taskId) || []
    const names = new Set<string>()
    for (const rec of existing) {
      if (rec?.name) names.add(rec.name)
    }
    for (const name of fromLedger) names.add(name)
    if (names.size === 0) continue

    const records: SkillImproveRecord[] = [...existing]
    for (const name of names) {
      if (!records.some(r => r.name === name)) records.push({ name, actions: ['create'] })
    }
    const needsCopy = records.some(r => !r.snapshot_dir)
    if (!needsCopy) continue

    const snapshotted = await snapshotImprovedSkills({
      reportsDir: opts.reportsDir,
      taskId,
      records,
      resolveSkillDir: opts.resolveSkillDir,
      source: 'backfill',
    })
    const copied = snapshotted.filter(r => r.snapshot_dir).length
    if (copied === 0) {
      result.skipped.push(taskId)
      continue
    }
    json.skills_improved = snapshotted
    writeFileSync(jsonPath, JSON.stringify(json, null, 2), 'utf-8')
    result.reports_updated += 1
    result.skills_copied += copied
  }
  return result
}
