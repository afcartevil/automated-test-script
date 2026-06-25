/**
 * AI 自检自动化流水线状态（项目节点 → 烧录 → 测试 → AI → Review）
 */
import { getProjectNodesView, getTestScheduleView } from './test-planning'
import { snapshotDevices, countPendingManualDecisions } from './device-self-check'
import { countPendingSelfCheckReports } from './self-check-reports'

export type PipelineStageStatus = 'idle' | 'queued' | 'running' | 'done' | 'attention'

export interface PipelineStage {
  key: string
  label: string
  status: PipelineStageStatus
  hint?: string
}

export interface SelfCheckPipelineView {
  stages: PipelineStage[]
  updatedAt: string
  runningTests: number
  pendingManual: number
  pendingReports: number
}

const TESTING_STATUSES = new Set(['初始化中', '等待测试开始', '测试中', '占用中', '待命'])
const COMPLETED_STATUSES = new Set(['完成(通过)', '完成(失败)'])

export async function getSelfCheckPipelineStatus(): Promise<SelfCheckPipelineView> {
  const [nodesView, scheduleView, pendingReports, pendingManual] = await Promise.all([
    getProjectNodesView(),
    getTestScheduleView(),
    countPendingSelfCheckReports(),
    Promise.resolve(countPendingManualDecisions()),
  ])

  const deviceList = snapshotDevices()
  const runningTests = deviceList.filter(d => TESTING_STATUSES.has(d.status)).length
  const recentlyCompleted = deviceList.filter(d => COMPLETED_STATUSES.has(d.status)).length
  const initDevices = deviceList.filter(d => d.status === '初始化中').length
  const activeSchedule = scheduleView.items.filter(i => i.status === 'active').length
  const hasNodes = nodesView.projects.length > 0

  const syncStage: PipelineStage = {
    key: 'sync',
    label: '项目节点同步',
    status: hasNodes ? 'done' : 'idle',
    hint: hasNodes ? `${nodesView.projects.length} 个项目` : undefined,
  }

  let flashStatus: PipelineStageStatus = 'idle'
  let flashHint: string | undefined
  if (initDevices > 0) {
    flashStatus = 'running'
    flashHint = `${initDevices} 台设备初始化中`
  } else if (activeSchedule > 0 && runningTests === 0) {
    flashStatus = 'queued'
    flashHint = `${activeSchedule} 项计划待执行`
  } else if (recentlyCompleted > 0 && runningTests === 0) {
    flashStatus = 'done'
  }

  const flashStage: PipelineStage = {
    key: 'flash',
    label: '版本拉取/烧录',
    status: flashStatus,
    hint: flashHint,
  }

  let testStatus: PipelineStageStatus = 'idle'
  if (runningTests > 0) {
    testStatus = 'running'
  } else if (activeSchedule > 0) {
    testStatus = 'queued'
  } else if (recentlyCompleted > 0) {
    testStatus = 'done'
  }

  const testStage: PipelineStage = {
    key: 'test',
    label: '自动测试',
    status: testStatus,
    hint: runningTests > 0 ? `${runningTests} 台运行中` : undefined,
  }

  const aiStage: PipelineStage = {
    key: 'ai',
    label: 'AI 分析',
    status: pendingManual > 0 ? 'attention' : runningTests > 0 ? 'running' : 'idle',
    hint: pendingManual > 0 ? `${pendingManual} 项待人工确认` : undefined,
  }

  const reviewStage: PipelineStage = {
    key: 'review',
    label: '人工 Review',
    status: pendingReports > 0 ? 'attention' : recentlyCompleted > 0 && runningTests === 0 ? 'done' : 'idle',
    hint: pendingReports > 0 ? `${pendingReports} 份待 Review` : undefined,
  }

  return {
    stages: [syncStage, flashStage, testStage, aiStage, reviewStage],
    updatedAt: new Date().toISOString(),
    runningTests,
    pendingManual,
    pendingReports,
  }
}
