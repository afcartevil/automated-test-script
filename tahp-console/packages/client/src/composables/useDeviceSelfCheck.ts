import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useDeviceSelfCheckLaunchStore } from '@/stores/tahp/device-self-check-launch'
import {
  fetchProjectNodes,
  fetchTestSchedule,
  syncProjectNodes,
  type NextNodeItem,
  type ScheduleItem,
} from '@/api/tahp/test-planning'
import {
  listDevices,
  refreshDevices,
  getDeviceDetail,
  setDeviceRole,
  startTest,
  pickFlashPath,
  startCustomTest,
  getCaseCatalogs,
  getCaseCatalogDetail,
  continueTest,
  endTest,
  updateCaseResult,
  getModuleConditions,
  submitManualDecision,
  getPendingManualDecision,
  retestCase,
  getSettings,
  updateSettings,
  fetchSelfCheckPipeline,
  fetchTPowerStatus,
  type DeviceRole,
  type DeviceInfo,
  type DeviceDetail,
  type ModuleCondition,
  type CaseResult,
  type CaseCatalog,
  type CaseCatalogGroup,
  type CaseCatalogDetailItem,
  type SelfCheckPipelineView,
  type TPowerStatus,
} from '@/api/tahp/device-self-check'
import {
  createFlashProgressState,
  parseFlashLogLine,
  flashPhaseLabel,
  type FlashProgressState,
} from '@/utils/flash-progress'
import {
  AUTO_RETEST_TOOLTIP,
  MODULE_ORDER,
  getTestTypeLabel,
  getStatusColor,
  getStatusIcon,
  getDisplayStatus,
  getRoleBadge,
  getCaseResultColor,
  parseManualSteps,
  type PipelineStage,
} from '@/components/tahp/self-check/self-check-utils'

export type SelfCheckTab = 'overview' | 'planning' | 'devices' | 'review' | 'gerrit'

export const SELF_CHECK_TABS = [
  { key: 'overview', label: '总览' },
  { key: 'planning', label: '项目规划' },
  { key: 'devices', label: '设备执行' },
  { key: 'gerrit', label: 'AI Review' },
  { key: 'review', label: '报告 Review' },
] as const

