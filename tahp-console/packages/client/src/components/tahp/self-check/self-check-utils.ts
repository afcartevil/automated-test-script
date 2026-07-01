import type { CaseCatalogGroup, DeviceInfo } from '@/api/tahp/device-self-check'

export const SELF_CHECK_SUBTITLE =
  '项目节点驱动，自动烧录、自动测试、AI Review，第二天人工复核报告'

export const AUTO_RETEST_TOOLTIP = '测试结束后自动复测无人工参与的失败用例'

/** 标准测试大类展示顺序（与用例列表 / 后端 catalog 一致） */
export const STANDARD_TEST_TYPE_ORDER = ['str4', 'week', 'monkey', 'smoke', 'gms', 'power'] as const

export type StandardTestTypeKey = (typeof STANDARD_TEST_TYPE_ORDER)[number]

export const MODULE_ORDER: Record<string, number> = {
  driver: 0,
  driver_component: 0,
  driver_hardware: 1,
  monkey: 2,
  usd: 3,
  cts: 10,
  gts: 11,
  vts: 12,
  current_analysis: 13,
  tdd: 99,
}

export function getTestTypeLabel(testType?: string): string {
  if (testType === 'str4') return '转测摸底测试'
  if (testType === 'week') return '周版本测试'
  if (testType === 'monkey') return 'monkey测试'
  if (testType === 'smoke') return '冒烟测试'
  if (testType === 'gms') return 'GMS测试'
  if (testType === 'power') return '功耗自动化测试'
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
    monkey: 'monkey测试',
    usd: 'USD冒烟测试',
    cts: 'CTS',
    gts: 'GTS',
    vts: 'VTS',
    current_analysis: '电流分析',
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

export function getDisplayRole(device: DeviceInfo): string {
  return device.status === '空闲' ? '未分配' : device.role
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

export const DEVICE_LIST_FILTER_OPTIONS = [
  { key: 'all', label: '全部' },
  { key: 'testing', label: '测试中' },
  { key: 'waiting', label: '等待测试' },
  { key: 'idle', label: '空闲' },
  { key: 'error', label: '错误' },
  { key: 'aux', label: '辅测机' },
] as const

export type DeviceListFilterKey = typeof DEVICE_LIST_FILTER_OPTIONS[number]['key']

/** 参与测试中的辅测机（待命/占用中等）；已释放为空闲的不算 */
export function isActiveAuxiliaryDevice(device: DeviceInfo): boolean {
  return device.role === '辅测机' && device.status !== '空闲'
}

export function getDeviceListFilterKey(device: DeviceInfo): DeviceListFilterKey | 'other' {
  if (isActiveAuxiliaryDevice(device)) return 'aux'

  const status = device.status as string
  if (
    status === '测试中'
    || status === '刷机中'
    || status === '占用中'
    || status === '初始化中'
  ) {
    return 'testing'
  }
  if (
    status === '等待测试开始'
    || status === '待命'
    || status === '不满足前置条件'
  ) {
    return 'waiting'
  }
  if (status === '空闲') return 'idle'
  if (status === '错误') return 'error'
  return 'other'
}

export function deviceMatchesListFilter(
  device: DeviceInfo,
  filter: DeviceListFilterKey,
): boolean {
  if (filter === 'all') return true
  return getDeviceListFilterKey(device) === filter
}

/** 用例大类卡片：模块覆盖范围 */
export function formatCatalogModuleScope(group: CaseCatalogGroup): string {
  return group.modules.map(m => m.moduleLabel).join('、')
}

/** 用例大类卡片：自动化说明 */
export function formatCatalogAutomation(group: CaseCatalogGroup): string {
  if (group.testType === 'monkey') {
    return '脚本全自动（Monkey）'
  }
  if (group.testType === 'smoke') {
    return '脚本全自动（SDD USD pytest）'
  }
  if (group.testType === 'gms') {
    return '脚本全自动（Tradefed CTS/GTS/VTS）'
  }
  const hasReuse = group.modules.some(m => m.cases.some(c => c.canReuse))
  const base = '脚本自动化 + 半自动化'
  return hasReuse ? `${base}（支持结果复用）` : base
}

/** 用例大类卡片：聚合各模块最高前置要求 */
export function formatCatalogPrereq(group: CaseCatalogGroup): string {
  const parts: string[] = ['ADB 连接测试机']
  const maxDutSim = Math.max(0, ...group.modules.map(m => m.conditions.dutSimCount))
  const maxAux = Math.max(0, ...group.modules.map(m => m.conditions.auxRequired))
  const maxAuxSim = Math.max(0, ...group.modules.map(m => m.conditions.auxSimCount))
  if (maxDutSim > 0) {
    parts.push(`测试机插入${maxDutSim}张SIM卡`)
  }
  if (maxAux > 0) {
    const auxPart = `${maxAux}台辅测机`
    parts.push(maxAuxSim > 0 ? `${auxPart}（各${maxAuxSim}张SIM）` : auxPart)
  }
  return parts.join('；')
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
