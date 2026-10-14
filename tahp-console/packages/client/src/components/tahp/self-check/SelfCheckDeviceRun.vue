<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import type { DeviceInfo, DeviceRole } from '@/api/tahp/device-self-check'
import { openDeviceCaseFailureLogs } from '@/api/tahp/device-self-check'
import EaCard from '@/components/layout/EaCard.vue'
import BitflipResultTable from './BitflipResultTable.vue'
import { DEVICE_SELF_CHECK_KEY } from './self-check-context'
import {
  AUTOMATION_MODE_FILTER_OPTIONS,
  DEVICE_LIST_FILTER_OPTIONS,
  bitflipResultOf,
  formatCatalogAutomation,
  formatCatalogModuleScope,
  formatCatalogPrereq,
  deviceMatchesListFilter,
  formatChipPlatforms,
  getAutomationModeIcon,
  getAutomationModeLabel,
  getCurrentCaseStepIndex,
  getDeviceListFilterKey,
  getModuleLabel,
  isActiveAuxiliaryDevice,
  normalizeAutomationMode,
  parseManualSteps,
  STANDARD_TEST_TYPE_ORDER,
} from './self-check-utils'
import type { AutomationModeFilterKey, DeviceListFilterKey } from './self-check-utils'
import type { CaseCatalogGroup } from '@/api/tahp/device-self-check'

const catalogPanelRef = ref<HTMLElement | null>(null)
const deviceListAnchorRef = ref<HTMLElement | null>(null)
const deviceDetailPanelRef = ref<HTMLElement | null>(null)
const deviceDetailBodyRef = ref<HTMLElement | null>(null)
const customTestPanelRef = ref<HTMLElement | null>(null)
const aiNlProcessLogRef = ref<HTMLElement | null>(null)
const deviceListFilter = ref<DeviceListFilterKey>('all')
const customAutomationFilter = ref<AutomationModeFilterKey>('all')

function getScrollParent(el: HTMLElement): HTMLElement | Window {
  let node: HTMLElement | null = el.parentElement
  while (node) {
    const { overflowY } = getComputedStyle(node)
    if (/(auto|scroll|overlay)/.test(overflowY) && node.scrollHeight > node.clientHeight) {
      return node
    }
    node = node.parentElement
  }
  return window
}

function scrollElementIntoView(el: HTMLElement) {
  const scrollMargin = 16
  const scrollParent = getScrollParent(el)
  if (scrollParent === window) {
    const top = el.getBoundingClientRect().top + window.scrollY - scrollMargin
    window.scrollTo({ top, behavior: 'smooth' })
    return
  }

  const elRect = el.getBoundingClientRect()
  const parentEl = scrollParent as HTMLElement
  const parentRect = parentEl.getBoundingClientRect()
  const top = parentEl.scrollTop + (elRect.top - parentRect.top) - scrollMargin
  parentEl.scrollTo({ top, behavior: 'smooth' })
}

async function scrollToElement(el: HTMLElement | null | undefined) {
  if (!el) return
  await nextTick()
  requestAnimationFrame(() => {
    scrollElementIntoView(el)
  })
}

async function scrollToElementWhenReady(getEl: () => HTMLElement | null | undefined) {
  await nextTick()
  await nextTick()
  requestAnimationFrame(() => {
    const el = getEl()
    if (el) scrollElementIntoView(el)
  })
}

const {
  viewMode,
  error,
  gerritPreselectCount,
  selectedCases,
  caseCatalogGroups,
  expandedCatalogTypes,
  expandedCatalogModules,
  catalogDetailLoading,
  selectedAiGeneratedCasesForDelete,
  aiGeneratedCasesDeleting,
  catalogDetailByModule,
  selectedCatalogCaseKey,
  selectedCatalogItem,
  catalogTypeSettings,
  catalogSettingsSaving,
  selectedCatalogTestType,
  selectedCatalogGroup,
  availableCustomDut,
  customTestDutDeviceId,
  customTestAuxDeviceIds,
  availableCustomAux,
  customTestStarting,
  prioritizeTddManual,
  showStandardTddManualPriority,
  hasSelectedStr4WeekTdd,
  selectedDevice,
  selectedDeviceId,
  getCaseGroups,
  isIdle,
  isError,
  errorReason,
  errorModuleLabel,
  canEndTest,
  canSkipCurrentCase,
  needsContinue,
  selectedCase,
  selectedCaseResult,
  followCurrent,
  selectedTestType,
  canSelectStartModules,
  toggleStartModule,
  isStartModuleSelected,
  loading,
  devices,
  AUTO_RETEST_TOOLTIP,
  toggleCatalogType,
  countGroupCases,
  isGroupAllSelected,
  toggleAllCasesInGroup,
  toggleCatalogModule,
  toggleAllCasesInModule,
  toggleCase,
  toggleSubTask,
  toggleAllSubTasks,
  isSubTaskSelected,
  isAllSubTasksSelected,
  toggleAuxDevice,
  handleStartCustomTest,
  openCaseCatalog,
  collapseCaseCatalog,
  catalogPanelExpanded,
  deviceDetailExpanded,
  deviceDetailScrollNonce,
  catalogPanelScrollNonce,
  collapseDeviceDetail,
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
  toggleCatalogDetailModule,
  isCatalogDetailModuleExpanded,
  openCustomTest,
  closeCustomTest,
  doRefreshDevices,
  loadDevices,
  handleEndTest,
  handleSkipCurrentCase,
  toggleModule,
  isModuleExpanded,
  selectCaseItem,
  isCaseSelected,
  getCaseItemClass,
  getCaseItemStyle,
  startTestIntentRole,
  setStartTestIntentRole,
  handleStartTest,
  handleContinueTest,
  handleResumeTest,
  toggleFollowCurrent,
  openRetestDialog,
  openModifyDialog,
  getStatusColor,
  getDisplayStatus,
  getRoleBadge,
  getTestTypeLabel,
  getCaseResultColor,
  selectDevice,
  saveCatalogTypeSettings,
  saveKernelFeatureCodeDir,
  saveBitflipRepeatCount,
  openGmsTradefedDialog,
  gmsTradefedConfiguredSummary,
  gmsHostSupported,
  isCatalogGroupUnavailable,
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
  handleBrowseReleaseUpgradePath,
  enableReleaseUpgrade,
  releaseTcardPaths,
  releaseUpgradeResolving,
  releaseUpgradePlan,
  pretestPanelTitle,
  pretestLogTitle,
  otaBatteryMessage,
  otaBatteryChecking,
  otaStartBlocked,
  otaPretestConfiguredSummary,
  openOtaPretestDialog,
  isSelectedCaseInConfig,
  getSelectedCaseName,
} = inject(DEVICE_SELF_CHECK_KEY)!

const message = useMessage()
const openingFailureLogs = ref(false)
/** 用例详情右侧可滚动区（真正挡住子步骤的是这个，不是内层列表） */
const caseDetailScrollRef = ref<HTMLElement | null>(null)

const currentCaseStepIndex = computed(() =>
  getCurrentCaseStepIndex(selectedCaseResult.value?.steps, selectedCaseResult.value?.status),
)

/** 当前选中用例的 bitflip 压测结果表（detail.bitflip，无则 null） */
const selectedBitflipResult = computed(() => bitflipResultOf(selectedCaseResult.value?.detail))

watch(
  () => [
    selectedCaseResult.value?.testType,
    selectedCaseResult.value?.module,
    selectedCaseResult.value?.caseIndex,
    currentCaseStepIndex.value,
    selectedCaseResult.value?.steps?.length,
  ],
  async ([, , , currentIndex, stepsLen]) => {
    if (typeof currentIndex !== 'number' || currentIndex < 0) return
    await nextTick()
    const scrollEl = caseDetailScrollRef.value
    if (!scrollEl) return
    const maxScroll = Math.max(0, scrollEl.scrollHeight - scrollEl.clientHeight)
    // 最新一步：滚到详情区底部，露出完整最新子步骤
    if (typeof stepsLen === 'number' && currentIndex >= stepsLen - 1) {
      scrollEl.scrollTo({ top: maxScroll, behavior: 'smooth' })
      return
    }
    const currentEl = scrollEl.querySelector(
      `[data-step-idx="${currentIndex}"]`,
    ) as HTMLElement | null
    if (!currentEl) return
    const scrollRect = scrollEl.getBoundingClientRect()
    const elRect = currentEl.getBoundingClientRect()
    const top = scrollEl.scrollTop + (elRect.top - scrollRect.top) - (scrollEl.clientHeight - elRect.height) / 2
    scrollEl.scrollTo({ top: Math.max(0, Math.min(top, maxScroll)), behavior: 'smooth' })
  },
)

const filteredCustomCatalogGroups = computed((): CaseCatalogGroup[] => {
  const filter = customAutomationFilter.value
  if (filter === 'all') return caseCatalogGroups.value
  return caseCatalogGroups.value
    .map(group => ({
      ...group,
      modules: group.modules
        .map(mod => ({
          ...mod,
          cases: mod.cases.filter(c => normalizeAutomationMode(c.automationMode) === filter),
        }))
        .filter(mod => mod.cases.length > 0),
    }))
    .filter(group => group.modules.length > 0)
})

const customAutomationFilterCounts = computed(() => {
  const counts = { all: 0, full: 0, semi: 0, manual: 0 }
  for (const group of caseCatalogGroups.value) {
    for (const mod of group.modules) {
      for (const c of mod.cases) {
        counts.all += 1
        counts[normalizeAutomationMode(c.automationMode)] += 1
      }
    }
  }
  return counts
})

watch(
  () => viewMode.value === 'customTest',
  (isCustom) => {
    if (isCustom) customAutomationFilter.value = 'all'
  },
)

function canOpenSelectedFailureLogs(): boolean {
  const result = selectedCaseResult.value
  if (!result) return false
  return Boolean(result.failureLogDir)
    || result.status === '失败'
    || result.status === '通过'
    || result.status === '部分通过'
}

async function handleOpenFailureLogs() {
  const deviceId = selectedDevice.value?.device.deviceId
  const result = selectedCaseResult.value
  if (!deviceId || !result || openingFailureLogs.value) return
  const caseKey = `${result.testType}/${result.module}/${result.caseIndex}`
  openingFailureLogs.value = true
  try {
    const { dirPath } = await openDeviceCaseFailureLogs(deviceId, caseKey)
    message.success(`已打开日志目录：${dirPath}`)
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '打开日志失败')
  } finally {
    openingFailureLogs.value = false
  }
}

const DIRECT_TEST_TYPE_ORDER = STANDARD_TEST_TYPE_ORDER

void [flashLogRef, isError, openRetestDialog, openModifyDialog, clearFlashPanel]

function handleCollapseCaseCatalog() {
  collapseCaseCatalog()
  void scrollToElement(deviceListAnchorRef.value)
}

function handleCollapseDeviceDetail() {
  collapseDeviceDetail()
  void scrollToElement(deviceListAnchorRef.value)
}

function handleOpenCustomTest() {
  openCustomTest()
  void scrollToElementWhenReady(() => customTestPanelRef.value)
}

watch(
  () => catalogPanelExpanded.value && !catalogDetailLoading.value,
  (ready) => {
    if (ready) void scrollToElementWhenReady(() => catalogPanelRef.value)
  },
  { flush: 'post' },
)

