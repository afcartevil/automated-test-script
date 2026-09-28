import { h, ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDialog, useMessage } from 'naive-ui'
import { useDeviceSelfCheckLaunchStore } from '@/stores/tahp/device-self-check-launch'
import {
  listDevices,
  refreshDevices,
  getDeviceDetail,
  setDeviceRole,
  startTest,
  pickFlashPath,
  pickTcardZipPath,
  pickGmsTradefedPath,
  resolveLatestDailyFlashPackage,
  resolveReleaseUpgradePlan,
  clearFlashPackageCache,
  startCustomTest,
  deleteAiGeneratedCases,
  createAiNlUiCase,
  updateAiNlUiCase,
  getCaseCatalogs,
  getCaseCatalogDetail,
  continueTest,
  resumeTest,
  endTest,
  skipCurrentCase,
  updateCaseResult,
  getModuleConditions,
  submitManualDecision,
  getPendingManualDecision,
  retestCase,
  getSettings,
  updateSettings,
  fetchSelfCheckPipeline,
  fetchTPowerStatus,
  listSelfCheckReports,
  type DeviceRole,
  type DeviceInfo,
  type DeviceDetail,
  type ModuleCondition,
  type CaseResult,
  type CaseCatalog,
  type CaseCatalogGroup,
  type CaseCatalogDetailItem,
  type SelfCheckPipelineView,
  type SelfCheckReportSummary,
  type TPowerStatus,
  type ReleaseUpgradePlan,
  type AndroidUpgradeStep,
} from '@/api/tahp/device-self-check'
import {
  createFlashProgressState,
  parseFlashLogLine,
  flashPhaseLabel,
  mergeFlashLogLine,
  type FlashProgressState,
} from '@/utils/flash-progress'
import {
  AUTO_RETEST_TOOLTIP,
  MODULE_ORDER,
  OTA_UPGRADE_FLASH_CONFIRM,
  OTA_UPGRADE_SOP,
  missingTcardZipHint,
  pickPreferredTcardZip,
  resolveReleaseUpgradeEnabledOnTypeChange,
  getTestTypeLabel,
  getStatusColor,
  getStatusIcon,
  getDisplayStatus,
  getRoleBadge,
  getCaseResultColor,
  parseManualSteps,
  type PipelineStage,
} from '@/components/tahp/self-check/self-check-utils'

export type SelfCheckTab = 'overview' | 'devices' | 'review' | 'gerrit'

export const SELF_CHECK_TABS = [
  { key: 'overview', label: '总览' },
  { key: 'devices', label: '测试执行' },
  { key: 'gerrit', label: '评审补全' },
  { key: 'review', label: '测试报告' },
] as const

