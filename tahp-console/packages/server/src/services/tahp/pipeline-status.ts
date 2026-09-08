/**
 * AI 自检自动化流水线状态（测试 → Review）
 * 2026-09 起「自动规划」由中心 BFF 定时任务接管，本机不再有排期数据，
 * 状态条精简为两个阶段：自动测试（设备驱动）+ 人工复核（报告驱动）。
 */
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
  const [pendingReports, pendingManual] = await Promise.all([
    countPendingSelfCheckReports(),
    Promise.resolve(countPendingManualDecisions()),
  ])

  const deviceList = snapshotDevices()
  const runningTests = deviceList.filter(d => TESTING_STATUSES.has(d.status)).length
  const recentlyCompleted = deviceList.filter(d => COMPLETED_STATUSES.has(d.status)).length

  const testStage: PipelineStage = {
    key: 'test',
    label: '自动测试',
    status: runningTests > 0 ? 'running' : recentlyCompleted > 0 ? 'done' : 'idle',
    hint: runningTests > 0
      ? `测试中 ${runningTests}`
      : recentlyCompleted > 0
        ? `已完成 ${recentlyCompleted}`
        : undefined,
  }

  const reviewStage: PipelineStage = {
    key: 'review',
    label: '人工复核测试报告',
    status: pendingReports > 0 ? 'attention' : recentlyCompleted > 0 && runningTests === 0 ? 'done' : 'idle',
    hint: pendingReports > 0 ? `${pendingReports} 份待复核` : undefined,
  }

  return {
    stages: [testStage, reviewStage],
    updatedAt: new Date().toISOString(),
    runningTests,
    pendingManual,
    pendingReports,
  }
}