watch(
  () => aiNlCaseProgress.value.length,
  async () => {
    await nextTick()
    const el = aiNlProcessLogRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

async function scrollToDeviceDetailBody() {
  await scrollToElementWhenReady(() => deviceDetailBodyRef.value ?? deviceDetailPanelRef.value)
}

watch(
  () => deviceDetailExpanded.value && !!selectedDevice.value,
  (ready) => {
    if (ready) void scrollToDeviceDetailBody()
  },
  { flush: 'post' },
)

watch(deviceDetailScrollNonce, () => {
  if (deviceDetailExpanded.value) {
    void scrollToDeviceDetailBody()
  }
})

watch(catalogPanelScrollNonce, () => {
  if (catalogPanelExpanded.value && !catalogDetailLoading.value) {
    void scrollToElementWhenReady(() => catalogPanelRef.value)
  }
})

watch(
  () => viewMode.value === 'customTest',
  (ready) => {
    if (ready) void scrollToElementWhenReady(() => customTestPanelRef.value)
  },
  { flush: 'post' },
)

const DUT_ROLE = '\u6d4b\u8bd5\u673a' as DeviceRole
const AUX_ROLE = '\u8f85\u6d4b\u673a' as DeviceRole
const STATUS_IDLE = '\u7a7a\u95f2'
const STATUS_STANDBY = '\u5f85\u547d'
const STATUS_INITIALIZING = '\u521d\u59cb\u5316\u4e2d'
const WORD_TESTING = '\u6d4b\u8bd5'
const WORD_WAITING = '\u7b49\u5f85'

function isAuxDevice(device: DeviceInfo) {
  return isActiveAuxiliaryDevice(device)
}

function isRunning(device: DeviceInfo) {
  const status = device.status as string
  return status.includes(WORD_TESTING)
    || status.includes(WORD_WAITING)
    || status === STATUS_INITIALIZING
    || status === '刷机中'
    || status === 'T卡升级中'
}

function isIdleDevice(device: DeviceInfo) {
  return (device.status as string) === STATUS_IDLE
}

const deviceFilterCounts = computed(() => {
  const counts = Object.fromEntries(
    DEVICE_LIST_FILTER_OPTIONS.map(opt => [opt.key, 0]),
  ) as Record<DeviceListFilterKey, number>
  counts.all = devices.value.length
  for (const device of devices.value) {
    const key = getDeviceListFilterKey(device)
    if (key !== 'other') counts[key] += 1
  }
  return counts
})

const filteredDevices = computed(() =>
  devices.value.filter(device => deviceMatchesListFilter(device, deviceListFilter.value)),
)

const showGroupedDeviceList = computed(() => deviceListFilter.value === 'all')

const filteredAuxDevices = computed(() => filteredDevices.value.filter(isAuxDevice))
const filteredRunningDevices = computed(() =>
  filteredDevices.value.filter(d => isRunning(d) && !isAuxDevice(d)),
)
const filteredIdleDevices = computed(() =>
  filteredDevices.value.filter(d => isIdleDevice(d) && !isAuxDevice(d)),
)
const filteredOtherDevices = computed(() =>
  filteredDevices.value.filter(d => !isRunning(d) && !isIdleDevice(d) && !isAuxDevice(d)),
)

function selectDeviceListFilter(key: DeviceListFilterKey) {
  deviceListFilter.value = key
}

function isDeviceCardRunning(device: DeviceInfo) {
  return isRunning(device)
}

function canSelectDevice(device: DeviceInfo) {
  const role = device.role as string
  const status = device.status as string
  return role !== AUX_ROLE || status === STATUS_STANDBY || status === STATUS_IDLE
}

function displayRole(device: DeviceInfo) {
  return (device.status as string) === STATUS_IDLE ? '\u672a\u5206\u914d' : device.role
}

const selectedDutDevice = computed(() =>
  availableCustomDut.value.find(d => d.deviceId === customTestDutDeviceId.value),
)

const selectedDutLabel = computed(() => selectedDutDevice.value?.deviceName ?? '未选择')

const selectedCaseDisplayName = computed(() => {
  if (!selectedCase.value) return '用例详情'
  for (const [, configs] of getCaseGroups.value) {
    for (const config of configs) {
      if (isSelectedCaseInConfig(config)) {
        return getSelectedCaseName(config)
      }
    }
  }
  return '用例详情'
})

function dutRowActionLabel(deviceId: string): string {
  if (customTestDutDeviceId.value !== deviceId) return '设为测试机'
  return '开始'
}

function canDutRowStart(deviceId: string): boolean {
  return customTestDutDeviceId.value === deviceId
    && selectedCases.value.size > 0
    && !customTestStarting.value
}

function handleDutRowAction(deviceId: string) {
  if (customTestDutDeviceId.value !== deviceId) {
    customTestDutDeviceId.value = deviceId
    return
  }
  if (canDutRowStart(deviceId)) {
    void handleStartCustomTest()
  }
}

</script>

<template>
    <!-- 自定义测试视图 -->
    <template v-if="viewMode === 'customTest'">
      <div ref="customTestPanelRef" class="custom-test-view">
        <div v-if="error" style="color: var(--error); margin: 12px 0;">{{ error }}</div>
        <p v-if="gerritPreselectCount > 0" class="gerrit-preselect-hint ea-muted">
          已根据 Gerrit Code Review 预选 {{ gerritPreselectCount }} 个测试用例，请选择测试机后执行。
        </p>

        <div class="custom-test-layout">
          <div class="custom-test-left">
            <EaCard class="custom-test-case-card">
              <div class="custom-test-case-header">
                <div class="section-title custom-test-case-title">
                  用例列表
                  <span class="ea-muted" style="font-size: 12px; margin-left: 8px;">
                    已选 {{ selectedCases.size }} 个
                  </span>
                </div>
                <div class="automation-mode-filters">
                  <button
                    v-for="opt in AUTOMATION_MODE_FILTER_OPTIONS"
                    :key="opt.key"
                    type="button"
                    class="automation-filter-chip"
                    :class="[
                      `automation-filter-chip--${opt.key}`,
                      { active: customAutomationFilter === opt.key },
                    ]"
                    @click="customAutomationFilter = opt.key"
                  >
                    <span v-if="opt.key !== 'all'" class="auto-mode-icon" :class="`auto-mode-icon--${opt.key}`">
                      {{ getAutomationModeIcon(opt.key) }}
                    </span>
                    {{ opt.label }}
                    <span class="automation-filter-count">{{ customAutomationFilterCounts[opt.key] }}</span>
                  </button>
                </div>
              </div>
              <div class="custom-test-case-scroll catalog-list">
                <div v-if="filteredCustomCatalogGroups.length === 0" class="ea-muted catalog-empty-cases">
                  当前筛选下无用例
                </div>
                <div
                  v-for="group in filteredCustomCatalogGroups"
                  :key="group.testType"
                  class="catalog-type-group"
                  :class="{ 'is-unavailable': isCatalogGroupUnavailable(group) }"
                >
                  <div class="catalog-type-header" @click="toggleCatalogType(group.testType)">
                    <span class="catalog-toggle">{{ expandedCatalogTypes.has(group.testType) ? '▼' : '▶' }}</span>
                    <span class="catalog-type-label">{{ group.label }}</span>
                    <span class="catalog-meta">{{ group.testType }} ({{ countGroupCases(group) }}个)</span>
                    <span v-if="isCatalogGroupUnavailable(group)" class="catalog-unavailable-tag">不可用</span>
                    <button
                      type="button"
                      class="ea-btn-ghost ea-btn-sm"
                      :disabled="isCatalogGroupUnavailable(group)"
                      @click.stop="toggleAllCasesInGroup(group)"
                    >
                      {{ isGroupAllSelected(group) ? '取消全选' : '全选' }}
                    </button>
                  </div>
                  <p v-if="isCatalogGroupUnavailable(group)" class="catalog-unavailable-hint">
                    {{ group.unavailableReason || '当前环境不支持该测试' }}
                  </p>
                  <div v-if="expandedCatalogTypes.has(group.testType)" class="catalog-type-body">
                    <div v-for="catalog in group.modules" :key="catalog.key" class="catalog-group">
                      <div class="catalog-header" @click="toggleCatalogModule(catalog.key)">
                        <span class="catalog-toggle catalog-toggle-nested">{{ expandedCatalogModules.has(catalog.key) ? '▼' : '▶' }}</span>
                        <span class="catalog-label">{{ catalog.moduleLabel }}</span>
                        <span class="catalog-meta">{{ catalog.module }} ({{ catalog.cases.length }}个)</span>
                        <button
                          type="button"
                          class="ea-btn-ghost ea-btn-sm"
                          :disabled="isCatalogGroupUnavailable(group)"
                          @click.stop="toggleAllCasesInModule(catalog)"
                        >
                          {{ catalog.cases.every(c => selectedCases.has(catalog.key + '/' + c.caseIndex)) ? '取消全选' : '全选' }}
                        </button>
                      </div>
                      <div v-if="expandedCatalogModules.has(catalog.key)" class="catalog-cases">
                        <template v-for="c in catalog.cases" :key="c.caseIndex">
                          <div
                            class="case-checkbox"
                            :class="{ selected: selectedCases.has(catalog.key + '/' + c.caseIndex) }"
                            role="checkbox"
                            tabindex="0"
                            :aria-checked="selectedCases.has(catalog.key + '/' + c.caseIndex)"
                            @click="toggleCase(catalog.key + '/' + c.caseIndex)"
                            @keydown.enter.prevent="toggleCase(catalog.key + '/' + c.caseIndex)"
                            @keydown.space.prevent="toggleCase(catalog.key + '/' + c.caseIndex)"
                          >
                            <input
                              type="checkbox"
                              :checked="selectedCases.has(catalog.key + '/' + c.caseIndex)"
                              @click.stop
                              @change="toggleCase(catalog.key + '/' + c.caseIndex)"
                            />
                            <span
                              class="auto-mode-icon"
                              :class="`auto-mode-icon--${normalizeAutomationMode(c.automationMode)}`"
                              :title="getAutomationModeLabel(c.automationMode)"
                            >{{ getAutomationModeIcon(c.automationMode) }}</span>
                            <span class="case-name">{{ c.caseIndex }}. {{ c.caseName }}</span>
                            <span
                              v-for="plat in formatChipPlatforms(c.platforms)"
                              :key="plat"
                              class="case-tag case-tag--platform"
                            >{{ plat }}</span>
                            <span v-if="c.canReuse" class="case-tag">可复用</span>
                          </div>
                          <!-- 子任务选择面板 -->
                          <div
                            v-if="c.subTasks?.length && selectedCases.has(catalog.key + '/' + c.caseIndex)"
                            class="subtask-panel"
                          >
                            <div class="subtask-header">
                              <span class="subtask-title">{{ c.caseName }} - 选择测试项</span>
                              <button
                                type="button"
                                class="ea-btn-ghost ea-btn-sm"
                                @click.stop="toggleAllSubTasks(catalog.key + '/' + c.caseIndex, c.subTasks!)"
                              >
                                {{ isAllSubTasksSelected(catalog.key + '/' + c.caseIndex, c.subTasks!) ? '取消全选' : '全选' }}
                              </button>
                            </div>
                            <div class="subtask-list">
                              <div v-for="st in c.subTasks" :key="st.caseId" class="subtask-block">
                                <label
                                  class="subtask-item"
                                  :class="{ selected: isSubTaskSelected(catalog.key + '/' + c.caseIndex, st.caseId) }"
                                >
                                  <input
                                    type="checkbox"
                                    :checked="isSubTaskSelected(catalog.key + '/' + c.caseIndex, st.caseId)"
                                    @change="toggleSubTask(catalog.key + '/' + c.caseIndex, st.caseId, (st.children || []).map(ch => ch.caseId))"
                                  />
                                  <span class="subtask-id">{{ st.caseId }}</span>
                                  <span class="subtask-label">{{ st.label }}</span>
                                </label>
                                <div
                                  v-if="st.children?.length && isSubTaskSelected(catalog.key + '/' + c.caseIndex, st.caseId)"
                                  class="subtask-children"
                                >
                                  <label
                                    v-for="ch in st.children"
                                    :key="ch.caseId"
                                    class="subtask-item"
                                    :class="{ selected: isSubTaskSelected(catalog.key + '/' + c.caseIndex, ch.caseId) }"
                                  >
                                    <input
                                      type="checkbox"
                                      :checked="isSubTaskSelected(catalog.key + '/' + c.caseIndex, ch.caseId)"
                                      @change="toggleSubTask(catalog.key + '/' + c.caseIndex, ch.caseId)"
                                    />
                                    <span class="subtask-id">{{ ch.caseId }}</span>
                                    <span class="subtask-label">{{ ch.label }}</span>
                                  </label>
                                </div>
                              </div>
                            </div>
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </EaCard>
          </div>

        <div class="custom-test-right">
          <EaCard class="custom-run-summary">
            <div class="catalog-overview-header custom-run-summary-header">
              <div class="section-title custom-run-summary-title">执行摘要</div>
              <button
                type="button"
                class="ea-btn-ghost ea-btn-sm"
                @click="closeCustomTest"
              >
                ← 返回
              </button>
            </div>
            <dl class="custom-run-meta">
              <div>
                <dt>用例</dt>
                <dd>{{ selectedCases.size }} 个</dd>
              </div>
              <div>
                <dt>测试机</dt>
                <dd>{{ selectedDutLabel }}</dd>
              </div>
              <div>
                <dt>辅测机</dt>
                <dd>{{ customTestAuxDeviceIds.size }} 个</dd>
              </div>
            </dl>
            <label
              v-if="hasSelectedStr4WeekTdd"
              class="checkbox-label tdd-manual-priority"
            >
              <input type="checkbox" v-model="prioritizeTddManual" />
              <span>优先测试通信的人工用例</span>
            </label>
            <p
              v-if="hasSelectedStr4WeekTdd"
              class="custom-run-hint ea-muted"
            >
              仅调整执行顺序，结果列表与报告顺序不变
            </p>
            <button
              type="button"
              class="ea-btn-primary ea-btn-lg custom-run-start"
              :disabled="!customTestDutDeviceId || selectedCases.size === 0 || customTestStarting"
              @click="handleStartCustomTest"
            >
              {{ customTestStarting ? '启动中...' : `开始测试（${selectedCases.size} 个用例）` }}
            </button>
            <p v-if="!customTestDutDeviceId" class="custom-run-hint ea-muted">请选择测试机</p>
            <p v-else-if="selectedCases.size === 0" class="custom-run-hint ea-muted">请勾选至少一个用例</p>
          </EaCard>

          <EaCard>
            <div class="device-section-head">
              <div class="section-title">测试机（单选）</div>
              <button
                type="button"
                class="ea-btn-ghost ea-btn-sm device-refresh-btn"
                :disabled="loading"
                @click="doRefreshDevices"
              >
                刷新设备
              </button>
            </div>
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
                <span class="device-status ea-muted">{{ getDisplayStatus(d) }}</span>
                <button
                  type="button"
                  class="ea-btn-primary ea-btn-sm device-radio-action"
                  :disabled="customTestDutDeviceId === d.deviceId && (selectedCases.size === 0 || customTestStarting)"
                  @click.stop="handleDutRowAction(d.deviceId)"
                >
                  {{ dutRowActionLabel(d.deviceId) }}
                </button>
              </label>
            </div>
          </EaCard>

          <EaCard>
            <div class="device-section-head">
              <div class="section-title">
                辅测机（多选）
                <span class="ea-muted" style="font-size: 12px; margin-left: 8px;">
                  已选 {{ customTestAuxDeviceIds.size }} 个
                </span>
              </div>
              <button
                type="button"
                class="ea-btn-ghost ea-btn-sm device-refresh-btn"
                :disabled="loading"
                @click="doRefreshDevices"
              >
                刷新设备
              </button>
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
                <span class="device-status ea-muted">{{ getDisplayStatus(d) }}</span>
              </label>
            </div>
          </EaCard>
        </div>
      </div>
      </div>
    </template>

    <!-- 设备列表视图 -->
    <template v-if="viewMode === 'list'">
      <div v-if="loading" class="ea-muted" style="padding: 40px; text-align: center;">
        加载中...
      </div>

      <div v-else-if="error && !catalogPanelExpanded" style="padding: 40px; text-align: center;">
        <div style="color: var(--error); margin-bottom: 16px;">
          {{ error }}
        </div>
        <button class="ea-btn-primary" @click="loadDevices">
          重试
        </button>
      </div>

      <template v-else>
        <div class="self-check-stack">
        <div
          v-if="catalogPanelExpanded"
          ref="catalogPanelRef"
          class="catalog-detail-layout self-check-stack-pane self-check-stack-pane--catalog"
        >
          <div v-if="catalogDetailLoading" class="ea-muted catalog-panel-loading">
            加载中...
          </div>
          <div v-else-if="error" class="catalog-panel-error">
            <div style="color: var(--error); margin-bottom: 16px;">{{ error }}</div>
            <button type="button" class="ea-btn-primary" @click="openCaseCatalog(selectedCatalogTestType!)">
              重试
            </button>
          </div>
          <template v-else>
            <EaCard class="catalog-overview-card">
              <div class="detail-card-content">
                <div class="catalog-overview-header">
                  <div class="section-title">{{ selectedCatalogGroup?.label || '用例整体情况' }}</div>
                  <button
                    type="button"
                    class="ea-btn-ghost ea-btn-sm"
                    @click="handleCollapseCaseCatalog"
                  >
                    收起
                  </button>
                </div>
                <dl v-if="selectedCatalogGroup" class="catalog-overview-meta">
                  <div>
                    <dt>覆盖</dt>
                    <dd>{{ formatCatalogModuleScope(selectedCatalogGroup) }}</dd>
                  </div>
                  <div>
                    <dt>自动化</dt>
                    <dd>{{ formatCatalogAutomation(selectedCatalogGroup) }}</dd>
                  </div>
                  <div>
                    <dt>前置</dt>
                    <dd>{{ formatCatalogPrereq(selectedCatalogGroup) }}</dd>
                  </div>
                </dl>
                <div v-if="isAiGeneratedCatalog()" class="ai-case-delete-toolbar">
                  <span class="ea-muted">
                    已选择 {{ selectedAiGeneratedCasesForDelete.size }} 个待删除 AI 用例
                  </span>
                  <button
                    type="button"
                    class="ea-btn-ghost ea-btn-sm"
                    :disabled="selectedAiGeneratedCasesForDelete.size === 0 || aiGeneratedCasesDeleting"
                    @click="clearAiGeneratedDeleteSelection"
                  >
                    清空选择
                  </button>
                  <button
                    type="button"
                    class="ea-btn-danger ea-btn-sm"
                    :disabled="selectedAiGeneratedCasesForDelete.size === 0 || aiGeneratedCasesDeleting"
                    @click="handleDeleteAiGeneratedCases"
                  >
                    {{ aiGeneratedCasesDeleting ? '删除中...' : '删除所选 AI 用例' }}
                  </button>
                </div>
                <div
                  v-if="selectedCatalogTestType === 'monkey'"
                  class="catalog-monkey-duration catalog-overview-retest"
                >
                  <label class="catalog-monkey-label" for="monkey-duration-input">monkey测试时长</label>
                  <input
                    id="monkey-duration-input"
                    v-model.trim="catalogTypeSettings.monkeyDuration"
                    type="text"
                    class="catalog-setting-input catalog-monkey-input"
                    :disabled="catalogSettingsSaving"
                    placeholder="7d"
                    @change="saveCatalogTypeSettings"
                  />
                  <span class="ea-muted catalog-monkey-help">
                    支持 Nm/Nd，例如 30m、7d；m 表示分钟，d 表示天，最长 14 天
                  </span>
                </div>
                <div
                  v-else-if="selectedCatalogTestType === 'smoke'"
                  class="catalog-smoke-settings catalog-overview-retest"
                >
                  <label class="checkbox-label catalog-smoke-skip-spd">
                    <input
                      type="checkbox"
                      v-model="catalogTypeSettings.smokeUsdSkipSpdInfo"
                      :disabled="catalogSettingsSaving"
                      @change="saveCatalogTypeSettings"
                    />
                    <span>跳过 SPD 拉取（--skip-spd-info）</span>
                  </label>
                  <span class="ea-muted catalog-smoke-help">
                    执行 si_run.py --test-type usd；无 SPD 网络时可勾选，SPD 依赖用例将自动跳过
                  </span>
                </div>
                <div
                  v-else-if="selectedCatalogTestType === 'gms'"
                  class="catalog-gms-settings catalog-overview-retest"
                >
                  <p v-if="!gmsHostSupported" class="catalog-gms-unavailable">
                    Windows 环境不支持 GMS 测试，请在 Linux 主机上运行 cts/gts/vts-tradefed。
                  </p>
                  <p class="catalog-gms-intro ea-muted">{{ gmsTradefedConfiguredSummary }}</p>
                  <label class="catalog-monkey-label" for="gms-timeout-hours-input">用例超时</label>
                  <input
                    id="gms-timeout-hours-input"
                    v-model.number="catalogTypeSettings.gmsTimeoutHours"
                    type="number"
                    min="1"
                    max="72"
                    class="catalog-setting-input catalog-monkey-input"
                    :disabled="catalogSettingsSaving"
                    @change="saveCatalogTypeSettings"
                  />
                  <span class="ea-muted catalog-monkey-help">小时                    小时，每个 CTS/GTS/VTS 子计划（指纹/传感器/多媒体/安全等）最长执行时间，默认 8
                  </span>
                  <button
                    type="button"
                    class="ea-btn-ghost ea-btn-sm"
                    @click="openGmsTradefedDialog"
                  >
                    配置 Tradefed 路径
                  </button>
                </div>
                <div
                  v-else-if="selectedCatalogTestType === 'kernel_feature'"
                  class="catalog-kernel-code-dir catalog-overview-retest"
                >
                  <label class="catalog-monkey-label" for="kernel-feature-code-dir-input">源码路径 (code_dir)</label>
                  <input
                    id="kernel-feature-code-dir-input"
                    v-model.trim="catalogTypeSettings.kernelFeatureCodeDir"
                    type="text"
                    class="catalog-setting-input catalog-kernel-code-input"
                    :disabled="catalogSettingsSaving"
                    placeholder="例如 Z:\alps 或 \\server\share\X6850"
                    @change="saveKernelFeatureCodeDir(false)"
                  />
                  <span class="ea-muted catalog-monkey-help">
                    稳定性 Checklist 源码对照项（7/11–14）使用；也可在设备「开始测试」面板配置
                  </span>
                </div>
                <div
                  v-else-if="selectedCatalogTestType === 'ai_generated'"
                  class="catalog-ai-generated-note catalog-overview-retest"
                >
                  <span class="ea-muted">AI用例失败后将立即停止，不自动复测；NL UI 用例全自动执行。</span>
                </div>
                <div
                  v-else-if="selectedCatalogTestType === 'ota_upgrade'"
                  class="catalog-ai-generated-note catalog-overview-retest"
                >
                  <span class="ea-muted">
                    已获取外发版本时按所选版本连续升级；未获取到版本时仍可开始，只执行前置步骤。完成后校验开机并记录版本。不自动复测。
                  </span>
                </div>
                <div
                  v-else-if="selectedCatalogTestType === 'bitflip'"
                  class="catalog-bitflip-settings catalog-overview-retest"
                >
                  <label class="catalog-monkey-label" for="bitflip-repeat-count-input">每项重复测试次数 (-r)</label>
                  <input
                    id="bitflip-repeat-count-input"
                    v-model.number="catalogTypeSettings.bitflipRepeatCount"
                    type="number"
                    min="1"
                    max="100"
                    class="catalog-setting-input catalog-monkey-input"
                    :disabled="catalogSettingsSaving"
                    @change="saveCatalogTypeSettings"
                  />
                  <span class="ea-muted catalog-monkey-help">
                    遍历条件下每项重复测试次数（BAT -r 参数），默认 1，范围 1-100；超时上限 = 20h × 重复次数（当前 {{ (catalogTypeSettings.bitflipRepeatCount || 1) * 20 }}h）；每轮约 12-20 小时，期间设备会多次重启
                  </span>
                </div>
                <div v-else class="catalog-auto-retest-row catalog-overview-retest">
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
            </EaCard>

            <div v-if="isAiGeneratedCatalog()" class="ai-nl-case-create">
              <div class="ai-nl-case-create-header">
                <div class="section-title">{{ aiNlCaseEditingKey ? '修改 NL UI 用例' : '新增 NL UI 用例' }}</div>
                <p class="ea-muted ai-nl-case-create-hint">
                  {{
                    aiNlCaseEditingKey
                      ? `正在编辑 ${aiNlCaseEditingKey}：调整描述后点「保存并覆盖」，将重新规划并覆盖原用例。`
                      : '左侧填写用例描述并提交；右侧展示 AI 判定可执行性、动作规划与落盘过程（失败原因也会显示在此）。'
                  }}
                </p>
              </div>
              <div class="ai-nl-case-create-split">
                <div class="ai-nl-case-create-left">
                  <label class="ai-nl-field">
                    <span class="form-label">用例名称</span>
                    <input
                      v-model.trim="aiNlCaseForm.caseName"
                      type="text"
                      class="catalog-setting-input ai-nl-input"
                      :disabled="aiNlCaseCreating"
                      placeholder="例如：验证设置页 WLAN 入口"
                    />
                  </label>
                  <label class="ai-nl-field ai-nl-field-grow">
                    <span class="form-label">自然语言执行描述</span>
                    <textarea
                      v-model.trim="aiNlCaseForm.nlDescription"
                      class="catalog-setting-input ai-nl-textarea"
                      rows="5"
                      :disabled="aiNlCaseCreating"
                      placeholder="请尽量写清：前置（亮屏/解锁）、操作路径（打开哪个页面、点击/滑动什么）、验证点（界面应出现/不出现什么文案）。仅图标无文案的按钮可填写 resource-id（如 dialpad_floating_action_button）"
                    />
                  </label>
                  <label class="ai-nl-field">
                    <span class="form-label">期望结果（可选）</span>
                    <textarea
                      v-model.trim="aiNlCaseForm.expectedResult"
                      class="catalog-setting-input ai-nl-textarea ai-nl-textarea-sm"
                      rows="2"
                      :disabled="aiNlCaseCreating"
                      placeholder="例如：界面出现 WLAN 开关或可用网络列表"
                    />
                  </label>
                  <div class="ai-nl-case-create-actions">
                    <button
                      type="button"
                      class="ea-btn-primary ai-nl-submit-btn"
                      :disabled="aiNlCaseCreating"
                      @click="handleCreateAiNlUiCase"
                    >
                      {{
                        aiNlCaseCreating
                          ? (aiNlCaseEditingKey ? '判定并覆盖中...' : '判定并保存中...')
                          : (aiNlCaseEditingKey ? '保存并覆盖' : '新增用例')
                      }}
                    </button>
                    <button
                      v-if="aiNlCaseEditingKey"
                      type="button"
                      class="ea-btn-ghost ea-btn-sm"
                      :disabled="aiNlCaseCreating"
                      @click="cancelEditAiNlCase"
                    >
                      取消修改
                    </button>
                    <button
                      v-if="aiNlCaseProgress.length"
                      type="button"
                      class="ea-btn-ghost ea-btn-sm"
                      :disabled="aiNlCaseCreating"
                      @click="clearAiNlProgress"
                    >
                      清空过程
                    </button>
                  </div>
                </div>
                <div
                  class="ai-nl-case-create-right"
                  :class="`is-${aiNlCaseProgressStatus}`"
                >
                  <div class="ai-nl-process-title">
                    <span>AI 判定 / 执行过程</span>
                    <span
                      class="ai-nl-process-badge"
                      :class="`is-${aiNlCaseProgressStatus}`"
                    >
                      {{
                        aiNlCaseProgressStatus === 'running' ? '进行中'
                          : aiNlCaseProgressStatus === 'success' ? '成功'
                            : aiNlCaseProgressStatus === 'error' ? '失败'
                              : '待命'
                      }}
                    </span>
                  </div>
                  <div
                    ref="aiNlProcessLogRef"
                    class="ai-nl-process-log"
                  >
                    <div
                      v-if="!aiNlCaseProgress.length"
                      class="ai-nl-process-empty ea-muted"
                    >
                      {{
                        aiNlCaseEditingKey
                          ? '点击「保存并覆盖」后，这里会展示重新规划与覆盖落盘过程。'
                          : '点击「新增用例」后，这里会实时展示：输入校验、LLM 思考、可执行性判定、动作计划与落盘结果。'
                      }}
                    </div>
                    <div
                      v-for="item in aiNlCaseProgress"
                      :key="item.id"
                      class="ai-nl-process-item"
                      :class="`level-${item.level}`"
                    >
                      <div class="ai-nl-process-item-head">
                        <span class="ai-nl-process-time">{{ item.at }}</span>
                        <span class="ai-nl-process-level">{{
                          item.level === 'thinking' ? '思考'
                            : item.level === 'success' ? '成功'
                              : item.level === 'error' ? '失败'
                                : '信息'
                        }}</span>
                      </div>
                      <div class="ai-nl-process-msg">{{ item.message }}</div>
                      <pre
                        v-if="item.detail"
                        class="ai-nl-process-detail"
                      >{{ item.detail }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="detail-container catalog-detail-body">
              <EaCard class="sidebar-card">
                <div class="section-title">用例列表</div>
                <div class="case-list">
                  <div v-if="catalogDetailByModule.length === 0" class="ea-muted catalog-empty-cases">
                    暂无用例，可在上方新增 NL UI 用例
                  </div>
                  <div
                    v-for="mod in catalogDetailByModule"
                    :key="mod.module"
                    class="module-group"
                  >
                    <div
                      class="module-name"
                      @click="toggleCatalogDetailModule(mod.module)"
                    >
                      <span class="module-arrow" :class="{ open: isCatalogDetailModuleExpanded(mod.module) }">&#9654;</span>
                      {{ mod.moduleLabel }}
                      <span class="module-count">{{ mod.cases.length }}</span>
                    </div>
                    <div class="module-cases" v-show="isCatalogDetailModuleExpanded(mod.module)">
                      <div
                        v-for="item in mod.cases"
                        :key="item.key"
                        class="case-item"
                        :class="{
                          selected: selectedCatalogCaseKey === item.key,
                          editing: aiNlCaseEditingKey === item.key,
                        }"
                        @click="selectCatalogCase(item.key)"
                      >
                        <input
                          v-if="isAiGeneratedCatalog()"
                          type="checkbox"
                          class="ai-case-delete-checkbox"
                          :checked="selectedAiGeneratedCasesForDelete.has(item.key)"
                          @click.stop
                          @change.stop="toggleAiGeneratedCaseForDelete(item.key)"
                        />
                        <span
                          class="auto-mode-icon"
                          :class="`auto-mode-icon--${normalizeAutomationMode(item.automationMode)}`"
                          :title="getAutomationModeLabel(item.automationMode)"
                        >{{ getAutomationModeIcon(item.automationMode) }}</span>
                        <span class="case-item-name">{{ item.caseName }}</span>
                        <span
                          v-for="plat in formatChipPlatforms(item.platforms)"
                          :key="plat"
                          class="case-tag case-tag--platform"
                        >{{ plat }}</span>
                        <button
                          v-if="isAiGeneratedCatalog()"
                          type="button"
                          class="ai-case-edit-btn"
                          title="修改用例"
                          :disabled="aiNlCaseCreating"
                          @click.stop="startEditAiNlCase(item)"
                        >
                          ✎
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </EaCard>

              <div class="detail-main">
                <EaCard class="catalog-case-detail-card">
                  <div v-if="selectedCatalogItem" class="case-detail-header">
                    <span class="catalog-case-title">{{ selectedCatalogItem.caseName }}</span>
                    <span
                      v-for="plat in formatChipPlatforms(selectedCatalogItem.platforms)"
                      :key="plat"
                      class="case-tag case-tag--platform"
                    >{{ plat }}</span>
                    <span
                      class="auto-mode-badge"
                      :class="`auto-mode-badge--${normalizeAutomationMode(selectedCatalogItem.automationMode)}`"
                    >
                      <span
                        class="auto-mode-icon"
                        :class="`auto-mode-icon--${normalizeAutomationMode(selectedCatalogItem.automationMode)}`"
                      >{{ getAutomationModeIcon(selectedCatalogItem.automationMode) }}</span>
                      {{ getAutomationModeLabel(selectedCatalogItem.automationMode) }}
                    </span>
                  </div>
                  <div v-if="selectedCatalogItem" class="case-detail-content">
                    <div v-if="selectedCatalogItem.preconditions" class="case-info">
                      <div class="detail-item">
                        <span class="detail-label">前置条件</span>
                        <span class="detail-value pre-wrap">{{ selectedCatalogItem.preconditions }}</span>
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
                    <div v-if="selectedCatalogItem.expectedResult" class="case-steps case-expected">
                      <div class="section-title">期望结果</div>
                      <div class="detail-value pre-wrap">{{ selectedCatalogItem.expectedResult }}</div>
                    </div>
                    <div
                      v-if="selectedCatalogTestType !== 'monkey' && selectedCatalogTestType !== 'smoke' && selectedCatalogTestType !== 'gms' && selectedCatalogTestType !== 'power' && selectedCatalogTestType !== 'power_feature' && selectedCatalogTestType !== 'thermal' && selectedCatalogTestType !== 'kernel_feature' && selectedCatalogTestType !== 'ota_upgrade' && !selectedCatalogItem.manualSteps && !selectedCatalogItem.preconditions && !selectedCatalogItem.expectedResult"
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
        </div>

        <div ref="deviceListAnchorRef" class="device-list-anchor self-check-stack-pane self-check-stack-pane--list">
        <EaCard class="device-list-section">
          <div class="device-list-header">
            <div class="section-title device-list-title">设备列表</div>
            <div class="device-list-actions">
              <button
                type="button"
                class="ea-btn-primary ea-btn-sm"
                @click="handleOpenCustomTest"
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

          <div v-if="devices.length > 0" class="device-list-filters">
            <button
              v-for="opt in DEVICE_LIST_FILTER_OPTIONS"
              :key="opt.key"
              type="button"
              class="device-filter-chip"
              :class="[
                `device-filter-chip--${opt.key}`,
                { active: deviceListFilter === opt.key },
              ]"
              @click="selectDeviceListFilter(opt.key)"
            >
              {{ opt.label }}
              <span class="device-filter-count">{{ deviceFilterCounts[opt.key] }}</span>
            </button>
          </div>

          <div v-if="devices.length === 0" class="ea-muted device-list-empty">
            暂无连接设备，请连接 Android 设备后刷新
          </div>

          <template v-else>
          <div v-if="!showGroupedDeviceList && filteredDevices.length === 0" class="ea-muted device-list-empty">
            暂无「{{ DEVICE_LIST_FILTER_OPTIONS.find(o => o.key === deviceListFilter)?.label }}」设备
          </div>

          <template v-else-if="!showGroupedDeviceList">
            <div class="device-group">
              <div class="device-grid">
                <EaCard
                  v-for="device in filteredDevices"
                  :key="device.deviceId"
                  class="device-card"
                  :class="{
                    'device-card-running': isDeviceCardRunning(device),
                    'device-card-selected': selectedDeviceId === device.deviceId,
                  }"
                  @click="canSelectDevice(device) && selectDevice(device.deviceId)"
                >
                  <div class="device-header">
                    <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
                    <div class="device-info"><h4>{{ device.deviceName }}</h4><span class="device-id">{{ device.deviceId }}</span></div>
                    <span class="role-badge" :style="getRoleBadge(displayRole(device))">{{ displayRole(device) }}</span>
                  </div>
                  <div class="device-details">
                    <div class="detail-row"><span class="detail-label">状态</span><span :style="{ color: getStatusColor(device.status) }">{{ getDisplayStatus(device) }}</span></div>
                    <div v-if="device.testType" class="detail-row"><span class="detail-label">用例</span><span>{{ getTestTypeLabel(device.testType) }}</span></div>
                  </div>
                </EaCard>
              </div>
            </div>
          </template>

          <template v-else>
          <div v-if="filteredRunningDevices.length" class="device-group">
            <h4 class="group-label">运行中</h4>
            <div class="device-grid">
              <EaCard v-for="device in filteredRunningDevices" :key="device.deviceId" class="device-card device-card-running" :class="{ 'device-card-selected': selectedDeviceId === device.deviceId }" @click="canSelectDevice(device) && selectDevice(device.deviceId)">
                <div class="device-header">
                  <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
                  <div class="device-info"><h4>{{ device.deviceName }}</h4><span class="device-id">{{ device.deviceId }}</span></div>
                  <span class="role-badge" :style="getRoleBadge(displayRole(device))">{{ displayRole(device) }}</span>
                </div>
                <div class="device-details">
                  <div class="detail-row"><span class="detail-label">状态</span><span :style="{ color: getStatusColor(device.status) }">{{ getDisplayStatus(device) }}</span></div>
                  <div v-if="device.testType" class="detail-row"><span class="detail-label">用例</span><span>{{ getTestTypeLabel(device.testType) }}</span></div>
                </div>
              </EaCard>
            </div>
          </div>
          <div v-if="filteredAuxDevices.length" class="device-group">
            <h4 class="group-label">辅测机</h4>
            <div class="device-grid">
              <EaCard
                v-for="device in filteredAuxDevices"
                :key="device.deviceId"
                class="device-card"
                :class="{
                  'device-card-running': (device.status as string) === '占用中' || (device.status as string) === '待命',
                  'device-card-selected': selectedDeviceId === device.deviceId,
                }"
                @click="canSelectDevice(device) && selectDevice(device.deviceId)"
              >
                <div class="device-header">
                  <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
                  <div class="device-info"><h4>{{ device.deviceName }}</h4><span class="device-id">{{ device.deviceId }}</span></div>
                  <span class="role-badge" :style="getRoleBadge(displayRole(device))">{{ displayRole(device) }}</span>
                </div>
                <div class="device-details">
                  <div class="detail-row"><span class="detail-label">状态</span><span :style="{ color: getStatusColor(device.status) }">{{ getDisplayStatus(device) }}</span></div>
                  <div v-if="device.testType" class="detail-row"><span class="detail-label">用例</span><span>{{ getTestTypeLabel(device.testType) }}</span></div>
                </div>
              </EaCard>
            </div>
          </div>
          <div v-if="filteredIdleDevices.length" class="device-group">
            <h4 class="group-label">空闲</h4>
            <div class="device-grid">
              <EaCard v-for="device in filteredIdleDevices" :key="device.deviceId" class="device-card" :class="{ 'device-card-selected': selectedDeviceId === device.deviceId }" @click="selectDevice(device.deviceId)">
                <div class="device-header">
                  <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
                  <div class="device-info"><h4>{{ device.deviceName }}</h4><span class="device-id">{{ device.deviceId }}</span></div>
                  <span class="role-badge" :style="getRoleBadge(displayRole(device))">{{ displayRole(device) }}</span>
                </div>
                <div class="device-details">
                  <div class="detail-row"><span class="detail-label">状态</span><span :style="{ color: getStatusColor(device.status) }">{{ getDisplayStatus(device) }}</span></div>
                </div>
              </EaCard>
            </div>
          </div>
          <div v-if="filteredOtherDevices.length" class="device-group">
            <h4 class="group-label">其他状态</h4>
            <div class="device-grid">
              <EaCard v-for="device in filteredOtherDevices" :key="device.deviceId" class="device-card" :class="{ 'device-card-selected': selectedDeviceId === device.deviceId }" @click="canSelectDevice(device) && selectDevice(device.deviceId)">
                <div class="device-header">
                  <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
                  <div class="device-info"><h4>{{ device.deviceName }}</h4><span class="device-id">{{ device.deviceId }}</span></div>
                  <span class="role-badge" :style="getRoleBadge(displayRole(device))">{{ displayRole(device) }}</span>
                </div>
                <div class="device-details">
                  <div class="detail-row"><span class="detail-label">状态</span><span :style="{ color: getStatusColor(device.status) }">{{ getDisplayStatus(device) }}</span></div>
                </div>
              </EaCard>
            </div>
          </div>
          </template>
            </template>
        </EaCard>
        </div>

        <div
          v-if="selectedDevice && deviceDetailExpanded"
          ref="deviceDetailPanelRef"
          class="device-detail-layout self-check-stack-pane self-check-stack-pane--device"
        >
          <EaCard class="device-overview-card">
            <div class="detail-card-content">
              <div class="catalog-overview-header">
                <div class="section-title device-detail-panel-title">{{ selectedDevice.device.deviceName }}</div>
                <button
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  @click="handleCollapseDeviceDetail"
                >
                  收起
                </button>
              </div>
              <dl class="catalog-overview-meta device-overview-meta">
                <div>
                  <dt>设备 ID</dt>
                  <dd class="device-id-inline">{{ selectedDevice.device.deviceId }}</dd>
                </div>
                <div v-if="!isIdle">
                  <dt>角色</dt>
                  <dd>{{ selectedDevice.device.role }}</dd>
                </div>
                <div>
                  <dt>所属用例</dt>
                  <dd>{{ getTestTypeLabel(selectedDevice.device.testType) }}</dd>
                </div>
                <div>
                  <dt>插卡</dt>
                  <dd>插入 {{ selectedDevice.device.simCards.filter(s => s.present).length }} 张 SIM 卡</dd>
                </div>
                <div v-if="!isIdle">
                  <dt>状态</dt>
                  <dd :style="{ color: getStatusColor(selectedDevice.device.status) }">
                    {{ getDisplayStatus(selectedDevice.device) }}
                  </dd>
                </div>
                <div v-if="!isIdle && selectedDevice.device.testStartTime && selectedDevice.device.role !== AUX_ROLE">
                  <dt>开始时间</dt>
                  <dd>{{ new Date(selectedDevice.device.testStartTime).toLocaleString('zh-CN') }}</dd>
                </div>
                <div v-if="!isIdle && selectedDevice.device.testDuration">
                  <dt>用时</dt>
                  <dd>{{ Math.round(selectedDevice.device.testDuration / 60) }} 分钟</dd>
                </div>
              </dl>
            </div>
          </EaCard>

          <div ref="deviceDetailBodyRef" class="detail-container device-detail-body">
            <EaCard class="sidebar-card">
              <div class="section-title">
                用例列表
                <span
                  v-if="isIdle && canSelectStartModules"
                  class="ea-muted"
                  style="font-size: 12px; margin-left: 8px; font-weight: 400; text-transform: none; letter-spacing: normal;"
                >
                  勾选模块后开始测试
                </span>
              </div>
              <div class="case-list">
                <template v-for="([label, configs]) in getCaseGroups" :key="label">
                  <template v-for="config in configs" :key="config.module">
                    <div class="module-group">
                      <div
                        class="module-name"
                        @click="toggleModule(`${config.module}`)"
                      >
                        <input
                          v-if="isIdle && canSelectStartModules"
                          type="checkbox"
                          class="module-select-checkbox"
                          :checked="isStartModuleSelected(config.module)"
                          :title="isStartModuleSelected(config.module) ? '取消勾选则跳过此模块' : '勾选后纳入本次测试'"
                          @click.stop
                          @change="toggleStartModule(config.module)"
                        />
                        <span class="module-arrow" :class="{ open: isModuleExpanded(config.module) }">&#9654;</span>
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
                            <span
                              class="auto-mode-icon"
                              :class="`auto-mode-icon--${normalizeAutomationMode(caseItem.automationMode)}`"
                              :title="getAutomationModeLabel(caseItem.automationMode)"
                            >{{ getAutomationModeIcon(caseItem.automationMode) }}</span>
                            <span class="case-item-name">{{ caseItem.caseName }}</span>
                            <span
                              v-for="plat in formatChipPlatforms(caseItem.platforms)"
                              :key="plat"
                              class="case-tag case-tag--platform"
                            >{{ plat }}</span>
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
                            <span
                              class="auto-mode-icon"
                              :class="`auto-mode-icon--${normalizeAutomationMode(caseItem.automationMode)}`"
                              :title="getAutomationModeLabel(caseItem.automationMode)"
                            >{{ getAutomationModeIcon(caseItem.automationMode) }}</span>
                            <span class="case-item-name">{{ caseItem.caseName }}</span>
                            <span
                              v-for="plat in formatChipPlatforms(caseItem.platforms)"
                              :key="plat"
                              class="case-tag case-tag--platform"
                            >{{ plat }}</span>
                          </div>
                        </template>
                      </div>
                    </div>
                  </template>
                </template>
              </div>
            </EaCard>

            <div class="detail-main">
              <EaCard class="device-detail-main-card">
                <div v-if="showFlashPanel && !showFlashFailureUI" class="device-detail-main-scroll">
                  <div class="flash-progress-header">
                    <span class="section-title">{{ pretestPanelTitle }}</span>
                    <div class="flash-progress-meta">
                      <span class="flash-progress-percent">{{ Math.min(flashProgress, 100) }}%</span>
                      <span class="flash-progress-badge" :class="flashStatusClass">{{ flashStatusText }}</span>
                    </div>
                  </div>
                  <div class="flash-progress-track">
                    <div
                      class="flash-progress-fill"
                      :class="{ 'is-indeterminate': isFlashIndeterminate }"
                      :style="!isFlashIndeterminate ? { width: `${Math.min(flashProgress, 100)}%` } : undefined"
                    />
                  </div>
                  <p class="flash-phase-text">{{ flashPhase || `等待${pretestLogTitle}...` }}</p>
                  <div class="flash-log-panel">
                    <span class="form-label">{{ pretestLogTitle }}</span>
                    <pre ref="flashLogRef" class="flash-log-content">{{ flashLogs.join('\n') }}</pre>
                  </div>
                </div>

                <template v-else-if="showFlashFailureUI">
                  <div class="case-detail-header">
                    <span class="catalog-case-title">{{ isFlashFailed ? pretestPanelTitle.replace('进度', '失败') : '测试异常' }}</span>
                  </div>
                  <div class="device-detail-main-scroll case-detail-content">
                    <div class="case-info">
                      <div v-if="errorModuleLabel" class="detail-item">
                        <span class="detail-label">异常位置</span>
                        <span class="detail-value">{{ errorModuleLabel }}</span>
                      </div>
                      <div class="detail-item detail-item--full">
                        <span class="detail-label">原因</span>
                        <span class="detail-value">{{ errorReason }}</span>
                      </div>
                    </div>
                    <div v-if="showFlashPanel || isFlashFailed" class="flash-log-panel" style="margin-bottom: 12px;">
                      <span class="form-label">{{ pretestLogTitle }}</span>
                      <pre class="flash-log-content">{{ flashLogs.join('\n') }}</pre>
                    </div>
                    <div class="device-detail-inline-actions">
                      <button
                        v-if="!isFlashFailed"
                        type="button"
                        class="ea-btn-primary ea-btn-sm"
                        @click.stop="handleResumeTest(selectedDevice.device.deviceId)"
                      >
                        恢复测试
                      </button>
                      <button
                        type="button"
                        class="ea-btn-primary ea-btn-sm end-test-btn"
                        @click.stop="handleEndTest(selectedDevice.device.deviceId)"
                      >
                        结束测试
                      </button>
                      <button
                        type="button"
                        class="ea-btn-ghost ea-btn-sm"
                        @click.stop="dismissFlashFailure()"
                      >
                        返回
                      </button>
                    </div>
                  </div>
                </template>

                <template v-else-if="isIdle && selectedDevice.device.testType !== 'custom'">
                  <div class="device-detail-main-header">
                    <span class="catalog-case-title">
                      {{ startTestIntentRole === AUX_ROLE ? '注册为辅测机' : '开始测试' }}
                    </span>
                  </div>
                  <div class="device-detail-main-scroll">
                    <div class="form-group">
                      <span class="form-label">设备角色</span>
                      <div class="role-selector">
                        <button
                          v-for="role in [DUT_ROLE, AUX_ROLE]"
                          :key="role"
                          type="button"
                          class="role-btn"
                          :class="{ active: startTestIntentRole === role }"
                          @click.stop="setStartTestIntentRole(role as DeviceRole)"
                        >
                          {{ role }}
                        </button>
                      </div>
                    </div>

                    <div class="form-group">
                      <span class="form-label">用例选择</span>
                      <div class="test-type-selector">
                        <button
                          v-for="testType in DIRECT_TEST_TYPE_ORDER"
                          :key="testType"
                          type="button"
                          class="test-type-btn"
                          :class="{ active: selectedTestType === testType }"
                          @click.stop="selectedTestType = testType"
                        >
                          <strong>{{ getTestTypeLabel(testType) }}</strong>
                        </button>
                      </div>
                    </div>

                    <div v-if="selectedTestType === 'gms'" class="form-group gms-tradefed-settings">
                      <span class="form-label">GMS Tradefed</span>
                      <p v-if="!gmsHostSupported" class="catalog-gms-unavailable">
                        Windows 环境不支持 GMS 测试，请在 Linux 主机上运行。
                      </p>
                      <p class="gms-tradefed-summary ea-muted">{{ gmsTradefedConfiguredSummary }}</p>
                      <button
                        type="button"
                        class="ea-btn-ghost ea-btn-sm"
                        @click.stop="openGmsTradefedDialog"
                      >
                        配置 Tradefed 路径
                      </button>
                    </div>

                    <div
                      v-if="selectedTestType === 'kernel_feature'"
                      class="form-group kernel-feature-code-dir-settings"
                    >
                      <span class="form-label">源码路径 (code_dir)</span>
                      <input
                        id="start-kernel-feature-code-dir"
                        v-model.trim="catalogTypeSettings.kernelFeatureCodeDir"
                        type="text"
                        class="form-input"
                        :disabled="catalogSettingsSaving"
                        placeholder="例如 Z:\alps 或 \\server\share\X6850"
                        @change="saveKernelFeatureCodeDir(false)"
                        @click.stop
                      />
                      <p class="flash-options-hint ea-muted">
                        稳定性 Checklist 源码对照项（7/11–14）需要 Android 源码根；开始测试前请先配置
                      </p>
                    </div>

                    <div
                      v-if="selectedTestType === 'bitflip'"
                      class="form-group bitflip-repeat-count-settings"
                    >
                      <span class="form-label">每项重复测试次数 (-r)</span>
                      <input
                        id="start-bitflip-repeat-count"
                        v-model.number="catalogTypeSettings.bitflipRepeatCount"
                        type="number"
                        min="1"
                        max="100"
                        class="form-input"
                        :disabled="catalogSettingsSaving"
                        @change="saveBitflipRepeatCount(false)"
                        @click.stop
                      />
                      <p class="flash-options-hint ea-muted">
                        遍历条件下每项重复测试次数（BAT -r 参数），默认 1；超时上限 = 20h × 重复次数（当前 {{ (catalogTypeSettings.bitflipRepeatCount || 1) * 20 }}h）；每轮约 12-20 小时，期间设备会多次重启，需 userdebug 已 root 且主机 java+adb 可用
                      </p>
                    </div>

                    <div v-if="selectedTestType !== 'ota_upgrade'" class="form-group flash-options">
                      <label class="checkbox-label flash-options-toggle">
                        <input type="checkbox" v-model="enableFlash" />
                        <span>刷机</span>
                      </label>

                      <div v-if="enableFlash" class="flash-options-panel">
                        <p class="flash-options-hint">开始测试前先执行 device_update 刷机；刷机成功后会自动进入所选自检用例。</p>

                        <div class="flash-field">
                          <label class="flash-field-label">刷机包路径</label>
                          <div class="flash-path-row">
                            <input
                              type="text"
                              class="form-input form-input-inline flash-path-input"
                              placeholder="zip / scatter xml / 刷机目录"
                              v-model="flashPath"
                            />
                            <button
                              type="button"
                              class="ea-btn-ghost ea-btn-sm flash-browse-btn"
                              :disabled="flashPathPicking"
                              @click.stop="handleBrowseFlashPath"
                            >
                              {{ flashPathPicking ? '选择中...' : '浏览' }}
                            </button>
                            <button
                              type="button"
                              class="ea-btn-primary ea-btn-sm flash-daily-resolve-btn"
                              :disabled="dailyFlashResolving"
                              @click.stop="handleResolveLatestDailyFlash"
                            >
                              {{ dailyFlashResolving ? '解析中...' : '获取最新daily版本' }}
                            </button>
                            <button
                              type="button"
                              class="ea-btn-ghost ea-btn-sm flash-clear-btn"
                              :disabled="flashPackagesClearing || (showFlashPanel && !showFlashFailureUI)"
                              title="清除本地下载/解压的刷机包缓存"
                              @click.stop="handleClearFlashPackages"
                            >
                              {{ flashPackagesClearing ? '清除中...' : '一键清除刷机包' }}
                            </button>
                          </div>
                        </div>

                        <div class="flash-field">
                          <label class="flash-field-label">市场版本</label>
                          <select v-model="flashStageVersion" class="form-input flash-market-select">
                            <option
                              v-for="opt in FLASH_MARKET_OPTIONS"
                              :key="opt.value || 'none'"
                              :value="opt.value"
                            >
                              {{ opt.label }}
                            </option>
                          </select>
                        </div>

                        <div class="flash-field flash-field--root">
                          <label class="checkbox-label flash-root-toggle">
                            <input type="checkbox" v-model="enableRootPkg" />
                            <span>刷 Root 包</span>
                            <span class="flash-field-hint">可选</span>
                          </label>
                        </div>
                      </div>
                    </div>

                    <div class="form-group flash-options">
                      <div class="flash-options-title-row">
                        <label
                          v-if="selectedTestType !== 'ota_upgrade'"
                          class="checkbox-label flash-options-toggle"
                        >
                          <input type="checkbox" v-model="enableReleaseUpgrade" />
                          <span>连续版本升级</span>
                        </label>
                        <div v-else class="flash-options-toggle">
                          <span class="form-label">连续版本升级</span>
                        </div>
                        <button
                          v-if="selectedTestType === 'ota_upgrade'"
                          type="button"
                          class="ea-btn-ghost ea-btn-sm ota-pretest-config-btn"
                          :title="otaPretestConfiguredSummary"
                          @click.stop="openOtaPretestDialog"
                        >
                          账号 / SWD
                        </button>
                      </div>
                      <div v-if="enableReleaseUpgrade || selectedTestType === 'ota_upgrade'" class="flash-options-panel">
                        <p class="flash-options-hint">
                          {{
                            selectedTestType === 'ota_upgrade'
                              ? '已获取外发版本时按所选版本连续升级；调试阶段未获取到版本也可以开始，只执行本次前置步骤。'
                              : '勾选需要升级的 Android 版本；最低版使用 device_update，更高版本依次 T卡升级，全部完成后开始测试。'
                          }}
                        </p>
                        <div class="flash-path-row">
                          <button
                            type="button"
                            class="ea-btn-primary ea-btn-sm flash-daily-resolve-btn"
                            :disabled="releaseUpgradeResolving"
                            @click.stop="handleResolveReleaseUpgrade"
                          >
                            {{ releaseUpgradeResolving ? '解析中...' : (releaseUpgradePlan ? '重新解析外发版本' : '获取外发版本') }}
                          </button>
                        </div>
                        <div v-if="releaseUpgradePlan" class="release-upgrade-panel">
                          <p class="flash-daily-meta">
                            {{ releaseUpgradePlan.brand }} / {{ releaseUpgradePlan.model }}
                          </p>
                          <p v-if="releaseUpgradePlan.dailyTcardOverrideApplied" class="release-upgrade-daily-note">
                            最高 Android 版本已使用 sw_ver_sh 最新 daily T卡包
                            <span v-if="releaseUpgradePlan.dailyTcardSource === 'TEST'">（DEV 无包，已从 TEST 获取）</span>
                          </p>
                          <p v-else-if="releaseUpgradePlan.dailyResolveWarning" class="release-upgrade-warning release-upgrade-warning--standalone">
                            sw_ver_sh 最新版本解析失败：{{ releaseUpgradePlan.dailyResolveWarning }}
                          </p>
                          <div
                            v-for="step in releaseUpgradePlan.steps"
                            :key="`${step.androidVersion}-${step.releaseFolder}`"
                            class="release-upgrade-row"
                            :class="{ 'release-upgrade-row--missing': step.needsTransfer || !step.available }"
                          >
                            <label class="release-upgrade-check">
                              <input
                                type="checkbox"
                                :checked="step.selected"
                                :disabled="step.needsTransfer || !step.available"
                                @change="toggleReleaseUpgradeStep(step)"
                              />
                              <strong>{{ step.androidLabel }}</strong>
                            </label>
                            <span class="release-upgrade-version">{{ step.releaseVersionName }}</span>
                            <span class="release-upgrade-method">{{ releaseUpgradeMethodLabel(step) }}</span>
                            <div class="release-upgrade-path-cell">
                              <input
                                type="text"
                                class="form-input release-upgrade-path"
                                :value="step.packagePath"
                                @input="updateReleaseUpgradePath(step, ($event.target as HTMLInputElement).value)"
                              />
                              <button
                                type="button"
                                class="ea-btn-ghost ea-btn-sm flash-browse-btn"
                                :disabled="releasePathPicking"
                                @click.stop="handleBrowseReleaseUpgradePath(step)"
                              >
                                {{ releasePathPicking ? '选择中...' : '浏览' }}
                              </button>
                            </div>
                            <p v-if="step.needsTransfer" class="release-upgrade-warning">
                              重庆无刷机包，请将上海包传输到 {{ step.cqTargetPath }} 后重新解析
                            </p>
                            <p v-else-if="step.unavailableReason" class="release-upgrade-warning">
                              {{ step.unavailableReason }}
                            </p>
                          </div>
                        </div>
                        <p v-else class="flash-daily-hint">点击“获取外发版本”识别当前项目可升级的 Android 版本。</p>
                        <p v-if="releaseTcardPaths.length > 1" class="flash-daily-hint">
                          将依次执行 {{ releaseTcardPaths.length }} 个 T 卡升级包
                        </p>
                      </div>
                    </div>

                    <div v-if="selectedTestType !== 'ota_upgrade'" class="form-group flash-options">
                      <label class="checkbox-label flash-options-toggle">
                        <input type="checkbox" v-model="enableTcardUpdate" />
                        <span>T卡升级</span>
                      </label>
                      <div v-if="enableTcardUpdate" class="flash-options-panel">
                        <p class="flash-options-hint">单包 T 卡升级：push 到 /sdcard 后调用系统更新，完成后开始测试。</p>
                        <div class="flash-field">
                          <label class="flash-field-label">升级包（ZIP）</label>
                          <div class="flash-path-row">
                            <input
                              type="text"
                              class="form-input form-input-inline flash-path-input"
                              placeholder="仅支持 .zip"
                              v-model="tcardUpdatePath"
                            />
                            <button
                              type="button"
                              class="ea-btn-ghost ea-btn-sm flash-browse-btn"
                              :disabled="tcardPathPicking"
                              @click.stop="handleBrowseTcardZip"
                            >
                              {{ tcardPathPicking ? '选择中...' : '浏览' }}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div v-if="showStandardTddManualPriority" class="form-group">
                      <label class="checkbox-label">
                        <input type="checkbox" v-model="prioritizeTddManual" />
                        <span>优先测试通信的人工用例</span>
                      </label>
                      <p class="flash-options-hint ea-muted">仅调整执行顺序，结果列表与报告顺序不变</p>
                    </div>

                    <div v-if="canSelectStartModules" class="form-group">
                      <p class="flash-options-hint ea-muted">
                        左侧用例列表可勾选模块；当前已选
                        {{
                          getCaseGroups
                            .flatMap(([, configs]) => configs)
                            .filter(c => isStartModuleSelected(c.module))
                            .map(c => c.moduleLabel)
                            .join('、') || '无'
                        }}
                      </p>
                    </div>

                    <p
                      v-if="selectedTestType === 'ota_upgrade' && startTestIntentRole !== AUX_ROLE && (otaBatteryChecking || otaBatteryMessage)"
                      class="flash-options-hint"
                    >
                      {{ otaBatteryChecking ? '正在检查电量...' : otaBatteryMessage }}
                    </p>
                    <button
                      type="button"
                      class="ea-btn-primary"
                      :disabled="(selectedTestType === 'gms' && !gmsHostSupported) || otaStartBlocked || (canSelectStartModules && !getCaseGroups.some(([, configs]) => configs.some(c => isStartModuleSelected(c.module))))"
                      @click.stop="handleStartTest(selectedDevice.device.deviceId)"
                    >
                      {{ startTestIntentRole === AUX_ROLE ? '开始待命' : '开始测试' }}
                    </button>
                  </div>
                </template>

                <template v-else-if="!isIdle">
                  <div class="case-detail-header">
                    <span class="catalog-case-title">{{ selectedCaseDisplayName }}</span>
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

                    <div v-if="canEndTest" class="device-detail-inline-actions">
                      <button
                        v-if="needsContinue"
                        type="button"
                        class="ea-btn-primary ea-btn-sm"
                        @click.stop="handleContinueTest(selectedDevice.device.deviceId)"
                      >
                        继续测试
                      </button>
                      <button
                        v-if="canSkipCurrentCase"
                        type="button"
                        class="ea-btn-ghost ea-btn-sm"
                        title="跳过当前用例并继续"
                        @click.stop="handleSkipCurrentCase(selectedDevice.device.deviceId)"
                      >
                        跳过
                      </button>
                      <button
                        type="button"
                        class="ea-btn-primary ea-btn-sm end-test-btn"
                        @click.stop="handleEndTest(selectedDevice.device.deviceId)"
                      >
                        结束测试
                      </button>
                    </div>

                  <div
                    v-if="selectedCaseResult"
                    ref="caseDetailScrollRef"
                    class="device-detail-main-scroll case-detail-content"
                  >
                    <div class="case-info">
                      <div class="detail-item">
                        <span class="detail-label">用例模块</span>
                        <span class="detail-value">{{ getModuleLabel(selectedCaseResult.module) }}</span>
                      </div>
                      <div class="detail-item">
                        <span class="detail-label">测试结果</span>
                        <span class="detail-value" :style="{ color: getCaseResultColor(selectedCaseResult.status || '') }">
                          {{ selectedCaseResult.status || '未开始' }}
                        </span>
                      </div>
                      <div class="detail-item detail-item--full">
                        <span class="detail-label">测试结论</span>
                        <span class="detail-value pre-wrap">{{ selectedCaseResult.message || '暂无' }}</span>
                      </div>
                    </div>

                    <div class="case-steps" v-if="selectedCaseResult.steps?.length">
                      <div class="section-title">子步骤</div>
                      <div
                        v-for="(step, idx) in selectedCaseResult.steps"
                        :key="idx"
                        class="step-item"
                        :class="{ 'is-current': idx === currentCaseStepIndex }"
                        :data-step-idx="idx"
                      >
                        {{ step.stepDesc }}
                      </div>
                    </div>
                    
                    <div class="case-evidence" v-if="selectedCaseResult.evidence?.length">
                      <div class="section-title">测量数据</div>
                      <table class="evidence-table">
                        <thead>
                          <tr>
                            <th>检查项</th>
                            <th>预期值</th>
                            <th>实测值</th>
                            <th>结果</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="(item, idx) in selectedCaseResult.evidence" :key="idx" :class="{ 'evidence-pass': item.ok, 'evidence-fail': !item.ok }">
                            <td>{{ item.name }}</td>
                            <td>{{ item.expected }}</td>
                            <td>{{ item.actual }}</td>
                            <td>
                              <span :class="item.ok ? 'status-pass' : 'status-fail'">
                                {{ item.ok ? '通过' : '失败' }}
                              </span>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <div class="case-bitflip" v-if="selectedBitflipResult">
                      <div class="section-title">bitflip 压测结果</div>
                      <BitflipResultTable :result="selectedBitflipResult" />
                    </div>
                    <div v-if="canOpenSelectedFailureLogs()" class="case-detail-actions">
                      <button
                        type="button"
                        class="ea-btn-ghost"
                        :disabled="openingFailureLogs"
                        @click="handleOpenFailureLogs"
                      >
                        {{ openingFailureLogs ? '打开中…' : '打开日志' }}
                      </button>
                    </div>
                  </div>

                  <div v-else-if="selectedCase" class="device-detail-main-scroll case-detail-empty">
                    <span class="ea-muted">请从左侧选择用例查看详情</span>
                  </div>
                </template>

                <div v-else class="device-detail-main-scroll case-detail-empty">
                  <span class="ea-muted">暂无操作</span>
                </div>
              </EaCard>
            </div>
          </div>
        </div>
        </div>
      </template>
    </template>
