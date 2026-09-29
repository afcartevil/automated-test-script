import type { BitflipResultDetail, CaseCatalogGroup, DeviceInfo, SelfCheckReportSummary, SelfCheckTestConfig } from '@/api/tahp/device-self-check'

export const SELF_CHECK_SUBTITLE =
  '验测任务 → 测试执行 → 评审补全 → 人工复核报告'

export const AUTO_RETEST_TOOLTIP = '测试结束后自动复测无人工参与的失败用例'

/** 连续OTA升级 SOP（飞书文档，作界面提示与刷机确认入口） */
export const OTA_UPGRADE_SOP = {
  url: 'https://transsioner.feishu.cn/docx/KPDTdp4UhovtfUxHJHocIb0Knjc',
  label: '连续OTA升级 SOP',
  inlineLabel: '前置操作',
  hint: '操作请按 SOP 执行',
} as const

/** 连续OTA升级进入时强制勾选连续版本升级；离开时恢复进入前的勾选，避免泄漏到其他测试项 */
export function resolveReleaseUpgradeEnabledOnTypeChange(input: {
  testType: string
  previousTestType?: string
  currentEnabled: boolean
  enabledBeforeOta: boolean
}): { enabled: boolean; enabledBeforeOta: boolean } {
  if (input.testType === 'ota_upgrade') {
    return {
      enabled: true,
      enabledBeforeOta: input.previousTestType === 'ota_upgrade'
        ? input.enabledBeforeOta
        : input.currentEnabled,
    }
  }
  if (input.previousTestType === 'ota_upgrade') {
    return {
      enabled: input.enabledBeforeOta,
      enabledBeforeOta: input.enabledBeforeOta,
    }
  }
  return {
    enabled: input.currentEnabled,
    enabledBeforeOta: input.enabledBeforeOta,
  }
}

function tcardZipFileName(path: string): string {
  return path.replace(/^.*[\\/]/, '')
}

export function isOfficialTcardZipName(name: string): boolean {
  const fileName = tcardZipFileName(name)
  return /^Tcard_/i.test(fileName) && /\.zip$/i.test(fileName) && !/_user(?:_|\.|$)/i.test(fileName)
}

/** A15 及以后只选 Tcard_*_a{上一档}.zip。A14→A15 选 Tcard_项目-15.x...zip，不认 _a14。 */
export function pickPreferredTcardZip(paths: string[], previousAndroid?: number): string {
  const tcard = paths.filter((path) => isOfficialTcardZipName(path))
  const rank = (path: string): number => {
    const fileName = tcardZipFileName(path)
    if (previousAndroid === 14) {
      if (/_a\d+\.zip$/i.test(fileName)) return -1
      const target = fileName.match(/^Tcard_[^-]+-(\d+)\./i)
      return target && Number(target[1]) === 15 ? 4 : -1
    }
    if (previousAndroid != null) {
      return new RegExp(`_a${previousAndroid}\\.zip$`, 'i').test(fileName) ? 4 : -1
    }
    if (!/_a\d+\.zip$/i.test(fileName)) return 2
    return 1
  }
  return tcard.filter((path) => rank(path) >= 0).slice().sort((a, b) => {
    const delta = rank(b) - rank(a)
    return delta || b.localeCompare(a)
  })[0] || ''
}

export function missingTcardZipHint(previousAndroid: number): string {
  if (previousAndroid === 14) return '未找到T卡包（需 Tcard_*-15.*.zip）'
  return `未找到T卡包（需 Tcard_*_a${previousAndroid}.zip）`
}

/** 连续OTA升级开始刷机前的人工确认 */
export const OTA_UPGRADE_FLASH_CONFIRM = {
  title: '开始刷机',
  lines: [
    '1.请确保手机已完成OEM解锁',
    '2.手机电量大于30%',
    '3.AP NV参数的usbdebug标志位已写为1',
  ],
  positiveText: '确认',
  negativeText: '取消',
} as const

/** 标准测试大类展示顺序（与用例列表 / 后端 catalog 一致） */
export const STANDARD_TEST_TYPE_ORDER = ['str4', 'week', 'monkey', 'monkey_check', 'smoke', 'ota_upgrade', 'gms', 'power', 'power_feature', 'thermal', 'kernel_feature', 'pipeline_adapt', 'bitflip', 'ai_generated'] as const

export type StandardTestTypeKey = (typeof STANDARD_TEST_TYPE_ORDER)[number]

