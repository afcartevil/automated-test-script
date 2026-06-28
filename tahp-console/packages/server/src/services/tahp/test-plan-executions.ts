/**
 * AI 测试规划执行态持久化
 */
import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { safeFileStore } from '../safe-file-store'
import { tahpPaths } from './paths'
import type { PlanTestType } from './test-planning'

export type PlanRuntimeStatus = 'pending' | 'no_device' | 'running' | 'completed'

export interface PlanExecutionRecord {
  scheduleKey: string
  runtimeStatus: PlanRuntimeStatus
  deviceId?: string
  startedAt?: string
  completedAt?: string
  updatedAt: string
}

interface PlanExecutionsFile {
  version: number
  records: Record<string, PlanExecutionRecord>
}

function configDir(): string {
  if (process.env.TAHP_TEST_PLANNING_CONFIG_DIR) {
    return process.env.TAHP_TEST_PLANNING_CONFIG_DIR
  }
  return join(tahpPaths.projectRoot, '.tahp-config')
}

export function planExecutionsConfigPath(): string {
  return join(configDir(), 'test-plan-executions.json')
}

function ensureConfigDir(): void {
  const dir = configDir()
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

export function buildScheduleKey(
  project: string,
  node: string,
  triggerDate: string,
  testType: PlanTestType,
): string {
  return `${project}|${node}|${triggerDate}|${testType}`
}

export async function loadPlanExecutions(): Promise<Record<string, PlanExecutionRecord>> {
  const path = planExecutionsConfigPath()
  if (!existsSync(path)) return {}
  try {
    const raw = await safeFileStore.readText(path)
    const data = JSON.parse(raw) as Partial<PlanExecutionsFile>
    return data.records && typeof data.records === 'object' ? data.records : {}
  } catch {
    return {}
  }
}

async function savePlanExecutions(records: Record<string, PlanExecutionRecord>): Promise<void> {
  ensureConfigDir()
  const payload: PlanExecutionsFile = { version: 1, records }
  await safeFileStore.writeText(
    planExecutionsConfigPath(),
    `${JSON.stringify(payload, null, 2)}\n`,
  )
}

export async function getPlanExecution(scheduleKey: string): Promise<PlanExecutionRecord | null> {
  const records = await loadPlanExecutions()
  return records[scheduleKey] ?? null
}

export async function upsertPlanExecution(
  scheduleKey: string,
  patch: Partial<Omit<PlanExecutionRecord, 'scheduleKey'>> & { runtimeStatus: PlanRuntimeStatus },
): Promise<PlanExecutionRecord> {
  const records = await loadPlanExecutions()
  const existing = records[scheduleKey]
  const record: PlanExecutionRecord = {
    scheduleKey,
    runtimeStatus: patch.runtimeStatus,
    deviceId: patch.deviceId ?? existing?.deviceId,
    startedAt: patch.startedAt ?? existing?.startedAt,
    completedAt: patch.completedAt ?? existing?.completedAt,
    updatedAt: new Date().toISOString(),
  }
  records[scheduleKey] = record
  await savePlanExecutions(records)
  return record
}

export async function markPlanExecutionRunning(
  scheduleKey: string,
  deviceId: string,
): Promise<PlanExecutionRecord> {
  return upsertPlanExecution(scheduleKey, {
    runtimeStatus: 'running',
    deviceId,
    startedAt: new Date().toISOString(),
  })
}

export async function markPlanExecutionNoDevice(scheduleKey: string): Promise<PlanExecutionRecord> {
  return upsertPlanExecution(scheduleKey, { runtimeStatus: 'no_device' })
}

export async function markPlanExecutionCompleted(scheduleKey: string): Promise<PlanExecutionRecord> {
  return upsertPlanExecution(scheduleKey, {
    runtimeStatus: 'completed',
    completedAt: new Date().toISOString(),
  })
}