</template>

<style scoped lang="scss">

.device-group { margin-bottom: 20px; }
.group-label { margin: 0 0 10px; font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.device-card-running { border-left: 3px solid var(--accent); }

.device-card-selected {
  box-shadow: 0 0 0 2px var(--accent);
}

.device-list-anchor {
  scroll-margin-top: 16px;
}

$catalog-pane-height: calc(100vh - 48px);

.self-check-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.self-check-stack-pane {
  scroll-margin-top: 16px;
  flex-shrink: 0;
}

.self-check-stack-pane--catalog {
  height: $catalog-pane-height;
  min-height: $catalog-pane-height;
  max-height: $catalog-pane-height;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  position: relative;
  z-index: 1;

  &.catalog-detail-layout {
    height: $catalog-pane-height;
    min-height: $catalog-pane-height;
    max-height: $catalog-pane-height;
  }

  .catalog-overview-card {
    flex-shrink: 0;
  }

  .ai-nl-case-create {
    flex: 0 1 auto;
    max-height: min(360px, 42%);
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .catalog-detail-body {
    flex: 1 1 0;
    min-height: 240px;
    overflow: hidden;
  }

  .catalog-detail-body.detail-container {
    display: flex;
    gap: 16px;
    height: 100%;
    min-height: 240px;
  }

  .catalog-detail-body .sidebar-card {
    /* 用例列表占内容区约 1/3 */
    width: auto;
    flex: 1 1 0;
    min-width: 0;
    height: 100%;
    max-height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;

    .section-title {
      flex-shrink: 0;
      margin-bottom: 8px;
    }

    .case-list {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior: contain;
    }
  }

  .catalog-detail-body .detail-main {
    /* 用例详情占内容区约 2/3 */
    flex: 2 1 0;
    min-width: 0;
    min-height: 0;
    height: 100%;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .catalog-detail-body .catalog-case-detail-card {
    flex: 1;
    min-height: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .catalog-detail-body .catalog-case-detail-card .case-detail-header {
    flex-shrink: 0;
  }

  .catalog-detail-body .catalog-case-detail-card .case-detail-content,
  .catalog-detail-body .catalog-case-detail-card .case-detail-empty {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
}

.self-check-stack-pane--list {
  min-height: 0;
  position: relative;
  z-index: 0;
}

.self-check-stack-pane--device {
  height: $catalog-pane-height;
  min-height: $catalog-pane-height;
  max-height: $catalog-pane-height;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  position: relative;
  z-index: 1;

  &.device-detail-layout {
    height: $catalog-pane-height;
    min-height: $catalog-pane-height;
    max-height: $catalog-pane-height;
  }

  .device-overview-card {
    flex-shrink: 0;
    height: 210px;
  }

  .device-detail-body {
    flex: 1 1 0;
    min-height: 0;
    overflow: hidden;
    scroll-margin-top: 16px;
  }

  .device-detail-body.detail-container {
    display: flex;
    gap: 16px;
    height: 100%;
    min-height: 0;
  }

  .device-detail-body .sidebar-card {
    width: 280px;
    flex-shrink: 0;
    height: 100%;
    max-height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;

    .section-title {
      flex-shrink: 0;
      margin-bottom: 8px;
    }

    .case-list {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior: contain;
    }
  }

  .device-detail-body .detail-main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    height: 100%;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .device-detail-body .device-detail-main-card {
    flex: 1;
    min-height: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .device-detail-body .device-detail-main-card .case-detail-header,
  .device-detail-body .device-detail-main-card .device-detail-main-header,
  .device-detail-body .device-detail-main-card .device-detail-inline-actions {
    flex-shrink: 0;
  }

  .device-detail-body .device-detail-main-card .device-detail-main-scroll,
  .device-detail-body .device-detail-main-card .case-detail-empty {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .device-detail-body .device-detail-main-card > .device-detail-main-scroll:first-child {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
}

.device-overview-meta {
  margin-bottom: 0;
}

.device-overview-card .detail-card-content {
  gap: 0;
}

.device-overview-card .catalog-overview-header {
  margin-bottom: 0;
}

.device-id-inline {
  font-family: monospace;
  font-size: 12px;
}

.device-detail-main-header {
  margin-bottom: 12px;
}

.device-detail-inline-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.device-detail-panel-title {
  margin-bottom: 0;
  text-transform: none;
  letter-spacing: 0;
  font-size: 14px;
  color: var(--text);
}

.detail-item--full {
  grid-column: 1 / -1;
}

.device-list-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.device-list-title { margin-bottom: 0; }
.detail-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.error-banner { color: var(--error); margin-bottom: 12px; font-size: 13px; }

.device-list-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.device-list-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.device-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--filter-border, var(--line));
  border-radius: 999px;
  background: var(--filter-bg, var(--bg));
  font-size: 12px;
  font-weight: 600;
  color: var(--filter-fg, var(--text));
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;

  &:hover {
    filter: brightness(0.97);
  }

  &.active {
    border-color: var(--filter-active-border, var(--filter-border, var(--accent)));
    background: var(--filter-active-bg, var(--filter-bg, var(--accent-soft)));
    color: var(--filter-active-fg, var(--filter-fg, var(--accent)));
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--filter-active-border, var(--accent)) 24%, transparent);
  }
}

.device-filter-chip--all {
  --filter-border: #94a3b8;
  --filter-bg: #f8fafc;
  --filter-fg: #475569;
  --filter-active-border: #64748b;
  --filter-active-bg: #e2e8f0;
  --filter-active-fg: #334155;
}

.device-filter-chip--testing {
  --filter-border: #60a5fa;
  --filter-bg: #eff6ff;
  --filter-fg: #1d4ed8;
  --filter-active-border: #2563eb;
  --filter-active-bg: #dbeafe;
  --filter-active-fg: #1e40af;
}

.device-filter-chip--waiting {
  --filter-border: #fbbf24;
  --filter-bg: #fffbeb;
  --filter-fg: #b45309;
  --filter-active-border: #d97706;
  --filter-active-bg: #fef3c7;
  --filter-active-fg: #92400e;
}

.device-filter-chip--idle {
  --filter-border: #a1a1aa;
  --filter-bg: #fafafa;
  --filter-fg: #52525b;
  --filter-active-border: #71717a;
  --filter-active-bg: #f4f4f5;
  --filter-active-fg: #3f3f46;
}

.device-filter-chip--error {
  --filter-border: #fb923c;
  --filter-bg: #fff7ed;
  --filter-fg: #c2410c;
  --filter-active-border: #ea580c;
  --filter-active-bg: #ffedd5;
  --filter-active-fg: #9a3412;
}

.device-filter-chip--aux {
  --filter-border: #34d399;
  --filter-bg: #ecfdf5;
  --filter-fg: #047857;
  --filter-active-border: #10b981;
  --filter-active-bg: #d1fae5;
  --filter-active-fg: #065f46;
}

.device-filter-count {
  min-width: 1.2em;
  padding: 0 5px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--filter-fg, var(--text)) 12%, var(--filter-bg, var(--bg)));
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  text-align: center;

  .device-filter-chip.active & {
    background: color-mix(in srgb, var(--filter-active-fg, var(--accent)) 16%, var(--filter-active-bg, var(--bg)));
  }
}

.device-list-empty {
  padding: 40px;
  text-align: center;
}

.catalog-auto-retest-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  font-size: 13px;
  margin-top: 0;
}

.catalog-overview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;

  .section-title {
    margin-bottom: 0;
  }
}

