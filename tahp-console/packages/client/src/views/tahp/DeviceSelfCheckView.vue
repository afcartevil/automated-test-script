<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import GerritReviewWorkspace from '@/components/tahp/GerritReviewWorkspace.vue'
import TestPlanningWorkspace from '@/components/tahp/TestPlanningWorkspace.vue'
import { useDeviceSelfCheckLaunchStore } from '@/stores/tahp/device-self-check-launch'
import {
  listDevices,
  refreshDevices,
  getDeviceDetail,
  setDeviceRole,
  startTest,
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
  type DeviceInfo,
  type DeviceRole,
  type DeviceDetail,
  type ModuleCondition,
  type CaseResult,
  type CaseCatalog,
  type CaseCatalogGroup,
  type CaseCatalogDetailItem
} from '@/api/tahp/device-self-check'

const SELF_CHECK_SUBTITLE =
  '周版本、STR4转测版本用例自动化；GMS、稳定性测试AI自规划；gerrit提交code review和测试建议'
const devices = ref<DeviceInfo[]>([])
const selectedDeviceId = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedDevice = ref<DeviceDetail | null>(null)
const moduleConditions = ref<Record<string, ModuleCondition>>({})

// 测试类型选择
const selectedTestType = ref<'str4' | 'week'>('week')

// 刷机相关选项（功能暂不实现）
const enableFlash = ref(false)
const flashPath = ref('')
const enableTcardUpdate = ref(false)
const tcardUpdatePath = ref('')

// 视图模式
const viewMode = ref<'overview' | 'detail' | 'customTest' | 'caseCatalog'>('overview')

// 自定义测试 / 概览用例目录
const caseCatalogGroups = ref<CaseCatalogGroup[]>([])
const selectedCatalogTestType = ref<string | null>(null)
const catalogDetailItems = ref<CaseCatalogDetailItem[]>([])
const selectedCatalogCaseKey = ref<string | null>(null)
const catalogDetailLoading = ref(false)
const catalogTypeSettings = ref({ autoRetestEnabled: true, autoRetestCount: 1 })
const catalogSettingsSaving = ref(false)
const AUTO_RETEST_TOOLTIP = '测试结束后自动复测无人工参与的失败用例'
const expandedCatalogTypes = ref<Set<string>>(new Set())
const expandedCatalogModules = ref<Set<string>>(new Set())
const expandedCatalogDetailModules = ref<Set<string>>(new Set())
const selectedCases = ref<Set<string>>(new Set())
const customTestDutDeviceId = ref<string | null>(null)
const customTestAuxDeviceIds = ref<Set<string>>(new Set())
const customTestStarting = ref(false)
const gerritPreselectCount = ref(0)
const launchStore = useDeviceSelfCheckLaunchStore()

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
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error refreshing devices:', e)
    error.value = e?.message || '刷新设备列表失败'
  } finally {
    loading.value = false
  }
}

async function selectDevice(deviceId: string) {
  try {
    selectedDeviceId.value = deviceId
    const detail = await getDeviceDetail(deviceId)
    selectedDevice.value = detail
    selectedCase.value = null
    followCurrent.value = true
    // 如果正在测试中，开始轮询
    if (detail.session?.isRunning) {
      startPolling()
    }
  } catch (e: any) {
    console.error('[DeviceSelfCheck] Error getting device detail:', e)
    error.value = e?.message || '获取设备详情失败'
  }
}

function backFromCaseCatalog() {
  viewMode.value = 'overview'
  selectedCatalogTestType.value = null
  catalogDetailItems.value = []
  selectedCatalogCaseKey.value = null
  expandedCatalogDetailModules.value = new Set()
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
  viewMode.value = 'caseCatalog'
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
      autoRetestEnabled: settingsData.autoRetestEnabled?.[testType] ?? true,
      autoRetestCount: settingsData.autoRetestCount?.[testType] ?? 1,
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
    })
  } catch (e) {
    console.error('[DeviceSelfCheck] Error saving catalog settings:', e)
  } finally {
    catalogSettingsSaving.value = false
  }
}

