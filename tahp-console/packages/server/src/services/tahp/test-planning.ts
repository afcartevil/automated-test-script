/**
 * AI 测试自规划 — 项目节点同步、规则配置与待执行计划计算
 */
import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { safeFileStore } from '../safe-file-store'
import { tahpPaths } from './paths'
import {
  NODE_KEYS,
  type ProjectNodeEntry,
  type ProjectNodeKey,
  parseProjectInfoXlsx,
} from './project-info-xlsx'

export const MAX_OFFSET_DAYS = 14
export const UPCOMING_HORIZON_DAYS = 14

export interface ProjectNodesFile {
  updatedAt: string
  sourcePath: string
  projects: ProjectNodeEntry[]
}

export interface TestPlanRule {
  node: ProjectNodeKey
  offsetDays: number
  testName: string
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
  project: string
  node: ProjectNodeKey
  nodeDate: string
  triggerDate: string
  testName: string
  status: 'active' | 'upcoming'
  display: string
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

export function buildTestSchedule(
  projects: ProjectNodeEntry[],
  rules: TestPlanRule[],
  today?: Date,
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
      items.push({
        project: project.name,
        node: rule.node,
        nodeDate: nodeDateStr,
        triggerDate: triggerDisplay,
        testName: rule.testName,
        status: isActive ? 'active' : 'upcoming',
        display: `${project.name} ${rule.node} ${triggerDisplay} ${rule.testName}`,
      })
    }
  }

  items.sort((a, b) => {
    const diff = fromDisplayDate(a.triggerDate).getTime() - fromDisplayDate(b.triggerDate).getTime()
    if (diff !== 0) return diff
    const projectDiff = a.project.localeCompare(b.project, 'zh-CN')
    if (projectDiff !== 0) return projectDiff
    return a.testName.localeCompare(b.testName, 'zh-CN')
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

export async function getTestPlanRules(): Promise<TestPlanRulesFile> {
  const path = testPlanRulesConfigPath()
  if (!existsSync(path)) {
    return { version: 1, rules: [] }
  }
  try {
    const raw = await safeFileStore.readText(path)
    const data = JSON.parse(raw) as Partial<TestPlanRulesFile>
    return {
      version: data.version ?? 1,
      rules: Array.isArray(data.rules) ? data.rules : [],
    }
  } catch {
    return { version: 1, rules: [] }
  }
}

export function validateTestPlanRules(rules: TestPlanRule[]): TestPlanRule[] {
  const validNodes = new Set<string>(NODE_KEYS)
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
    const testName = String(rule.testName || '').trim()
    if (!testName) {
      throw new Error('测试项名称不能为空')
    }
    cleaned.push({ node, offsetDays, testName })
  }

  return cleaned
}

export async function saveTestPlanRules(rules: TestPlanRule[]): Promise<TestPlanRulesFile> {
  ensureConfigDir()
  const cleaned = validateTestPlanRules(rules)
  const payload: TestPlanRulesFile = { version: 1, rules: cleaned }
  await safeFileStore.writeText(
    testPlanRulesConfigPath(),
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
  await safeFileStore.writeText(
    projectNodesConfigPath(),
    `${JSON.stringify(payload, null, 2)}\n`,
  )
  return payload
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
  const projects = file?.projects ?? []
  return {
    updatedAt: file?.updatedAt ?? null,
    rules: rulesFile.rules,
    items: buildTestSchedule(projects, rulesFile.rules, today),
  }
}
