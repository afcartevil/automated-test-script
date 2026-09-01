/**
 * 射频校准 MetaCLI run 持久化：{projectRoot}/.tahp-config/rf-calib-meta/
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'fs'
import { join } from 'path'
import { randomBytes } from 'crypto'
import { tahpPaths } from '../paths'
import type { RfCalibMetaConnectionStrategy } from './types'
import type { RfCalibMetaRunRecord, RfCalibMetaRunStatus, RfCalibMetaRunSummary } from './types'

interface RunIndexFile {
  version: number
  items: RfCalibMetaRunSummary[]
}

const memoryRuns = new Map<string, RfCalibMetaRunRecord>()
const ACTIVE: RfCalibMetaRunStatus[] = ['pending', 'running']

function rootDir(): string {
  if (process.env.TAHP_RF_CALIB_META_DIR) return process.env.TAHP_RF_CALIB_META_DIR
  return join(tahpPaths.projectRoot, '.tahp-config', 'rf-calib-meta')
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

function toSummary(run: RfCalibMetaRunRecord): RfCalibMetaRunSummary {
  return {
    run_id: run.run_id,
    label: run.label,
    mode: run.mode,
    status: run.status,
    phase: run.phase,
    progress: run.progress,
    message: run.message,
    cal_file_path: run.cal_file_path,
    items_ini_path: run.items_ini_path,
    output_cal_path: run.output_cal_path,
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

function writeIndex(items: RfCalibMetaRunSummary[]): void {
  ensureDirs()
  writeAtomic(indexPath(), JSON.stringify({ version: 1, items }, null, 2))
}

function upsertIndex(run: RfCalibMetaRunRecord): void {
  const idx = readIndex()
  const summary = toSummary(run)
  const i = idx.items.findIndex(x => x.run_id === run.run_id)
  if (i >= 0) idx.items[i] = summary
  else idx.items.unshift(summary)
  idx.items = idx.items.slice(0, 200)
  writeIndex(idx.items)
}

export function newRfCalibMetaRunId(): string {
  return `rf-cal-${Date.now()}-${randomBytes(3).toString('hex')}`
}

export function createRfCalibMetaRun(opts: {
  runId?: string
  label: string
  mode: RfCalibMetaRunRecord['mode']
  calFilePath: string
  itemsIniPath: string
  outputCalPath?: string
  comPort?: string
  metaRoot?: string
  initFilePath?: string
  adbDeviceId?: string
  connectionStrategy?: RfCalibMetaConnectionStrategy
}): RfCalibMetaRunRecord {
  const now = new Date().toISOString()
  const run: RfCalibMetaRunRecord = {
    run_id: opts.runId || newRfCalibMetaRunId(),
    label: opts.label.trim() || (opts.mode === 'backup' ? '备份校准数据' : '恢复校准数据'),
    mode: opts.mode,
    cal_file_path: opts.calFilePath,
    items_ini_path: opts.itemsIniPath,
    output_cal_path: opts.outputCalPath,
    com_port: opts.comPort,
    meta_root: opts.metaRoot,
    init_file_path: opts.initFilePath,
    adb_device_id: opts.adbDeviceId,
    connection_strategy: opts.connectionStrategy,
    status: 'pending',
    phase: 'init',
    progress: 0,
    log_tail: [],
    created_at: now,
    updated_at: now,
  }
  saveRfCalibMetaRun(run)
  return run
}

export function saveRfCalibMetaRun(run: RfCalibMetaRunRecord): void {
  ensureDirs()
  run.updated_at = new Date().toISOString()
  memoryRuns.set(run.run_id, run)
  writeAtomic(runFilePath(run.run_id), JSON.stringify(run, null, 2))
  upsertIndex(run)
}

export function getRfCalibMetaRun(runId: string): RfCalibMetaRunRecord | undefined {
  const cached = memoryRuns.get(runId)
  if (cached) return cached
  const path = runFilePath(runId)
  if (!existsSync(path)) return undefined
  try {
    const run = JSON.parse(readFileSync(path, 'utf-8')) as RfCalibMetaRunRecord
    memoryRuns.set(runId, run)
    return run
  } catch {
    return undefined
  }
}

export function listRfCalibMetaRuns(limit = 50): RfCalibMetaRunSummary[] {
  return readIndex().items.slice(0, limit)
}

export function appendRfCalibMetaLog(runId: string, line: string, max = 800): void {
  const run = getRfCalibMetaRun(runId)
  if (!run || !line?.trim()) return
  run.log_tail = [...run.log_tail, line.trim()].slice(-max)
  memoryRuns.set(runId, run)
}

export function patchRfCalibMetaRun(
  runId: string,
  patch: Partial<RfCalibMetaRunRecord>,
  opts?: { persist?: boolean },
): RfCalibMetaRunRecord | undefined {
  const run = getRfCalibMetaRun(runId)
  if (!run) return undefined
  Object.assign(run, patch)
  if (opts?.persist === false) {
    memoryRuns.set(runId, run)
    return run
  }
  saveRfCalibMetaRun(run)
  return run
}

export function listActiveRfCalibMetaRuns(): RfCalibMetaRunRecord[] {
  ensureDirs()
  const out: RfCalibMetaRunRecord[] = []
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
    const run = getRfCalibMetaRun(id)
    if (run && ACTIVE.includes(run.status)) out.push(run)
  }
  return out
}

export function resetRfCalibMetaStoreForTest(): void {
  memoryRuns.clear()
}

export function rfCalibMetaConfigRoot(): string {
  return rootDir()
}
