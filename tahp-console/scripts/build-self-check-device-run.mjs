import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { execSync } from 'child_process'

const root = path.dirname(fileURLToPath(import.meta.url))
const outPath = path.join(root, '../packages/client/src/components/tahp/self-check/SelfCheckDeviceRun.vue')

const old = execSync('git show HEAD:tahp-console/packages/client/src/views/tahp/DeviceSelfCheckView.vue', {
  cwd: path.join(root, '../..'),
  encoding: 'utf8',
})
const template = old.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? ''
const styles = old.match(/<style scoped lang="scss">([\s\S]*)<\/style>/)?.[1] ?? ''

// Extract device-related template blocks from original and wrap with inject destructuring header
const script = `import { computed, inject } from 'vue'
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
  startTestIntentRole,
  setStartTestIntentRole,
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
  enableTcardUpdate,
  tcardUpdatePath,
  isSelectedCaseInConfig,
  getSelectedCaseName,
} = inject(DEVICE_SELF_CHECK_KEY)!

function isRunning(device: DeviceInfo) {
  const status = device.status as string
  return status.includes('测试') || status.includes('等待') || status === '初始化中'
}

function isIdleDevice(device: DeviceInfo) {
  return (device.status as string) === '空闲'
}

const runningDevices = computed(() => devices.value.filter(isRunning))
const idleDevices = computed(() => devices.value.filter(isIdleDevice))
const otherDevices = computed(() => devices.value.filter(d => !isRunning(d) && !isIdleDevice(d)))

function canSelectDevice(device: DeviceInfo) {
  const role = device.role as string
  const status = device.status as string
  return role !== '辅测机' || status === '待命' || status === '空闲'
}

function displayRole(device: DeviceInfo) {
  return (device.status as string) === '空闲' ? '未分配' : device.role
}
`

// Build template from original sections - replace view conditions
let body = template
  .replace(/[\s\S]*?<!-- 自定义测试视图 -->/, '  <!-- 自定义测试视图 -->')

// Fix overview condition: original used !selectedDeviceId && viewMode !== customTest && caseCatalog
// We use viewMode and selectedDevice only

body = body
  .replace(/!selectedDeviceId && viewMode !== 'customTest' && viewMode !== 'caseCatalog'/g, "viewMode === 'list' && !selectedDevice")
  .replace(/viewMode === 'overview'/g, "viewMode === 'list'")
  .replace(/v-else-if="selectedDevice"/g, 'v-else-if="selectedDevice"')
  .replace(/<template v-if="!selectedDeviceId && viewMode !== 'customTest' && viewMode !== 'caseCatalog'">/g, '<template v-if="viewMode === \'list\' && !selectedDevice">')
const groupedList = `
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
        </template>`

body = body.replace(
  /<div v-else class="device-grid">[\s\S]*?<\/div>\s*<\/EaCard>/,
  groupedList + '\n        </EaCard>',
)

// Remove expandable panels and dialog overlays
body = body.replace(/<SelfCheckExpandablePanel[\s\S]*?<\/SelfCheckExpandablePanel>\s*/g, '')
const dialogIdx = body.indexOf('<!-- 修改用例结果对话框 -->')
if (dialogIdx >= 0) {
  body = body.slice(0, dialogIdx).trimEnd()
}
// Drop page wrapper remnants
body = body.replace(/^<div class="page[^"]*">\s*/, '')
body = body.replace(/\s*<\/div>\s*$/, '')

const extraStyles = `
.device-group { margin-bottom: 20px; }
.group-label { margin: 0 0 10px; font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.device-card-running { border-left: 3px solid var(--accent); }
.device-list-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.device-list-title { margin-bottom: 0; }
.detail-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.error-banner { color: var(--error); margin-bottom: 12px; font-size: 13px; }
`

const vue = `<script setup lang="ts">\n${script}\n</script>\n\n<template>\n${body}\n</template>\n\n<style scoped lang="scss">\n${extraStyles}\n${styles}\n</style>\n`

fs.writeFileSync(outPath, vue, 'utf8')
console.log('Wrote', outPath, vue.length)
