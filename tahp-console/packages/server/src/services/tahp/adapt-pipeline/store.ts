import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'fs'
import { join } from 'path'
import { randomBytes } from 'crypto'
import { tahpPaths } from '../paths'
import { loadWorkflow } from './workflow'
import type {
  CreateRunInput,
  PipelineDomain,
  PipelineRun,
  ResourceConflict,
  RunStatus,
  RunSummary,
  StageState,
} from './types'

interface RunIndexFile {
  version: number
  items: RunSummary[]
}

const ACTIVE_STATUSES: RunStatus[] = ['running', 'waiting_human']

const memoryRuns = new Map<string, PipelineRun>()
const pendingWrites = new Map<string, ReturnType<typeof setTimeout>>()

function pipelineRoot(): string {
  if (process.env.TAHP_ADAPT_PIPELINE_DIR) {
    return process.env.TAHP_ADAPT_PIPELINE_DIR
  }
  return join(tahpPaths.projectRoot, '.tahp-config', 'adapt-pipeline')
}

export function adaptPipelineConfigDir(): string {
  return pipelineRoot()
}

function runsDir(): string {
  return join(pipelineRoot(), 'runs')
}

function indexPath(): string {
  return join(pipelineRoot(), 'index.json')
}

function runFilePath(runId: string): string {
  return join(runsDir(), `${runId}.json`)
}

function ensureDirs(): void {
  const root = pipelineRoot()
  const runs = runsDir()
  if (!existsSync(root)) mkdirSync(root, { recursive: true })
  if (!existsSync(runs)) mkdirSync(runs, { recursive: true })
}

function writeFileAtomic(path: string, content: string): void {
  const tmp = `${path}.${randomBytes(4).toString('hex')}.tmp`
  writeFileSync(tmp, content, 'utf-8')
  renameSync(tmp, path)
}

