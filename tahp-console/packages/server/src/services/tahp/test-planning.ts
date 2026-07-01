/**
 * AI 测试自规划 — 项目节点同步、规则配置与待执行计划计算
 */
import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { safeFileStore } from '../safe-file-store'
import { tahpPaths } from './paths'
import {
  NODE_KEYS,
  type ProjectNodeEntry,
  type ProjectNodeKey,
  parseProjectInfoXlsx,
} from './project-info-xlsx'
import {
  buildScheduleKey,
  loadPlanExecutions,
  type PlanRuntimeStatus,
} from './test-plan-executions'

export const MAX_OFFSET_DAYS = 14
export const UPCOMING_HORIZON_DAYS = 14

export type PlanTestType = 'str4' | 'week' | 'monkey' | 'smoke' | 'gms' | 'power'

export interface ProjectNodesFile {
  updatedAt: string
  sourcePath: string
  projects: ProjectNodeEntry[]
}

export interface TestPlanRule {
  node: ProjectNodeKey
  offsetDays: number
  testType: PlanTestType
}

export interface TestPlanRulesFile {
  version: number
  rules: TestPlanRule[]
}

export interface NextNodeItem {
  project: string
  node: ProjectNodeKey
  nodeDate: string
  display: string
}

export interface ScheduleItem {
  scheduleKey: string
  project: string
  node: ProjectNodeKey
  nodeDate: string
  triggerDate: string
  testType: PlanTestType
  testTypeLabel: string
  phase: 'upcoming' | 'active'
  runtimeStatus: PlanRuntimeStatus
  displayLabel: '即将开始' | '进行中' | '已完成'
  tags: string[]
  display: string
  /** @deprecated 保留兼容，等同 testTypeLabel */
  testName?: string
  /** @deprecated 保留兼容，由 phase + runtimeStatus 推导 */
  status?: 'active' | 'upcoming'
}

const TEST_TYPE_LABELS: Record<PlanTestType, string> = {
  str4: '转测摸底测试',
  week: '周版本测试',
  monkey: 'monkey测试',
  smoke: '冒烟测试',
  gms: 'GMS测试',
  power: '功耗自动化测试',
}

export function getTestTypeLabel(testType: PlanTestType): string {
  return TEST_TYPE_LABELS[testType] || testType
}

export function normalizePlanTestType(raw: unknown): PlanTestType | null {
  const text = String(raw || '').trim().toLowerCase()
  if (text === 'str4' || text.includes('转测') || text.includes('摸底')) return 'str4'
  if (text === 'week' || text.includes('周版本')) return 'week'
  if (text === 'monkey' || text.includes('monkey')) return 'monkey'
  if (text === 'smoke' || text.includes('冒烟')) return 'smoke'
  if (text === 'gms' || text.includes('gms')) return 'gms'
  if (text === 'power' || text.includes('功耗')) return 'power'
  return null
}

function configDir(): string {
  if (process.env.TAHP_TEST_PLANNING_CONFIG_DIR) {
    return process.env.TAHP_TEST_PLANNING_CONFIG_DIR
  }
  return join(tahpPaths.projectRoot, '.tahp-config')
}

export function projectNodesConfigPath(): string {
  return join(configDir(), 'project-nodes.json')
}

export function testPlanRulesConfigPath(): string {
  return join(configDir(), 'test-plan-rules.json')
}

