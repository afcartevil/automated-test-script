<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import GerritReviewWorkspace from '@/components/tahp/GerritReviewWorkspace.vue'
import TestPlanningWorkspace from '@/components/tahp/TestPlanningWorkspace.vue'
import {
  listDevices,
  refreshDevices,
  getDeviceDetail,
  setDeviceRole,
  startTest,
  continueTest,
  endTest,
  updateCaseResult,
  getModuleConditions,
  submitManualDecision,
  getPendingManualDecision,
  type DeviceInfo,
  type DeviceRole,
  type DeviceDetail,
  type ModuleCondition,
  type CaseResult
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

function goBack() {
  stopPolling()
  selectedDeviceId.value = null
  selectedDevice.value = null
}

function startPolling() {
  stopPolling()
  // SSE 实时推送
  const baseUrl = window.location.origin
  eventSource.value = new EventSource(`${baseUrl}/api/tahp/device-self-check/events`)
  eventSource.value.addEventListener('case_completed', async (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (!data.deviceId || data.deviceId !== selectedDeviceId.value) return
      const detail = await getDeviceDetail(selectedDeviceId.value!)
      selectedDevice.value = detail
      if (followCurrent.value && detail.session?.isRunning) {
        const session = detail.session
        const mod = session.modules[session.currentModuleIndex]
        if (mod) {
          const prog = session.moduleProgress[`${session.testType}/${mod}`]
          if (prog?.currentCaseIndex) {
            selectedCase.value = `${mod}/${prog.currentCaseIndex}`
          }
        }
      }
      if (!detail.session?.isRunning) {
        stopPolling()
      }
      // 检查是否有待处理的人工决策（SSE manual_confirm 可能丢失）
      const pending = await getPendingManualDecision(selectedDeviceId.value!)
      if (pending) {
        manualDecisionId.value = pending.decisionId
        manualMessage.value = pending.message
        showManualDialog.value = true
      }
    } catch {}
  })
  eventSource.value.addEventListener('test_completed', () => {
    stopPolling()
  })
  eventSource.value.addEventListener('manual_confirm', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      manualDecisionId.value = data.decisionId
      manualMessage.value = data.message
      showManualDialog.value = true
    } catch {}
  })
  eventSource.value.onerror = () => {
    // SSE 断开时降级为轮询
    stopPolling()
    pollingTimer.value = setInterval(async () => {
      if (!selectedDeviceId.value) return
      try {
        const detail = await getDeviceDetail(selectedDeviceId.value)
        selectedDevice.value = detail
        if (followCurrent.value && detail.session?.isRunning) {
          const session = detail.session
          const mod = session.modules[session.currentModuleIndex]
          if (mod) {
            const prog = session.moduleProgress[`${session.testType}/${mod}`]
            if (prog?.currentCaseIndex) {
              selectedCase.value = `${mod}/${prog.currentCaseIndex}`
            }
          }
        }
        if (!detail.session?.isRunning) {
          stopPolling()
          return
        }
        // 轮询检查人工决策
        const pending = await getPendingManualDecision(selectedDeviceId.value)
        if (pending) {
          manualDecisionId.value = pending.decisionId
          manualMessage.value = pending.message
          showManualDialog.value = true
        }
      } catch {}
    }, 1000)
  }
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
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
    stopPolling()
    await endTest(deviceId)
    // 辅测机停止待命后刷新详情页，其他情况回到概览
    if (selectedDevice.value?.device.status === '待命' || selectedDevice.value?.device.role === '辅测机') {
      const detail = await getDeviceDetail(deviceId)
      selectedDevice.value = detail
    } else {
      selectedDevice.value = null
    }
    await loadDevices()
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

async function handleManualDecision(decision: 'pass' | 'fail' | 'ack') {
  if (manualDecisionId.value) {
    await submitManualDecision(manualDecisionId.value, decision)
  }
  showManualDialog.value = false
  manualDecisionId.value = null
  manualMessage.value = ''
}

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
  const modules: Record<string, ModuleCondition[]> = {}
  
  for (const [key, config] of Object.entries(moduleConditions.value)) {
    if (config.testType === testType) {
      if (!modules[config.moduleLabel]) {
        modules[config.moduleLabel] = []
      }
      modules[config.moduleLabel].push(config)
    }
  }

  // 按 MODULE_ORDER 排序为数组
  return Object.entries(modules).sort((a, b) => {
    const orderA = MODULE_ORDER[a[1][0]?.module] ?? 50
    const orderB = MODULE_ORDER[b[1][0]?.module] ?? 50
    return orderA - orderB
  })
})