.catalog-overview-meta {
  margin: 0 0 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;

  div {
    display: grid;
    grid-template-columns: 48px 1fr;
    gap: 8px;
    font-size: 12px;
  }

  dt {
    color: var(--muted);
    font-weight: 600;
  }

  dd {
    margin: 0;
    line-height: 1.4;
  }
}

.catalog-overview-retest {
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.ai-case-delete-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.ai-nl-case-create {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg, #fff);
}

.ai-nl-case-create-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}

.ai-nl-case-create-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}

.ai-nl-case-create-split {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) minmax(260px, 1.15fr);
  gap: 12px;
  min-height: 220px;
  align-items: stretch;
}

.ai-nl-case-create-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg, #fff);
}

.ai-nl-case-create-right {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 180px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.02);
  overflow: hidden;

  &.is-running {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
  }

  &.is-success {
    border-color: color-mix(in srgb, var(--success) 45%, var(--line));
  }

  &.is-error {
    border-color: color-mix(in srgb, var(--error) 45%, var(--line));
  }
}

.ai-nl-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-nl-field-grow {
  flex: 1;
}

.ai-nl-input.catalog-setting-input,
.ai-nl-textarea.catalog-setting-input {
  width: 100%;
  max-width: none;
  flex-shrink: 1;
  box-sizing: border-box;
}