function ensureConfigDir(): void {
  const dir = configDir()
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

export function toIsoDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function fromDisplayDate(display: string): Date {
  const [y, m, d] = display.split('/').map(Number)
  return new Date(y, m - 1, d)
}

export function toDisplayDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}/${m}/${d}`
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function startOfToday(today?: Date): Date {
  const base = today ? new Date(today) : new Date()
  base.setHours(0, 0, 0, 0)
  return base
}

export function matchProjectToDevice(
  project: string,
  device: { deviceName: string; status: string; role: string },
): boolean {
  if (device.status !== '空闲') return false
  if (device.role === '辅测机') return false
  const projectCode = project.trim().toUpperCase()
  if (!projectCode) return false
  return device.deviceName.toUpperCase().includes(projectCode)
}

export function getNextNodes(projects: ProjectNodeEntry[], today?: Date): NextNodeItem[] {
  const now = startOfToday(today)
  const items: NextNodeItem[] = []

  for (const project of projects) {
    let best: { node: ProjectNodeKey; date: Date; display: string } | null = null

    for (const node of NODE_KEYS) {
      const raw = project.nodes[node]
      if (!raw) continue
      const date = fromDisplayDate(raw)
      if (date <= now) continue
      if (!best || date < best.date) {
        best = { node, date, display: raw }
      }
    }

    if (best) {
      items.push({
        project: project.name,
        node: best.node,
        nodeDate: best.display,
        display: `${project.name} ${best.node} ${best.display}`,
      })
    }
  }

  items.sort((a, b) => {
    const diff = fromDisplayDate(a.nodeDate).getTime() - fromDisplayDate(b.nodeDate).getTime()
    return diff !== 0 ? diff : a.project.localeCompare(b.project, 'zh-CN')
  })

  return items
}

function resolveDisplayLabel(
  phase: 'upcoming' | 'active',
  runtimeStatus: PlanRuntimeStatus,
): ScheduleItem['displayLabel'] {
  if (runtimeStatus === 'completed') return '已完成'
  if (runtimeStatus === 'running') return '进行中'
  if (runtimeStatus === 'no_device') return '即将开始'
  return phase === 'active' ? '进行中' : '即将开始'
}

function resolveTags(runtimeStatus: PlanRuntimeStatus): string[] {
  if (runtimeStatus === 'no_device') return ['无设备']
  return []
}

export function buildTestSchedule(
  projects: ProjectNodeEntry[],
  rules: TestPlanRule[],
  today?: Date,
  executions: Record<string, { runtimeStatus: PlanRuntimeStatus }> = {},
): ScheduleItem[] {
  const now = startOfToday(today)
  const horizonEnd = addDays(now, UPCOMING_HORIZON_DAYS)
  const items: ScheduleItem[] = []

  for (const project of projects) {
    for (const rule of rules) {
      const nodeDateStr = project.nodes[rule.node]
      if (!nodeDateStr) continue

      const nodeDate = fromDisplayDate(nodeDateStr)
      const triggerDate = addDays(nodeDate, rule.offsetDays)

      const isActive = triggerDate <= now && now <= nodeDate
      const isUpcoming = now < triggerDate && triggerDate <= horizonEnd
      if (!isActive && !isUpcoming) continue

      const triggerDisplay = toDisplayDate(triggerDate)
      const testTypeLabel = getTestTypeLabel(rule.testType)
      const scheduleKey = buildScheduleKey(project.name, rule.node, triggerDisplay, rule.testType)
      const execution = executions[scheduleKey]
      const runtimeStatus: PlanRuntimeStatus = execution?.runtimeStatus ?? 'pending'
      const phase = isActive ? 'active' : 'upcoming'
      const displayLabel = resolveDisplayLabel(phase, runtimeStatus)
      const tags = resolveTags(runtimeStatus)

      items.push({
        scheduleKey,
        project: project.name,
        node: rule.node,
        nodeDate: nodeDateStr,
        triggerDate: triggerDisplay,
        testType: rule.testType,
        testTypeLabel,
        phase,
        runtimeStatus,
        displayLabel,
        tags,
        display: `${project.name} ${rule.node} ${triggerDisplay} ${testTypeLabel}`,
        testName: testTypeLabel,
        status: phase,
      })
    }
  }

  items.sort((a, b) => {
    const diff = fromDisplayDate(a.triggerDate).getTime() - fromDisplayDate(b.triggerDate).getTime()
    if (diff !== 0) return diff
    const projectDiff = a.project.localeCompare(b.project, 'zh-CN')
    if (projectDiff !== 0) return projectDiff
    return a.testTypeLabel.localeCompare(b.testTypeLabel, 'zh-CN')
  })

  return items
}

export async function getProjectNodesFile(): Promise<ProjectNodesFile | null> {
  const path = projectNodesConfigPath()
  if (!existsSync(path)) return null
  try {
    const raw = await safeFileStore.readText(path)
    return JSON.parse(raw) as ProjectNodesFile
  } catch {
    return null
  }
}

function normalizeStoredRule(raw: Record<string, unknown>): TestPlanRule | null {
  const node = String(raw.node || '').trim() as ProjectNodeKey
  const offsetDays = Number(raw.offsetDays)
  let testType = normalizePlanTestType(raw.testType)
  if (!testType && raw.testName) {
    testType = normalizePlanTestType(raw.testName)
    if (testType) {
      logger.warn(
        { node, testName: raw.testName, testType },
        '[test-planning] migrated legacy testName to testType',
      )
    } else {
      logger.warn({ node, testName: raw.testName }, '[test-planning] dropped legacy rule with unknown testName')
      return null
    }
  }
  if (!testType) return null
  if (!Number.isInteger(offsetDays)) return null
  return { node, offsetDays, testType }
}

export async function getTestPlanRules(): Promise<TestPlanRulesFile> {
  const path = testPlanRulesConfigPath()
  if (!existsSync(path)) {
    return { version: 2, rules: [] }
  }
  try {
    const raw = await safeFileStore.readText(path)
    const data = JSON.parse(raw) as Partial<TestPlanRulesFile> & { rules?: unknown[] }
    const rules: TestPlanRule[] = []
    if (Array.isArray(data.rules)) {
      for (const item of data.rules) {
        if (!item || typeof item !== 'object') continue
        const normalized = normalizeStoredRule(item as Record<string, unknown>)
        if (normalized) rules.push(normalized)
      }
    }
    return {
      version: 2,
      rules,
    }
  } catch {
    return { version: 2, rules: [] }
  }
}

export function validateTestPlanRules(rules: TestPlanRule[]): TestPlanRule[] {
  const validNodes = new Set<string>(NODE_KEYS)
  const validTypes = new Set<string>(['str4', 'week', 'monkey', 'smoke', 'gms', 'power'])
  const cleaned: TestPlanRule[] = []

  for (const rule of rules) {
    const node = String(rule.node || '').trim() as ProjectNodeKey
    if (!validNodes.has(node)) {
      throw new Error(`无效节点: ${rule.node}`)
    }
    const offsetDays = Number(rule.offsetDays)
    if (!Number.isInteger(offsetDays) || offsetDays < -MAX_OFFSET_DAYS || offsetDays > MAX_OFFSET_DAYS) {
      throw new Error(`偏移天数须在 -${MAX_OFFSET_DAYS} 至 ${MAX_OFFSET_DAYS} 之间`)
    }
    const testType = String(rule.testType || '').trim() as PlanTestType
    if (!validTypes.has(testType)) {
      throw new Error(`无效测试大类: ${rule.testType}，须为 str4 / week / monkey / smoke / gms`)
    }
    cleaned.push({ node, offsetDays, testType })
  }

  return cleaned
}

export async function saveTestPlanRules(rules: TestPlanRule[]): Promise<TestPlanRulesFile> {
  ensureConfigDir()
  const cleaned = validateTestPlanRules(rules)
  const payload: TestPlanRulesFile = { version: 2, rules: cleaned }
  await safeFileStore.writeText(
    testPlanRulesConfigPath(),
    `${JSON.stringify(payload, null, 2)}\n`,
  )
  return payload
}

async function writeProjectNodesFile(payload: ProjectNodesFile): Promise<ProjectNodesFile> {
  ensureConfigDir()
  await safeFileStore.writeText(
    projectNodesConfigPath(),
    `${JSON.stringify(payload, null, 2)}\n`,
  )
  return payload
}

export async function syncProjectNodesFromXlsx(filePath?: string): Promise<ProjectNodesFile> {
  ensureConfigDir()
  const parsed = await parseProjectInfoXlsx(filePath)
  const payload: ProjectNodesFile = {
    updatedAt: new Date().toISOString(),
    sourcePath: parsed.sourcePath,
    projects: parsed.projects,
  }
  return writeProjectNodesFile(payload)
}

export async function syncProjectNodesFromRemoteUrl(url: string): Promise<ProjectNodesFile> {
  const res = await fetch(url, { signal: AbortSignal.timeout(30_000) })
  if (!res.ok) {
    throw new Error(`远端项目节点同步失败: HTTP ${res.status}`)
  }
  const data = await res.json() as Partial<ProjectNodesFile> & { projects?: ProjectNodeEntry[] }
  const projects = Array.isArray(data.projects) ? data.projects : []
  if (!projects.length) {
    throw new Error('远端返回的项目节点为空')
  }
  const payload: ProjectNodesFile = {
    updatedAt: new Date().toISOString(),
    sourcePath: url,
    projects,
  }
  return writeProjectNodesFile(payload)
}

export async function syncProjectNodesFromRemote(filePath?: string): Promise<ProjectNodesFile> {
  const remoteUrl = process.env.TAHP_PROJECT_NODES_SYNC_URL?.trim()
  if (remoteUrl) {
    try {
      return await syncProjectNodesFromRemoteUrl(remoteUrl)
    } catch (err) {
      logger.warn({ err: (err as Error).message, remoteUrl }, '[test-planning] remote sync failed, fallback to xlsx')
    }
  }
  return syncProjectNodesFromXlsx(filePath)
}

export async function getProjectNodesView(today?: Date) {
  const file = await getProjectNodesFile()
  const projects = file?.projects ?? []
  return {
    updatedAt: file?.updatedAt ?? null,
    sourcePath: file?.sourcePath ?? null,
    projects,
    nextNodes: getNextNodes(projects, today),
  }
}

export async function getTestScheduleView(today?: Date) {
  const file = await getProjectNodesFile()
  const rulesFile = await getTestPlanRules()
  const executions = await loadPlanExecutions()
  const projects = file?.projects ?? []
  return {
    updatedAt: file?.updatedAt ?? null,
    rules: rulesFile.rules,
    items: buildTestSchedule(projects, rulesFile.rules, today, executions),
  }
}
