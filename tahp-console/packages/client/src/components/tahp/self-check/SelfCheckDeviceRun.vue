<script setup lang="ts">
import { computed, inject } from 'vue'
import type { DeviceInfo, DeviceRole } from '@/api/tahp/device-self-check'
import EaCard from '@/components/layout/EaCard.vue'
import { DEVICE_SELF_CHECK_KEY } from './self-check-context'

const {
  viewMode,
  error,
  gerritPreselectCount,
  selectedCases,
  caseCatalogGroups,
  expandedCatalogTypes,
  expandedCatalogModules,
  catalogDetailLoading,
  catalogDetailByModule,
  selectedCatalogCaseKey,
  selectedCatalogItem,
  catalogTypeSettings,
  catalogSettingsSaving,
  selectedCatalogTestType,
  availableCustomDut,
  customTestDutDeviceId,
  customTestAuxDeviceIds,
  availableCustomAux,
  customTestStarting,
  selectedDevice,
  getCaseGroups,
  isIdle,
  canEndTest,
  needsContinue,
  isTestComplete,
  selectedCase,
  selectedCaseResult,
  followCurrent,
  selectedTestType,
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
  toggleAuxDevice,
  handleStartCustomTest,
  openCaseCatalog,
  selectCatalogCase,
  toggleCatalogDetailModule,
  isCatalogDetailModuleExpanded,
  parseManualSteps,
  openCustomTest,
  doRefreshDevices,
  loadDevices,
  handleEndTest,
  toggleModule,
  isModuleExpanded,
  selectCaseItem,
  isCaseSelected,
  getCaseItemClass,
  getCaseItemStyle,
  handleSetRole,
  handleStartTest,
  handleContinueTest,
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
  isSelectedCaseInConfig,
  getSelectedCaseName,
} = inject(DEVICE_SELF_CHECK_KEY)!
void flashLogRef

const DUT_ROLE = '\u6d4b\u8bd5\u673a' as DeviceRole
const AUX_ROLE = '\u8f85\u6d4b\u673a' as DeviceRole
const STATUS_IDLE = '\u7a7a\u95f2'
const STATUS_STANDBY = '\u5f85\u547d'
const STATUS_INITIALIZING = '\u521d\u59cb\u5316\u4e2d'
const WORD_TESTING = '\u6d4b\u8bd5'
const WORD_WAITING = '\u7b49\u5f85'

function isRunning(device: DeviceInfo) {
  const status = device.status as string
  return status.includes(WORD_TESTING) || status.includes(WORD_WAITING) || status === STATUS_INITIALIZING
}

function isIdleDevice(device: DeviceInfo) {
  return (device.status as string) === STATUS_IDLE
}

const runningDevices = computed(() => devices.value.filter(isRunning))
const idleDevices = computed(() => devices.value.filter(isIdleDevice))
const otherDevices = computed(() => devices.value.filter(d => !isRunning(d) && !isIdleDevice(d)))

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
                      <div
                        v-for="c in catalog.cases"
                        :key="c.caseIndex"
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
                        <span class="case-name">{{ c.caseIndex }}. {{ c.caseName }}</span>
                        <span v-if="c.canReuse" class="case-tag">可复用</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </EaCard>
        </div>

        <div class="custom-test-right">
          <EaCard class="custom-run-summary">
            <div class="section-title">执行摘要</div>
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
              </label>
            </div>
          </EaCard>
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
                <span class="module-arrow" :class="{ open: isCatalogDetailModuleExpanded(mod.module) }">&#9654;</span>
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
    <template v-if="viewMode === 'list' && !selectedDevice">
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

          
        <template v-else>
          <div v-if="runningDevices.length" class="device-group">
            <h4 class="group-label">运行中</h4>
            <div class="device-grid">
              <EaCard v-for="device in runningDevices" :key="device.deviceId" class="device-card device-card-running" @click="canSelectDevice(device) && selectDevice(device.deviceId)">
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
          <div v-if="idleDevices.length" class="device-group">
            <h4 class="group-label">空闲</h4>
            <div class="device-grid">
              <EaCard v-for="device in idleDevices" :key="device.deviceId" class="device-card" @click="selectDevice(device.deviceId)">
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
          <div v-if="otherDevices.length" class="device-group">
            <h4 class="group-label">其他状态</h4>
            <div class="device-grid">
              <EaCard v-for="device in otherDevices" :key="device.deviceId" class="device-card" @click="canSelectDevice(device) && selectDevice(device.deviceId)">
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
        </EaCard>
      </template>

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
                  <div class="detail-item" v-if="!isIdle && selectedDevice.device.testStartTime && selectedDevice.device.role !== AUX_ROLE">
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
                  {{ selectedDevice.device.role === AUX_ROLE ? '注册为辅测机' : '开始测试' }}
                </div>

                <!-- 设备角色选择 -->
                <div class="form-group">
                  <span class="form-label">设备角色</span>
                  <div class="role-selector">
                    <button
                      v-for="role in [DUT_ROLE, AUX_ROLE]"
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

                <!-- 刷机选项（device_update） -->
                <div class="form-group flash-options">
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
                      <div v-show="enableRootPkg" class="flash-path-row">
                        <input
                          type="text"
                          class="form-input form-input-inline flash-path-input"
                          placeholder="Root 包路径：zip / scatter xml / 刷机目录"
                          v-model="rootPkgPath"
                        />
                        <button
                          type="button"
                          class="ea-btn-ghost ea-btn-sm flash-browse-btn"
                          :disabled="rootPkgPathPicking"
                          @click.stop="handleBrowseRootPkgPath"
                        >
                          {{ rootPkgPathPicking ? '选择中...' : '浏览' }}
                        </button>
                      </div>
                    </div>
                  </div>
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
                  {{ selectedDevice.device.role === AUX_ROLE ? '开始待命' : '开始测试' }}
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

          <EaCard v-if="showFlashPanel" class="flash-progress-card" style="margin-bottom: 16px;">
            <div class="flash-progress-header">
              <span class="section-title">刷机进度</span>
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
            <p class="flash-phase-text">{{ flashPhase || '等待刷机日志...' }}</p>
            <div class="flash-log-panel">
              <span class="form-label">刷机日志</span>
              <pre ref="flashLogRef" class="flash-log-content">{{ flashLogs.join('\n') }}</pre>
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
</template>

<style scoped lang="scss">

.device-group { margin-bottom: 20px; }
.group-label { margin: 0 0 10px; font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.device-card-running { border-left: 3px solid var(--accent); }
.device-list-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.device-list-title { margin-bottom: 0; }
.detail-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.error-banner { color: var(--error); margin-bottom: 12px; font-size: 13px; }


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
    align-self: flex-start;
  }
}

.custom-run-summary {
  position: sticky;
  top: 12px;
  z-index: 2;
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
  .flash-options-toggle {
    font-weight: 600;
  }
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