export function useDeviceSelfCheck() {
  const message = useMessage()
  const dialog = useDialog()

const devices = ref<DeviceInfo[]>([])
const selectedDeviceId = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedDevice = ref<DeviceDetail | null>(null)
const moduleConditions = ref<Record<string, ModuleCondition>>({})

// 测试类型选择
const selectedTestType = ref<'str4' | 'week' | 'monkey' | 'monkey_check' | 'smoke' | 'ota_upgrade' | 'gms' | 'power' | 'power_feature' | 'thermal' | 'kernel_feature' | 'pipeline_adapt' | 'ai_generated' | 'bitflip'>('week')
/** 空闲设备开始测试前勾选的模块（多模块大类可筛；默认全选） */
const selectedStartModules = ref<Set<string>>(new Set())
/** 空闲设备开始测试前的角色意向（仅 UI，选中设备时默认测试机；点击开始测试时才落盘） */
const startTestIntentRole = ref<DeviceRole>('测试机')

function setStartTestIntentRole(role: DeviceRole) {
  startTestIntentRole.value = role
}

function listModulesForTestType(testType: string): string[] {
  const mods = new Set<string>()
  for (const config of Object.values(moduleConditions.value)) {
    if (config.customOnly) continue
    if (config.testType === testType) mods.add(config.module)
  }
  return Array.from(mods).sort((a, b) => (MODULE_ORDER[a] ?? 50) - (MODULE_ORDER[b] ?? 50))
}

function syncSelectedStartModules(testType: string = selectedTestType.value) {
  selectedStartModules.value = new Set(listModulesForTestType(testType))
}

function toggleStartModule(module: string) {
  if (selectedStartModules.value.has(module)) {
    selectedStartModules.value.delete(module)
  } else {
    selectedStartModules.value.add(module)
  }
  selectedStartModules.value = new Set(selectedStartModules.value)
}

function isStartModuleSelected(module: string): boolean {
  return selectedStartModules.value.has(module)
}

const canSelectStartModules = computed(() => listModulesForTestType(selectedTestType.value).length > 1)

// 刷机相关选项（device_update，工具位于 self-check/flash_tool/）
const enableFlash = ref(false)
const flashPath = ref('')
const dailyFlashResolving = ref(false)
const flashPackagesClearing = ref(false)
const enableRootPkg = ref(false)
const flashStageVersion = ref('Open')
const flashLogs = ref<string[]>([])
const flashLogRef = ref<HTMLElement | null>(null)
const flashActive = ref(false)
const flashDone = ref<'success' | 'error' | null>(null)
/** 当前刷机 UI 绑定的设备；切换设备或结束测试后清空 */
const flashDeviceId = ref<string | null>(null)
const flashProgressState = ref<FlashProgressState>(createFlashProgressState())
const flashPathPicking = ref(false)
const FLASH_MARKET_OPTIONS = [
  { label: 'Base', value: '' },
  { label: 'Open', value: 'Open' },
  { label: 'Open-Payjoy', value: 'Open-Payjoy' },
  { label: 'RU', value: 'RU' },
  { label: 'Turkey', value: 'Turkey' },
  { label: 'India', value: 'India' },
]

interface DeviceFlashFormOptions {
  enableFlash: boolean
  flashPath: string
  enableRootPkg: boolean
  flashStageVersion: string
  enableTcardUpdate: boolean
  tcardUpdatePath: string
  enableReleaseUpgrade: boolean
  releaseFlashPath: string
  releaseTcardPaths: string[]
  releaseUpgradePlan: ReleaseUpgradePlan | null
}

/** 每台设备独立保存刷机表单，切换设备时恢复 */
const flashFormByDeviceId = ref<Record<string, DeviceFlashFormOptions>>({})

const enableTcardUpdate = ref(false)
const tcardUpdatePath = ref('')
const tcardPathPicking = ref(false)
const releasePathPicking = ref(false)
const enableReleaseUpgrade = ref(false)
let releaseUpgradeEnabledBeforeOta = false
const releaseFlashPath = ref('')
const releaseTcardPaths = ref<string[]>([])
const releaseUpgradeResolving = ref(false)
const releaseUpgradePlan = ref<ReleaseUpgradePlan | null>(null)

watch(enableReleaseUpgrade, (enabled) => {
  if (!enabled) return
  enableFlash.value = false
  enableTcardUpdate.value = false
})
watch(enableFlash, (enabled) => {
  if (enabled) enableReleaseUpgrade.value = false
})
watch(enableTcardUpdate, (enabled) => {
  if (enabled) enableReleaseUpgrade.value = false
})

function cloneReleaseUpgradePlan(plan: ReleaseUpgradePlan | null): ReleaseUpgradePlan | null {
  return plan ? JSON.parse(JSON.stringify(plan)) as ReleaseUpgradePlan : null
}

function snapshotFlashFormOptions(): DeviceFlashFormOptions {
  return {
    enableFlash: enableFlash.value,
    flashPath: flashPath.value,
    enableRootPkg: enableRootPkg.value,
    flashStageVersion: flashStageVersion.value,
    enableTcardUpdate: enableTcardUpdate.value,
    tcardUpdatePath: tcardUpdatePath.value,
    enableReleaseUpgrade: enableReleaseUpgrade.value,
    releaseFlashPath: releaseFlashPath.value,
    releaseTcardPaths: [...releaseTcardPaths.value],
    releaseUpgradePlan: cloneReleaseUpgradePlan(releaseUpgradePlan.value),
  }
}

function saveFlashFormForDevice(deviceId: string) {
  flashFormByDeviceId.value = {
    ...flashFormByDeviceId.value,
    [deviceId]: snapshotFlashFormOptions(),
  }
}

function applyFlashFormOptions(opts?: DeviceFlashFormOptions) {
  enableFlash.value = opts?.enableFlash ?? false
  flashPath.value = opts?.flashPath ?? ''
  enableRootPkg.value = opts?.enableRootPkg ?? false
  flashStageVersion.value = opts?.flashStageVersion ?? 'Open'
  enableTcardUpdate.value = opts?.enableTcardUpdate ?? false
  tcardUpdatePath.value = opts?.tcardUpdatePath ?? ''
  enableReleaseUpgrade.value = opts?.enableReleaseUpgrade ?? false
  releaseFlashPath.value = opts?.releaseFlashPath ?? ''
  releaseTcardPaths.value = [...(opts?.releaseTcardPaths ?? [])]
  releaseUpgradePlan.value = cloneReleaseUpgradePlan(opts?.releaseUpgradePlan ?? null)
  dailyFlashResolving.value = false
  tcardPathPicking.value = false
  releasePathPicking.value = false
  releaseUpgradeResolving.value = false
}

function clearFlashFormForDevice(deviceId: string) {
  const next = { ...flashFormByDeviceId.value }
  delete next[deviceId]
  flashFormByDeviceId.value = next
}

function resetFlashProgress() {
  flashActive.value = false
  flashDone.value = null
  flashProgressState.value = createFlashProgressState()
}

function clearFlashPanel() {
  flashDeviceId.value = null
  flashLogs.value = []
  resetFlashProgress()
}

async function dismissFlashFailure() {
  const deviceId = flashDeviceId.value || selectedDeviceId.value
  clearFlashPanel()
  if (deviceId) {
    try {
      await refreshDeviceState(deviceId)
    } catch {}
  }
}

function scrollFlashLogToBottom() {
  nextTick(() => {
    const el = flashLogRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function appendFlashLog(line: string) {
  flashLogs.value = mergeFlashLogLine(flashLogs.value, line)
  flashActive.value = true
  parseFlashLogLine(flashProgressState.value, line)
  scrollFlashLogToBottom()
}

watch(flashLogs, scrollFlashLogToBottom)

// 视图模式
const viewMode = ref<'list' | 'customTest'>('list')
const catalogPanelExpanded = ref(false)
const deviceDetailExpanded = ref(false)
/** 重复选中同一设备/用例时递增，供视图层滚动到详情 */
const deviceDetailScrollNonce = ref(0)
const catalogPanelScrollNonce = ref(0)

// 自定义测试 / 概览用例目录
const caseCatalogGroups = ref<CaseCatalogGroup[]>([])
const selectedCatalogTestType = ref<string | null>(null)
const catalogDetailItems = ref<CaseCatalogDetailItem[]>([])
const selectedCatalogCaseKey = ref<string | null>(null)
const catalogDetailLoading = ref(false)
const selectedAiGeneratedCasesForDelete = ref<Set<string>>(new Set())
const aiGeneratedCasesDeleting = ref(false)
const aiNlCaseForm = ref({
  caseName: '',
  nlDescription: '',
  expectedResult: '',
})
const aiNlCaseEditingKey = ref<string | null>(null)
const aiNlCaseCreating = ref(false)
type AiNlCaseProgressLevel = 'info' | 'thinking' | 'success' | 'error'
interface AiNlCaseProgressItem {
  id: string
  level: AiNlCaseProgressLevel
  message: string
  detail?: string
  at: string
}
const aiNlCaseProgress = ref<AiNlCaseProgressItem[]>([])
const aiNlCaseProgressStatus = ref<'idle' | 'running' | 'success' | 'error'>('idle')

function pushAiNlProgress(
  level: AiNlCaseProgressLevel,
  message: string,
  detail?: string,
) {
  aiNlCaseProgress.value = [
    ...aiNlCaseProgress.value,
    {
      id: `nl-${Date.now()}-${aiNlCaseProgress.value.length}`,
      level,
      message,
      detail,
      at: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    },
  ]
}

function clearAiNlProgress() {
  aiNlCaseProgress.value = []
  aiNlCaseProgressStatus.value = 'idle'
}

function formatNlUiStep(step: { op?: string; [key: string]: unknown }, index: number): string {
  const op = String(step.op || '')
  const text = step.text != null ? String(step.text).trim() : ''
  const desc = step.desc != null ? String(step.desc).trim() : ''
  const cmd = step.cmd != null ? String(step.cmd).trim() : ''
  const direction = step.direction != null ? String(step.direction).trim() : ''
  const condition = step.condition != null ? String(step.condition).trim() : ''
  const keys = step.keys != null ? String(step.keys).trim() : ''
  const rid = step.rid != null
    ? String(step.rid).trim()
    : step['resource-id'] != null
      ? String(step['resource-id']).trim()
      : step.resourceId != null
        ? String(step.resourceId).trim()
        : ''
  const name = step.name != null ? String(step.name).trim() : ''
  const present = step.present

  let summary = op
  if (op === 'tap_text' && text) summary = `tap_text ${text}`
  else if (op === 'tap_desc' && desc) summary = `tap_desc ${desc}`
  else if (op === 'tap_rid' && rid) summary = `tap_rid ${rid}`
  else if (op === 'assert_text' && text) {
    summary = present === false ? `assert_text 不应出现 ${text}` : `assert_text ${text}`
  }
  else if (op === 'assert_desc' && desc) {
    summary = present === false ? `assert_desc 不应出现 ${desc}` : `assert_desc ${desc}`
  }
  else if (op === 'shell' && cmd) summary = `shell ${cmd.length > 56 ? `${cmd.slice(0, 53)}...` : cmd}`
  else if (op === 'wait_until') {
    const detail = text || desc
    summary = detail ? `wait_until ${condition} ${detail}` : `wait_until ${condition}`
  }
  else if (op === 'dial_keys' && keys) summary = `dial_keys ${keys}`
  else if (op === 'swipe' && direction) summary = `swipe ${direction}`
  else if (op === 'wait') {
    const seconds = step.seconds != null
      ? Number(step.seconds)
      : Number(step.ms ?? 1000) / 1000
    summary = `wait ${seconds}s`
  }
  else if (op === 'screenshot' && name) summary = `screenshot ${name}`

  const flags: string[] = []
  if (step.optional) flags.push('optional')
  if (step.scroll === false) flags.push('scroll=false')
  const suffix = flags.length ? ` (${flags.join(', ')})` : ''
  return `${index}. ${summary}${suffix}`
}
const catalogTypeSettings = ref({
  autoRetestEnabled: true,
  autoRetestCount: 1,
  monkeyDuration: '7d',
  smokeUsdSkipSpdInfo: false,
  kernelFeatureCodeDir: '',
  gmsTimeoutHours: 8,
  gmsTradefedPath: {
    cts: '',
    gts: '',
    vts: '',
  },
  bitflipRepeatCount: 5,
})
const catalogSettingsSaving = ref(false)
const gmsHostSupported = ref(true)
const gmsPathPickingSuite = ref<'cts' | 'gts' | 'vts' | null>(null)
const showGmsTradefedDialog = ref(false)
const gmsTradefedDraft = ref({
  cts: '',
  gts: '',
  vts: '',
})
const expandedCatalogTypes = ref<Set<string>>(new Set())
const expandedCatalogModules = ref<Set<string>>(new Set())
const expandedCatalogDetailModules = ref<Set<string>>(new Set())
const selectedCases = ref<Set<string>>(new Set())
const customTestDutDeviceId = ref<string | null>(null)
const customTestAuxDeviceIds = ref<Set<string>>(new Set())

watch(customTestDutDeviceId, (deviceId, prevId) => {
  if (deviceId !== prevId && deviceId !== null) {
    customTestAuxDeviceIds.value = new Set()
  }
})
const customTestStarting = ref(false)
const prioritizeTddManual = ref(false)
const gerritPreselectCount = ref(0)
const launchStore = useDeviceSelfCheckLaunchStore()

  const activeTab = ref<SelfCheckTab>('overview')
  // 支持 ?tab=devices 直达（验测任务通知「打开验测」跳转「测试执行」）
  const route = useRoute()
  const initialTab = String(route.query.tab || '')
  if (SELF_CHECK_TABS.some(t => t.key === initialTab)) activeTab.value = initialTab as SelfCheckTab
  const pipelineView = ref<SelfCheckPipelineView | null>(null)
  const tpowerStatus = ref<TPowerStatus | null>(null)
  const overviewReports = ref<SelfCheckReportSummary[]>([])
  const reportsLoading = ref(false)
  /** 报告列表刷新序号：测试报告落盘后递增，供「测试报告」Tab 同步重载 */
  const reportsEpoch = ref(0)

  async function loadPipelineStatus() {
    try {
      pipelineView.value = await fetchSelfCheckPipeline()
    } catch {
      pipelineView.value = null
    }
  }

  async function loadTPowerStatus() {
    try {
      tpowerStatus.value = await fetchTPowerStatus()
    } catch {
      tpowerStatus.value = null
    }
  }

  async function loadOverviewReports() {
    reportsLoading.value = true
    try {
      // 仅按 72h 过滤，不再要求 pendingOnly：已审阅报告也算「新报告」，
      // 避免出现「近 72 小时暂无新报告」而报告页却有 72h 内报告的矛盾。
      // 「待审阅」计数仍由 pipelineView.pendingReports 提供（全量 pending）。
      overviewReports.value = await listSelfCheckReports({ sinceHours: 72 })
    } catch {
      overviewReports.value = []
    } finally {
      reportsLoading.value = false
    }
  }

  async function refreshReportsAfterTest() {
    await loadOverviewReports()
    await loadPipelineStatus()
    reportsEpoch.value += 1
  }

  function handleNewTask() {
    activeTab.value = 'devices'
    openCustomTest()
  }

  const stats = computed(() => ({
    runningTests: pipelineView.value?.runningTests ?? devices.value.filter(d =>
      d.status.includes('测试') || d.status.includes('等待') || d.status === '初始化中',
    ).length,
    pendingManual: pipelineView.value?.pendingManual ?? devices.value.filter(d =>
      d.status.includes('待确认') || d.status.includes('不满足'),
    ).length,
    pendingReports: pipelineView.value?.pendingReports ?? 0,
  }))

  const pipelineStages = computed((): PipelineStage[] => {
    if (pipelineView.value?.stages?.length) {
      return pipelineView.value.stages
    }
    // 服务端 pipeline 接口不可用时的本地兜底（与服务端 2 阶段口径一致）
    const runningTests = devices.value.filter(d =>
      d.status.includes('测试') || d.status.includes('等待') || d.status === '初始化中',
    ).length
    const recentlyCompleted = devices.value.filter(d =>
      d.status === '完成(通过)' || d.status === '完成(失败)',
    ).length
    return [
      {
        key: 'test',
        label: '自动测试',
        status: runningTests > 0 ? 'running' : recentlyCompleted > 0 ? 'done' : 'idle',
        hint: runningTests > 0
          ? `测试中 ${runningTests}`
          : recentlyCompleted > 0
            ? `已完成 ${recentlyCompleted}`
            : undefined,
      },
      {
        key: 'review',
        label: '人工复核测试报告',
        status: stats.value.pendingReports > 0 ? 'attention' : recentlyCompleted > 0 && runningTests === 0 ? 'done' : 'idle',
        hint: stats.value.pendingReports > 0 ? `${stats.value.pendingReports} 份待复核` : undefined,
      },
    ]
  })


const availableCustomAux = computed(() => {
  return devices.value.filter(d =>
    d.deviceId !== customTestDutDeviceId.value &&
    d.status === '空闲' &&
    (d.role === '辅测机' || d.role === '未分配')
  )
})

const availableCustomDut = computed(() => {
  return devices.value.filter(d => d.status === '空闲')
})

// 用例列表相关
const selectedCase = ref<string | null>(null)
const expandedModules = ref<Set<string>>(new Set())
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)
const followCurrent = ref(true)
const eventSource = ref<EventSource | null>(null)

interface ParsedSelectedCase {
  testType: string
  module: string
  caseIndex: number
}

function parseSelectedCaseKey(
  selected: string | null | undefined,
  fallbackTestType?: string,
): ParsedSelectedCase | null {
  if (!selected) return null
  const parts = selected.split('/').filter(Boolean)
  if (parts.length >= 3) {
    const caseIndex = parseInt(parts[parts.length - 1], 10)
    if (!Number.isFinite(caseIndex)) return null
    return {
      testType: parts.slice(0, -2).join('/'),
      module: parts[parts.length - 2],
      caseIndex,
    }
  }
  if (parts.length === 2) {
    const caseIndex = parseInt(parts[1], 10)
    if (!Number.isFinite(caseIndex)) return null
    return {
      testType: fallbackTestType || 'str4',
      module: parts[0],
      caseIndex,
    }
  }
  return null
}

function formatSelectedCaseKey(testType: string, module: string, caseIndex: number): string {
  return `${testType}/${module}/${caseIndex}`
}

function formatCaseResultKey(parsed: ParsedSelectedCase): string {
  return formatSelectedCaseKey(parsed.testType, parsed.module, parsed.caseIndex)
}

async function loadDevices() {
  loading.value = true
  error.value = null
  try {
    console.log('[DeviceSelfCheck] Loading devices...')
    const result = await listDevices()
    console.log('[DeviceSelfCheck] Devices loaded:', result)
    devices.value = result
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error loading devices:', e)
    error.value = e?.message || '加载设备列表失败'
  } finally {
    loading.value = false
  }
}

async function doRefreshDevices() {
  loading.value = true
  error.value = null
  try {
    console.log('[DeviceSelfCheck] Refreshing devices...')
    const result = await refreshDevices()
    console.log('[DeviceSelfCheck] Devices refreshed:', result)
    devices.value = result
    await Promise.all([loadPipelineStatus(), loadTPowerStatus()])
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error refreshing devices:', e)
    error.value = e?.message || '刷新设备列表失败'
  } finally {
    loading.value = false
  }
}

function applyFollowCurrentCase(session?: { testType: string; selectedCases?: string[]; caseResults: Record<string, CaseResult>; modules: string[]; currentModuleIndex: number; moduleProgress: Record<string, { currentCaseIndex?: number }> }) {
  if (!session) return
  if (session.testType === 'custom' && session.selectedCases) {
    const modulesToExpand = new Set(expandedModules.value)
    for (const caseKey of session.selectedCases) {
      const parts = caseKey.split('/')
      parts.pop()
      const module = parts.pop() || ''
      if (module) modulesToExpand.add(module)
      const result = session.caseResults[caseKey]
      if (result?.status === '进行中') {
        selectedCase.value = caseKey
        expandedModules.value = modulesToExpand
        return
      }
    }
    expandedModules.value = modulesToExpand
    return
  }
  const mod = session.modules[session.currentModuleIndex]
  if (!mod) return
  const prog = session.moduleProgress[`${session.testType}/${mod}`]
  if (prog?.currentCaseIndex) {
    selectedCase.value = formatSelectedCaseKey(session.testType, mod, prog.currentCaseIndex)
  } else {
    selectedCase.value = formatSelectedCaseKey(session.testType, mod, 1)
    expandedModules.value = new Set([...expandedModules.value, mod])
  }
}

async function selectDevice(deviceId: string) {
  const reselect = selectedDeviceId.value === deviceId && deviceDetailExpanded.value
  const previousDeviceId = selectedDeviceId.value
  const switchingDevice = previousDeviceId !== null && previousDeviceId !== deviceId
  if (switchingDevice && previousDeviceId) {
    saveFlashFormForDevice(previousDeviceId)
  }
  try {
    selectedDeviceId.value = deviceId
    deviceDetailExpanded.value = true
    applyFlashFormOptions(flashFormByDeviceId.value[deviceId])
    const detail = await getDeviceDetail(deviceId)
    selectedDevice.value = detail
    // 切回仍在刷机的设备时恢复刷机面板绑定（切换其他设备期间不清理刷机状态）
    if (detail.device.status === '刷机中' || detail.device.status === 'T卡升级中') {
      if (!flashDeviceId.value || flashDeviceId.value === deviceId) {
        flashDeviceId.value = deviceId
        flashActive.value = true
      }
    }
    selectedCase.value = null
    followCurrent.value = true
    if (detail.device.status === '空闲') {
      startTestIntentRole.value = '测试机'
    }
    applyFollowCurrentCase(detail.session)
    // 如果正在测试中，开始轮询
    if (detail.session?.isRunning) {
      startPolling()
    }
    if (reselect) {
      deviceDetailScrollNonce.value += 1
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error getting device detail:', e)
    error.value = e?.message || '获取设备详情失败'
  }
}

function collapseCaseCatalog() {
  catalogPanelExpanded.value = false
  selectedCatalogTestType.value = null
  catalogDetailItems.value = []
  selectedCatalogCaseKey.value = null
  expandedCatalogDetailModules.value = new Set()
}

function collapseDeviceDetail() {
  deviceDetailExpanded.value = false
}

function catalogDetailModuleKey(module: string): string {
  return `${selectedCatalogTestType.value}/${module}`
}

function isCatalogDetailModuleExpanded(module: string): boolean {
  return expandedCatalogDetailModules.value.has(catalogDetailModuleKey(module))
}

function toggleCatalogDetailModule(module: string) {
  const key = catalogDetailModuleKey(module)
  if (expandedCatalogDetailModules.value.has(key)) {
    expandedCatalogDetailModules.value.delete(key)
  } else {
    expandedCatalogDetailModules.value.add(key)
  }
  expandedCatalogDetailModules.value = new Set(expandedCatalogDetailModules.value)
}

async function loadGmsTradefedSettings() {
  try {
    const settingsData = await getSettings()
    gmsHostSupported.value = settingsData.gmsHostSupported !== false
    catalogTypeSettings.value.gmsTimeoutHours = settingsData.gmsTimeoutHours || 8
    catalogTypeSettings.value.gmsTradefedPath = {
      cts: settingsData.gmsTradefedPath?.cts || '',
      gts: settingsData.gmsTradefedPath?.gts || '',
      vts: settingsData.gmsTradefedPath?.vts || '',
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Failed to load GMS tradefed settings:', e)
  }
}

async function loadKernelFeatureSettings() {
  try {
    const settingsData = await getSettings()
    catalogTypeSettings.value.kernelFeatureCodeDir = settingsData.kernelFeatureCodeDir || ''
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Failed to load kernel feature settings:', e)
  }
}

async function saveKernelFeatureCodeDir(showToast = false) {
  catalogSettingsSaving.value = true
  try {
    const current = await getSettings()
    const autoRetestEnabled = { ...(current.autoRetestEnabled || {}) }
    const autoRetestCount = { ...(current.autoRetestCount || {}) }
    delete autoRetestEnabled.kernel_feature
    delete autoRetestCount.kernel_feature
    await updateSettings({
      ...current,
      autoRetestEnabled,
      autoRetestCount,
      kernelFeatureCodeDir: catalogTypeSettings.value.kernelFeatureCodeDir?.trim() || '',
    })
    if (showToast) {
      message.success('内核源码路径已保存')
    }
  } catch (e: any) {
    const text = e?.message || '保存内核源码路径失败'
    error.value = text
    message.error(text)
    throw e
  } finally {
    catalogSettingsSaving.value = false
  }
}

async function saveBitflipRepeatCount(showToast = false) {
  catalogSettingsSaving.value = true
  try {
    const current = await getSettings()
    const autoRetestEnabled = { ...(current.autoRetestEnabled || {}) }
    const autoRetestCount = { ...(current.autoRetestCount || {}) }
    delete autoRetestEnabled.bitflip
    delete autoRetestCount.bitflip
    const repeatCount = Math.min(100, Math.max(1, Math.round(Number(catalogTypeSettings.value.bitflipRepeatCount) || 5)))
    catalogTypeSettings.value.bitflipRepeatCount = repeatCount
    await updateSettings({
      ...current,
      autoRetestEnabled,
      autoRetestCount,
      bitflipRepeatCount: repeatCount,
    })
    if (showToast) {
      message.success('bitflip 每项重复测试次数已保存')
    }
  } catch (e: any) {
    const text = e?.message || '保存 bitflip 配置失败'
    error.value = text
    message.error(text)
    throw e
  } finally {
    catalogSettingsSaving.value = false
  }
}

async function saveGmsTradefedSettings(showToast = false) {
  catalogSettingsSaving.value = true
  try {
    const current = await getSettings()
    const autoRetestEnabled = { ...(current.autoRetestEnabled || {}) }
    const autoRetestCount = { ...(current.autoRetestCount || {}) }
    delete autoRetestEnabled.gms
    delete autoRetestCount.gms
    const paths = catalogTypeSettings.value.gmsTradefedPath || { cts: '', gts: '', vts: '' }
    const timeoutHours = Math.min(72, Math.max(1, Math.round(Number(catalogTypeSettings.value.gmsTimeoutHours) || 8)))
    catalogTypeSettings.value.gmsTimeoutHours = timeoutHours
    await updateSettings({
      ...current,
      autoRetestEnabled,
      autoRetestCount,
      gmsTimeoutHours: timeoutHours,
      gmsTradefedPath: {
        cts: paths.cts?.trim() || '',
        gts: paths.gts?.trim() || '',
        vts: paths.vts?.trim() || '',
      },
    })
    if (showToast) {
      message.success('GMS Tradefed 路径已保存')
    }
  } catch (e: any) {
    const text = e?.message || '保存 GMS 配置失败'
    error.value = text
    message.error(text)
    throw e
  } finally {
    catalogSettingsSaving.value = false
  }
}

async function handleBrowseGmsTradefedPath(suite: 'cts' | 'gts' | 'vts') {
  if (gmsPathPickingSuite.value) return
  gmsPathPickingSuite.value = suite
  error.value = null
  try {
    const result = await pickGmsTradefedPath()
    if (result.path) {
      const target = showGmsTradefedDialog.value
        ? gmsTradefedDraft.value
        : catalogTypeSettings.value.gmsTradefedPath
      target[suite] = result.path
    } else if (result.error) {
      error.value = result.error
      message.error(result.error)
    }
  } catch (e: any) {
    const text = e?.message || '选择 Tradefed 路径失败'
    error.value = text
    message.error(text)
  } finally {
    gmsPathPickingSuite.value = null
  }
}

async function openGmsTradefedDialog() {
  await loadGmsTradefedSettings()
  const paths = catalogTypeSettings.value.gmsTradefedPath || { cts: '', gts: '', vts: '' }
  gmsTradefedDraft.value = {
    cts: paths.cts || '',
    gts: paths.gts || '',
    vts: paths.vts || '',
  }
  showGmsTradefedDialog.value = true
}

function closeGmsTradefedDialog() {
  showGmsTradefedDialog.value = false
}

async function saveGmsTradefedSettingsFromDialog() {
  catalogTypeSettings.value.gmsTradefedPath = {
    cts: gmsTradefedDraft.value.cts?.trim() || '',
    gts: gmsTradefedDraft.value.gts?.trim() || '',
    vts: gmsTradefedDraft.value.vts?.trim() || '',
  }
  await saveGmsTradefedSettings(true)
  showGmsTradefedDialog.value = false
}

async function openCaseCatalog(testType: string) {
  const reselect = catalogPanelExpanded.value && selectedCatalogTestType.value === testType
  selectedCatalogTestType.value = testType
  catalogPanelExpanded.value = true
  viewMode.value = 'list'
  selectedCatalogCaseKey.value = null
  catalogDetailLoading.value = true
  error.value = null
  try {
    const [detail, settingsData] = await Promise.all([
      getCaseCatalogDetail(testType),
      getSettings(),
    ])
    catalogDetailItems.value = detail
    if (testType !== 'ai_generated') {
      clearAiGeneratedDeleteSelection()
    } else {
      const validKeys = new Set(detail.map(item => item.key))
      selectedAiGeneratedCasesForDelete.value = new Set(
        Array.from(selectedAiGeneratedCasesForDelete.value).filter(key => validKeys.has(key)),
      )
    }
    expandedCatalogDetailModules.value = new Set(
      [...new Set(detail.map(item => `${testType}/${item.module}`))]
    )
    catalogTypeSettings.value = {
      autoRetestEnabled: testType === 'monkey' || testType === 'monkey_check' || testType === 'smoke' || testType === 'gms' || testType === 'power' || testType === 'power_feature' || testType === 'thermal' || testType === 'kernel_feature' || testType === 'ai_generated' || testType === 'ota_upgrade' || testType === 'bitflip'
        ? false
        : (settingsData.autoRetestEnabled?.[testType] ?? true),
      autoRetestCount: testType === 'monkey' || testType === 'monkey_check' || testType === 'smoke' || testType === 'gms' || testType === 'power' || testType === 'power_feature' || testType === 'thermal' || testType === 'kernel_feature' || testType === 'ai_generated' || testType === 'ota_upgrade' || testType === 'bitflip'
        ? 0
        : (settingsData.autoRetestCount?.[testType] ?? 1),
      monkeyDuration: settingsData.monkeyDuration || '7d',
      smokeUsdSkipSpdInfo: Boolean(settingsData.smokeUsdSkipSpdInfo),
      kernelFeatureCodeDir: settingsData.kernelFeatureCodeDir || '',
      gmsTimeoutHours: settingsData.gmsTimeoutHours || 8,
      gmsTradefedPath: {
        cts: settingsData.gmsTradefedPath?.cts || '',
        gts: settingsData.gmsTradefedPath?.gts || '',
        vts: settingsData.gmsTradefedPath?.vts || '',
      },
      bitflipRepeatCount: settingsData.bitflipRepeatCount || 5,
    }
    gmsHostSupported.value = settingsData.gmsHostSupported !== false
    if (detail.length > 0) {
      selectedCatalogCaseKey.value = detail[0].key
    }
  } catch (e: any) {
    error.value = e?.message || '加载用例详情失败'
  } finally {
    catalogDetailLoading.value = false
    if (reselect) {
      catalogPanelScrollNonce.value += 1
    }
  }
}

function selectCatalogCase(caseKey: string) {
  const reselect = selectedCatalogCaseKey.value === caseKey && catalogPanelExpanded.value
  selectedCatalogCaseKey.value = caseKey
  if (reselect) {
    catalogPanelScrollNonce.value += 1
  }
}

function isAiGeneratedCatalog(): boolean {
  return selectedCatalogTestType.value === 'ai_generated'
}

function toggleAiGeneratedCaseForDelete(caseKey: string) {
  if (!caseKey.startsWith('ai_generated/generated/')) return
  const next = new Set(selectedAiGeneratedCasesForDelete.value)
  if (next.has(caseKey)) next.delete(caseKey)
  else next.add(caseKey)
  selectedAiGeneratedCasesForDelete.value = next
}

function clearAiGeneratedDeleteSelection() {
  selectedAiGeneratedCasesForDelete.value = new Set()
}

async function handleDeleteAiGeneratedCases() {
  if (!isAiGeneratedCatalog() || selectedAiGeneratedCasesForDelete.value.size === 0) return
  const caseKeys = Array.from(selectedAiGeneratedCasesForDelete.value)
  aiGeneratedCasesDeleting.value = true
  try {
    await deleteAiGeneratedCases(caseKeys)
    selectedCases.value = new Set(Array.from(selectedCases.value).filter(key => !caseKeys.includes(key)))
    clearAiGeneratedDeleteSelection()
    await loadCaseCatalogs({ silent: true })
    if (selectedCatalogTestType.value) {
      await openCaseCatalog(selectedCatalogTestType.value)
    }
    message.success(`已删除 ${caseKeys.length} 个 AI 用例`)
  } catch (e: any) {
    message.error(e?.message || '删除 AI 用例失败')
  } finally {
    aiGeneratedCasesDeleting.value = false
  }
}

async function handleCreateAiNlUiCase() {
  if (!isAiGeneratedCatalog()) return
  const caseName = aiNlCaseForm.value.caseName.trim()
  const nlDescription = aiNlCaseForm.value.nlDescription.trim()
  const expectedResult = aiNlCaseForm.value.expectedResult.trim()
  const editingKey = aiNlCaseEditingKey.value
  const isUpdate = Boolean(editingKey)
  if (!caseName) {
    message.warning('请填写用例名称')
    return
  }
  if (!nlDescription) {
    message.warning('请填写自然语言执行描述')
    return
  }

  aiNlCaseCreating.value = true
  aiNlCaseProgressStatus.value = 'running'
  aiNlCaseProgress.value = []
  pushAiNlProgress(
    'info',
    isUpdate ? '开始修改并覆盖 NL UI 用例' : '开始新增 NL UI 用例',
    isUpdate ? `覆盖：${editingKey}` : `用例名：${caseName}`,
  )
  pushAiNlProgress('thinking', '校验输入完整性', `描述长度 ${nlDescription.length} 字`)
  pushAiNlProgress('thinking', '调用 LLM 判定可执行性并生成动作计划…', '可能需要数十秒，请稍候')

  const thinkingTimer = window.setInterval(() => {
    if (!aiNlCaseCreating.value) return
    pushAiNlProgress('thinking', 'AI 仍在分析自然语言描述…', '解析操作步骤与 UI 断言')
  }, 8000)

  try {
    const saved = isUpdate
      ? await updateAiNlUiCase({
        caseKey: editingKey!,
        caseName,
        nlDescription,
        expectedResult: expectedResult || undefined,
      })
      : await createAiNlUiCase({
        caseName,
        nlDescription,
        expectedResult: expectedResult || undefined,
      })
    clearInterval(thinkingTimer)
    pushAiNlProgress('success', 'LLM 判定：可执行', saved.plan?.reason || '已通过动作 schema 白名单校验')
    const steps = saved.plan?.steps || []
    if (steps.length) {
      pushAiNlProgress(
        'info',
        `已生成 ${steps.length} 步动作计划`,
        steps.map((step, index) => formatNlUiStep(step, index + 1)).join('\n'),
      )
    }
    pushAiNlProgress('thinking', isUpdate ? '覆盖落盘用例资产…' : '落盘用例资产…', 'case_config / plans / caseN.py')
    aiNlCaseForm.value = { caseName: '', nlDescription: '', expectedResult: '' }
    aiNlCaseEditingKey.value = null
    await loadCaseCatalogs({ silent: true })
    if (selectedCatalogTestType.value) {
      await openCaseCatalog(selectedCatalogTestType.value)
      selectedCatalogCaseKey.value = saved.caseKey
    }
    pushAiNlProgress(
      'success',
      isUpdate ? '覆盖成功' : '新增成功',
      `${saved.caseKey} · ${saved.caseName}`,
    )
    aiNlCaseProgressStatus.value = 'success'
    message.success(isUpdate ? `已覆盖 AI 用例：${saved.caseName}` : `已新增 AI 用例：${saved.caseName}`)
  } catch (e: any) {
    clearInterval(thinkingTimer)
    const errMsg = e?.message || (isUpdate ? '覆盖 AI 用例失败' : '新增 AI 用例失败')
    const notExecutable = /不可|无法|过短|缺少|无效|不存在/i.test(errMsg)
    pushAiNlProgress(
      'error',
      notExecutable ? '判定结果：不可用手机 UI 自动化执行' : (isUpdate ? '覆盖失败' : '新增失败'),
      errMsg,
    )
    aiNlCaseProgressStatus.value = 'error'
    if (notExecutable) {
      message.warning(`不可用手机 UI 自动化执行：${errMsg}`)
    } else {
      message.error(errMsg)
    }
  } finally {
    clearInterval(thinkingTimer)
    aiNlCaseCreating.value = false
  }
}

function startEditAiNlCase(item: CaseCatalogDetailItem) {
  if (!isAiGeneratedCatalog() || aiNlCaseCreating.value) return
  aiNlCaseEditingKey.value = item.key
  aiNlCaseForm.value = {
    caseName: item.caseName || '',
    nlDescription: item.manualSteps || '',
    expectedResult: item.expectedResult || '',
  }
  selectedCatalogCaseKey.value = item.key
  clearAiNlProgress()
  pushAiNlProgress('info', '已载入用例到编辑区', `${item.key} · 可调整描述后保存并覆盖`)
  aiNlCaseProgressStatus.value = 'idle'
}

function cancelEditAiNlCase() {
  if (aiNlCaseCreating.value) return
  aiNlCaseEditingKey.value = null
  aiNlCaseForm.value = { caseName: '', nlDescription: '', expectedResult: '' }
  clearAiNlProgress()
}

async function saveCatalogTypeSettings() {
  if (!selectedCatalogTestType.value) return
  catalogSettingsSaving.value = true
  try {
    const current = await getSettings()
    const testType = selectedCatalogTestType.value
    const monkeyDuration = catalogTypeSettings.value.monkeyDuration?.trim() || '7d'

    if (testType === 'monkey') {
      const autoRetestEnabled = { ...(current.autoRetestEnabled || {}) }
      const autoRetestCount = { ...(current.autoRetestCount || {}) }
      delete autoRetestEnabled.monkey
      delete autoRetestCount.monkey
      await updateSettings({
        ...current,
        autoRetestEnabled,
        autoRetestCount,
        monkeyDuration,
      })
      return
    }

    if (testType === 'smoke') {
      const autoRetestEnabled = { ...(current.autoRetestEnabled || {}) }
      const autoRetestCount = { ...(current.autoRetestCount || {}) }
      delete autoRetestEnabled.smoke
      delete autoRetestCount.smoke
      await updateSettings({
        ...current,
        autoRetestEnabled,
        autoRetestCount,
        smokeUsdSkipSpdInfo: catalogTypeSettings.value.smokeUsdSkipSpdInfo,
      })
      return
    }

    if (testType === 'gms') {
      await saveGmsTradefedSettings(false)
      return
    }

    if (testType === 'kernel_feature') {
      await saveKernelFeatureCodeDir(false)
      return
    }

    if (testType === 'bitflip') {
      await saveBitflipRepeatCount(false)
      return
    }

    if (testType === 'power') {
      const autoRetestEnabled = { ...(current.autoRetestEnabled || {}) }
      const autoRetestCount = { ...(current.autoRetestCount || {}) }
      delete autoRetestEnabled.power
      delete autoRetestCount.power
      await updateSettings({
        ...current,
        autoRetestEnabled,
        autoRetestCount,
        monkeyDuration,
      })
      return
    }

    if (testType === 'ai_generated' || testType === 'ota_upgrade') {
      return
    }

    const count = Math.max(0, Math.min(10, catalogTypeSettings.value.autoRetestCount || 0))
    catalogTypeSettings.value.autoRetestCount = count
    await updateSettings({
      ...current,
      autoRetestEnabled: {
        ...(current.autoRetestEnabled || {}),
        [testType]: catalogTypeSettings.value.autoRetestEnabled,
      },
      autoRetestCount: {
        ...(current.autoRetestCount || {}),
        [testType]: count,
      },
      monkeyDuration,
    })
  } catch (e) {
    console.error('[DeviceSelfCheck] Error saving catalog settings:', e)
  } finally {
    catalogSettingsSaving.value = false
  }
}

const catalogDetailByModule = computed(() => {
  const groups: { module: string; moduleLabel: string; cases: CaseCatalogDetailItem[] }[] = []
  const indexByModule = new Map<string, number>()
  for (const item of catalogDetailItems.value) {
    const idx = indexByModule.get(item.module)
    if (idx === undefined) {
      indexByModule.set(item.module, groups.length)
      groups.push({ module: item.module, moduleLabel: item.moduleLabel, cases: [item] })
    } else {
      groups[idx].cases.push(item)
    }
  }
  return groups
})

const selectedCatalogItem = computed(() =>
  catalogDetailItems.value.find(item => item.key === selectedCatalogCaseKey.value)
)

const selectedCatalogGroup = computed(() =>
  caseCatalogGroups.value.find(group => group.testType === selectedCatalogTestType.value)
)

const gmsTradefedConfiguredSummary = computed(() => {
  const paths = catalogTypeSettings.value.gmsTradefedPath || { cts: '', gts: '', vts: '' }
  const configured = (['cts', 'gts', 'vts'] as const).filter(suite => Boolean(paths[suite]?.trim()))
  if (configured.length === 0) return '未配置 Tradefed 路径'
  return `已配置 ${configured.length}/3：${configured.map(s => `${s}-tradefed`).join('、')}`
})

function backToOverview() {
  viewMode.value = 'list'
  selectedDeviceId.value = null
  selectedDevice.value = null
  selectedCase.value = null
  stopPollingTimer()
  loadDevices()
}

function goBack() {
  stopPollingTimer()
  selectedDeviceId.value = null
  selectedDevice.value = null
  loadDevices()
}

function patchDeviceInList(device: DeviceInfo) {
  const idx = devices.value.findIndex(d => d.deviceId === device.deviceId)
  if (idx >= 0) {
    devices.value[idx] = device
  } else {
    devices.value.push(device)
  }
}

async function refreshDeviceState(deviceId: string) {
  const detail = await getDeviceDetail(deviceId)
  patchDeviceInList(detail.device)
  if (selectedDeviceId.value === deviceId) {
    selectedDevice.value = detail
  }
}

/** 已提示过「本次选择的测试机测试完成」的键，避免重复弹窗 */
const completedNoticeKeys = new Set<string>()

/** 本次选择的测试机测试项全部完成 → 提示并可跳转「测试报告」查看结果 */
function notifySelectedDeviceComplete(deviceId: string, sessionStart?: string) {
  if (deviceId !== selectedDeviceId.value) return
  const key = `${deviceId}@${sessionStart || ''}`
  if (completedNoticeKeys.has(key)) return
  completedNoticeKeys.add(key)
  const name = selectedDevice.value?.device.deviceName || deviceId
  const inst = dialog.success({
    title: '测试完成',
    content: `本次选择的测试机「${name}」的测试项已全部完成，可前往「测试报告」查看结果。`,
    positiveText: '查看测试报告',
    negativeText: '稍后',
    onPositiveClick: () => {
      activeTab.value = 'review'
      void refreshReportsAfterTest()
    },
  })
  // 展示 5s 后自动关闭
  setTimeout(() => inst.destroy(), 5000)
}

function connectEventStream() {
  if (eventSource.value) return
  const baseUrl = window.location.origin
  eventSource.value = new EventSource(`${baseUrl}/api/tahp/device-self-check/events`)

  eventSource.value.addEventListener('device_updated', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (data.device) {
        patchDeviceInList(data.device)
        if (selectedDeviceId.value === data.device.deviceId && selectedDevice.value) {
          selectedDevice.value = { ...selectedDevice.value, device: data.device }
        }
      }
    } catch {}
  })

  eventSource.value.addEventListener('flash_log', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (data.deviceId === flashDeviceId.value && data.line) {
        appendFlashLog(data.line)
      }
    } catch {}
  })

  eventSource.value.addEventListener('flash_completed', async (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (!data.deviceId || data.deviceId !== flashDeviceId.value) return
      flashActive.value = false
      if (data.success) {
        if (data.continuePretest) {
          flashActive.value = true
          appendFlashLog('[T卡升级] 刷机完成，开始 T卡升级…')
        } else {
          clearFlashPanel()
          followCurrent.value = true
          const detail = await getDeviceDetail(data.deviceId)
          if (selectedDeviceId.value === data.deviceId) {
            selectedDevice.value = detail
          }
          applyFollowCurrentCase(detail.session)
        }
      } else {
        flashDone.value = 'error'
        parseFlashLogLine(
          flashProgressState.value,
          `[刷机] 刷机失败：${data.error || `返回码 ${data.returnCode ?? '?'}`}`,
        )
        if (data.error) appendFlashLog(`[刷机] ${data.error}`)
        await refreshDeviceState(data.deviceId)
      }
    } catch {}
  })

  eventSource.value.addEventListener('case_completed', async (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (!data.deviceId || data.deviceId !== selectedDeviceId.value) return
      const detail = await getDeviceDetail(selectedDeviceId.value!)
      selectedDevice.value = detail
      if (followCurrent.value && detail.session?.isRunning) {
        const session = detail.session
        if (session.testType === 'custom' && session.selectedCases) {
          for (const caseKey of session.selectedCases) {
            const result = session.caseResults[caseKey]
            if (result?.status === '进行中') {
              selectedCase.value = caseKey
              break
            }
          }
        } else {
          const mod = session.modules[session.currentModuleIndex]
          if (mod) {
            const prog = session.moduleProgress[`${session.testType}/${mod}`]
            if (prog?.currentCaseIndex) {
              selectedCase.value = formatSelectedCaseKey(session.testType, mod, prog.currentCaseIndex)
            }
          }
        }
      }
      if (!detail.session?.isRunning) {
        await refreshDeviceState(selectedDeviceId.value!)
      }
      const pending = await getPendingManualDecision(selectedDeviceId.value!)
      if (pending) {
        applyManualPrompt(pending)
      }
    } catch {}
  })
  eventSource.value.addEventListener('test_completed', async (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (data.deviceId) {
        await refreshDeviceState(data.deviceId)
        notifySelectedDeviceComplete(data.deviceId, data.session?.startTime)
      } else {
        await loadDevices()
      }
      await loadPipelineStatus()
    } catch {
      await loadDevices()
      await loadPipelineStatus()
    }
  })
  eventSource.value.addEventListener('report_ready', async () => {
    try {
      await refreshReportsAfterTest()
    } catch {
      reportsEpoch.value += 1
    }
  })
  eventSource.value.addEventListener('test_ended', async (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (data.deviceId) {
        await refreshDeviceState(data.deviceId)
      }
      // 报告已在 report_ready 刷新；此处兜底（例如报告生成失败仍需刷新总览）
      await loadPipelineStatus()
    } catch {}
  })
  eventSource.value.addEventListener('manual_confirm', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      applyManualPrompt(data)
    } catch {}
  })
  eventSource.value.onerror = () => {
    if (pollingTimer.value) return
    pollingTimer.value = setInterval(async () => {
      if (!selectedDeviceId.value) return
      try {
        await refreshDeviceState(selectedDeviceId.value)
        const detail = selectedDevice.value
        if (!detail?.session?.isRunning) {
          stopPollingTimer()
        }
        const pending = await getPendingManualDecision(selectedDeviceId.value)
        if (pending) {
          applyManualPrompt(pending)
        }
      } catch {}
    }, 1000)
  }
}

