/**
 * 为历史诊断报告回填自改进 Skill 快照（snapshot_source=backfill）。
 *
 * 用法（在 tahp-console 目录）:
 *   node scripts/backfill-skill-improve-snapshots.mjs
 *   node scripts/backfill-skill-improve-snapshots.mjs --dry-run
 */
import { createHash } from 'crypto'
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
  cpSync,
} from 'fs'
import { join, relative } from 'path'
import { getTahpProjectRoot } from './lib/tahp-paths.mjs'

const dryRun = process.argv.includes('--dry-run')

function hermesSkillsDir() {
  if (process.env.HERMES_HOME) return join(process.env.HERMES_HOME, 'skills')
  if (process.platform === 'win32') {
    const base = process.env.LOCALAPPDATA || process.env.APPDATA
    if (base) return join(base, 'hermes', 'skills')
  }
  return join(process.env.HOME || process.env.USERPROFILE || '', '.hermes', 'skills')
}

function isSkillName(name) {
  return !!name && !name.startsWith('.') && /^[a-z0-9][a-z0-9._-]*$/i.test(name)
}

function taskIdFromSessionId(sessionId) {
  const s = String(sessionId || '').trim()
  if (s.startsWith('tahp-bug-')) return s.slice('tahp-bug-'.length) || null
  return null
}

function parseLedger(text) {
  const entries = []
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    try {
      const obj = JSON.parse(line)
      if (!isSkillName(obj.skill) || !obj.action) continue
      entries.push(obj)
    } catch { /* skip */ }
  }
  return entries
}

function findSkillDir(profileSkillsDir, name) {
  const flat = join(profileSkillsDir, name)
  if (existsSync(join(flat, 'SKILL.md'))) return flat
  let entries = []
  try { entries = readdirSync(profileSkillsDir, { withFileTypes: true }) } catch { return null }
  for (const e of entries) {
    if (!e.isDirectory() || e.name.startsWith('.')) continue
    const nested = join(profileSkillsDir, e.name, name)
    if (existsSync(join(nested, 'SKILL.md'))) return nested
  }
  return null
}

function collectFiles(root) {
  const out = []
  const walk = (current) => {
    let entries = []
    try { entries = readdirSync(current, { withFileTypes: true }) } catch { return }
    for (const entry of entries) {
      if (entry.name === '.git' || entry.name === 'node_modules') continue
      const abs = join(current, entry.name)
      if (entry.isDirectory()) { walk(abs); continue }
      if (!entry.isFile()) continue
      if (entry.name === 'manifest.json' && current === root) continue
      out.push({ abs, rel: relative(root, abs).replace(/\\/g, '/'), size: statSync(abs).size })
    }
  }
  walk(root)
  return out
}

function sha256File(abs) {
  return createHash('sha256').update(readFileSync(abs)).digest('hex')
}

const projectRoot = getTahpProjectRoot()
const reportsDir = join(projectRoot, 'reports')
const profileSkills = hermesSkillsDir()
const ledgerPath = join(profileSkills, '.curator_ledger.jsonl')

console.log(`[backfill] projectRoot=${projectRoot}`)
console.log(`[backfill] profileSkills=${profileSkills}`)
console.log(`[backfill] ledger=${existsSync(ledgerPath) ? ledgerPath : 'MISSING'}`)
if (dryRun) console.log('[backfill] dry-run')

if (!existsSync(ledgerPath)) {
  console.error('curator ledger 不存在，无法回填')
  process.exit(1)
}

const entries = parseLedger(readFileSync(ledgerPath, 'utf-8'))
const byTask = new Map()
for (const entry of entries) {
  const tid = taskIdFromSessionId(entry.evidence?.session_id)
  if (!tid) continue
  const list = byTask.get(tid) || []
  if (!list.includes(entry.skill)) list.push(entry.skill)
  byTask.set(tid, list)
}

const reportDir = join(reportsDir, 'bug-analysis')
if (!existsSync(reportDir)) {
  console.error('reports/bug-analysis 不存在')
  process.exit(1)
}

let scanned = 0
let updated = 0
let copied = 0
for (const file of readdirSync(reportDir)) {
  if (!file.endsWith('.json')) continue
  const taskId = file.slice(0, -5)
  scanned += 1
  const jsonPath = join(reportDir, file)
  let json
  try { json = JSON.parse(readFileSync(jsonPath, 'utf-8')) } catch { continue }
  const existing = Array.isArray(json.skills_improved) ? json.skills_improved : []
  const names = new Set(existing.map(r => r?.name).filter(Boolean))
  for (const n of byTask.get(taskId) || []) names.add(n)
  if (!names.size) continue
  const records = [...existing]
  for (const name of names) {
    if (!records.some(r => r.name === name)) records.push({ name, actions: ['create'] })
  }
  if (records.every(r => r.snapshot_dir)) continue

  const next = []
  for (const rec of records) {
    const srcDir = findSkillDir(profileSkills, rec.name)
    if (!srcDir) { next.push(rec); continue }
    const destDir = join(reportDir, 'skills', taskId, rec.name)
    if (dryRun) {
      next.push({
        ...rec,
        snapshot_dir: `bug-analysis/skills/${taskId}/${rec.name}`,
        snapshot_source: 'backfill',
      })
      copied += 1
      continue
    }
    if (existsSync(destDir)) rmSync(destDir, { recursive: true, force: true })
    mkdirSync(destDir, { recursive: true })
    cpSync(srcDir, destDir, { recursive: true })
    const files = collectFiles(destDir)
    writeFileSync(join(destDir, 'manifest.json'), JSON.stringify({
      skill: rec.name,
      source_path: srcDir,
      snapshot_at: new Date().toISOString(),
      snapshot_source: 'backfill',
      truncated: false,
      files: files.map(f => ({ path: f.rel, sha256: sha256File(f.abs), size: f.size })),
    }, null, 2), 'utf-8')
    next.push({
      ...rec,
      snapshot_dir: `bug-analysis/skills/${taskId}/${rec.name}`,
      snapshot_source: 'backfill',
    })
    copied += 1
  }
  if (next.some(r => r.snapshot_dir) && JSON.stringify(next) !== JSON.stringify(existing)) {
    json.skills_improved = next
    if (!dryRun) writeFileSync(jsonPath, JSON.stringify(json, null, 2), 'utf-8')
    updated += 1
    console.log(`[backfill] ${taskId} → ${next.filter(r => r.snapshot_dir).map(r => r.name).join(', ')}`)
  }
}

console.log(`[backfill] scanned=${scanned} updated=${updated} skills_copied=${copied}`)
