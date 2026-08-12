/**
 * 代码拉取 run 持久化：{projectRoot}/.tahp-config/code-pull/runs/{runId}.json
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'fs'
import { join } from 'path'
import { randomBytes } from 'crypto'
import { tahpPaths } from '../paths'
import type { CodePullRunRecord, CodePullRunSummary, CodePullRunStatus } from './types'

interface RunIndexFile {
  version: number
  items: CodePullRunSummary[]
}

const memoryRuns = new Map<string, CodePullRunRecord>()
const ACTIVE: CodePullRunStatus[] = ['pending', 'running']

function rootDir(): string {
  if (process.env.TAHP_CODE_PULL_DIR) return process.env.TAHP_CODE_PULL_DIR
  return join(tahpPaths.projectRoot, '.tahp-config', 'code-pull')
}

function runsDir(): string {
  return join(rootDir(), 'runs')
}

function indexPath(): string {
  return join(rootDir(), 'index.json')
}

function runFilePath(runId: string): string {
  return join(runsDir(), `${runId}.json`)
}

function ensureDirs(): void {
  if (!existsSync(rootDir())) mkdirSync(rootDir(), { recursive: true })
  if (!existsSync(runsDir())) mkdirSync(runsDir(), { recursive: true })
}

function writeAtomic(path: string, content: string): void {
  const tmp = `${path}.${randomBytes(4).toString('hex')}.tmp`
  writeFileSync(tmp, content, 'utf-8')
  renameSync(tmp, path)
}

function toSummary(run: CodePullRunRecord): CodePullRunSummary {
  return {
    run_id: run.run_id,
    project_name: run.project_name,
    status: run.status,
    phase: run.phase,
    progress: run.progress,
    message: run.message,
    system_path_win: run.system_path_win,
    vendor_path_win: run.vendor_path_win,
    code_path_win: run.code_path_win || run.system_path_win,
    code_path_linux: run.code_path_linux || run.system_path_linux,
    created_at: run.created_at,
    updated_at: run.updated_at,
    completed_at: run.completed_at,
  }
}

function readIndex(): RunIndexFile {
  ensureDirs()
  if (!existsSync(indexPath())) return { version: 1, items: [] }
  try {
    return JSON.parse(readFileSync(indexPath(), 'utf-8')) as RunIndexFile
  } catch {
    return { version: 1, items: [] }
  }
}

function writeIndex(items: CodePullRunSummary[]): void {
  ensureDirs()
  writeAtomic(indexPath(), JSON.stringify({ version: 1, items }, null, 2))
}

function upsertIndex(run: CodePullRunRecord): void {
  const idx = readIndex()
  const summary = toSummary(run)
  const i = idx.items.findIndex(x => x.run_id === run.run_id)
  if (i >= 0) idx.items[i] = summary
  else idx.items.unshift(summary)
  idx.items = idx.items.slice(0, 200)
  writeIndex(idx.items)
}

export function newCodePullRunId(): string {
  return `code-pull-${Date.now()}-${randomBytes(3).toString('hex')}`
}

export function createCodePullRun(opts: {
  label: string
  systemRepoInit: string
  vendorRepoInit: string
}): CodePullRunRecord {
  const now = new Date().toISOString()
  const run: CodePullRunRecord = {
    run_id: newCodePullRunId(),
    project_name: opts.label.trim() || 'repo-sync',
    system_repo_init: opts.systemRepoInit,
    vendor_repo_init: opts.vendorRepoInit,
    status: 'pending',
    phase: 'init',
    progress: 0,
    log_tail: [],
    created_at: now,
    updated_at: now,
  }
  saveCodePullRun(run)
  return run
}

export function saveCodePullRun(run: CodePullRunRecord): void {
  ensureDirs()
  run.updated_at = new Date().toISOString()
  memoryRuns.set(run.run_id, run)
  writeAtomic(runFilePath(run.run_id), JSON.stringify(run, null, 2))
  upsertIndex(run)
}

export function getCodePullRun(runId: string): CodePullRunRecord | undefined {
  const cached = memoryRuns.get(runId)
  if (cached) return cached
  const path = runFilePath(runId)
  if (!existsSync(path)) return undefined
  try {
    const run = JSON.parse(readFileSync(path, 'utf-8')) as CodePullRunRecord
    memoryRuns.set(runId, run)
    return run
  } catch {
    return undefined
  }
}

export function listCodePullRuns(limit = 50): CodePullRunSummary[] {
  return readIndex().items.slice(0, limit)
}

export function appendCodePullLog(runId: string, line: string, max = 800): void {
  const run = getCodePullRun(runId)
  if (!run || !line?.trim()) return
  run.log_tail = [...run.log_tail, line.trim()].slice(-max)
  memoryRuns.set(runId, run)
}

export function patchCodePullRun(
  runId: string,
  patch: Partial<CodePullRunRecord>,
  opts?: { persist?: boolean },
): CodePullRunRecord | undefined {
  const run = getCodePullRun(runId)
  if (!run) return undefined
  Object.assign(run, patch)
  if (opts?.persist === false) {
    memoryRuns.set(runId, run)
    return run
  }
  saveCodePullRun(run)
  return run
}

export function listActiveCodePullRuns(): CodePullRunRecord[] {
  ensureDirs()
  const out: CodePullRunRecord[] = []
  const seen = new Set<string>()
  for (const run of memoryRuns.values()) {
    if (ACTIVE.includes(run.status)) {
      out.push(run)
      seen.add(run.run_id)
    }
  }
  if (!existsSync(runsDir())) return out
  for (const name of readdirSync(runsDir())) {
    if (!name.endsWith('.json')) continue
    const id = name.replace(/\.json$/, '')
    if (seen.has(id)) continue
    const run = getCodePullRun(id)
    if (run && ACTIVE.includes(run.status)) out.push(run)
  }
  return out
}

export function resetCodePullStoreForTest(): void {
  memoryRuns.clear()
}
