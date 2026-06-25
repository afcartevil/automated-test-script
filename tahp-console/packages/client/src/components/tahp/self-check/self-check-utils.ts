import type { DeviceInfo } from '@/api/tahp/device-self-check'

export const SELF_CHECK_SUBTITLE =
  '项目节点驱动，自动烧录、自动测试、AI Review，第二天人工复核报告'

export const AUTO_RETEST_TOOLTIP = '测试结束后自动复测无人工参与的失败用例'

export const MODULE_ORDER: Record<string, number> = {
  driver: 0,
  driver_component: 0,
  driver_hardware: 1,
  tdd: 99,
}

export function getTestTypeLabel(testType?: string): string {
  if (testType === 'str4') return '转测摸底测试'
  if (testType === 'week') return '周版本测试'
  if (testType === 'custom') return '自定义测试'
  return '未分配'
}

export function getStatusColor(status: string): string {
  if (status.includes('通过') || status === '空闲') return 'var(--success)'
  if (status.includes('失败') || status.includes('错误')) return 'var(--error)'
  if (status.includes('测试中') || status.includes('等待') || status.includes('待命')) return 'var(--accent)'
  if (status.includes('不满足前置条件')) return 'var(--warning, #f59e0b)'
  return 'var(--muted)'
}

export function getStatusIcon(status: string): string {
  if (status.includes('通过')) return '✓'
  if (status.includes('失败')) return '✗'
  if (status.includes('测试中')) return '●'
  if (status.includes('待命')) return '🛡'
  if (status.includes('等待')) return '⏳'
  if (status.includes('错误')) return '⚠'
  if (status.includes('不满足前置条件')) return '!'
  return '○'
}

export function getModuleLabel(module: string): string {
  const labels: Record<string, string> = {
    tdd: '通信框架',
    driver: '驱动',
    driver_component: '驱动-器件',
    driver_hardware: '驱动-硬测',
  }
  return labels[module] || module
}

export function getDisplayStatus(device: DeviceInfo): string {
  if (device.status === '等待测试开始' && device.currentModule) {
    return `等待${getModuleLabel(device.currentModule)}开始测试`
  }
  if (device.status === '不满足前置条件' && device.currentModule) {
    return `${getModuleLabel(device.currentModule)}不满足前置条件`
  }
  return device.status
}

export function getRoleBadge(role: string): string {
  const colors: Record<string, string> = {
    未分配: 'background: var(--bg)',
    测试机: 'background: var(--accent-soft); color: var(--accent)',
    辅测机: 'background: rgba(16, 185, 129, 0.1); color: #10b981',
  }
  return colors[role] || ''
}

export function getCaseResultColor(status: string): string {
  const colors: Record<string, string> = {
    通过: 'var(--success)',
    失败: 'var(--error)',
    部分通过: '#f59e0b',
    待确认: '#f59e0b',
    NA: 'var(--muted)',
    跳过: 'var(--muted)',
    未开始: 'var(--muted)',
    进行中: 'var(--accent)',
  }
  return colors[status] || 'var(--muted)'
}

export function parseManualSteps(steps: string): string[] {
  if (!steps.trim()) return []
  return steps.split('\n').map(line => line.trim()).filter(Boolean)
}

export type PipelineStageStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'done'
  | 'attention'

export interface PipelineStage {
  key: string
  label: string
  status: PipelineStageStatus
  hint?: string
}

export function pipelineStatusLabel(status: PipelineStageStatus): string {
  const map: Record<PipelineStageStatus, string> = {
    idle: '未开始',
    queued: '排队中',
    running: '执行中',
    done: '已完成',
    attention: '需人工处理',
  }
  return map[status]
}