.ai-nl-textarea {
  min-height: 88px;
  resize: vertical;
  line-height: 1.5;
}

.ai-nl-textarea-sm {
  min-height: 48px;
}

.ai-nl-case-create-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.ai-nl-submit-btn {
  min-width: 148px;
  height: 36px;
  padding: 0 18px;
  font-weight: 600;
}

.ai-nl-process-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
  font-weight: 650;
}

.ai-nl-process-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg);
  color: var(--muted);
  border: 1px solid var(--line);

  &.is-running {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  &.is-success {
    color: var(--success);
    border-color: color-mix(in srgb, var(--success) 35%, var(--line));
    background: color-mix(in srgb, var(--success) 10%, transparent);
  }

  &.is-error {
    color: var(--error);
    border-color: color-mix(in srgb, var(--error) 35%, var(--line));
    background: color-mix(in srgb, var(--error) 10%, transparent);
  }
}

.ai-nl-process-log {
  flex: 1;
  overflow: auto;
  padding: 10px 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 220px;
}

.ai-nl-process-empty {
  margin: auto 0;
  text-align: center;
  font-size: 12px;
  line-height: 1.6;
  padding: 24px 12px;
}

.ai-nl-process-item {
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: var(--bg, #fff);

  &.level-thinking {
    border-left: 3px solid var(--accent);
  }

  &.level-success {
    border-left: 3px solid var(--success);
  }

  &.level-error {
    border-left: 3px solid var(--error);
  }

  &.level-info {
    border-left: 3px solid var(--muted);
  }
}

.ai-nl-process-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.ai-nl-process-time {
  font-size: 11px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.ai-nl-process-level {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.ai-nl-process-msg {
  font-size: 13px;
  line-height: 1.45;
  font-weight: 550;
}

.ai-nl-process-detail {
  margin: 6px 0 0;
  padding: 8px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.04);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--text);
}

@media (max-width: 960px) {
  .ai-nl-case-create-split {
    grid-template-columns: 1fr;
  }
}

.catalog-empty-cases {
  padding: 16px 8px;
  font-size: 13px;
}

.ai-case-delete-checkbox {
  margin-right: 8px;
}

.ea-btn-danger {
  border-color: rgba(239, 68, 68, 0.35);
  color: var(--error);

  &:hover:not(:disabled) {
    background: rgba(239, 68, 68, 0.08);
  }
}

.catalog-monkey-duration {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
}

.catalog-monkey-label {
  font-weight: 600;
  color: var(--text);
}

.catalog-monkey-input {
  width: 90px;
}

.catalog-kernel-code-dir {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
  width: 100%;
  max-width: 720px;
}

.catalog-monkey-help {
  font-size: 12px;
}

.catalog-smoke-settings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.catalog-smoke-help {
  font-size: 12px;
}

.catalog-gms-settings {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.catalog-gms-intro {
  font-size: 12px;
  margin: 0;
}

.catalog-gms-unavailable,
.catalog-unavailable-hint {
  margin: 0;
  font-size: 12px;
  color: #b42318;
}

.catalog-unavailable-tag {
  font-size: 11px;
  color: #b42318;
  border: 1px solid #fecdca;
  background: #fef3f2;
  border-radius: 4px;
  padding: 0 6px;
  line-height: 18px;
}

.catalog-type-group.is-unavailable {
  opacity: 0.78;
}

.catalog-type-group.is-unavailable .case-checkbox {
  pointer-events: none;
}

.gms-tradefed-settings {
  padding: 12px 0 4px;
  border-top: 1px solid var(--line);
}

.gms-tradefed-summary {
  font-size: 12px;
  margin: 0 0 8px;
}

.ota-pretest-checks {
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 32px;
}

.ota-pretest-path-row {
  flex-wrap: wrap;
}

.ota-pretest-config-row,
.ota-pretest-account-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.ota-pretest-config-row .flash-field,
.ota-pretest-account-row .flash-field {
  flex: 1 1 220px;
  min-width: 0;
}

.ota-pretest-account-row {
  margin-top: 10px;
}

.ota-pretest-account-row .ea-btn-sm {
  height: 34px;
}

@media (max-width: 900px) {
  .ota-pretest-checks {
    flex-wrap: wrap;
    gap: 12px 24px;
  }
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

.catalog-setting-input.catalog-kernel-code-input {
  width: 100%;
  min-width: 280px;
  max-width: 720px;
  box-sizing: border-box;
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

.self-check-stack-pane--catalog .catalog-detail-body.detail-container {
  height: 100%;
  min-height: 240px;
}

.self-check-stack-pane--device .device-detail-body.detail-container {
  height: 100%;
  min-height: 0;
}

.self-check-stack .detail-container:not(.catalog-detail-body):not(.device-detail-body) {
  height: auto;
  min-height: 0;
}

.catalog-detail-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.self-check-stack-pane--catalog.catalog-detail-layout {
  height: $catalog-pane-height;
  min-height: $catalog-pane-height;
}

.device-detail-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.self-check-stack-pane--device.device-detail-layout {
  height: $catalog-pane-height;
  min-height: $catalog-pane-height;
  max-height: $catalog-pane-height;
}

.catalog-detail-layout .detail-container {
  flex: 1;
  min-height: 0;
  height: auto;
}

.catalog-panel-loading,
.catalog-panel-error {
  padding: 40px;
  text-align: center;
}

.catalog-overview-card .detail-card-content {
  gap: 8px;
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
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.test-type-btn {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: auto;
  padding: 8px 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
  cursor: pointer;
  transition: all 0.15s;
  text-align: center;
  font-family: inherit;
  font-size: 13px;
  white-space: nowrap;
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

.module-select-checkbox {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  margin: 0 2px 0 0;
  cursor: pointer;
  accent-color: var(--primary, #2563eb);
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
  display: flex;
  align-items: center;
  gap: 8px;
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

  &.editing {
    outline: 1px solid var(--accent);
  }

  &.passed {
    border-left: 3px solid var(--success);
  }

  &.failed {
    border-left: 3px solid var(--error);
  }
}

.case-item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-case-edit-btn {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1;

  &:hover:not(:disabled) {
    color: var(--accent);
    background: var(--accent-soft);
  }

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
}

.case-detail-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.catalog-case-title {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.4;
  color: var(--text);
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

.case-expected .detail-value {
  font-size: 13px;
  line-height: 1.5;
}

.step-item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--line);
  font-size: 13px;

  &:last-child {
    border-bottom: none;
  }

  &.is-current {
    margin: 0 -8px;
    padding: 8px;
    border-radius: 8px;
    border-bottom-color: transparent;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    font-weight: 600;
    color: var(--accent);
  }
}

.case-evidence {
  padding-top: 16px;
  border-top: 1px solid var(--line);
  margin-top: 16px;
}

.evidence-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: 8px;

  th, td {
    padding: 8px 12px;
    text-align: left;
    border: 1px solid var(--line);
  }

  th {
    background: var(--bg-soft);
    font-weight: 600;
    color: var(--text);
  }

  .evidence-pass {
    background: color-mix(in srgb, var(--success, #10b981) 8%, transparent);
  }

  .evidence-fail {
    background: color-mix(in srgb, var(--error, #ef4444) 8%, transparent);
  }

  .status-pass {
    color: var(--success, #10b981);
    font-weight: 600;
  }

  .status-fail {
    color: var(--error, #ef4444);
    font-weight: 600;
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
  .self-check-stack-pane--catalog,
  .self-check-stack-pane--device {
    height: calc(100vh - 32px);
    min-height: calc(100vh - 32px);
    max-height: calc(100vh - 32px);
  }

  .detail-container,
  .catalog-detail-layout,
  .device-detail-layout {
    flex-direction: column;
    height: auto;
    min-height: auto;
  }

  .catalog-detail-layout .detail-container {
    flex: none;
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

    .custom-test-left {
      width: 100%;
      height: calc(100vh - 120px);
      max-height: calc(100vh - 120px);
    }

    .custom-test-right {
      width: 100%;
      max-height: none;
    }
  }
}

.custom-test-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-margin-top: 16px;
}

.custom-test-layout {
  display: flex;
  gap: 16px;
  min-height: 0;

  .custom-test-left {
    flex: 1;
    min-width: 0;
    min-height: 0;
    height: $catalog-pane-height;
    max-height: $catalog-pane-height;
  }

  .custom-test-right {
    width: 360px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    align-self: flex-start;
    max-height: $catalog-pane-height;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
}

.custom-test-case-card {
  height: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.custom-test-case-header {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.custom-test-case-title {
  margin-bottom: 0;
}

.automation-mode-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.automation-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid var(--filter-border, var(--line));
  background: var(--filter-bg, var(--bg));
  color: var(--filter-fg, var(--text));
  font-size: 12px;
  cursor: pointer;
  line-height: 1.2;

  &:hover {
    filter: brightness(0.97);
  }

  &.active {
    border-color: var(--filter-active-border, var(--accent));
    background: var(--filter-active-bg, var(--accent-soft));
    color: var(--filter-active-fg, var(--accent));
  }
}

.automation-filter-chip--all {
  --filter-border: #94a3b8;
  --filter-bg: #f8fafc;
  --filter-fg: #475569;
  --filter-active-border: #64748b;
  --filter-active-bg: #e2e8f0;
  --filter-active-fg: #334155;
}

.automation-filter-chip--full {
  --filter-border: #34d399;
  --filter-bg: #ecfdf5;
  --filter-fg: #047857;
  --filter-active-border: #10b981;
  --filter-active-bg: #d1fae5;
  --filter-active-fg: #065f46;
}

.automation-filter-chip--semi {
  --filter-border: #fbbf24;
  --filter-bg: #fffbeb;
  --filter-fg: #b45309;
  --filter-active-border: #d97706;
  --filter-active-bg: #fef3c7;
  --filter-active-fg: #92400e;
}

.automation-filter-chip--manual {
  --filter-border: #94a3b8;
  --filter-bg: #f1f5f9;
  --filter-fg: #475569;
  --filter-active-border: #64748b;
  --filter-active-bg: #e2e8f0;
  --filter-active-fg: #334155;
}

.automation-filter-count {
  font-size: 11px;
  padding: 0 5px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--filter-fg, var(--text)) 12%, var(--filter-bg, var(--bg)));
}

.auto-mode-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.auto-mode-icon--full {
  background: #d1fae5;
  color: #047857;
}

.auto-mode-icon--semi {
  background: #fef3c7;
  color: #b45309;
}

.auto-mode-icon--manual {
  background: #e2e8f0;
  color: #475569;
}

.auto-mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px 2px 4px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
}

.auto-mode-badge--full {
  background: #ecfdf5;
  color: #047857;
}

.auto-mode-badge--semi {
  background: #fffbeb;
  color: #b45309;
}

.auto-mode-badge--manual {
  background: #f1f5f9;
  color: #475569;
}

.custom-test-case-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;

  .catalog-cases {
    max-height: none;
    overflow-y: visible;
  }
}

.custom-run-summary {
  position: sticky;
  top: 12px;
  z-index: 2;
}

.custom-run-summary-header {
  margin-bottom: 12px;
}

.custom-run-summary-title {
  margin-bottom: 0;
}

.custom-run-meta {
  margin: 0 0 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;

  div {
    display: grid;
    grid-template-columns: 56px 1fr;
    gap: 8px;
    font-size: 13px;
  }

  dt {
    color: var(--muted);
    font-weight: 600;
  }

  dd {
    margin: 0;
    font-weight: 600;
  }
}

.custom-run-start {
  width: 100%;
}

.custom-run-hint {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}

.tdd-manual-priority {
  margin-top: 12px;
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
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  user-select: none;

  &:hover {
    background: var(--bg);
  }

  &.selected {
    background: var(--accent-soft);
  }

  input {
    flex-shrink: 0;
    cursor: pointer;
  }

  .case-name {
    flex: 1;
    min-width: 0;
  }

  .case-tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--accent);
    color: #fff;
  }
}

.subtask-panel {
  margin: 4px 0 8px 24px;
  padding: 8px 12px;
  background: var(--bg-soft, #f5f5f5);
  border-radius: 6px;
  border: 1px solid var(--border, #e0e0e0);

  .subtask-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;

    .subtask-title {
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary, #666);
    }
  }

  .subtask-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 4px;
  }

  .subtask-block:has(.subtask-children) {
    grid-column: 1 / -1;
  }

  .subtask-children {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 4px;
    margin: 4px 0 4px 22px;
    padding: 6px 8px;
    border-left: 2px solid var(--accent, #1976d2);
  }

  .subtask-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    user-select: none;

    &:hover {
      background: var(--bg, #fff);
    }

    &.selected {
      background: var(--accent-soft, #e3f2fd);
    }

    input {
      flex-shrink: 0;
      cursor: pointer;
    }

    .subtask-id {
      font-weight: 500;
      color: var(--accent, #1976d2);
      min-width: 28px;
    }

    .subtask-label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

.case-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--accent);
  color: #fff;
  flex-shrink: 0;
}

.case-tag--platform {
  background: transparent;
  color: var(--ea-text-secondary, #64748b);
  border: 1px solid var(--ea-border, #cbd5e1);
}

.device-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;

  .section-title {
    margin-bottom: 0;
  }
}

.device-refresh-btn {
  flex-shrink: 0;
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

    .device-name { font-weight: 500; flex: 1; min-width: 0; }
    .device-id { font-size: 11px; color: var(--muted); }
    .device-role { font-size: 11px; color: var(--accent); }
    .device-radio-action {
      margin-left: auto;
      flex-shrink: 0;
    }
  }
}


.flash-options {
  .flash-options-title-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .flash-options-toggle {
    font-weight: 600;
  }

  .ota-pretest-config-btn {
    margin-left: auto;
  }
}

.release-upgrade-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.release-upgrade-row {
  display: grid;
  grid-template-columns: 120px minmax(130px, 0.7fr) 110px minmax(220px, 1.5fr);
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
}

.release-upgrade-row--missing {
  border-color: color-mix(in srgb, var(--danger, #dc2626) 40%, var(--line));
  background: color-mix(in srgb, var(--danger, #dc2626) 5%, var(--bg));
}

.release-upgrade-check {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
}

.release-upgrade-version,
.release-upgrade-method {
  font-size: 12px;
  color: var(--muted);
}

.release-upgrade-path-cell {
  display: flex;
  align-items: stretch;
  gap: 8px;
  min-width: 0;
}

.release-upgrade-path {
  flex: 1;
  min-width: 0;
  margin-top: 0;
  font-size: 12px;
}

.release-upgrade-warning {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--danger, #dc2626);
  word-break: break-all;
}

.release-upgrade-warning--standalone {
  grid-column: auto;
}

.release-upgrade-daily-note {
  margin: 0;
  padding: 7px 9px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--accent);
  background: var(--accent-soft);
}

.flash-options-panel {
  margin-top: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 3%, var(--bg));
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.flash-options-hint {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--warning, #b45309);
  background: color-mix(in srgb, var(--warning, #b45309) 10%, var(--bg));
  border-radius: 6px;
}

.flash-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.flash-field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.02em;
}

.flash-path-row {
  display: flex;
  align-items: stretch;
  gap: 8px;

  .flash-path-input {
    flex: 1;
    min-width: 0;
    margin-top: 0;
  }
}

.flash-browse-btn {
  flex-shrink: 0;
  align-self: stretch;
  min-width: 64px;
}

.flash-field--root {
  gap: 8px;
  padding-top: 2px;
}

.flash-root-toggle {
  font-size: 13px;
  color: var(--text);

  .flash-field-hint {
    font-size: 12px;
    font-weight: 400;
    color: var(--muted);
  }
}

.flash-daily-panel {
  padding: 12px;
  border: 1px dashed var(--line-strong, var(--line));
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg) 94%, var(--accent));
}

.flash-daily-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.flash-daily-resolve-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

.flash-clear-btn {
  flex-shrink: 0;
  white-space: nowrap;
  color: var(--warning, #b45309);
  border-color: color-mix(in srgb, var(--warning, #b45309) 35%, var(--line));

  &:hover:not(:disabled) {
    background: color-mix(in srgb, var(--warning, #b45309) 10%, var(--bg));
  }

  &:disabled {
    opacity: 0.55;
  }
}

.flash-daily-meta {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text);
}

.flash-daily-field--full {
  margin-bottom: 4px;
}

.flash-daily-grid {
  display: grid;
  grid-template-columns: 0.8fr 1fr 1.1fr 1.1fr;
  gap: 8px;
}

.flash-daily-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

.flash-daily-input {
  margin-top: 0;
  font-size: 13px;
}

.flash-daily-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted);
  word-break: break-all;
}

.flash-field-hint {
  margin-left: 2px;
}

.flash-market-select {
  width: 100%;
  margin-top: 0;
  padding: 8px 12px;
  font-size: 13px;
}

.flash-progress-card {
  .flash-progress-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;

    .section-title {
      margin-bottom: 0;
    }
  }
}

.flash-progress-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.flash-progress-percent {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
  min-width: 3.2em;
  text-align: right;
}

.flash-progress-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  white-space: nowrap;

  &.is-running {
    color: var(--accent);
    background: var(--accent-soft);
  }

  &.is-success {
    color: var(--success, #16a34a);
    background: color-mix(in srgb, var(--success, #16a34a) 12%, var(--bg));
  }

  &.is-error {
    color: var(--error);
    background: color-mix(in srgb, var(--error) 12%, var(--bg));
  }

  &.is-idle {
    color: var(--muted);
    background: var(--line);
  }
}

.flash-progress-track {
  height: 8px;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}

.flash-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 70%, #fff));
  transition: width 0.35s ease;
  min-width: 0;

  &.is-indeterminate {
    width: 38% !important;
    animation: flash-progress-slide 1.2s ease-in-out infinite;
  }
}

@keyframes flash-progress-slide {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}

.flash-phase-text {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}

.flash-log-panel {
  margin-top: 12px;

  .form-label {
    margin-bottom: 6px;
  }

  .flash-log-content {
    margin: 0;
    padding: 10px 12px;
    max-height: 260px;
    overflow: auto;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 11px;
    line-height: 1.5;
    color: var(--text);
    background: color-mix(in srgb, var(--bg) 88%, #000);
    border: 1px solid var(--line);
    border-radius: 8px;
    white-space: pre-wrap;
  }
}

</style>