function startPolling() {
  connectEventStream()
}

function stopPollingTimer() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

function disconnectEventStream() {
  stopPollingTimer()
  if (eventSource.value) {
    eventSource.value.close()
    eventSource.value = null
  }
}

async function handleBrowseFlashPath() {
  if (flashPathPicking.value) return
  flashPathPicking.value = true
  error.value = null
  try {
    const result = await pickFlashPath()
    if (result.path) {
      flashPath.value = result.path
    } else if (result.error) {
      error.value = result.error
    }
  } catch (e: any) {
    error.value = e?.message || '选择刷机包失败'
  } finally {
    flashPathPicking.value = false
  }
}

async function handleBrowseTcardZip() {
  if (tcardPathPicking.value) return
  tcardPathPicking.value = true
  error.value = null
  try {
    const result = await pickTcardZipPath()
    if (result.path) {
      if (!/\.zip$/i.test(result.path)) {
        error.value = 'T卡升级仅支持 ZIP 文件'
        return
      }
      tcardUpdatePath.value = result.path
    } else if (result.error) {
      error.value = result.error
    }
  } catch (e: any) {
    error.value = e?.message || '选择 T卡升级 ZIP 失败'
  } finally {
    tcardPathPicking.value = false
  }
}

async function handleResolveLatestDailyFlash() {
  if (dailyFlashResolving.value) return
  const deviceId = selectedDeviceId.value
  if (!deviceId) {
    const text = '请先选择设备'
    error.value = text
    message.error(text)
    return
  }
  dailyFlashResolving.value = true
  error.value = null
  try {
    const result = await resolveLatestDailyFlashPackage({ deviceId })
    flashPath.value = result.packagePath
    flashStageVersion.value = 'Open'
    message.success(
      `已找到 ${result.systemVersion} 最新 daily：${result.versionName}${result.usedIdhFallback ? '（已使用 IDH 路径）' : ''}`
    )
  } catch (e: any) {
    const text = e?.message || '解析最新 daily 刷机包失败'
    error.value = text
    message.error(text)
  } finally {
    dailyFlashResolving.value = false
  }
}