export const MODULE_ORDER: Record<string, number> = {
  driver: 0,
  driver_component: 0,
  driver_hardware: 1,
  monkey: 2,
  tne: 3,
  usd: 4,
  ota: 5,
  cts: 10,
  gts: 11,
  vts: 12,
  cts_tele: 13,
  current_analysis: 14,
  wbs: 15,
  scheme: 16,
  stability: 17,
  generated: 20,
  bst: 21,
  tp: 30,
  vibrator: 31,
  audio: 32,
  lcm: 33,
  fingerprint: 34,
  charger: 35,
  tdd: 99,
}

export function getTestTypeLabel(testType?: string): string {
  if (testType === 'str4') return '转测摸底测试'
  if (testType === 'week') return '周版本测试'
  if (testType === 'monkey') return 'monkey测试'
  if (testType === 'monkey_check') return 'monkey结果检查'
  if (testType === 'smoke') return '冒烟测试'
  if (testType === 'ota_upgrade') return '连续OTA升级'
  if (testType === 'gms') return 'GMS测试'
  if (testType === 'power') return '功耗自动化测试'
  if (testType === 'power_feature') return '功耗特性自检'
  if (testType === 'thermal' || testType === 'therm') return '温升方案自检'
  if (testType === 'kernel_feature') return '内核特性自检'
  if (testType === 'pipeline_adapt') return '流水线适配自动化测试'
  if (testType === 'bitflip') return 'bitflip压测'
  if (testType === 'ai_generated') return 'AI用例'
  if (testType === 'custom') return '自定义测试'
  return '未分配'
}