const isIdle = computed(() => {
  return selectedDevice.value?.device.status === '空闲'
})

const isTestComplete = computed(() => {
  const status = selectedDevice.value?.device.status || ''
  return status.includes('完成')
})

const needsContinue = computed(() => {
  const status = selectedDevice.value?.device.status || ''
  return status.includes('不满足前置条件')
})

// 当前选中的用例结果
const selectedCaseResult = computed((): CaseResult | undefined => {
  if (!selectedCase.value || !selectedDevice.value?.session?.caseResults) return undefined
  const session = selectedDevice.value.session
  const parts = selectedCase.value.split('/')
  const index = parseInt(parts.pop() || '1')
  const module = parts.join('/')
  const testType = selectedDevice.value.device.testType || 'str4'
  const key = `${testType}/${module}/${index}`
  const result = session.caseResults[key]
  // 从 moduleConditions 中获取用例名称
  if (result) {
    const config = moduleConditions.value[`${testType}/${module}`]
    if (config) {
      const caseItem = config.cases.find(c => c.caseIndex === index)
      if (caseItem) {
        result.caseName = caseItem.caseName
      }
    }
  }
  return result
})

onMounted(async () => {
  await loadDevices()
  try {
    moduleConditions.value = await getModuleConditions()
    // 默认展开所有模块
    expandedModules.value = new Set(Object.keys(moduleConditions.value).map(k => moduleConditions.value[k].module))
  } catch (e) {
    console.error('[DeviceSelfCheck] Failed to load module conditions:', e)
  }
})

onUnmounted(() => {
  stopPolling()
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

function selectCaseItem(module: string, caseIndex: number) {
  selectedCase.value = `${module}/${caseIndex}`
  followCurrent.value = false
}

function toggleFollowCurrent() {
  followCurrent.value = !followCurrent.value
  if (followCurrent.value) {
    const s = selectedDevice.value?.session
    if (s) {
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
      :title="selectedDeviceId ? (selectedDevice?.device.deviceName || '设备详情') : 'AI 自检'"
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
          <button v-if="isTestComplete && selectedDevice?.device.role === '测试机'" type="button" class="ea-btn-primary ea-btn-sm">
            打开结果
          </button>
          <button v-if="isTestComplete && selectedDevice?.device.role === '测试机'" type="button" class="ea-btn-ghost ea-btn-sm" @click="handleEndTest(selectedDeviceId!)">
            结束测试
          </button>
          <button v-if="selectedDevice?.device.status === '待命'" type="button" class="ea-btn-ghost ea-btn-sm" @click="handleEndTest(selectedDeviceId!)">
            停止待命
          </button>
        </template>
        <template v-else>
          <button
            type="button"
            class="ea-btn-primary"
            :disabled="loading"
            @click="doRefreshDevices"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            刷新设备
          </button>
        </template>
      </template>
    </EaPageHead>

    <!-- 设备列表视图 -->
    <template v-if="!selectedDeviceId">
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

        <div v-if="devices.length === 0" class="ea-muted" style="padding: 40px; text-align: center;">
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
                  {{ device.status }}
                </span>
              </div>
              <div class="detail-row" v-if="device.testType">
                <span class="detail-label">所属用例</span>
                <span class="detail-value">{{ device.testType === 'str4' ? '转测摸底测试' : '周版本测试' }}</span>
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
                        :class="{ selected: selectedCase === `${config.module}/${caseItem.caseIndex}` }"
                        @click="selectCaseItem(config.module, caseItem.caseIndex)"
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
                          selected: selectedCase === `${config.module}/${caseItem.caseIndex}`,
                          [getCaseItemClass(config, caseItem.caseIndex)]: true
                        }"
                        :style="getCaseItemStyle(config, caseItem.caseIndex)"
                        @click="selectCaseItem(config.module, caseItem.caseIndex)"
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
                    <span class="detail-value">{{ selectedDevice.device.testType ? (selectedDevice.device.testType === 'str4' ? '转测摸底测试' : '周版本测试') : '未分配' }}</span>
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
                      {{ selectedDevice.device.status }}
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

              <!-- 空闲时的操作 -->
              <div v-if="isIdle" class="actions-section">
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
                  <template v-if="selectedCase.startsWith(config.module)">
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
                <button type="button" class="ea-btn-primary" @click="openModifyDialog(selectedCase!)">复测此用例</button>
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
          <button type="button" class="ea-btn-ghost" @click="handleManualDecision('fail')">失败</button>
          <button type="button" class="ea-btn-primary" @click="handleManualDecision('pass')">通过</button>
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
}
</style>
