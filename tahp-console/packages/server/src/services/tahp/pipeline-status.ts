/**
 * AI 自检自动化流水线状态（项目节点 → 烧录 → 测试 → Review）
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
  const pendingSchedules = scheduleView.items.filter(i => i.runtimeStatus === 'pending').length
  const noDeviceSchedules = scheduleView.items.filter(i => i.runtimeStatus === 'no_device').length
  const runningSchedules = scheduleView.items.filter(i => i.runtimeStatus === 'running').length
  const completedSchedules = scheduleView.items.filter(i => i.runtimeStatus === 'completed').length
  const hasNodes = nodesView.projects.length > 0

  const syncStage: PipelineStage = {
    key: 'sync',
    label: '项目节点同步',
    status: hasNodes ? 'done' : 'idle',
    hint: hasNodes ? `${nodesView.projects.length} 个项目` : undefined,
  }

  let flashStatus: PipelineStageStatus = 'idle'
  let flashHint: string | undefined
  const flashHintParts: string[] = []
  if (pendingSchedules > 0) flashHintParts.push(`待执行 ${pendingSchedules}`)
  if (noDeviceSchedules > 0) flashHintParts.push(`无设备 ${noDeviceSchedules}`)
  if (noDeviceSchedules > 0) {
    flashStatus = 'attention'
  } else if (pendingSchedules > 0) {
    flashStatus = 'queued'
  }
  flashHint = flashHintParts.length ? flashHintParts.join(' · ') : undefined

  const flashStage: PipelineStage = {
    key: 'flash',
    label: '版本拉取/烧录',
    status: flashStatus,
    hint: flashHint,
  }

  let testStatus: PipelineStageStatus = 'idle'
  if (runningSchedules > 0) {
    testStatus = 'running'
  } else if (completedSchedules > 0) {
    testStatus = 'done'
  }
  const testHintParts: string[] = []
  if (runningSchedules > 0) testHintParts.push(`测试中 ${runningSchedules}`)
  if (completedSchedules > 0) testHintParts.push(`已完成 ${completedSchedules}`)

  const testStage: PipelineStage = {
    key: 'test',
    label: '自动测试',
    status: testStatus,
    hint: testHintParts.length ? testHintParts.join(' · ') : undefined,
  }

  const reviewStage: PipelineStage = {
    key: 'review',
    label: '人工 Review',
    status: pendingReports > 0 ? 'attention' : recentlyCompleted > 0 && runningTests === 0 ? 'done' : 'idle',
    hint: pendingReports > 0 ? `${pendingReports} 份待 Review` : undefined,
  }

  return {
    stages: [syncStage, flashStage, testStage, reviewStage],
    updatedAt: new Date().toISOString(),
    runningTests,
    pendingManual,
    pendingReports,
  }
}
