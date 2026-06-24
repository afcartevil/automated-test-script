/**
 * AI 测试自规划 API
 */
import { tahpGet, tahpPost } from './client'

export type ProjectNodeKey = 'STR4' | 'STR4A' | 'STR5' | 'STR6'

export interface ProjectNodeEntry {
  name: string
  status: string
  nodes: Record<ProjectNodeKey, string | null>
}

export interface NextNodeItem {
  project: string
  node: ProjectNodeKey
  nodeDate: string
  display: string
}

export interface ProjectNodesView {
  updatedAt: string | null
  sourcePath: string | null
  projects: ProjectNodeEntry[]
  nextNodes: NextNodeItem[]
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

export interface ScheduleItem {
  project: string
  node: ProjectNodeKey
  nodeDate: string
  triggerDate: string
  testName: string
  status: 'active' | 'upcoming'
  display: string
}

export interface TestScheduleView {
  updatedAt: string | null
  rules: TestPlanRule[]
  items: ScheduleItem[]
}

export function fetchProjectNodes(): Promise<ProjectNodesView> {
  return tahpGet<ProjectNodesView>('/api/tahp/test-planning/nodes')
}

export function syncProjectNodes(): Promise<ProjectNodesView> {
  return tahpPost<ProjectNodesView>('/api/tahp/test-planning/nodes/sync', {})
}

export function fetchTestPlanRules(): Promise<TestPlanRulesFile> {
  return tahpGet<TestPlanRulesFile>('/api/tahp/test-planning/rules')
}

export function saveTestPlanRules(rules: TestPlanRule[]): Promise<TestPlanRulesFile> {
  return tahpPost<TestPlanRulesFile>('/api/tahp/test-planning/rules/save', { rules })
}

export function fetchTestSchedule(): Promise<TestScheduleView> {
  return tahpGet<TestScheduleView>('/api/tahp/test-planning/schedule')
}