function pickTcardPath(step: AndroidUpgradeStep, previousAndroid: number): string {
  return pickPreferredTcardZip(step.tcardZips, previousAndroid)
}

function syncReleaseUpgradeSelection(): boolean {
  const plan = releaseUpgradePlan.value
  if (!plan) return true
  const selected = plan.steps
    .filter((step) => step.selected)
    .sort((a, b) => a.androidVersion - b.androidVersion)
  if (!selected.length) {
    releaseFlashPath.value = ''
    releaseTcardPaths.value = []
    return false
  }

  const baseline = selected[0]!
  if (baseline.needsTransfer || !baseline.available || !baseline.fullZip) {
    return false
  }
  baseline.packagePath = baseline.fullZip
  releaseFlashPath.value = baseline.packagePath

  const tcardPaths: string[] = []
  let previousAndroid = baseline.androidVersion
  for (const step of selected.slice(1)) {
    const path = pickTcardPath(step, previousAndroid)
    if (!path) {
      if (!step.needsTransfer) {
        step.packagePath = ''
        step.unavailableReason = missingTcardZipHint(previousAndroid)
        step.available = false
        step.selected = false
      }
      releaseTcardPaths.value = tcardPaths
      return false
    }
    step.packagePath = path
    if (step.needsTransfer || !step.available) {
      releaseTcardPaths.value = tcardPaths
      return false
    }
    tcardPaths.push(path)
    previousAndroid = step.androidVersion
  }
  releaseTcardPaths.value = tcardPaths
  return true
}