export function useDeviceSelfCheck() {
  const message = useMessage()

const devices = ref<DeviceInfo[]>([])
const selectedDeviceId = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedDevice = ref<DeviceDetail | null>(null)
const moduleConditions = ref<Record<string, ModuleCondition>>({})

// 测试类型选择
const selectedTestType = ref<'str4' | 'week' | 'monkey'>('week')

// 刷机相关选项（device_update，工具位于 self-check/flash_tool/）
const enableFlash = ref(false)
const flashPath = ref('')
const enableRootPkg = ref(false)
const rootPkgPath = ref('')
const flashStageVersion = ref('')
const flashLogs = ref<string[]>([])
const flashLogRef = ref<HTMLElement | null>(null)
const flashActive = ref(false)
const flashDone = ref<'success' | 'error' | null>(null)
const flashProgressState = ref<FlashProgressState>(createFlashProgressState())
const flashPathPicking = ref(false)
const rootPkgPathPicking = ref(false)
const FLASH_MARKET_OPTIONS = [
  { label: 'Base', value: '' },
  { label: 'Open', value: 'Open' },
  { label: 'Open-Payjoy', value: 'Open-Payjoy' },
  { label: 'RU', value: 'RU' },
  { label: 'Turkey', value: 'Turkey' },
  { label: 'India', value: 'India' },
]
watch(enableRootPkg, (enabled) => {
  if (!enabled) rootPkgPath.value = ''
})

function resetFlashProgress() {
  flashActive.value = false
  flashDone.value = null
  flashProgressState.value = createFlashProgressState()
}

function scrollFlashLogToBottom() {
  nextTick(() => {
    const el = flashLogRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function appendFlashLog(line: string) {
  flashLogs.value.push(line)
  flashActive.value = true
  parseFlashLogLine(flashProgressState.value, line)
  scrollFlashLogToBottom()
}

watch(flashLogs, scrollFlashLogToBottom)

const enableTcardUpdate = ref(false)
const tcardUpdatePath = ref('')

// 视图模式
const viewMode = ref<'list' | 'customTest'>('list')
const catalogPanelExpanded = ref(false)
const deviceDetailExpanded = ref(false)

// 自定义测试 / 概览用例目录
const caseCatalogGroups = ref<CaseCatalogGroup[]>([])
const selectedCatalogTestType = ref<string | null>(null)
const catalogDetailItems = ref<CaseCatalogDetailItem[]>([])
const selectedCatalogCaseKey = ref<string | null>(null)
const catalogDetailLoading = ref(false)
const catalogTypeSettings = ref({
  autoRetestEnabled: true,
  autoRetestCount: 1,
  monkeyDuration: '7d',
})
const catalogSettingsSaving = ref(false)
const expandedCatalogTypes = ref<Set<string>>(new Set())
const expandedCatalogModules = ref<Set<string>>(new Set())
const expandedCatalogDetailModules = ref<Set<string>>(new Set())
const selectedCases = ref<Set<string>>(new Set())
const customTestDutDeviceId = ref<string | null>(null)
const customTestAuxDeviceIds = ref<Set<string>>(new Set())
const customTestStarting = ref(false)
const gerritPreselectCount = ref(0)
const launchStore = useDeviceSelfCheckLaunchStore()

  const activeTab = ref<SelfCheckTab>('overview')
  const syncing = ref(false)
  const nextNodes = ref<NextNodeItem[]>([])
  const scheduleItems = ref<ScheduleItem[]>([])
  const pipelineView = ref<SelfCheckPipelineView | null>(null)
  const tpowerStatus = ref<TPowerStatus | null>(null)

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

  async function loadPlanningSummary() {
    try {
      const [nodesView, scheduleView] = await Promise.all([
        fetchProjectNodes(),
        fetchTestSchedule(),
      ])
      nextNodes.value = nodesView.nextNodes
      scheduleItems.value = scheduleView.items
    } catch {
      // ignore summary load errors
    }
  }

  async function handleSyncNodes() {
    syncing.value = true
    try {
      await syncProjectNodes()
      message.success('项目节点已更新')
      await loadPlanningSummary()
      await loadPipelineStatus()
      activeTab.value = 'planning'
    } catch (err) {
      message.error((err as Error).message || '同步项目节点失败')
    } finally {
      syncing.value = false
    }
  }

  function handleNewTask() {
    activeTab.value = 'devices'
    openCustomTest()
  }

  const stats = computed(() => ({
    pendingProjects: scheduleItems.value.filter(
      i => i.runtimeStatus !== 'completed' && i.displayLabel !== '已完成',
    ).length,
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
    const hasNodes = nextNodes.value.length > 0
    const hasRunning = stats.value.runningTests > 0
    const hasSchedule = scheduleItems.value.length > 0
    return [
      {
        key: 'sync',
        label: '项目节点同步',
        status: hasNodes ? 'done' : 'idle',
        hint: hasNodes ? `${nextNodes.value.length} 个项目` : undefined,
      },
      {
        key: 'flash',
        label: '版本拉取/烧录',
        status: hasRunning ? 'running' : hasNodes ? 'queued' : 'idle',
      },
      {
        key: 'test',
        label: '自动测试',
        status: hasRunning ? 'running' : hasSchedule ? 'queued' : 'idle',
      },
      {
        key: 'ai',
        label: 'AI 分析',
        status: hasRunning ? 'running' : 'idle',
      },
      {
        key: 'review',
        label: '人工 Review',
        status: stats.value.pendingManual > 0 ? 'attention' : 'idle',
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
    for (const caseKey of session.selectedCases) {
      const result = session.caseResults[caseKey]
      if (result?.status === '进行中') {
        selectedCase.value = caseKey
        return
      }
    }
    return
  }
  const mod = session.modules[session.currentModuleIndex]
  if (!mod) return
  const prog = session.moduleProgress[`${session.testType}/${mod}`]
  if (prog?.currentCaseIndex) {
    selectedCase.value = `${mod}/${prog.currentCaseIndex}`
  } else {
    selectedCase.value = `${mod}/1`
    expandedModules.value = new Set([...expandedModules.value, mod])
  }
}

async function selectDevice(deviceId: string) {
  try {
    selectedDeviceId.value = deviceId
    deviceDetailExpanded.value = true
    const detail = await getDeviceDetail(deviceId)
    selectedDevice.value = detail
    selectedCase.value = null
    followCurrent.value = true
    applyFollowCurrentCase(detail.session)
    // 如果正在测试中，开始轮询
    if (detail.session?.isRunning) {
      startPolling()
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

async function openCaseCatalog(testType: string) {
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
    expandedCatalogDetailModules.value = new Set(
      [...new Set(detail.map(item => `${testType}/${item.module}`))]
    )
    catalogTypeSettings.value = {
      autoRetestEnabled: testType === 'monkey'
        ? false
        : (settingsData.autoRetestEnabled?.[testType] ?? true),
      autoRetestCount: testType === 'monkey'
        ? 0
        : (settingsData.autoRetestCount?.[testType] ?? 1),
      monkeyDuration: settingsData.monkeyDuration || '7d',
    }
    if (detail.length > 0) {
      selectedCatalogCaseKey.value = detail[0].key
    }
  } catch (e: any) {
    error.value = e?.message || '加载用例详情失败'
  } finally {
    catalogDetailLoading.value = false
  }
}

function selectCatalogCase(caseKey: string) {
  selectedCatalogCaseKey.value = caseKey
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
      if (data.deviceId === selectedDeviceId.value && data.line) {
        appendFlashLog(data.line)
      }
    } catch {}
  })

  eventSource.value.addEventListener('flash_completed', async (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (data.deviceId !== selectedDeviceId.value) return
      flashActive.value = false
      if (data.success) {
        flashLogs.value = []
        resetFlashProgress()
        followCurrent.value = true
        const detail = await getDeviceDetail(selectedDeviceId.value!)
        selectedDevice.value = detail
        applyFollowCurrentCase(detail.session)
      } else {
        flashDone.value = 'error'
        parseFlashLogLine(
          flashProgressState.value,
          `[刷机] 刷机失败：${data.error || `返回码 ${data.returnCode ?? '?'}`}`,
        )
        if (data.error) appendFlashLog(`[刷机] ${data.error}`)
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
              selectedCase.value = `${mod}/${prog.currentCaseIndex}`
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
      } else {
        await loadDevices()
      }
      await loadPipelineStatus()
      await loadPlanningSummary()
    } catch {
      await loadDevices()
      await loadPipelineStatus()
      await loadPlanningSummary()
    }
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

async function handleSetRole(deviceId: string, role: DeviceRole) {
  try {
    await setDeviceRole(deviceId, role)
    await loadDevices()
    if (selectedDeviceId.value === deviceId) {
      await selectDevice(deviceId)
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error setting device role:', e)
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

async function handleBrowseRootPkgPath() {
  if (rootPkgPathPicking.value) return
  rootPkgPathPicking.value = true
  error.value = null
  try {
    const result = await pickFlashPath()
    if (result.path) {
      rootPkgPath.value = result.path
    } else if (result.error) {
      error.value = result.error
    }
  } catch (e: any) {
    error.value = e?.message || '选择 Root 包失败'
  } finally {
    rootPkgPathPicking.value = false
  }
}

async function handleStartTest(deviceId: string) {
  try {
    if (enableFlash.value && !flashPath.value.trim()) {
      error.value = '请先选择刷机包路径'
      return
    }
    if (enableFlash.value && enableRootPkg.value && !rootPkgPath.value.trim()) {
      error.value = '请先选择 Root 包路径'
      return
    }
    flashLogs.value = []
    resetFlashProgress()
    const flash = enableFlash.value
      ? {
          enabled: true,
          pkgPath: flashPath.value.trim(),
          rootPkgPath: enableRootPkg.value ? rootPkgPath.value.trim() : undefined,
          stageVersion: flashStageVersion.value || undefined,
        }
      : undefined
    if (flash) {
      flashActive.value = true
      flashProgressState.value = createFlashProgressState()
      appendFlashLog('[刷机] 已提交刷机任务，等待设备进入刷机流程...')
    }
    const result = await startTest(deviceId, selectedTestType.value, flash)
    if (result) {
      selectedDevice.value = result
      followCurrent.value = true
      startPolling()
    }
    await loadDevices()
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error starting test:', e)
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
  }
}

async function handleEndTest(deviceId: string) {
  try {
    stopPollingTimer()
    const result = await endTest(deviceId)
    patchDeviceInList(result.device)
    await loadDevices()
    if (result.device.role === '辅测机' && (result.device.status as string) === '待命') {
      selectedDeviceId.value = deviceId
      selectedDevice.value = result
    } else {
      selectedDeviceId.value = null
      selectedDevice.value = null
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error ending test:', e)
  }
}

// 修改用例结果
const showModifyDialog = ref(false)
const modifyCaseKey = ref<string | null>(null)
const modifyStatus = ref('通过')
const modifyMessage = ref('')

// 人工确认弹窗
const showManualDialog = ref(false)
const manualDecisionId = ref<string | null>(null)
const manualMessage = ref('')
const manualPassLabel = ref('通过')
const manualFailLabel = ref('失败')
const manualMode = ref<'decision' | 'ack'>('decision')
const manualSubmitting = ref(false)

function applyManualPrompt(data: {
  decisionId: string
  message?: string
  passLabel?: string
  failLabel?: string
  mode?: 'decision' | 'ack'
}) {
  manualDecisionId.value = data.decisionId
  manualMessage.value = data.message || '需人工确认'
  manualPassLabel.value = data.passLabel || '通过'
  manualFailLabel.value = data.failLabel || '失败'
  manualMode.value = data.mode === 'ack' ? 'ack' : 'decision'
  showManualDialog.value = true
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
  if (!manualDecisionId.value || manualSubmitting.value) return
  manualSubmitting.value = true
  try {
    await submitManualDecision(manualDecisionId.value, decision)
    showManualDialog.value = false
    manualDecisionId.value = null
    manualMessage.value = ''
    manualMode.value = 'decision'
    manualPassLabel.value = '通过'
    manualFailLabel.value = '失败'
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
    expandedCatalogModules.value = new Set(
      caseCatalogGroups.value.flatMap(g => g.modules.map(m => m.key))
    )
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
  if (selectedCases.value.has(caseKey)) {
    selectedCases.value.delete(caseKey)
  } else {
    selectedCases.value.add(caseKey)
  }
  selectedCases.value = new Set(selectedCases.value)
}

function toggleAllCasesInModule(catalog: CaseCatalog) {
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

function toggleAuxDevice(deviceId: string) {
  if (customTestAuxDeviceIds.value.has(deviceId)) {
    customTestAuxDeviceIds.value.delete(deviceId)
  } else {
    customTestAuxDeviceIds.value.add(deviceId)
  }
  customTestAuxDeviceIds.value = new Set(customTestAuxDeviceIds.value)
}

async function handleStartCustomTest() {
  if (!customTestDutDeviceId.value || selectedCases.value.size === 0) return
  customTestStarting.value = true
  error.value = null
  try {
    const result = await startCustomTest(
      customTestDutDeviceId.value,
      Array.from(selectedCases.value),
      Array.from(customTestAuxDeviceIds.value)
    )
    viewMode.value = 'list'
    selectedDeviceId.value = customTestDutDeviceId.value
    selectedDevice.value = result
    followCurrent.value = true
    startPolling()
    await loadDevices()
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
      cases: { caseIndex: number; caseName: string; testType: string; module: string }[]
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
      })
    }

    return Object.entries(groups)
      .sort((a, b) => {
        const orderA = MODULE_ORDER[a[1].cases[0]?.module] ?? 50
        const orderB = MODULE_ORDER[b[1].cases[0]?.module] ?? 50
        return orderA - orderB
      })
      .map(([moduleKey, group]) => [group.label, [{
        testType: group.cases[0]?.testType || 'str4',
        module: group.cases[0]?.module || '',
        moduleLabel: group.label,
        moduleKey,
        cases: group.cases.map(c => ({
          caseIndex: c.caseIndex,
          caseName: c.caseName,
          mode: '',
          canReuse: false,
        })),
      }]] as [string, (ModuleCondition & { moduleKey: string })[]])
  }

  const modules: Record<string, ModuleCondition[]> = {}
  
  for (const [, config] of Object.entries(moduleConditions.value)) {
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

const isFlashing = computed(() => selectedDevice.value?.device.status === '刷机中')

const flashProgress = computed(() => flashProgressState.value.progress)

const flashPhase = computed(() => flashPhaseLabel(flashProgressState.value))

const showFlashPanel = computed(() => {
  if (!selectedDeviceId.value) return false
  if (isFlashing.value || flashActive.value) return true
  return flashDone.value === 'error' && flashLogs.value.length > 0
})

const isFlashIndeterminate = computed(() => {
  return (flashActive.value || isFlashing.value) && flashProgress.value < 8
})

const flashStatusText = computed(() => {
  if (isFlashing.value || flashActive.value) return '刷机中'
  if (flashDone.value === 'success') return '刷机完成'
  if (flashDone.value === 'error') return '刷机失败'
  return '待刷机'
})

const flashStatusClass = computed(() => {
  if (isFlashing.value || flashActive.value) return 'is-running'
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
  return 'AI 自检'
})

const isTestComplete = computed(() => {
  const status = selectedDevice.value?.device.status || ''
  return status.includes('完成')
})

const canEndTest = computed(() => {
  const device = selectedDevice.value?.device
  if (!device || device.role === '辅测机') return false
  if ((device.status as string) === '待命') return false
  return !isIdle.value
})

const needsContinue = computed(() => {
  const status = selectedDevice.value?.device.status || ''
  return status.includes('不满足前置条件')
})

// 当前选中的用例结果
const selectedCaseResult = computed((): CaseResult | undefined => {
  if (!selectedCase.value || !selectedDevice.value?.session?.caseResults) return undefined
  const session = selectedDevice.value.session
  const isCustom = selectedDevice.value.device.testType === 'custom'
  let key: string
  if (isCustom) {
    key = selectedCase.value
  } else {
    const parts = selectedCase.value.split('/')
    const index = parseInt(parts.pop() || '1')
    const module = parts.join('/')
    const testType = selectedDevice.value.device.testType || 'str4'
    key = `${testType}/${module}/${index}`
  }
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

onMounted(async () => {
  connectEventStream()
  await loadDevices()
  await Promise.all([loadPlanningSummary(), loadPipelineStatus(), loadTPowerStatus()])
  loadCaseCatalogs({ silent: true })
  try {
    moduleConditions.value = await getModuleConditions()
    // 默认展开所有模块
    expandedModules.value = new Set(Object.keys(moduleConditions.value).map(k => moduleConditions.value[k].module))
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
  const caseIndex = parseInt(selectedCase.value?.split('/').pop() || '1')
  const caseItem = config.cases.find(c => c.caseIndex === caseIndex)
  return caseItem?.caseName || `用例${caseIndex}`
}

function selectCaseItem(module: string, caseIndex: number, testType?: string) {
  if (testType || selectedDevice.value?.device.testType === 'custom') {
    const tt = testType || selectedCase.value?.split('/')[0] || 'str4'
    selectedCase.value = `${tt}/${module}/${caseIndex}`
  } else {
    selectedCase.value = `${module}/${caseIndex}`
  }
  followCurrent.value = false
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
            selectedCase.value = m + '/' + p.currentCaseIndex
          }
        }
      }
    }
  }
}

function isSelectedCaseInConfig(config: ModuleCondition): boolean {
  if (!selectedCase.value) return false
  if (selectedDevice.value?.device.testType === 'custom') {
    const parts = selectedCase.value.split('/')
    const caseIndex = parts.pop()
    const module = parts.pop()
    const testType = parts.join('/')
    return testType === config.testType && module === config.module && String(config.cases.find(c => c.caseIndex === parseInt(caseIndex || '0'))?.caseIndex) === caseIndex
  }
  return selectedCase.value.startsWith(config.module)
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
  if (selectedDevice.value?.device.testType === 'custom') {
    return selectedCase.value === `${config.testType}/${config.module}/${caseIndex}`
  }
  return selectedCase.value === `${config.module}/${caseIndex}`
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
    syncing,
    nextNodes,
    scheduleItems,
    stats,
    pipelineStages,
    tpowerStatus,
    loadTPowerStatus,
    handleSyncNodes,
    handleNewTask,
    AUTO_RETEST_TOOLTIP,
    devices,
    selectedDeviceId,
    loading,
    error,
    selectedDevice,
    moduleConditions,
    selectedTestType,
    enableFlash,
    flashPath,
    enableRootPkg,
    rootPkgPath,
    flashStageVersion,
    flashLogs,
    flashLogRef,
    flashPathPicking,
    rootPkgPathPicking,
    FLASH_MARKET_OPTIONS,
    flashProgress,
    flashPhase,
    showFlashPanel,
    isFlashIndeterminate,
    flashStatusText,
    flashStatusClass,
    handleBrowseFlashPath,
    handleBrowseRootPkgPath,
    enableTcardUpdate,
    tcardUpdatePath,
    viewMode,
    catalogPanelExpanded,
    deviceDetailExpanded,
    caseCatalogGroups,
    selectedCatalogTestType,
    catalogDetailItems,
    selectedCatalogCaseKey,
    catalogDetailLoading,
    catalogTypeSettings,
    catalogSettingsSaving,
    expandedCatalogTypes,
    expandedCatalogModules,
    expandedCatalogDetailModules,
    selectedCases,
    customTestDutDeviceId,
    customTestAuxDeviceIds,
    customTestStarting,
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
    manualMessage,
    manualPassLabel,
    manualFailLabel,
    manualMode,
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
    pageTitle,
    isTestComplete,
    canEndTest,
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
    saveCatalogTypeSettings,
    backToOverview,
    goBack,
    handleSetRole,
    handleStartTest,
    handleContinueTest,
    handleEndTest,
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