function newRunId(): string {
  return `run-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function initStageState(key: string): StageState {
  return {
    key,
    status: 'pending',
    attempt: 0,
    refs: {},
  }
}

function toSummary(run: PipelineRun): RunSummary {
  return {
    run_id: run.run_id,
    project_code: run.project_code,
    status: run.status,
    iteration: run.iteration,
    current_node: run.current_node,
    created_at: run.created_at,
    updated_at: run.updated_at,
  }
}

function readIndex(): RunIndexFile {
  const path = indexPath()
  if (!existsSync(path)) {
    return { version: 1, items: [] }
  }
  try {
    const data = JSON.parse(readFileSync(path, 'utf-8')) as RunIndexFile
    return {
      version: data.version ?? 1,
      items: Array.isArray(data.items) ? data.items : [],
    }
  } catch {
    return { version: 1, items: [] }
  }
}

function writeIndex(items: RunSummary[]): void {
  ensureDirs()
  const payload: RunIndexFile = { version: 1, items }
  writeFileAtomic(indexPath(), `${JSON.stringify(payload, null, 2)}\n`)
}

function upsertIndexSummary(summary: RunSummary): void {
  const index = readIndex()
  const pos = index.items.findIndex(i => i.run_id === summary.run_id)
  if (pos >= 0) {
    index.items[pos] = summary
  } else {
    index.items.unshift(summary)
  }
  index.items.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  writeIndex(index.items)
}

function writeRunToDisk(run: PipelineRun): void {
  ensureDirs()
  writeFileSync(runFilePath(run.run_id), `${JSON.stringify(run, null, 2)}\n`, 'utf-8')
}

function flushPending(runId: string): void {
  const timer = pendingWrites.get(runId)
  if (timer) {
    clearTimeout(timer)
    pendingWrites.delete(runId)
  }
}

function filterDomains(input: CreateRunInput): PipelineDomain[] {
  const domains = input.domains ?? []
  if (!input.domain_ids?.length) return domains
  const allowed = new Set(input.domain_ids)
  return domains.map(d => ({
    ...d,
    enabled: d.enabled && allowed.has(d.domain_id),
  }))
}

function buildRunObject(input: CreateRunInput, runId: string): PipelineRun {
  const workflow = loadWorkflow()
  const now = new Date().toISOString()
  const stages: Record<string, StageState> = {}
  for (const node of workflow.nodes) {
    if (node.enabled) {
      stages[node.key] = initStageState(node.key)
    }
  }

  return {
    run_id: runId,
    workflow_id: input.workflow_id ?? workflow.id,
    workflow_version: workflow.version,
    project_code: input.project_code,
    campaign_id: input.campaign_id,
    from_os: input.from_os,
    to_os: input.to_os,
    status: 'draft',
    current_node: null,
    iteration: 1,
    max_iterations: input.max_iterations ?? workflow.maxIterations,
    created_at: now,
    updated_at: now,
    domains: filterDomains(input),
    build_context: input.build_context,
    device_id: input.device_id,
    test_plan: input.test_plan,
    stages,
    iterations: [],
    artifacts: {},
  }
}

/** 不落盘，仅用于创建前资源冲突预检 */
export function buildRunPreview(input: CreateRunInput): PipelineRun {
  return buildRunObject(input, newRunId())
}

export function createRun(input: CreateRunInput): PipelineRun {
  const run = buildRunObject(input, newRunId())
  saveRun(run, { immediate: true })
  return run
}

export function getRun(runId: string): PipelineRun | null {
  const cached = memoryRuns.get(runId)
  if (cached) return cached

  const path = runFilePath(runId)
  if (!existsSync(path)) return null
  try {
    const run = JSON.parse(readFileSync(path, 'utf-8')) as PipelineRun
    memoryRuns.set(runId, run)
    return run
  } catch {
    return null
  }
}

export function saveRun(run: PipelineRun, opts?: { immediate?: boolean }): void {
  run.updated_at = new Date().toISOString()
  memoryRuns.set(run.run_id, run)

  const persist = () => {
    writeRunToDisk(run)
    upsertIndexSummary(toSummary(run))
    pendingWrites.delete(run.run_id)
  }

  if (opts?.immediate) {
    flushPending(run.run_id)
    persist()
    return
  }

  flushPending(run.run_id)
  const timer = setTimeout(persist, 500)
  pendingWrites.set(run.run_id, timer)
}

export function listRuns(filter?: {
  status?: RunStatus[]
  limit?: number
  offset?: number
}): { items: RunSummary[]; total: number } {
  const index = readIndex()
  let items = index.items
  if (filter?.status?.length) {
    const allowed = new Set(filter.status)
    items = items.filter(i => allowed.has(i.status))
  }
  const total = items.length
  const offset = filter?.offset ?? 0
  const limit = filter?.limit ?? total
  return { items: items.slice(offset, offset + limit), total }
}

export function listActiveRunIds(): string[] {
  return readIndex()
    .items.filter(i => ACTIVE_STATUSES.includes(i.status))
    .map(i => i.run_id)
}

function workspaceKey(run: PipelineRun): string | null {
  const ws = run.build_context?.workspace?.trim()
  if (!ws) return null
  const root = (run.build_context?.mapped_root ?? '').trim().replace(/\\/g, '/').toLowerCase()
  return `${root}|${ws}`
}

/** 与 running / waiting_human 的 run 比对独占资源 */
export function findResourceConflict(candidate: PipelineRun): ResourceConflict | null {
  const candidateWs = workspaceKey(candidate)
  const candidateDevice = candidate.device_id?.trim()

  for (const runId of listActiveRunIds()) {
    if (runId === candidate.run_id) continue
    const other = getRun(runId)
    if (!other) continue

    if (candidateWs) {
      const otherWs = workspaceKey(other)
      if (otherWs && otherWs === candidateWs) {
        const node = other.current_node || '—'
        return {
          kind: 'workspace',
          holderRunId: other.run_id,
          detail:
            `workspace \`${other.build_context.workspace}\` 正被 ${other.run_id} 占用`
            + `（状态 ${other.status}，节点 ${node}）。`
            + `请到运行看板打开该任务并「终止」，或等其结束后再启动。`,
        }
      }
    }

    if (candidateDevice && other.device_id?.trim() === candidateDevice) {
      return {
        kind: 'device',
        holderRunId: other.run_id,
        detail:
          `设备 ${other.device_id} 正被 ${other.run_id} 占用（状态 ${other.status}）。`
          + `请终止占用任务或更换设备。`,
      }
    }

    for (const domain of candidate.domains) {
      if (!domain.enabled) continue
      const conflict = other.domains.find(d =>
        d.enabled
        && d.domain_id === domain.domain_id
        && d.workspace_id === domain.workspace_id
        && d.status === 'running'
        && d.adapt_task_id,
      )
      if (conflict) {
        return {
          kind: 'domain',
          holderRunId: other.run_id,
          detail: `域 ${domain.domain_id} 正被 ${other.run_id} 占用（任务 ${conflict.adapt_task_id}）`,
        }
      }
    }
  }

  return null
}

/** 删除未启动的草稿运行（启动失败时清理） */
export function deleteDraftRun(runId: string): boolean {
  const run = getRun(runId)
  if (!run || run.status !== 'draft') return false

  flushPending(runId)
  memoryRuns.delete(runId)

  const path = runFilePath(runId)
  if (existsSync(path)) {
    try {
      unlinkSync(path)
    } catch {
      return false
    }
  }

  const index = readIndex()
  writeIndex(index.items.filter(i => i.run_id !== runId))
  return true
}

/** 测试用：清空内存缓存与待写队列 */
export function resetStoreForTest(): void {
  for (const timer of pendingWrites.values()) {
    clearTimeout(timer)
  }
  pendingWrites.clear()
  memoryRuns.clear()
}