function toggleReleaseUpgradeStep(step: AndroidUpgradeStep) {
  if (!step.available || step.needsTransfer) return
  step.selected = !step.selected
  syncReleaseUpgradeSelection()
}

function isReleaseUpgradeFlashStep(step: AndroidUpgradeStep): boolean {
  const selected = releaseUpgradePlan.value?.steps
    .filter((item) => item.selected)
    .sort((a, b) => a.androidVersion - b.androidVersion) || []
  if (selected[0]) return selected[0] === step
  const all = [...(releaseUpgradePlan.value?.steps || [])].sort((a, b) => a.androidVersion - b.androidVersion)
  return all[0] === step
}

function updateReleaseUpgradePath(step: AndroidUpgradeStep, path: string) {
  step.packagePath = path
  if (step.needsTransfer) {
    step.sourcePath = path
    return
  }
  if (isReleaseUpgradeFlashStep(step)) {
    step.fullZip = path
  } else {
    step.tcardZips = path ? [path, ...step.tcardZips.filter((item) => item !== path)] : []
  }
  syncReleaseUpgradeSelection()
}

async function handleBrowseReleaseUpgradePath(step: AndroidUpgradeStep) {
  if (releasePathPicking.value) return
  releasePathPicking.value = true
  error.value = null
  try {
    const pickFlash = isReleaseUpgradeFlashStep(step)
    const result = pickFlash ? await pickFlashPath() : await pickTcardZipPath()
    if (result.path) {
      if (!pickFlash && !/\.zip$/i.test(result.path)) {
        error.value = 'T卡升级仅支持 ZIP 文件'
        return
      }
      if (!step.needsTransfer) {
        step.available = true
        step.unavailableReason = undefined
      }
      updateReleaseUpgradePath(step, result.path)
    } else if (result.error) {
      error.value = result.error
    }
  } catch (e: any) {
    error.value = e?.message || '选择升级包失败'
  } finally {
    releasePathPicking.value = false
  }
}

function releaseUpgradeMethodLabel(step: AndroidUpgradeStep): string {
  if (step.needsTransfer) return '待回传重庆'
  if (!step.available) return '缺少T卡包'
  if (!step.selected) return '未选择'
  const selected = releaseUpgradePlan.value?.steps
    .filter((item) => item.selected)
    .sort((a, b) => a.androidVersion - b.androidVersion) || []
  return selected[0] === step ? 'device_update' : 'T卡升级'
}

async function handleResolveReleaseUpgrade() {
  if (releaseUpgradeResolving.value) return
  const deviceId = selectedDeviceId.value
  if (!deviceId) {
    message.error('请先选择设备')
    return
  }
  releaseUpgradeResolving.value = true
  error.value = null
  try {
    releaseUpgradePlan.value = await resolveReleaseUpgradePlan(deviceId)
    enableReleaseUpgrade.value = true
    syncReleaseUpgradeSelection()
    const transferable = releaseUpgradePlan.value.steps.filter((step) => step.needsTransfer).length
    const missingTcard = releaseUpgradePlan.value.steps.filter((step) =>
      !step.available && !step.needsTransfer && Boolean(step.unavailableReason)
    ).length
    const summary = releaseUpgradePlan.value.dailyTcardOverrideApplied
      ? `已识别各 Android 最新版本，最高版本已使用 sw_ver_sh 最新 daily T卡包${transferable ? `；${transferable} 个其他版本需传回重庆` : ''}`
      : transferable
      ? `已识别各 Android 最新版本，${transferable} 个版本需先传回重庆`
      : missingTcard
      ? `已识别各 Android 大版本，${missingTcard} 个版本未找到T卡包`
      : '已识别各 Android 最新版本并生成连续升级顺序'
    if (missingTcard) message.warning(summary)
    else message.success(summary)
  } catch (e: any) {
    const text = e?.message || '解析已外发 Android 版本失败'
    if (text.includes('不能使用连续版本升级')) {
      enableReleaseUpgrade.value = false
      releaseUpgradePlan.value = null
      releaseFlashPath.value = ''
      releaseTcardPaths.value = []
    }
    error.value = text
    message.error(text)
  } finally {
    releaseUpgradeResolving.value = false
  }
}

function formatFreedBytes(bytes: number): string {
  const gib = bytes / 1024 / 1024 / 1024
  if (gib >= 1) return `${gib.toFixed(2)} GiB`
  const mib = bytes / 1024 / 1024
  if (mib >= 1) return `${mib.toFixed(1)} MiB`
  if (bytes > 0) return `${Math.max(1, Math.round(bytes / 1024))} KiB`
  return '0 B'
}