export function getStatusColor(status: string): string {
  if (status.includes('通过') || status === '空闲') return 'var(--success)'
  if (status.includes('失败') || status.includes('错误')) return 'var(--error)'
  if (status.includes('测试中') || status.includes('等待') || status.includes('待命') || status.includes('刷机') || status.includes('T卡升级')) return 'var(--accent)'
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
    tne: 'TNE异常检查',
    usd: 'USD冒烟测试',
    ota: '连续OTA升级',
    cts: 'CTS',
    gts: 'GTS',
    vts: 'VTS',
    current_analysis: '场景功耗测量',
    wbs: '功耗特性检测',
    scheme: '温升方案检测',
    tp: 'TP',
    vibrator: '马达',
    audio: '音频',
    lcm: 'LCM',
    fingerprint: '指纹/人脸',
    charger: 'Charger',
    generated: 'AI生成用例',
    bst: 'bitflip压测(BAT)',
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

/** 当前执行到的子步骤下标：执行中始终跟最新一步（列表末尾） */
export function getCurrentCaseStepIndex(
  steps: { status: string }[] | undefined | null,
  caseStatus?: string,
): number {
  const list = Array.isArray(steps) ? steps : []
  if (!list.length) return -1
  // 用例执行中：高亮/跟随最后一步（避免前面残留的「正在执行…」抢高亮）
  if (caseStatus === '进行中') return list.length - 1
  for (let i = list.length - 1; i >= 0; i--) {
    if (list[i].status === '进行中') return i
  }
  return -1
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

export const AUTOMATION_MODE_FILTER_OPTIONS = [
  { key: 'all', label: '全部' },
  { key: 'full', label: '全自动' },
  { key: 'semi', label: '半自动' },
  { key: 'manual', label: '人工' },
] as const

export type AutomationModeFilterKey = typeof AUTOMATION_MODE_FILTER_OPTIONS[number]['key']

export function getAutomationModeLabel(mode?: string): string {
  if (mode === 'full') return '全自动'
  if (mode === 'semi') return '半自动'
  if (mode === 'manual') return '人工'
  return '全自动'
}

/** 列表用单字图标：自 / 半 / 人 */
export function getAutomationModeIcon(mode?: string): string {
  if (mode === 'semi') return '半'
  if (mode === 'manual') return '人'
  return '自'
}

export function normalizeAutomationMode(mode?: string): 'full' | 'semi' | 'manual' {
  if (mode === 'semi' || mode === 'manual') return mode
  return 'full'
}

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
    || status === 'T卡升级中'
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
  if (group.testType === 'power') {
    return '电流场景测试包括不限于（通用全域测试、基础场景、待机、PFMMod；DOU 暂不实现）'
  }
  if (group.testType === 'kernel_feature') {
    return '稳定性、内存、调度（小系统/安全后续接入）'
  }
  if (!group.modules.length) return '暂无用例'
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
  if (group.testType === 'ota_upgrade') {
    return '脚本全自动（连续版本升级 + 开机校验）'
  }
  if (group.testType === 'gms') {
    return '脚本全自动（Tradefed CTS/GTS/VTS）'
  }
  if (group.testType === 'power') {
    return '脚本自动化'
  }
  if (group.testType === 'power_feature') {
    return '脚本全自动（WBS 特性检测）'
  }
  if (group.testType === 'kernel_feature') {
    return '脚本全自动（稳定性 Checklist；源码项需配置 code_dir）'
  }
  if (group.testType === 'thermal') {
    return '脚本全自动（tpytest_dzppt_therm）'
  }
  if (group.testType === 'pipeline_adapt') {
    return '脚本全自动（节点检查 + 工模 + 应用 UI）'
  }
  if (group.testType === 'bitflip') {
    return '脚本全自动（MTK BAT bitflip 压测）'
  }
  if (group.testType === 'ai_generated') {
    const totalCases = group.modules.reduce((sum, m) => sum + m.cases.length, 0)
    return totalCases > 0 ? 'NL UI 自动化 + 半自动（Gerrit）' : '支持 NL UI 自动化新增'
  }
  const hasReuse = group.modules.some(m => m.cases.some(c => c.canReuse))
  const base = '脚本自动化 + 半自动化'
  return hasReuse ? `${base}（支持结果复用）` : base
}

/** 用例大类卡片：聚合各模块最高前置要求 */
export function formatCatalogPrereq(group: CaseCatalogGroup): string {
  if (group.testType === 'power') {
    return 'ADB 连接测试机+TPower测量仪器'
  }
  if (group.testType === 'bitflip') {
    return 'ADB 连接测试机（userdebug 已 root）；主机需 java+adb；测试中途设备会多次重启'
  }
  if (group.testType === 'ota_upgrade') {
    return 'ADB 连接测试机；开始前须获取外发版本；按 SOP 操作'
  }
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

export function reportShortType(testType: string): string {
  if (testType === 'monkey') return 'monkey'
  if (testType === 'monkey_check') return 'monkey检查'
  if (testType === 'smoke') return '冒烟'
  if (testType === 'ota_upgrade') return '连续OTA'
  if (testType === 'power_feature') return '功耗特性'
  if (testType === 'kernel_feature') return '内核特性'
  if (testType === 'thermal' || testType === 'therm') return '温升方案'
  if (testType === 'pipeline_adapt') return '流水线适配'
  if (testType === 'bitflip') return 'bitflip压测'
  if (testType === 'str4') return 'STR4'
  if (testType === 'week') return '周版本'
  if (testType === 'custom') return '自定义'
  return testType
}

export function reportTitle(report: SelfCheckReportSummary): string {
  const typeLabel = report.testType === 'custom'
    ? '自定义测试'
    : getTestTypeLabel(report.testType)
  if (report.aiPlanned) {
    return `${report.deviceName} · ${reportShortType(report.testType)} · AI规划`
  }
  return `${report.deviceName} · ${typeLabel}`
}

/** 本地会话目录名（与 reports/self-check/<设备>/<目录> 一致） */
export function selfCheckSessionDirName(report: {
  reportPath?: string
  startTime?: string
}): string {
  const parts = String(report.reportPath || '').replace(/\\/g, '/').split('/').filter(Boolean)
  if (parts.length) return parts[parts.length - 1]
  if (report.startTime) return report.startTime.replace(/[:.]/g, '-')
  return ''
}

export function formatSelfCheckIsoTime(iso?: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

/**
 * 列表卡片时间：展示开始时间（对应本地会话目录），便于对照文件夹名。
 * 结束时间放在详情里。
 */
export function reportListTimeLabel(report: SelfCheckReportSummary): string {
  return `开始 ${formatSelfCheckIsoTime(report.startTime)}`
}

export type ReportStatusKind = 'passed' | 'pending' | 'reviewed' | 'retest'

export function displayReportStatus(report: SelfCheckReportSummary): string {
  if (report.reviewStatus === 'reviewed') return '已审阅'
  if (report.reviewStatus === 'retest') return '待补测'
  if (report.failedCases > 0) return '待审阅'
  return report.status.includes('通过') ? '通过' : '待审阅'
}

/** 通过率分母：总项数排除人工待补录 */
export function selfCheckScoredTotal(report: {
  totalCases: number
  pendingManualCases?: number
}): number {
  return Math.max(0, report.totalCases - (report.pendingManualCases ?? 0))
}

/** 通过率分子/分母文案（NA 计入通过，人工项不计入分母） */
export function selfCheckPassRateLabel(report: {
  totalCases: number
  passedCases: number
  pendingManualCases?: number
}): string {
  return `${report.passedCases}/${selfCheckScoredTotal(report)}`
}

export function selfCheckPassRatePercent(report: {
  totalCases: number
  passedCases: number
  pendingManualCases?: number
}): number {
  const scored = selfCheckScoredTotal(report)
  if (scored <= 0) return 0
  return Math.round((report.passedCases / scored) * 100)
}

export function reportStatusKind(report: SelfCheckReportSummary): ReportStatusKind {
  if (report.reviewStatus === 'reviewed') return 'reviewed'
  if (report.reviewStatus === 'retest') return 'retest'
  if (report.failedCases > 0 || !report.status.includes('通过')) return 'pending'
  return 'passed'
}

/** 报告审阅：前置配置展示行 */
export function formatTestConfigEntries(cfg?: SelfCheckTestConfig): { label: string; value: string }[] {
  if (!cfg) return []
  const rows: { label: string; value: string }[] = []
  if (cfg.monkeyDuration) rows.push({ label: 'monkey测试时长', value: cfg.monkeyDuration })
  if (cfg.smokeUsdSkipSpdInfo !== undefined) {
    rows.push({ label: '跳过 SPD 拉取', value: cfg.smokeUsdSkipSpdInfo ? '是' : '否' })
  }
  if (cfg.gmsTradefedPath) {
    for (const suite of ['cts', 'gts', 'vts'] as const) {
      const path = cfg.gmsTradefedPath[suite]
      if (path) rows.push({ label: `GMS ${suite.toUpperCase()} Tradefed`, value: path })
    }
  }
  if (cfg.gmsTimeoutHours) {
    rows.push({ label: 'GMS 用例超时', value: `${cfg.gmsTimeoutHours} 小时` })
  }
  if (cfg.kernelFeatureCodeDir) {
    rows.push({ label: '内核源码路径', value: cfg.kernelFeatureCodeDir })
  }
  if (cfg.bitflipRepeatCount) {
    rows.push({ label: 'bitflip 每项重复次数 (-r)', value: String(cfg.bitflipRepeatCount) })
  }
  if (cfg.bitflipTimeoutHours) {
    rows.push({ label: 'bitflip 超时上限 (20h×-r)', value: `${cfg.bitflipTimeoutHours} 小时` })
  }
  if (cfg.autoRetestEnabled !== undefined) {
    rows.push({
      label: '自动复测',
      value: cfg.autoRetestEnabled ? `开启（${cfg.autoRetestCount ?? 0} 次）` : '关闭',
    })
  }
  if (cfg.prioritizeTddManual) rows.push({ label: '通信人工用例优先', value: '是' })
  if (cfg.flashBeforeTest?.enabled) {
    rows.push({ label: '测试前刷机', value: '是' })
    if (cfg.flashBeforeTest.pkgPath) rows.push({ label: '刷机包路径', value: cfg.flashBeforeTest.pkgPath })
    if (cfg.flashBeforeTest.stageVersion) rows.push({ label: '市场版本', value: cfg.flashBeforeTest.stageVersion })
    if (cfg.flashBeforeTest.enableRootPkg && cfg.flashBeforeTest.rootPkgPath) {
      rows.push({ label: 'Root 刷机包', value: cfg.flashBeforeTest.rootPkgPath })
    }
  }
  if (cfg.tcardBeforeTest?.enabled) {
    rows.push({ label: 'T卡升级', value: '是' })
    const zipPaths = cfg.tcardBeforeTest.zipPaths?.length
      ? cfg.tcardBeforeTest.zipPaths
      : (cfg.tcardBeforeTest.zipPath ? [cfg.tcardBeforeTest.zipPath] : [])
    zipPaths.forEach((path, index) => {
      rows.push({
        label: zipPaths.length > 1 ? `T卡升级 ZIP ${index + 1}` : 'T卡升级 ZIP',
        value: path,
      })
    })
  }
  if (cfg.selectedCases?.length) {
    rows.push({ label: '自定义勾选用例数', value: String(cfg.selectedCases.length) })
  }
  return rows
}

/** 执行阶段跳过的人工用例，待在测试报告中补录 */
export function isPendingManualReportFillIn(item: {
  status?: string
  message?: string
  automationMode?: string
}): boolean {
  return item.automationMode === 'manual'
    && item.status === '待确认'
    && Boolean(item.message?.includes('报告中补录'))
}

/** 从用例 detail 中提取 bitflip 压测结果表（无 bitflip 数据时返回 null） */
export function bitflipResultOf(detail?: Record<string, any> | null): BitflipResultDetail | null {
  const bitflip = detail?.bitflip
  if (!bitflip || !Array.isArray(bitflip.columns) || !bitflip.columns.length) return null
  if (!Array.isArray(bitflip.rows)) return null
  return bitflip as BitflipResultDetail
}