function parseManualSteps(steps: string): string[] {
  if (!steps.trim()) return []
  return steps.split('\n').map(line => line.trim()).filter(Boolean)
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
  viewMode.value = 'overview'
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
    } catch {
      await loadDevices()
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

function stopPolling() {
  disconnectEventStream()
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

async function handleStartTest(deviceId: string) {
  try {
    const result = await startTest(deviceId, selectedTestType.value)
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
    if (result.device.role === '辅测机' && result.device.status === '待命') {
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

function getTestTypeLabel(testType?: string): string {
  if (testType === 'str4') return '转测摸底测试'
  if (testType === 'week') return '周版本测试'
  if (testType === 'custom') return '自定义测试'
  return '未分配'
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
    viewMode.value = 'overview'
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
  viewMode.value = 'customTest'
  customTestDutDeviceId.value = null
  customTestAuxDeviceIds.value = new Set()
  loadCaseCatalogs()
}

function applyPendingGerritLaunch() {
  const keys = launchStore.consumePendingCustomCases()
  if (!keys.length) return
  selectedCases.value = new Set(keys)
  gerritPreselectCount.value = keys.length
  openCustomTest()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

watch(
  () => launchStore.pendingCustomCaseKeys.length,
  (len) => {
    if (len > 0) applyPendingGerritLaunch()
  },
)

function getStatusColor(status: string) {
  if (status.includes('通过') || status === '空闲') return 'var(--success)'
  if (status.includes('失败') || status.includes('错误')) return 'var(--error)'
  if (status.includes('测试中') || status.includes('等待') || status.includes('待命')) return 'var(--accent)'
  if (status.includes('不满足前置条件')) return 'var(--warning, #f59e0b)'
  return 'var(--muted)'
}

function getStatusIcon(status: string) {
  if (status.includes('通过')) return '✓'
  if (status.includes('失败')) return '✗'
  if (status.includes('测试中')) return '●'
  if (status.includes('待命')) return '🛡'
  if (status.includes('等待')) return '⏳'
  if (status.includes('错误')) return '⚠'
  if (status.includes('不满足前置条件')) return '!'
  return '○'
}

function getModuleLabel(module: string): string {
  const labels: Record<string, string> = {
    'tdd': '通信框架',
    'driver': '驱动',
    'driver_component': '驱动-器件',
    'driver_hardware': '驱动-硬测',
  }
  return labels[module] || module
}

function getDisplayStatus(device: DeviceInfo): string {
  if (device.status === '等待测试开始' && device.currentModule) {
    return `等待${getModuleLabel(device.currentModule)}开始测试`
  }
  if (device.status === '不满足前置条件' && device.currentModule) {
    return `${getModuleLabel(device.currentModule)}不满足前置条件`
  }
  return device.status
}

function getRoleBadge(role: string) {
  const colors: Record<string, string> = {
    '未分配': 'background: var(--bg)',
    '测试机': 'background: var(--accent-soft); color: var(--accent)',
    '辅测机': 'background: rgba(16, 185, 129, 0.1); color: #10b981',
  }
  return colors[role] || ''
}

function getCaseResultColor(status: string) {
  const colors: Record<string, string> = {
    '通过': 'var(--success)',
    '失败': 'var(--error)',
    '部分通过': '#f59e0b',
    '待确认': '#f59e0b',
    'NA': 'var(--muted)',
    '跳过': 'var(--muted)',
    '未开始': 'var(--muted)',
    '进行中': 'var(--accent)',
  }
  return colors[status] || 'var(--muted)'
}

// 模块显示顺序：通信框架放最后
const MODULE_ORDER: Record<string, number> = {
  'driver': 0,
  'driver_component': 0,
  'driver_hardware': 1,
  'tdd': 99,
}

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
  
  for (const [key, config] of Object.entries(moduleConditions.value)) {
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

const pageTitle = computed(() => {
  if (selectedDeviceId.value) {
    return selectedDevice.value?.device.deviceName || '设备详情'
  }
  if (viewMode.value === 'customTest') return '自定义测试'
  if (viewMode.value === 'caseCatalog') {
    return selectedCatalogGroup.value?.label || '用例详情'
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
  if (device.status === '待命') return false
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
</script>

<template>
  <div class="page" :class="{ 'page-wide': !selectedDeviceId }">
    <EaPageHead
      :title="pageTitle"
      :subtitle="selectedDeviceId ? '多设备并行自动化测试，支持结果复用' : SELF_CHECK_SUBTITLE"
    >
      <template #actions>
        <template v-if="selectedDeviceId">
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="goBack">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            返回概览
          </button>
          <button v-if="isTestComplete && selectedDevice?.device.role !== '辅测机'" type="button" class="ea-btn-primary ea-btn-sm">
            打开结果
          </button>
          <button v-if="canEndTest" type="button" class="ea-btn-ghost ea-btn-sm" @click="handleEndTest(selectedDeviceId!)">
            结束测试
          </button>
          <button v-if="selectedDevice?.device.status === '待命'" type="button" class="ea-btn-ghost ea-btn-sm" @click="handleEndTest(selectedDeviceId!)">
            停止待命
          </button>
        </template>
        <template v-else-if="viewMode === 'customTest'">
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="viewMode = 'overview'">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            返回概览
          </button>
        </template>
        <template v-else-if="viewMode === 'caseCatalog'">
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="backFromCaseCatalog">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            返回概览
          </button>
        </template>
      </template>
    </EaPageHead>

    <!-- 自定义测试视图 -->
    <template v-if="viewMode === 'customTest'">
      <div v-if="error" style="color: var(--error); margin: 12px 0;">{{ error }}</div>
      <p v-if="gerritPreselectCount > 0" class="gerrit-preselect-hint ea-muted">
        已根据 Gerrit Code Review 预选 {{ gerritPreselectCount }} 个测试用例，请选择测试机后执行。
      </p>

      <div class="custom-test-layout">
        <div class="custom-test-left">
          <EaCard>
            <div class="section-title">
              用例列表
              <span class="ea-muted" style="font-size: 12px; margin-left: 8px;">
                已选 {{ selectedCases.size }} 个
              </span>
            </div>
            <div class="catalog-list">
              <div v-for="group in caseCatalogGroups" :key="group.testType" class="catalog-type-group">
                <div class="catalog-type-header" @click="toggleCatalogType(group.testType)">
                  <span class="catalog-toggle">{{ expandedCatalogTypes.has(group.testType) ? '▼' : '▶' }}</span>
                  <span class="catalog-type-label">{{ group.label }}</span>
                  <span class="catalog-meta">{{ group.testType }} ({{ countGroupCases(group) }}个)</span>
                  <button
                    type="button"
                    class="ea-btn-ghost ea-btn-sm"
                    @click.stop="toggleAllCasesInGroup(group)"
                  >
                    {{ isGroupAllSelected(group) ? '取消全选' : '全选' }}
                  </button>
                </div>
                <div v-if="expandedCatalogTypes.has(group.testType)" class="catalog-type-body">
                  <div v-for="catalog in group.modules" :key="catalog.key" class="catalog-group">
                    <div class="catalog-header" @click="toggleCatalogModule(catalog.key)">
                      <span class="catalog-toggle catalog-toggle-nested">{{ expandedCatalogModules.has(catalog.key) ? '▼' : '▶' }}</span>
                      <span class="catalog-label">{{ catalog.moduleLabel }}</span>
                      <span class="catalog-meta">{{ catalog.module }} ({{ catalog.cases.length }}个)</span>
                      <button
                        type="button"
                        class="ea-btn-ghost ea-btn-sm"
                        @click.stop="toggleAllCasesInModule(catalog)"
                      >
                        {{ catalog.cases.every(c => selectedCases.has(catalog.key + '/' + c.caseIndex)) ? '取消全选' : '全选' }}
                      </button>
                    </div>
                    <div v-if="expandedCatalogModules.has(catalog.key)" class="catalog-cases">
                      <label
                        v-for="c in catalog.cases"
                        :key="c.caseIndex"
                        class="case-checkbox"
                      >
                        <input
                          type="checkbox"
                          :checked="selectedCases.has(catalog.key + '/' + c.caseIndex)"
                          @change="toggleCase(catalog.key + '/' + c.caseIndex)"
                        />
                        <span class="case-name">{{ c.caseIndex }}. {{ c.caseName }}</span>
                        <span v-if="c.canReuse" class="case-tag">可复用</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </EaCard>
        </div>

        <div class="custom-test-right">
          <EaCard>
            <div class="section-title">测试机（单选）</div>
            <div class="device-select-list">
              <div v-if="availableCustomDut.length === 0" class="ea-muted">无可用设备</div>
              <label
                v-for="d in availableCustomDut"
                :key="d.deviceId"
                class="device-radio"
                :class="{ selected: customTestDutDeviceId === d.deviceId }"
              >
                <input
                  type="radio"
                  name="customDut"
                  :value="d.deviceId"
                  v-model="customTestDutDeviceId"
                />
                <span class="device-name">{{ d.deviceName }}</span>
                <span class="device-id">{{ d.deviceId }}</span>
                <span class="device-role">{{ d.role }}</span>
              </label>
            </div>
          </EaCard>

          <EaCard>
            <div class="section-title">
              辅测机（多选）
              <span class="ea-muted" style="font-size: 12px; margin-left: 8px;">
                已选 {{ customTestAuxDeviceIds.size }} 个
              </span>
            </div>
            <div class="device-select-list">
              <div v-if="availableCustomAux.length === 0" class="ea-muted">无可用设备</div>
              <label
                v-for="d in availableCustomAux"
                :key="d.deviceId"
                class="device-checkbox"
                :class="{ selected: customTestAuxDeviceIds.has(d.deviceId) }"
              >
                <input
                  type="checkbox"
                  :checked="customTestAuxDeviceIds.has(d.deviceId)"
                  @change="toggleAuxDevice(d.deviceId)"
                />
                <span class="device-name">{{ d.deviceName }}</span>
                <span class="device-id">{{ d.deviceId }}</span>
                <span class="device-role">{{ d.role }}</span>
              </label>
            </div>
          </EaCard>

          <div style="text-align: center; margin-top: 16px;">
            <button
              type="button"
              class="ea-btn-primary ea-btn-lg"
              :disabled="!customTestDutDeviceId || selectedCases.size === 0 || customTestStarting"
              @click="handleStartCustomTest"
            >
              {{ customTestStarting ? '启动中...' : `开始测试（${selectedCases.size} 个用例）` }}
            </button>
            <div v-if="!customTestDutDeviceId" class="ea-muted" style="margin-top: 8px;">
              请选择测试机
            </div>
            <div v-else-if="selectedCases.size === 0" class="ea-muted" style="margin-top: 8px;">
              请勾选至少一个用例
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 用例大类详情视图 -->
    <template v-if="viewMode === 'caseCatalog'">
      <div v-if="catalogDetailLoading" class="ea-muted" style="padding: 40px; text-align: center;">
        加载中...
      </div>
      <div v-else-if="error" style="padding: 40px; text-align: center;">
        <div style="color: var(--error); margin-bottom: 16px;">{{ error }}</div>
        <button type="button" class="ea-btn-primary" @click="openCaseCatalog(selectedCatalogTestType!)">
          重试
        </button>
      </div>
      <div v-else class="detail-container">
        <EaCard class="sidebar-card">
          <div class="section-title">用例列表</div>
          <div class="case-list">
            <div
              v-for="mod in catalogDetailByModule"
              :key="mod.module"
              class="module-group"
            >
              <div
                class="module-name"
                @click="toggleCatalogDetailModule(mod.module)"
              >
                <span class="module-arrow" :class="{ open: isCatalogDetailModuleExpanded(mod.module) }">▶</span>
                {{ mod.moduleLabel }}
                <span class="module-count">{{ mod.cases.length }}</span>
              </div>
              <div class="module-cases" v-show="isCatalogDetailModuleExpanded(mod.module)">
                <div
                  v-for="item in mod.cases"
                  :key="item.key"
                  class="case-item"
                  :class="{ selected: selectedCatalogCaseKey === item.key }"
                  @click="selectCatalogCase(item.key)"
                >
                  {{ item.caseName }}
                </div>
              </div>
            </div>
          </div>
        </EaCard>

        <div class="detail-main">
          <EaCard style="margin-bottom: 16px;">
            <div class="detail-card-content">
              <div class="detail-section">
                <div class="section-title">用例设置</div>
                <div class="catalog-auto-retest-row">
                  <label
                    class="checkbox-label"
                    :title="AUTO_RETEST_TOOLTIP"
                  >
                    <input
                      type="checkbox"
                      v-model="catalogTypeSettings.autoRetestEnabled"
                      :disabled="catalogSettingsSaving"
                      @change="saveCatalogTypeSettings"
                    />
                    <span>自动复测</span>
                  </label>
                  <input
                    type="number"
                    class="catalog-setting-input"
                    min="0"
                    max="10"
                    v-model.number="catalogTypeSettings.autoRetestCount"
                    :disabled="!catalogTypeSettings.autoRetestEnabled || catalogSettingsSaving"
                    @change="saveCatalogTypeSettings"
                  />
                  <span>次</span>
                </div>
              </div>
            </div>
          </EaCard>

          <EaCard>
            <div class="case-detail-header">
              <span class="section-title">用例详情</span>
            </div>
            <div v-if="selectedCatalogItem" class="case-detail-content">
              <div class="case-info">
                <div class="detail-item">
                  <span class="detail-label">用例模块</span>
                  <span class="detail-value">{{ selectedCatalogItem.moduleLabel }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">用例名称</span>
                  <span class="detail-value">{{ selectedCatalogItem.caseName }}</span>
                </div>
                <div v-if="selectedCatalogItem.preconditions" class="detail-item">
                  <span class="detail-label">前置条件</span>
                  <span class="detail-value pre-wrap">{{ selectedCatalogItem.preconditions }}</span>
                </div>
                <div v-if="selectedCatalogItem.expectedResult" class="detail-item">
                  <span class="detail-label">期望结果</span>
                  <span class="detail-value pre-wrap">{{ selectedCatalogItem.expectedResult }}</span>
                </div>
              </div>
              <div v-if="selectedCatalogItem.manualSteps" class="case-steps">
                <div class="section-title">测试步骤</div>
                <div
                  v-for="(step, idx) in parseManualSteps(selectedCatalogItem.manualSteps)"
                  :key="idx"
                  class="step-item"
                >
                  {{ step }}
                </div>
              </div>
              <div
                v-if="!selectedCatalogItem.manualSteps && !selectedCatalogItem.preconditions && !selectedCatalogItem.expectedResult"
                class="ea-muted"
              >
                暂无手动测试步骤
              </div>
            </div>
            <div v-else class="case-detail-empty">
              <span class="ea-muted">请从左侧选择用例查看详情</span>
            </div>
          </EaCard>
        </div>
      </div>
    </template>

    <!-- 设备列表视图 -->
    <template v-if="!selectedDeviceId && viewMode !== 'customTest' && viewMode !== 'caseCatalog'">
      <div v-if="loading" class="ea-muted" style="padding: 40px; text-align: center;">
        加载中...
      </div>

      <div v-else-if="error" style="padding: 40px; text-align: center;">
        <div style="color: var(--error); margin-bottom: 16px;">
          {{ error }}
        </div>
        <button class="ea-btn-primary" @click="loadDevices">
          重试
        </button>
      </div>

      <template v-else>
        <h3 class="section-heading">多设备并行自动化测试</h3>
        <p class="section-desc ea-muted">支持结果复用，连接 Android 设备后刷新列表</p>

        <EaCard v-if="caseCatalogGroups.length" class="overview-catalog-section">
          <div class="section-title">用例大类</div>
          <div class="ea-domain-bar overview-catalog-bar">
            <button
              v-for="group in caseCatalogGroups"
              :key="group.testType"
              type="button"
              class="ea-domain-chip"
              @click="openCaseCatalog(group.testType)"
            >
              {{ group.label }}
            </button>
          </div>
        </EaCard>

        <EaCard class="device-list-section" :class="{ 'device-list-section-spaced': caseCatalogGroups.length }">
          <div class="device-list-header">
            <div class="section-title device-list-title">设备列表</div>
            <div class="device-list-actions">
              <button
                type="button"
                class="ea-btn-primary ea-btn-sm"
                @click="openCustomTest"
              >
                自定义测试
              </button>
              <button
                type="button"
                class="ea-btn-primary ea-btn-sm"
                :disabled="loading"
                @click="doRefreshDevices"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="23 4 23 10 17 10"/>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                </svg>
                刷新设备
              </button>
            </div>
          </div>

          <div v-if="devices.length === 0" class="ea-muted device-list-empty">
            暂无连接设备，请连接 Android 设备后刷新
          </div>

          <div v-else class="device-grid">
            <EaCard
              v-for="device in devices"
              :key="device.deviceId"
              class="device-card"
              @click="(device.role !== '辅测机' || device.status === '待命' || device.status === '空闲') ? selectDevice(device.deviceId) : null"
            >
              <div class="device-header">
                <div class="device-status-icon" :style="{ color: getStatusColor(device.status) }">
                  {{ getStatusIcon(device.status) }}
                </div>
                <div class="device-info">
                  <h4>{{ device.deviceName }}</h4>
                  <span class="device-id">{{ device.deviceId }}</span>
                </div>
                <span class="role-badge" :style="getRoleBadge(device.status === '空闲' ? '未分配' : device.role)">
                  {{ device.status === '空闲' ? '未分配' : device.role }}
                </span>
              </div>
              <div class="device-details">
                <div class="detail-row">
                  <span class="detail-label">测试状态</span>
                  <span class="detail-value" :style="{ color: getStatusColor(device.status) }">
                    {{ getDisplayStatus(device) }}
                  </span>
                </div>
                <div class="detail-row" v-if="device.testType">
                  <span class="detail-label">所属用例</span>
                  <span class="detail-value">{{ getTestTypeLabel(device.testType) }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">插卡情况</span>
                  <span class="detail-value">
                    插入{{ device.simCards.filter(s => s.present).length }}张SIM卡
                  </span>
                </div>
                <div class="detail-row" v-if="device.testStartTime && device.role !== '辅测机'">
                  <span class="detail-label">测试开始时间</span>
                  <span class="detail-value">{{ new Date(device.testStartTime).toLocaleString('zh-CN') }}</span>
                </div>
                <div class="detail-row" v-if="device.testDuration">
                  <span class="detail-label">测试用时</span>
                  <span class="detail-value">{{ Math.round(device.testDuration / 60) }} 分钟</span>
                </div>
              </div>
              <div class="device-actions" v-if="device.role !== '辅测机' && device.status.includes('完成')">
                <button type="button" class="ea-btn-ghost ea-btn-sm" @click.stop>
                  打开结果
                </button>
              </div>
            </EaCard>
          </div>
        </EaCard>
      </template>

      <GerritReviewWorkspace />
      <TestPlanningWorkspace />
    </template>

    <!-- 设备详情视图 -->
    <template v-else-if="selectedDevice">
      <div class="detail-container">
        <!-- 左侧用例列表 -->
        <EaCard class="sidebar-card">
          <div class="section-title">用例列表</div>
          <div class="case-list">
            <template v-for="([label, configs]) in getCaseGroups" :key="label">
              <template v-for="config in configs" :key="config.module">
                <div class="module-group">
                  <div
                    class="module-name"
                    @click="toggleModule(`${config.module}`)"
                  >
                    <span class="module-arrow" :class="{ open: isModuleExpanded(config.module) }">▶</span>
                    {{ config.moduleLabel }}
                    <span class="module-count">{{ config.cases.length }}</span>
                  </div>
                  <div class="module-cases" v-show="isModuleExpanded(config.module)">
                    <template v-if="isIdle">
                      <div
                        v-for="caseItem in config.cases"
                        :key="caseItem.caseIndex"
                        class="case-item"
                        :class="{ selected: isCaseSelected(config, caseItem.caseIndex) }"
                        @click="selectCaseItem(config.module, caseItem.caseIndex, config.testType)"
                      >
                        {{ caseItem.caseName }}
                      </div>
                    </template>
                    <template v-else>
                      <div
                        v-for="caseItem in config.cases"
                        :key="caseItem.caseIndex"
                        class="case-item"
                        :class="{
                          selected: isCaseSelected(config, caseItem.caseIndex),
                          [getCaseItemClass(config, caseItem.caseIndex)]: true
                        }"
                        :style="getCaseItemStyle(config, caseItem.caseIndex)"
                        @click="selectCaseItem(config.module, caseItem.caseIndex, config.testType)"
                      >
                        {{ caseItem.caseName }}
                      </div>
                    </template>
                  </div>
                </div>
              </template>
            </template>
          </div>
        </EaCard>

        <!-- 右侧区域 -->
        <div class="detail-main">
          <!-- 设备信息卡片 -->
          <EaCard style="margin-bottom: 16px;">
            <div class="detail-card-content">
              <div class="detail-section">
                <div class="section-title">设备信息</div>
                <div class="detail-grid">
                  <div class="detail-item" v-if="!isIdle">
                    <span class="detail-label">设备角色</span>
                    <span class="detail-value">{{ selectedDevice.device.role }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">所属用例</span>
                    <span class="detail-value">{{ getTestTypeLabel(selectedDevice.device.testType) }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">插卡情况</span>
                    <span class="detail-value">
                      插入{{ selectedDevice.device.simCards.filter(s => s.present).length }}张SIM卡
                    </span>
                  </div>
                  <div class="detail-item" v-if="!isIdle">
                    <span class="detail-label">设备测试情况</span>
                    <span class="detail-value" :style="{ color: getStatusColor(selectedDevice.device.status) }">
                      {{ getDisplayStatus(selectedDevice.device) }}
                    </span>
                  </div>
                  <div class="detail-item" v-if="!isIdle && selectedDevice.device.testStartTime && selectedDevice.device.role !== '辅测机'">
                    <span class="detail-label">测试开始时间</span>
                    <span class="detail-value">{{ new Date(selectedDevice.device.testStartTime).toLocaleString('zh-CN') }}</span>
                  </div>
                  <div class="detail-item" v-if="!isIdle && selectedDevice.device.testDuration">
                    <span class="detail-label">测试用时</span>
                    <span class="detail-value">{{ Math.round(selectedDevice.device.testDuration / 60) }} 分钟</span>
                  </div>
                </div>
              </div>

              <!-- 空闲时的操作（自定义测试不显示常规开始测试） -->
              <div v-if="isIdle && selectedDevice.device.testType !== 'custom'" class="actions-section">
                <div class="section-title">
                  {{ selectedDevice.device.role === '辅测机' ? '注册为辅测机' : '开始测试' }}
                </div>

                <!-- 设备角色选择 -->
                <div class="form-group">
                  <span class="form-label">设备角色</span>
                  <div class="role-selector">
                    <button
                      v-for="role in ['测试机', '辅测机']"
                      :key="role"
                      type="button"
                      class="role-btn"
                      :class="{ active: selectedDevice.device.role === role }"
                      @click.stop="handleSetRole(selectedDevice.device.deviceId, role as DeviceRole)"
                    >
                      {{ role }}
                    </button>
                  </div>
                </div>

                <!-- 用例选择 -->
                <div class="form-group">
                  <span class="form-label">用例选择</span>
                  <div class="test-type-selector">
                    <button
                      type="button"
                      class="test-type-btn"
                      :class="{ active: selectedTestType === 'str4' }"
                      @click.stop="selectedTestType = 'str4'"
                    >
                      <strong>转测摸底测试</strong>
                    </button>
                    <button
                      type="button"
                      class="test-type-btn"
                      :class="{ active: selectedTestType === 'week' }"
                      @click.stop="selectedTestType = 'week'"
                    >
                      <strong>周版本测试</strong>
                    </button>
                  </div>
                </div>

                <!-- 刷机选项（功能暂不实现） -->
                <div class="form-group form-row">
                  <label class="checkbox-label">
                    <input type="checkbox" v-model="enableFlash" />
                    <span>刷机</span>
                  </label>
                  <template v-if="enableFlash">
                    <input
                      type="text"
                      class="form-input form-input-inline"
                      placeholder="刷机路径"
                      v-model="flashPath"
                    />
                    <button type="button" class="ea-btn-ghost ea-btn-sm" @click.stop>浏览</button>
                  </template>
                </div>

                <!-- T卡升级选项（功能暂不实现） -->
                <div class="form-group form-row">
                  <label class="checkbox-label">
                    <input type="checkbox" v-model="enableTcardUpdate" />
                    <span>T卡升级</span>
                  </label>
                  <template v-if="enableTcardUpdate">
                    <input
                      type="text"
                      class="form-input form-input-inline"
                      placeholder="T卡升级路径"
                      v-model="tcardUpdatePath"
                    />
                    <button type="button" class="ea-btn-ghost ea-btn-sm" @click.stop>浏览</button>
                  </template>
                </div>

                <button
                  type="button"
                  class="ea-btn-primary"
                  @click.stop="handleStartTest(selectedDevice.device.deviceId)"
                >
                  {{ selectedDevice.device.role === '辅测机' ? '开始待命' : '开始测试' }}
                </button>
              </div>

              <!-- 前置条件不满足时的操作 -->
              <div v-if="needsContinue" class="actions-section">
                <div class="section-title">继续测试</div>
                <button
                  type="button"
                  class="ea-btn-primary"
                  @click.stop="handleContinueTest(selectedDevice.device.deviceId)"
                >
                  继续测试
                </button>
              </div>

              <!-- 结束测试 -->
              <div v-if="canEndTest" class="actions-section">
                <div class="section-title">测试操作</div>
                <button
                  type="button"
                  class="ea-btn-primary"
                  @click.stop="handleEndTest(selectedDevice.device.deviceId)"
                >
                  结束测试
                </button>
              </div>
            </div>
          </EaCard>

          <!-- 用例详情（空闲时隐藏） -->
          <EaCard v-if="!isIdle">
            <div class="case-detail-header">
              <span class="section-title">用例详情</span>
              <button
                v-if="selectedDevice?.session?.isRunning"
                type="button"
                class="ea-btn-ghost ea-btn-sm"
                :style="{ opacity: followCurrent ? 1 : 0.5 }"
                @click="toggleFollowCurrent"
              >
                {{ followCurrent ? '● 跟随当前' : '○ 跟随当前' }}
              </button>
            </div>
            
            <div v-if="selectedCase && selectedDevice?.session?.caseResults" class="case-detail-content">
              <template v-for="([label, configs]) in getCaseGroups" :key="label">
                <template v-for="config in configs" :key="config.module">
                  <template v-if="isSelectedCaseInConfig(config)">
                    <div class="case-info">
                      <div class="detail-item">
                        <span class="detail-label">用例模块</span>
                        <span class="detail-value">{{ config.moduleLabel }}</span>
                      </div>
                      <div class="detail-item">
                        <span class="detail-label">用例名称</span>
                        <span class="detail-value">
                          {{ getSelectedCaseName(config) }}
                        </span>
                      </div>
                      <div class="detail-item">
                        <span class="detail-label">测试结果</span>
                        <span class="detail-value" :style="{ color: getCaseResultColor(selectedCaseResult?.status || '') }">
                          {{ selectedCaseResult?.status || '未开始' }}
                        </span>
                      </div>
                      <div class="detail-item">
                        <span class="detail-label">测试结论</span>
                        <span class="detail-value">{{ selectedCaseResult?.message || '暂无' }}</span>
                      </div>
                    </div>
                    
                    <div class="case-steps" v-if="selectedCaseResult?.steps?.length">
                      <div class="section-title">子步骤</div>
                      <div
                        v-for="(step, idx) in selectedCaseResult.steps"
                        :key="idx"
                        class="step-item"
                      >
                        {{ step.stepDesc }}
                      </div>
                    </div>
                  </template>
                </template>
              </template>
              
              <div v-if="isTestComplete" class="case-detail-actions">
                <button type="button" class="ea-btn-primary" @click="openRetestDialog(selectedCase!)">复测此用例</button>
                <button type="button" class="ea-btn-ghost" @click="openModifyDialog(selectedCase!)">修改用例结果</button>
              </div>
            </div>
            
            <div v-else class="case-detail-empty">
              <span class="ea-muted">请从左侧选择用例查看详情</span>
            </div>
          </EaCard>
        </div>
      </div>
    </template>
  <!-- 修改用例结果对话框 -->
    <div v-if="showModifyDialog" class="modify-overlay" @click.self="showModifyDialog = false">
      <div class="modify-dialog">
        <div class="modify-dialog-header">
          <span class="section-title">修改用例结果</span>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="showModifyDialog = false">✕</button>
        </div>
        <div class="modify-dialog-body">
          <div class="form-group">
            <label class="form-label">测试结果</label>
            <select v-model="modifyStatus" class="form-input">
              <option value="通过">通过</option>
              <option value="失败">失败</option>
              <option value="部分通过">部分通过</option>
              <option value="NA">NA</option>
              <option value="跳过">跳过</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">备注</label>
            <textarea v-model="modifyMessage" class="form-input" rows="3" placeholder="输入备注..."></textarea>
          </div>
        </div>
        <div class="modify-dialog-footer">
          <button type="button" class="ea-btn-ghost" @click="showModifyDialog = false">取消</button>
          <button type="button" class="ea-btn-primary" @click="handleModifyCaseResult">确认修改</button>
        </div>
      </div>
    </div>
  <!-- 复测用例弹窗 -->
    <div v-if="showRetestDialog" class="modify-overlay" @click.self="showRetestDialog = false">
      <div class="modify-dialog">
        <div class="modify-dialog-header">
          <span class="section-title">复测用例</span>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="showRetestDialog = false">✕</button>
        </div>
        <div class="modify-dialog-body">
          <div class="form-group">
            <label class="form-label">选择辅测机（可选）</label>
            <select v-model="retestAuxDeviceId" class="form-input">
              <option :value="null">无（不需要辅测机）</option>
              <option v-for="d in availableAuxForRetest" :key="d.deviceId" :value="d.deviceId">
                {{ d.deviceName }}（{{ d.role }}）
              </option>
            </select>
          </div>
        </div>
        <div class="modify-dialog-footer">
          <button type="button" class="ea-btn-ghost" :disabled="retesting" @click="showRetestDialog = false">取消</button>
          <button type="button" class="ea-btn-primary" :disabled="retesting" @click="handleRetestCase">
            {{ retesting ? '正在复测...' : '开始复测' }}
          </button>
        </div>
      </div>
    </div>
  <!-- 人工确认弹窗 -->
    <div v-if="showManualDialog" class="modify-overlay">
      <div class="modify-dialog">
        <div class="modify-dialog-header">
          <span class="section-title">需人工确认</span>
        </div>
        <div class="modify-dialog-body">
          <p class="manual-message">{{ manualMessage }}</p>
        </div>
        <div class="modify-dialog-footer">
          <template v-if="manualMode === 'ack'">
            <button
              type="button"
              class="ea-btn-primary"
              :disabled="manualSubmitting"
              @click="handleManualDecision('ack')"
            >
              {{ manualSubmitting ? '提交中...' : '知道了' }}
            </button>
          </template>
          <template v-else>
            <button
              type="button"
              class="ea-btn-ghost"
              :disabled="manualSubmitting"
              @click="handleManualDecision('fail')"
            >
              {{ manualFailLabel }}
            </button>
            <button
              type="button"
              class="ea-btn-primary"
              :disabled="manualSubmitting"
              @click="handleManualDecision('pass')"
            >
              {{ manualSubmitting ? '提交中...' : manualPassLabel }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.section-heading {
  font-size: 15px;
  font-weight: 700;
  margin: 0 0 4px;
}

.section-desc {
  font-size: 13px;
  margin: 0 0 16px;
}

.section-heading-spaced {
  margin-top: 20px;
}

.device-list-section-spaced {
  margin-top: 20px;
}

.device-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.device-list-title {
  margin-bottom: 0;
}

.device-list-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.device-list-empty {
  padding: 40px;
  text-align: center;
}

.overview-catalog-section {
  margin-bottom: 8px;
}

.overview-catalog-bar {
  margin-bottom: 0;
}

.catalog-auto-retest-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  font-size: 13px;
  margin-top: 0;
}

.catalog-setting-input {
  width: 64px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg);
  margin: 0;
  flex-shrink: 0;
  cursor: text;

  &:focus {
    outline: none;
    border-color: var(--accent);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.pre-wrap {
  white-space: pre-wrap;
}

.device-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.device-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  }
}

.device-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.device-status-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  font-size: 24px;
  border-radius: 12px;
  background: var(--bg);
}

.device-info {
  flex: 1;
}

.device-info h4 {
  font-size: 16px;
  font-weight: 700;
  margin: 0 0 2px;
}

.device-id {
  font-size: 12px;
  color: var(--muted);
  font-family: monospace;
}

.role-badge {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.device-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.detail-label {
  color: var(--muted);
}

.device-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.detail-container {
  display: flex;
  gap: 16px;
  height: calc(100vh - 180px);
  min-height: 500px;
}

.sidebar-card {
  width: 280px;
  flex-shrink: 0;
  overflow-y: auto;
}

.detail-main {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.detail-card-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.role-selector {
  display: flex;
  gap: 8px;
}

.role-btn {
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;

  &.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
  }

  &:hover:not(.active) {
    border-color: var(--line-strong);
  }
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--muted);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg);
  margin-top: 8px;

  &:focus {
    outline: none;
    border-color: var(--accent);
  }
}

.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.form-input-inline {
  flex: 1;
  min-width: 160px;
  margin-top: 0;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;

  input {
    width: 16px;
    height: 16px;
  }
}

.actions-section {
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.hint-text {
  font-size: 13px;
  color: #888;
  color: var(--muted, #888);
  padding: 12px 0;
  margin: 0;
}

.test-type-selector {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.test-type-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  cursor: pointer;
  transition: all 0.15s;
  text-align: center;
  font-family: inherit;
  color: var(--text);

  &:hover {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  &.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
  }
}

.case-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.module-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.module-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;

  &:hover {
    color: var(--text);
  }
}

.module-arrow {
  font-size: 10px;
  transition: transform 0.15s;
  display: inline-block;

  &.open {
    transform: rotate(90deg);
  }
}

.module-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted);
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 999px;
}

.module-cases {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.case-item {
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 13px;
  background: var(--bg);

  &:hover {
    background: var(--line);
  }

  &.selected {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
  }

  &.passed {
    border-left: 3px solid var(--success);
  }

  &.failed {
    border-left: 3px solid var(--error);
  }
}

.case-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.case-detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.case-info {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.case-steps {
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.step-item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--line);
  font-size: 13px;

  &:last-child {
    border-bottom: none;
  }
}

.case-detail-actions {
  display: flex;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.case-detail-empty {
  padding: 40px;
  text-align: center;
}

// 修改结果对话框
.modify-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modify-dialog {
  background: #fff;
  background: var(--card, #fff);
  border-radius: 16px;
  width: 440px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  color: #222;
  color: var(--text, #222);
}

.modify-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e5e5;
  border-bottom: 1px solid var(--line, #e5e5e5);
}

.modify-dialog-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modify-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #e5e5e5;
  border-top: 1px solid var(--line, #e5e5e5);
}

.manual-message {
  font-size: 14px;
  color: #222;
  color: var(--text, #222);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1024px) {
  .detail-container {
    flex-direction: column;
    height: auto;
    min-height: auto;
  }

  .sidebar-card {
    width: 100%;
    max-height: 300px;
  }
}

@media (max-width: 720px) {
  .device-grid {
    grid-template-columns: 1fr;
  }

  .case-info {
    grid-template-columns: 1fr;
  }

  .custom-test-layout {
    flex-direction: column;

    .custom-test-right {
      width: 100%;
    }
  }
}

.custom-test-layout {
  display: flex;
  gap: 16px;
  margin-top: 16px;

  .custom-test-left {
    flex: 1;
    min-width: 0;
  }

  .custom-test-right {
    width: 360px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
}

.catalog-type-group {
  border: 1px solid var(--line);
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;

  .catalog-type-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    cursor: pointer;
    background: var(--accent-soft);
    font-weight: 700;

    .catalog-type-label { font-size: 14px; }
    .catalog-meta { font-size: 12px; color: var(--muted); margin-left: auto; }
  }

  .catalog-type-body {
    padding: 8px;
  }
}

.catalog-group {
  border: 1px solid var(--line);
  border-radius: 8px;
  margin-bottom: 8px;

  &:last-child {
    margin-bottom: 0;
  }

  .catalog-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    cursor: pointer;
    background: var(--bg);
    border-radius: 8px 8px 0 0;

    .catalog-toggle { font-size: 10px; width: 14px; flex-shrink: 0; }
    .catalog-toggle-nested { margin-left: 4px; }
    .catalog-label { font-weight: 600; }
    .catalog-meta { font-size: 12px; color: var(--muted); margin-left: auto; }
  }

  .catalog-cases {
    padding: 8px 12px 8px 28px;
    max-height: 280px;
    overflow-y: auto;
  }
}

.catalog-toggle {
  font-size: 10px;
  width: 14px;
  flex-shrink: 0;
}

.case-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
  font-size: 13px;

  .case-tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--accent);
    color: #fff;
  }
}

.device-select-list {
  .device-radio, .device-checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border: 1px solid var(--line);
    border-radius: 6px;
    margin-bottom: 4px;
    cursor: pointer;

    &.selected {
      border-color: var(--accent);
      background: var(--accent-soft);
    }

    .device-name { font-weight: 500; }
    .device-id { font-size: 11px; color: var(--muted); margin-left: auto; }
    .device-role { font-size: 11px; color: var(--accent); }
  }
}
</style>