function isPathUnderFlashCache(target: string, cacheDir: string): boolean {
  const norm = target.trim().replace(/\//g, '\\').toLowerCase()
  const base = cacheDir.trim().replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase()
  if (!norm || !base) return false
  return norm === base || norm.startsWith(`${base}\\`)
}

async function handleClearFlashPackages() {
  if (flashPackagesClearing.value || flashActive.value) return

  dialog.warning({
    title: '清除刷机包',
    content: '清除本地下载/解压的刷机包缓存',
    positiveText: '确认清除',
    negativeText: '取消',
    onPositiveClick: async () => {
      flashPackagesClearing.value = true
      error.value = null
      try {
        const result = await clearFlashPackageCache()
        if (isPathUnderFlashCache(flashPath.value, result.flashPackageDir)) {
          flashPath.value = ''
        }
        if (result.removedEntries === 0) {
          dialog.info({
            title: '无需清理',
            content: '本地刷机包缓存为空，无需清理',
            positiveText: '知道了',
          })
        } else {
          dialog.success({
            title: '清除完成',
            content: `已清除 ${result.removedEntries} 项本地刷机包缓存，释放约 ${formatFreedBytes(result.freedBytes)}`,
            positiveText: '知道了',
          })
        }
      } catch (e: any) {
        const text = e?.message || '清除刷机包缓存失败'
        error.value = text
        dialog.error({
          title: '清除失败',
          content: text,
          positiveText: '知道了',
        })
      } finally {
        flashPackagesClearing.value = false
      }
    },
  })
}

function confirmOtaUpgradeFlashThenStart(deviceId: string) {
  dialog.warning({
    title: OTA_UPGRADE_FLASH_CONFIRM.title,
    content: () => h(
      'div',
      { style: 'line-height: 1.7' },
      [
        ...OTA_UPGRADE_FLASH_CONFIRM.lines.map(line => h('p', { style: 'margin: 0 0 8px' }, line)),
        h('p', { style: 'margin: 12px 0 0; font-size: 13px' }, [
          `${OTA_UPGRADE_SOP.hint}：`,
          h(
            'a',
            {
              href: OTA_UPGRADE_SOP.url,
              target: '_blank',
              rel: 'noopener noreferrer',
            },
            OTA_UPGRADE_SOP.label,
          ),
        ]),
      ],
    ),
    positiveText: OTA_UPGRADE_FLASH_CONFIRM.positiveText,
    negativeText: OTA_UPGRADE_FLASH_CONFIRM.negativeText,
    onPositiveClick: () => commitStartTest(deviceId),
  })
}

async function handleStartTest(deviceId: string) {
  try {
    if (selectedTestType.value === 'gms' && !gmsHostSupported.value) {
      error.value = 'Windows 环境不支持 GMS 测试，请在 Linux 主机上运行'
      message.error(error.value)
      return
    }
    const releaseActive = enableReleaseUpgrade.value || selectedTestType.value === 'ota_upgrade'
    if (releaseActive && !releaseUpgradePlan.value) {
      error.value = '请先获取外发版本'
      return
    }
    if (releaseActive && releaseUpgradePlan.value) {
      const selected = releaseUpgradePlan.value.steps.filter((step) => step.selected)
      if (!selected.length) {
        error.value = '请至少选择一个可用的 Android 版本'
        return
      }
      if (selected.some((step) => step.needsTransfer || !step.available)) {
        error.value = '所选版本包含尚未传回重庆的刷机包，请传输后重新解析'
        return
      }
      if (!syncReleaseUpgradeSelection()) {
        error.value = '最低选中版本缺少 device_update 整包，或更高版本缺少 T卡升级包'
        return
      }
    }
    if (!releaseActive && enableFlash.value && !flashPath.value.trim()) {
      error.value = '请先选择刷机包路径'
      return
    }
    if (!releaseActive && enableTcardUpdate.value) {
      const zipPaths = tcardUpdatePath.value.trim() ? [tcardUpdatePath.value.trim()] : []
      if (!zipPaths.length) {
        error.value = '请先选择 T卡升级 ZIP 包'
        return
      }
      if (zipPaths.some((path) => !/\.zip$/i.test(path))) {
        error.value = 'T卡升级仅支持 ZIP 文件'
        return
      }
    }
    if (selectedTestType.value === 'kernel_feature') {
      await saveKernelFeatureCodeDir(false)
    }
    if (selectedTestType.value === 'gms') {
      await saveGmsTradefedSettings(false)
    }
    if (selectedTestType.value === 'bitflip') {
      await saveBitflipRepeatCount(false)
    }
    const availableModules = listModulesForTestType(selectedTestType.value)
    const modulesToRun = availableModules.filter(m => selectedStartModules.value.has(m))
    if (availableModules.length > 1 && modulesToRun.length === 0) {
      error.value = '请至少勾选一个测试模块'
      return
    }
    if (selectedTestType.value === 'ota_upgrade' && startTestIntentRole.value !== '辅测机') {
      confirmOtaUpgradeFlashThenStart(deviceId)
      return
    }
    await commitStartTest(deviceId)
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error starting test:', e)
    clearFlashPanel()
    error.value = e?.message || '启动测试失败'
  }
}

async function commitStartTest(deviceId: string) {
  try {
    const releaseActive = enableReleaseUpgrade.value || selectedTestType.value === 'ota_upgrade'
    const intent = startTestIntentRole.value
    const current = devices.value.find(d => d.deviceId === deviceId)
    if (current && current.role !== intent) {
      const updated = await setDeviceRole(deviceId, intent)
      if (!updated) return
      patchDeviceInList(updated)
      if (selectedDeviceId.value === deviceId && selectedDevice.value) {
        selectedDevice.value = { ...selectedDevice.value, device: updated }
      }
    }
    const availableModules = listModulesForTestType(selectedTestType.value)
    const modulesToRun = availableModules.filter(m => selectedStartModules.value.has(m))
    clearFlashPanel()
    const flash = releaseActive
      ? {
          enabled: true,
          pkgPath: releaseFlashPath.value.trim(),
          stageVersion: 'Open',
        }
      : enableFlash.value
      ? {
          enabled: true,
          pkgPath: flashPath.value.trim(),
          enableRootPkg: enableRootPkg.value,
          stageVersion: flashStageVersion.value || undefined,
        }
      : undefined
    const tcard = releaseActive && releaseTcardPaths.value.length
      ? {
          enabled: true,
          zipPath: releaseTcardPaths.value[0],
          zipPaths: [...releaseTcardPaths.value],
        }
      : !releaseActive && enableTcardUpdate.value
      ? {
          enabled: true,
          zipPath: tcardUpdatePath.value.trim(),
          zipPaths: [tcardUpdatePath.value.trim()],
        }
      : undefined
    if (flash || tcard) {
      flashDeviceId.value = deviceId
      flashActive.value = true
      flashProgressState.value = createFlashProgressState()
      appendFlashLog(
        flash
          ? '[刷机] 已提交刷机任务，等待设备进入刷机流程...'
          : '[T卡升级] 已提交 T卡升级任务，等待推送 ZIP...',
      )
    }
    const result = await startTest(
      deviceId,
      selectedTestType.value,
      flash,
      undefined,
      prioritizeTddManual.value,
      tcard,
      availableModules.length > 1 ? modulesToRun : undefined,
    )
    if (result) {
      selectedDevice.value = result
      followCurrent.value = true
      startPolling()
    }
    await loadDevices()
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error starting test:', e)
    clearFlashPanel()
    error.value = e?.message || '启动测试失败'
  }
}

async function handleContinueTest(deviceId: string) {
  try {
    const result = await continueTest(deviceId)
    if (result) {
      selectedDevice.value = result
      followCurrent.value = true
      startPolling()
    }
    await loadDevices()
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error continuing test:', e)
    message.error(e?.message || '继续测试失败')
  }
}

async function handleResumeTest(deviceId: string) {
  try {
    const result = await resumeTest(deviceId)
    if (result) {
      selectedDevice.value = result
      followCurrent.value = true
      startPolling()
      message.success('已从报错模块恢复测试')
    } else {
      message.error('无法恢复测试，请检查设备状态')
    }
    await loadDevices()
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error resuming test:', e)
    message.error(e?.message || '恢复测试失败')
  }
}

async function handleEndTest(deviceId: string) {
  try {
    stopPollingTimer()
    clearFlashPanel()
    clearFlashFormForDevice(deviceId)
    const result = await endTest(deviceId)
    if (!result?.device) {
      message.error('结束测试失败：设备不存在或已释放')
      await loadDevices()
      return
    }
    patchDeviceInList(result.device)
    await loadDevices()
    message.success('测试已终止，报告将记为失败')
    if (result.device.role === '辅测机' && (result.device.status as string) === '待命') {
      selectedDeviceId.value = deviceId
      selectedDevice.value = result
    } else {
      selectedDeviceId.value = null
      selectedDevice.value = null
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error ending test:', e)
    message.error(e?.message || '结束测试失败')
    await loadDevices()
  }
}

async function handleSkipCurrentCase(deviceId: string) {
  try {
    const result = await skipCurrentCase(deviceId)
    if (!result?.device) {
      message.error('跳过失败：设备不存在')
      return
    }
    patchDeviceInList(result.device)
    if (selectedDeviceId.value === deviceId) {
      selectedDevice.value = result
    }
    message.success('已跳过当前用例')
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error skipping case:', e)
    message.error(e?.message || '跳过当前用例失败')
  }
}

// 修改用例结果
const showModifyDialog = ref(false)
const modifyCaseKey = ref<string | null>(null)
const modifyStatus = ref('通过')
const modifyMessage = ref('')

// 人工确认弹窗（FIFO 队列，避免多机并行时互相覆盖）
type ManualPrompt = {
  decisionId: string
  deviceId?: string
  deviceName: string
  message: string
  passLabel: string
  failLabel: string
  mode: 'decision' | 'ack'
}

const manualQueue = ref<ManualPrompt[]>([])
const manualSubmitting = ref(false)

const manualHead = computed(() => manualQueue.value[0] ?? null)
const showManualDialog = computed(() => manualHead.value != null)
const manualDecisionId = computed(() => manualHead.value?.decisionId ?? null)
const manualDeviceName = computed(() => manualHead.value?.deviceName ?? '')
const manualMessage = computed(() => manualHead.value?.message ?? '')
const manualPassLabel = computed(() => manualHead.value?.passLabel ?? '通过')
const manualFailLabel = computed(() => manualHead.value?.failLabel ?? '失败')
const manualMode = computed(() => manualHead.value?.mode ?? 'decision')
const manualQueueRemaining = computed(() => Math.max(0, manualQueue.value.length - 1))

function applyManualPrompt(data: {
  decisionId: string
  deviceId?: string
  deviceName?: string
  message?: string
  passLabel?: string
  failLabel?: string
  mode?: 'decision' | 'ack'
}) {
  if (!data.decisionId) return
  if (manualQueue.value.some((item) => item.decisionId === data.decisionId)) return

  const prompt: ManualPrompt = {
    decisionId: data.decisionId,
    deviceId: data.deviceId,
    deviceName:
      data.deviceName ||
      devices.value.find((d) => d.deviceId === data.deviceId)?.deviceName ||
      data.deviceId ||
      '',
    message: data.message || '需人工确认',
    passLabel: data.passLabel || '通过',
    failLabel: data.failLabel || '失败',
    mode: data.mode === 'ack' ? 'ack' : 'decision',
  }
  manualQueue.value = [...manualQueue.value, prompt]
}

function openModifyDialog(caseKey: string) {
  modifyCaseKey.value = caseKey
  const result = selectedDevice.value?.session?.caseResults?.[caseKey]
  modifyStatus.value = result?.status || '通过'
  modifyMessage.value = result?.message || ''
  showModifyDialog.value = true
}

async function handleModifyCaseResult() {
  if (!modifyCaseKey.value || !selectedDeviceId.value) return
  const parts = modifyCaseKey.value.split('/')
  const caseIndex = parseInt(parts.pop() || '1')
  const module = parts.pop() || ''
  const testType = parts.join('/')
  try {
    await updateCaseResult(
      selectedDeviceId.value,
      testType,
      module,
      caseIndex,
      modifyStatus.value,
      modifyMessage.value
    )
    showModifyDialog.value = false
    await selectDevice(selectedDeviceId.value)
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error modifying case result:', e)
  }
}

// 复测用例
const showRetestDialog = ref(false)
const retestCaseKey = ref<string | null>(null)
const retestAuxDeviceId = ref<string | null>(null)
const retesting = ref(false)

const availableAuxForRetest = computed(() => {
  return devices.value.filter(d =>
    d.deviceId !== selectedDeviceId.value &&
    (d.role === '辅测机' || d.role === '测试机') &&
    d.status === '空闲'
  )
})

function openRetestDialog(caseKey: string) {
  retestCaseKey.value = caseKey
  retestAuxDeviceId.value = null
  showRetestDialog.value = true
}

async function handleRetestCase() {
  if (!retestCaseKey.value || !selectedDeviceId.value) return
  const parts = retestCaseKey.value.split('/')
  const caseIndex = parseInt(parts.pop() || '1')
  const module = parts.pop() || ''
  const testType = parts.join('/')
  retesting.value = true
  try {
    await retestCase(
      selectedDeviceId.value,
      testType,
      module,
      caseIndex,
      retestAuxDeviceId.value || undefined
    )
    showRetestDialog.value = false
    await selectDevice(selectedDeviceId.value)
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error retesting case:', e)
  } finally {
    retesting.value = false
  }
}

async function handleManualDecision(decision: 'pass' | 'fail' | 'ack') {
  const head = manualHead.value
  if (!head || manualSubmitting.value) return
  const decisionId = head.decisionId
  const deviceIdForPending = head.deviceId
  manualSubmitting.value = true
  try {
    await submitManualDecision(decisionId, decision)
    // operator_notify(ack) 后 Python 常立刻再发 manual_confirm；
    // 提交期间新入队的项必须保留，只移除刚提交的那条。
    if (manualQueue.value[0]?.decisionId === decisionId) {
      manualQueue.value = manualQueue.value.slice(1)
    } else {
      manualQueue.value = manualQueue.value.filter((item) => item.decisionId !== decisionId)
    }
    // 兜底：ack 后下一轮提示偶发丢 SSE 时主动拉取（仅队列已空时，避免覆盖其它机）
    if (decision === 'ack' && deviceIdForPending && manualQueue.value.length === 0) {
      try {
        const pending = await getPendingManualDecision(deviceIdForPending)
        if (pending) applyManualPrompt(pending)
      } catch {}
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error submitting manual decision:', e)
  } finally {
    manualSubmitting.value = false
  }
}

async function loadCaseCatalogs(options?: { silent?: boolean }) {
  try {
    caseCatalogGroups.value = await getCaseCatalogs()
    expandedCatalogTypes.value = new Set(caseCatalogGroups.value.map(g => g.testType))
    expandedCatalogModules.value = new Set()
  } catch (e) {
    console.error('[DeviceSelfCheck] Error loading case catalogs:', e)
    if (!options?.silent) {
      error.value = '加载用例目录失败'
    }
  }
}

function toggleCatalogType(testType: string) {
  if (expandedCatalogTypes.value.has(testType)) {
    expandedCatalogTypes.value.delete(testType)
  } else {
    expandedCatalogTypes.value.add(testType)
  }
  expandedCatalogTypes.value = new Set(expandedCatalogTypes.value)
}

function toggleCatalogModule(moduleKey: string) {
  if (expandedCatalogModules.value.has(moduleKey)) {
    expandedCatalogModules.value.delete(moduleKey)
  } else {
    expandedCatalogModules.value.add(moduleKey)
  }
  expandedCatalogModules.value = new Set(expandedCatalogModules.value)
}

function toggleCase(caseKey: string) {
  if (caseKey.startsWith('gms/') && !gmsHostSupported.value) return
  if (selectedCases.value.has(caseKey)) {
    selectedCases.value.delete(caseKey)
  } else {
    selectedCases.value.add(caseKey)
  }
  selectedCases.value = new Set(selectedCases.value)
}

function isCatalogGroupUnavailable(group: { testType: string; unavailableReason?: string }): boolean {
  return Boolean(group.unavailableReason) || (group.testType === 'gms' && !gmsHostSupported.value)
}

function toggleAllCasesInModule(catalog: CaseCatalog) {
  if (catalog.testType === 'gms' && !gmsHostSupported.value) return
  const allSelected = catalog.cases.every(c =>
    selectedCases.value.has(`${catalog.key}/${c.caseIndex}`)
  )
  for (const c of catalog.cases) {
    const key = `${catalog.key}/${c.caseIndex}`
    if (allSelected) {
      selectedCases.value.delete(key)
    } else {
      selectedCases.value.add(key)
    }
  }
  selectedCases.value = new Set(selectedCases.value)
}

function toggleAllCasesInGroup(group: CaseCatalogGroup) {
  if (isCatalogGroupUnavailable(group)) return
  const allKeys: string[] = []
  for (const mod of group.modules) {
    for (const c of mod.cases) {
      allKeys.push(`${mod.key}/${c.caseIndex}`)
    }
  }
  const allSelected = allKeys.every(k => selectedCases.value.has(k))
  for (const key of allKeys) {
    if (allSelected) {
      selectedCases.value.delete(key)
    } else {
      selectedCases.value.add(key)
    }
  }
  selectedCases.value = new Set(selectedCases.value)
}

function countGroupCases(group: CaseCatalogGroup): number {
  return group.modules.reduce((sum, m) => sum + m.cases.length, 0)
}

function isGroupAllSelected(group: CaseCatalogGroup): boolean {
  for (const mod of group.modules) {
    for (const c of mod.cases) {
      if (!selectedCases.value.has(`${mod.key}/${c.caseIndex}`)) return false
    }
  }
  return group.modules.length > 0
}

async function toggleAuxDevice(deviceId: string) {
  if (customTestAuxDeviceIds.value.has(deviceId)) {
    customTestAuxDeviceIds.value.delete(deviceId)
  } else {
    customTestAuxDeviceIds.value.add(deviceId)
    const dev = devices.value.find(d => d.deviceId === deviceId)
    if (dev?.role === '未分配') {
      try {
        const updated = await setDeviceRole(deviceId, '辅测机')
        if (updated) patchDeviceInList(updated)
      } catch (e: any) {
        console.error('[DeviceSelfCheck] Error setting aux role:', e)
      }
    }
  }
  customTestAuxDeviceIds.value = new Set(customTestAuxDeviceIds.value)
}

async function handleStartCustomTest() {
  if (!customTestDutDeviceId.value || selectedCases.value.size === 0) return
  if (!gmsHostSupported.value && Array.from(selectedCases.value).some(key => key.startsWith('gms/'))) {
    error.value = 'Windows 环境不支持 GMS 测试，请取消勾选 GMS 用例或在 Linux 主机上运行'
    message.error(error.value)
    return
  }
  customTestStarting.value = true
  error.value = null
  try {
    const result = await startCustomTest(
      customTestDutDeviceId.value,
      Array.from(selectedCases.value),
      Array.from(customTestAuxDeviceIds.value),
      prioritizeTddManual.value,
    )
    viewMode.value = 'list'
    catalogPanelExpanded.value = false
    selectedDeviceId.value = customTestDutDeviceId.value
    selectedDevice.value = result
    deviceDetailExpanded.value = true
    followCurrent.value = true
    applyFollowCurrentCase(result.session)
    startPolling()
    await loadDevices()
    deviceDetailScrollNonce.value += 1
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error starting custom test:', e)
    error.value = e?.message || '启动自定义测试失败'
  } finally {
    customTestStarting.value = false
  }
}

function openCustomTest() {
  activeTab.value = 'devices'
  viewMode.value = 'customTest'
  customTestDutDeviceId.value = null
  customTestAuxDeviceIds.value = new Set()
  loadCaseCatalogs()
}

function closeCustomTest() {
  viewMode.value = 'list'
}

function applyPendingGerritLaunch() {
  const keys = launchStore.consumePendingCustomCases()
  if (!keys.length) return
  selectedCases.value = new Set(keys)
  gerritPreselectCount.value = keys.length
  activeTab.value = 'devices'
  openCustomTest()
}

watch(
  () => launchStore.pendingCustomCaseKeys.length,
  (len) => {
    if (len > 0) applyPendingGerritLaunch()
  },
)

// 根据设备测试类型和模块获取用例列表
const getCaseGroups = computed(() => {
  const testType = selectedDevice.value?.device.testType || selectedTestType.value
  const session = selectedDevice.value?.session

  if (testType === 'custom' && session?.selectedCases) {
    const groups: Record<string, {
      label: string
      moduleKey: string
      cases: { caseIndex: number; caseName: string; testType: string; module: string; automationMode?: string }[]
    }> = {}

    for (const caseKey of session.selectedCases) {
      const parts = caseKey.split('/')
      const caseIndex = parseInt(parts.pop() || '1', 10)
      const module = parts.pop() || ''
      const tt = parts.join('/')
      const moduleKey = `${tt}/${module}`
      const config = moduleConditions.value[moduleKey]
      const result = session.caseResults[caseKey]

      if (!groups[moduleKey]) {
        groups[moduleKey] = {
          label: config?.moduleLabel || module,
          moduleKey,
          cases: [],
        }
      }
      groups[moduleKey].cases.push({
        caseIndex,
        caseName: result?.caseName || config?.cases.find(c => c.caseIndex === caseIndex)?.caseName || `用例${caseIndex}`,
        testType: tt,
        module,
        automationMode: config?.cases.find(c => c.caseIndex === caseIndex)?.automationMode || 'full',
      })
    }

    return Object.entries(groups)
      .sort((a, b) => {
        const orderA = MODULE_ORDER[a[1].cases[0]?.module] ?? 50
        const orderB = MODULE_ORDER[b[1].cases[0]?.module] ?? 50
        return orderA - orderB
      })
      .map(([moduleKey, group]) => {
        const moduleConfig = moduleConditions.value[moduleKey]
        return [group.label, [{
          testType: group.cases[0]?.testType || 'str4',
          module: group.cases[0]?.module || '',
          moduleLabel: group.label,
          moduleKey,
          cases: group.cases.map(c => {
            const caseMeta = moduleConfig?.cases.find(x => x.caseIndex === c.caseIndex)
            return {
              caseIndex: c.caseIndex,
              caseName: c.caseName,
              mode: '',
              canReuse: false,
              automationMode: caseMeta?.automationMode || c.automationMode || 'full',
            }
          }),
        }]] as [string, (ModuleCondition & { moduleKey: string })[]]
      })
  }

  const modules: Record<string, ModuleCondition[]> = {}
  
  for (const [, config] of Object.entries(moduleConditions.value)) {
    if (config.customOnly) continue
    if (config.testType === testType) {
      if (!modules[config.moduleLabel]) {
        modules[config.moduleLabel] = []
      }
      modules[config.moduleLabel].push(config)
    }
  }

  return Object.entries(modules).sort((a, b) => {
    const orderA = MODULE_ORDER[a[1][0]?.module] ?? 50
    const orderB = MODULE_ORDER[b[1][0]?.module] ?? 50
    return orderA - orderB
  })
})

const isIdle = computed(() => {
  return selectedDevice.value?.device.status === '空闲'
})

const isError = computed(() => selectedDevice.value?.device.status === '错误')

const errorReason = computed(() => {
  const session = selectedDevice.value?.session
  if (session?.errorReason) return session.errorReason
  if (flashDone.value === 'error' && flashLogs.value.length) {
    const last = [...flashLogs.value].reverse().find(l => /失败|error|错误/i.test(l))
    if (last) return last
  }
  return '测试流程异常中断'
})

const errorModuleLabel = computed(() => selectedDevice.value?.device.currentModule || '')

const isFlashing = computed(() => selectedDevice.value?.device.status === '刷机中')
const isTcardUpdating = computed(() => selectedDevice.value?.device.status === 'T卡升级中')
const isPretesting = computed(() => isFlashing.value || isTcardUpdating.value)

const flashProgress = computed(() => flashProgressState.value.progress)

const flashPhase = computed(() => flashPhaseLabel(flashProgressState.value))

const isFlashFailed = computed(() => {
  return flashDone.value === 'error'
    && flashDeviceId.value === selectedDeviceId.value
    && flashLogs.value.length > 0
})

const showFlashPanel = computed(() => {
  if (!selectedDeviceId.value) return false
  if (isPretesting.value) return true
  if (!flashDeviceId.value || flashDeviceId.value !== selectedDeviceId.value) return false
  if (flashActive.value) return true
  return isFlashFailed.value
})

const showFlashFailureUI = computed(() => isError.value || isFlashFailed.value)

const isFlashIndeterminate = computed(() => {
  return (flashActive.value || isPretesting.value) && flashProgress.value < 8
})

const pretestPanelTitle = computed(() => (
  isTcardUpdating.value || flashLogs.value.some(line => line.includes('[T卡升级]'))
    ? 'T卡升级进度'
    : '刷机进度'
))

const pretestLogTitle = computed(() => (
  pretestPanelTitle.value === 'T卡升级进度' ? 'T卡升级日志' : '刷机日志'
))

const flashStatusText = computed(() => {
  if (isTcardUpdating.value) return 'T卡升级中'
  if (isFlashing.value || flashActive.value) {
    return flashLogs.value.some(line => line.includes('[T卡升级]')) ? 'T卡升级中' : '刷机中'
  }
  if (flashDone.value === 'success') return '完成'
  if (flashDone.value === 'error') {
    return flashLogs.value.some(line => line.includes('[T卡升级]')) ? 'T卡升级失败' : '刷机失败'
  }
  return '待开始'
})

const flashStatusClass = computed(() => {
  if (isPretesting.value || flashActive.value) return 'is-running'
  if (flashDone.value === 'success') return 'is-success'
  if (flashDone.value === 'error') return 'is-error'
  return 'is-idle'
})

const pageTitle = computed(() => {
  if (selectedDeviceId.value) {
    return selectedDevice.value?.device.deviceName || '设备详情'
  }
  if (viewMode.value === 'customTest') return '自定义测试'
  if (catalogPanelExpanded.value && selectedCatalogGroup.value) {
    return selectedCatalogGroup.value.label
  }
  return '质量验测'
})

const showStandardTddManualPriority = computed(() =>
  selectedTestType.value === 'str4' || selectedTestType.value === 'week',
)

const hasSelectedStr4WeekTdd = computed(() => {
  for (const key of selectedCases.value) {
    if (/^(str4|week)\/tdd\/\d+$/.test(key)) return true
  }
  return false
})

const isTestComplete = computed(() => {
  const status = selectedDevice.value?.device.status || ''
  return status.includes('完成')
})

const canEndTest = computed(() => {
  const device = selectedDevice.value?.device
  const session = selectedDevice.value?.session
  if (!device || device.role === '辅测机') return false
  if ((device.status as string) === '待命') return false
  if (session?.isRunning) return true
  const status = device.status || ''
  return status === '测试中' || status === '初始化中' || status === '等待测试开始' || status === '刷机中' || status === 'T卡升级中' || status === '错误'
})

const canSkipCurrentCase = computed(() => {
  const device = selectedDevice.value?.device
  const session = selectedDevice.value?.session
  if (!device || device.role === '辅测机') return false
  if (!session?.isRunning) return false
  return Object.values(session.caseResults || {}).some(
    r => r.status === '进行中' || r.status === '待确认',
  )
})

const needsContinue = computed(() => {
  const status = selectedDevice.value?.device.status || ''
  return status.includes('不满足前置条件')
})

// 当前选中的用例结果
const selectedCaseResult = computed((): CaseResult | undefined => {
  if (!selectedCase.value || !selectedDevice.value?.session?.caseResults) return undefined
  const session = selectedDevice.value.session
  const parsed = parseSelectedCaseKey(
    selectedCase.value,
    selectedDevice.value.device.testType,
  )
  if (!parsed) return undefined
  const key = formatCaseResultKey(parsed)
  const result = session.caseResults[key]
  if (result) {
    const config = moduleConditions.value[`${result.testType}/${result.module}`]
    if (config) {
      const caseItem = config.cases.find(c => c.caseIndex === result.caseIndex)
      if (caseItem) {
        result.caseName = caseItem.caseName
      }
    }
  }
  return result
})

watch(selectedTestType, (testType, previous) => {
  syncSelectedStartModules(testType)
  const next = resolveReleaseUpgradeEnabledOnTypeChange({
    testType,
    previousTestType: previous,
    currentEnabled: enableReleaseUpgrade.value,
    enabledBeforeOta: releaseUpgradeEnabledBeforeOta,
  })
  releaseUpgradeEnabledBeforeOta = next.enabledBeforeOta
  if (enableReleaseUpgrade.value !== next.enabled) {
    enableReleaseUpgrade.value = next.enabled
    if (previous === 'ota_upgrade' && selectedDeviceId.value) {
      saveFlashFormForDevice(selectedDeviceId.value)
    }
  }
  if (testType === 'gms') {
    void loadGmsTradefedSettings()
  }
  if (testType === 'kernel_feature') {
    void loadKernelFeatureSettings()
  }
})

onMounted(async () => {
  connectEventStream()
  await loadDevices()
  await Promise.all([
    loadPipelineStatus(),
    loadTPowerStatus(),
    loadOverviewReports(),
  ])
  loadCaseCatalogs({ silent: true })
  await Promise.all([
    loadGmsTradefedSettings(),
    loadKernelFeatureSettings(),
  ])
  try {
    moduleConditions.value = await getModuleConditions()
    // 默认展开所有模块
    expandedModules.value = new Set(Object.keys(moduleConditions.value).map(k => moduleConditions.value[k].module))
    syncSelectedStartModules()
  } catch (e) {
    console.error('[DeviceSelfCheck] Failed to load module conditions:', e)
  }
})

onUnmounted(() => {
  disconnectEventStream()
})

// 辅助函数：获取当前选中用例名称
function toggleModule(key: string) {
  if (expandedModules.value.has(key)) {
    expandedModules.value.delete(key)
  } else {
    expandedModules.value.add(key)
  }
  // 触发响应式更新
  expandedModules.value = new Set(expandedModules.value)
}

function isModuleExpanded(key: string): boolean {
  return expandedModules.value.has(key)
}

// 辅助函数：获取当前选中用例名称
function getSelectedCaseName(config: ModuleCondition): string {
  const parsed = parseSelectedCaseKey(
    selectedCase.value,
    selectedDevice.value?.device.testType,
  )
  const caseIndex = parsed?.caseIndex ?? parseInt(selectedCase.value?.split('/').pop() || '1', 10)
  const caseItem = config.cases.find(c => c.caseIndex === caseIndex)
  return caseItem?.caseName || `用例${caseIndex}`
}

function selectCaseItem(module: string, caseIndex: number, testType?: string) {
  const tt = testType || selectedDevice.value?.device.testType || 'str4'
  const nextKey = formatSelectedCaseKey(tt, module, caseIndex)
  const reselect = selectedCase.value === nextKey && deviceDetailExpanded.value
  selectedCase.value = nextKey
  followCurrent.value = false
  if (reselect) {
    deviceDetailScrollNonce.value += 1
  }
}

function toggleFollowCurrent() {
  followCurrent.value = !followCurrent.value
  if (followCurrent.value) {
    const s = selectedDevice.value?.session
    if (s) {
      if (s.testType === 'custom' && s.selectedCases) {
        for (const caseKey of s.selectedCases) {
          const result = s.caseResults[caseKey]
          if (result?.status === '进行中') {
            selectedCase.value = caseKey
            return
          }
        }
      } else {
        const m = s.modules[s.currentModuleIndex]
        if (m) {
          const p = s.moduleProgress[s.testType + '/' + m]
          if (p?.currentCaseIndex) {
            selectedCase.value = formatSelectedCaseKey(s.testType, m, p.currentCaseIndex)
          }
        }
      }
    }
  }
}

function isSelectedCaseInConfig(config: ModuleCondition): boolean {
  const parsed = parseSelectedCaseKey(
    selectedCase.value,
    selectedDevice.value?.device.testType,
  )
  if (!parsed) return false
  return parsed.testType === config.testType && parsed.module === config.module
}

// 辅助函数：获取用例结果样式类
function getCaseItemClass(config: ModuleCondition, index: number): string {
  const session = selectedDevice.value?.session
  if (!session?.caseResults) return ''
  const key = `${config.testType}/${config.module}/${index}`
  const result = session.caseResults[key]
  if (!result) return ''
  if (result.status === '通过') return 'passed'
  if (result.status === '失败') return 'failed'
  if (result.status === '待确认') return 'pending'
  return ''
}

function isCaseSelected(config: ModuleCondition, caseIndex: number): boolean {
  const parsed = parseSelectedCaseKey(
    selectedCase.value,
    selectedDevice.value?.device.testType,
  )
  if (!parsed) return false
  return (
    parsed.testType === config.testType
    && parsed.module === config.module
    && parsed.caseIndex === caseIndex
  )
}

// 辅助函数：获取用例结果样式
function getCaseItemStyle(config: ModuleCondition, index: number): Record<string, string> {
  const session = selectedDevice.value?.session
  if (!session?.caseResults) return {}
  const key = `${config.testType}/${config.module}/${index}`
  const result = session.caseResults[key]
  if (!result) return {}
  return { borderLeftColor: getCaseResultColor(result.status) }
}

  return {
    activeTab,
    stats,
    pipelineStages,
    overviewReports,
    reportsLoading,
    reportsEpoch,
    loadOverviewReports,
    tpowerStatus,
    loadTPowerStatus,
    handleNewTask,
    AUTO_RETEST_TOOLTIP,
    devices,
    selectedDeviceId,
    loading,
    error,
    selectedDevice,
    moduleConditions,
    selectedTestType,
    selectedStartModules,
    canSelectStartModules,
    toggleStartModule,
    isStartModuleSelected,
    startTestIntentRole,
    setStartTestIntentRole,
    enableFlash,
    flashPath,
    dailyFlashResolving,
    flashPackagesClearing,
    enableRootPkg,
    flashStageVersion,
    flashLogs,
    flashLogRef,
    flashPathPicking,
    FLASH_MARKET_OPTIONS,
    flashProgress,
    flashPhase,
    showFlashPanel,
    isFlashFailed,
    showFlashFailureUI,
    clearFlashPanel,
    dismissFlashFailure,
    isFlashIndeterminate,
    flashStatusText,
    flashStatusClass,
    handleBrowseFlashPath,
    handleBrowseTcardZip,
    handleBrowseReleaseUpgradePath,
    handleResolveLatestDailyFlash,
    handleResolveReleaseUpgrade,
    toggleReleaseUpgradeStep,
    updateReleaseUpgradePath,
    releaseUpgradeMethodLabel,
    handleClearFlashPackages,
    enableTcardUpdate,
    tcardUpdatePath,
    tcardPathPicking,
    releasePathPicking,
    enableReleaseUpgrade,
    releaseTcardPaths,
    releaseUpgradeResolving,
    releaseUpgradePlan,
    pretestPanelTitle,
    pretestLogTitle,
    viewMode,
    catalogPanelExpanded,
    deviceDetailExpanded,
    deviceDetailScrollNonce,
    catalogPanelScrollNonce,
    caseCatalogGroups,
    selectedCatalogTestType,
    catalogDetailItems,
    selectedCatalogCaseKey,
    catalogDetailLoading,
    selectedAiGeneratedCasesForDelete,
    aiGeneratedCasesDeleting,
    catalogTypeSettings,
    catalogSettingsSaving,
    expandedCatalogTypes,
    expandedCatalogModules,
    expandedCatalogDetailModules,
    selectedCases,
    customTestDutDeviceId,
    customTestAuxDeviceIds,
    customTestStarting,
    prioritizeTddManual,
    showStandardTddManualPriority,
    hasSelectedStr4WeekTdd,
    gerritPreselectCount,
    availableCustomAux,
    availableCustomDut,
    selectedCase,
    expandedModules,
    followCurrent,
    showModifyDialog,
    modifyCaseKey,
    modifyStatus,
    modifyMessage,
    showManualDialog,
    manualDecisionId,
    manualDeviceName,
    manualMessage,
    manualPassLabel,
    manualFailLabel,
    manualMode,
    manualQueueRemaining,
    manualSubmitting,
    showRetestDialog,
    retestCaseKey,
    retestAuxDeviceId,
    retesting,
    availableAuxForRetest,
    catalogDetailByModule,
    selectedCatalogItem,
    selectedCatalogGroup,
    getCaseGroups,
    isIdle,
    isError,
    errorReason,
    errorModuleLabel,
    pageTitle,
    isTestComplete,
    canEndTest,
    canSkipCurrentCase,
    needsContinue,
    selectedCaseResult,
    loadDevices,
    doRefreshDevices,
    selectDevice,
    collapseCaseCatalog,
    collapseDeviceDetail,
    isCatalogDetailModuleExpanded,
    toggleCatalogDetailModule,
    openCaseCatalog,
    selectCatalogCase,
    isAiGeneratedCatalog,
    toggleAiGeneratedCaseForDelete,
    clearAiGeneratedDeleteSelection,
    handleDeleteAiGeneratedCases,
    handleCreateAiNlUiCase,
    startEditAiNlCase,
    cancelEditAiNlCase,
    aiNlCaseForm,
    aiNlCaseEditingKey,
    aiNlCaseCreating,
    aiNlCaseProgress,
    aiNlCaseProgressStatus,
    clearAiNlProgress,
    saveCatalogTypeSettings,
    saveKernelFeatureCodeDir,
    loadKernelFeatureSettings,
    saveBitflipRepeatCount,
    saveGmsTradefedSettings,
    saveGmsTradefedSettingsFromDialog,
    openGmsTradefedDialog,
    closeGmsTradefedDialog,
    showGmsTradefedDialog,
    gmsTradefedDraft,
    gmsTradefedConfiguredSummary,
    gmsHostSupported,
    isCatalogGroupUnavailable,
    handleBrowseGmsTradefedPath,
    gmsPathPickingSuite,
    backToOverview,
    goBack,
    handleStartTest,
    handleContinueTest,
    handleResumeTest,
    handleEndTest,
    handleSkipCurrentCase,
    openModifyDialog,
    handleModifyCaseResult,
    openRetestDialog,
    handleRetestCase,
    handleManualDecision,
    toggleCatalogType,
    toggleCatalogModule,
    toggleCase,
    toggleAllCasesInModule,
    toggleAllCasesInGroup,
    countGroupCases,
    isGroupAllSelected,
    toggleAuxDevice,
    handleStartCustomTest,
    openCustomTest,
    closeCustomTest,
    getTestTypeLabel,
    getStatusColor,
    getStatusIcon,
    getDisplayStatus,
    getRoleBadge,
    getCaseResultColor,
    parseManualSteps,
    toggleModule,
    isModuleExpanded,
    getSelectedCaseName,
    selectCaseItem,
    toggleFollowCurrent,
    isSelectedCaseInConfig,
    getCaseItemClass,
    isCaseSelected,
    getCaseItemStyle,
  }
}
