import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const vuePath = path.join(__dirname, '../packages/client/src/views/tahp/DeviceSelfCheckView.vue')
const outPath = path.join(__dirname, '../packages/client/src/composables/useDeviceSelfCheck.ts')

const src = fs.readFileSync(vuePath, 'utf8')
const m = src.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)
if (!m) throw new Error('no script block')

let body = m[1]

// Remove old imports block - will replace with new header
body = body.replace(/^import[\s\S]*?from '@\/api\/tahp\/device-self-check'\n\n/, '')

const header = `import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
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
  type DeviceRole,
  type DeviceDetail,
  type ModuleCondition,
  type CaseResult,
  type CaseCatalog,
  type CaseCatalogGroup,
  type CaseCatalogDetailItem,
} from '@/api/tahp/device-self-check'
import {
  AUTO_RETEST_TOOLTIP,
  MODULE_ORDER,
  getTestTypeLabel,
  getStatusColor,
  getStatusIcon,
  getModuleLabel,
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
  { key: 'review', label: '测试报告' },
] as const

export function useDeviceSelfCheck() {
  const message = useMessage()
`

const footer = `
  return {
    activeTab,
    syncing,
    nextNodes,
    scheduleItems,
    stats,
    pipelineStages,
    handleSyncNodes,
    handleNewTask,
    handleChecklistStr4,
    handleChecklistPower,
    handleChecklistStress,
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
    enableTcardUpdate,
    tcardUpdatePath,
    viewMode,
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
    backFromCaseCatalog,
    isCatalogDetailModuleExpanded,
    toggleCatalogDetailModule,
    openCaseCatalog,
    selectCatalogCase,
    saveCatalogTypeSettings,
    backToOverview,
    goBack,
    startTestIntentRole,
    setStartTestIntentRole,
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
`

// Remove duplicated constants/helpers now in utils
body = body.replace(/const SELF_CHECK_SUBTITLE[\s\S]*?\n\n/, '')
body = body.replace(/const AUTO_RETEST_TOOLTIP[\s\S]*?\n\n/, '')
body = body.replace(/function getTestTypeLabel[\s\S]*?\n\}\n\nfunction loadCaseCatalogs/, 'async function loadCaseCatalogs')
body = body.replace(/function getStatusColor[\s\S]*?\n\}\n\nfunction getStatusIcon[\s\S]*?\n\}\n\nfunction getModuleLabel[\s\S]*?\n\}\n\nfunction getDisplayStatus[\s\S]*?\n\}\n\nfunction getRoleBadge[\s\S]*?\n\}\n\nfunction getCaseResultColor[\s\S]*?\n\}\n\n\/\/ 模块显示顺序[\s\S]*?const MODULE_ORDER[\s\S]*?\n\}\n\n/, '')
body = body.replace(/function parseManualSteps[\s\S]*?\n\}\n\nconst catalogDetailByModule/, 'const catalogDetailByModule')

body = body.replace(
  /const gerritPanelExpanded[\s\S]*?const planningPanelExpanded[\s\S]*?\n\n/,
  '',
)

body = body.replace(
  /const viewMode = ref<'overview' \| 'detail' \| 'customTest' \| 'caseCatalog'>\('overview'\)/,
  "const viewMode = ref<'list' | 'customTest' | 'caseCatalog'>('list')",
)

const insertAfter = 'const launchStore = useDeviceSelfCheckLaunchStore()'
const newState = `${insertAfter}

  const activeTab = ref<SelfCheckTab>('overview')
  const syncing = ref(false)
  const nextNodes = ref<NextNodeItem[]>([])
  const scheduleItems = ref<ScheduleItem[]>([])

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

  function handleChecklistStr4(_domain: 'driver' | 'comm') {
    activeTab.value = 'devices'
    selectedTestType.value = 'str4'
  }

  function handleChecklistPower() {
    message.info('功耗 T-Power 测试需连接硬件，请在设备执行中选择对应用例')
    activeTab.value = 'devices'
  }

  function handleChecklistStress() {
    activeTab.value = 'planning'
  }

  const stats = computed(() => ({
    pendingProjects: scheduleItems.value.filter(i => i.status === 'upcoming').length,
    runningTests: devices.value.filter(d =>
      d.status.includes('测试') || d.status.includes('等待') || d.status === '初始化中',
    ).length,
    pendingManual: devices.value.filter(d =>
      d.status.includes('待确认') || d.status.includes('不满足'),
    ).length,
    pendingReports: 0,
  }))

  const pipelineStages = computed((): PipelineStage[] => {
    const hasNodes = nextNodes.value.length > 0
    const hasRunning = stats.value.runningTests > 0
    const hasSchedule = scheduleItems.value.length > 0
    return [
      {
        key: 'sync',
        label: '项目节点同步',
        status: hasNodes ? 'done' : 'idle',
        hint: hasNodes ? \`\${nextNodes.value.length} 个项目\` : undefined,
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
`

body = body.replace(insertAfter, newState)

body = body.replace(/viewMode\.value = 'overview'/g, "viewMode.value = 'list'")

body = body.replace(
  /onMounted\(async \(\) => \{\n  connectEventStream\(\)/,
  'onMounted(async () => {\n  await loadPlanningSummary()\n  connectEventStream()',
)

// Remove DeviceInfo import usage if still referenced - add devices ref type inline ok

fs.writeFileSync(outPath, header + body + footer)
console.log('Wrote', outPath)
