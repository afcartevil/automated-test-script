import { tahpGet, tahpPost } from './client'

export type DeviceRole = '未分配' | '测试机' | '辅测机'
export type DeviceStatus =
  | '空闲'
  | '初始化中'
  | '等待测试开始'
  | '测试中'
  | '不满足前置条件'
  | '完成(通过)'
  | '完成(失败)'
  | '错误'
  | '占用中'
  | '刷机中'

export interface SimCardInfo {
  slotIndex: number
  operator: string
  phoneNumber: string
  present: boolean
}

export interface DeviceInfo {
  deviceId: string
  deviceName: string
  role: DeviceRole
  status: DeviceStatus
  testType?: 'str4' | 'week' | 'custom'
  currentModule?: string
  simCards: SimCardInfo[]
  testStartTime?: string
  testDuration: number
  resultDir?: string
  isMirroredResult: boolean
}

export interface CaseCondition {
  dutSimCount: number
  auxRequired: number
  auxSimCount: number
}

export interface CaseInfo {
  caseIndex: number
  caseName: string
  mode: string
  canReuse: boolean
}

export interface ModuleCondition {
  testType: string
  module: string
  moduleLabel: string
  conditions: CaseCondition
  defaultCaseMode: string
  cases: CaseInfo[]
}

export interface CaseStep {
  stepDesc: string
  status: string
  timestamp: string
}

export interface CaseResult {
  testType: string
  module: string
  caseIndex: number
  caseName: string
  status: '未开始' | '进行中' | '通过' | '失败' | '部分通过' | '待确认' | 'NA' | '跳过'
  message: string
  fullAutomation: boolean
  steps: CaseStep[]
  startTime?: string
  endTime?: string
}

export interface ModuleProgress {
  module: string
  totalCases: number
  completedCases: number
  passedCases: number
  failedCases: number
  currentCaseIndex?: number
}

export interface TestSession {
  deviceId: string
  testType: 'str4' | 'week' | 'custom'
  modules: string[]
  currentModuleIndex: number
  moduleProgress: Record<string, ModuleProgress>
  caseResults: Record<string, CaseResult>
  startTime?: string
  endTime?: string
  isRunning: boolean
  auxiliaryDevices: string[]
  selectedCases?: string[]
  customAuxDevices?: string[]
}

export interface CaseCatalogItem {
  caseIndex: number
  caseName: string
  canReuse: boolean
}

export interface CaseCatalog {
  key: string
  testType: string
  module: string
  moduleLabel: string
  conditions: {
    dutSimCount: number
    auxRequired: number
    auxSimCount: number
  }
  cases: CaseCatalogItem[]
}

export interface CaseCatalogGroup {
  testType: string
  label: string
  modules: CaseCatalog[]
}

export interface CaseCatalogDetailItem {
  key: string
  testType: string
  module: string
  moduleLabel: string
  caseIndex: number
  caseName: string
  canReuse: boolean
  preconditions: string
  manualSteps: string
  expectedResult: string
}

export interface DeviceDetail {
  device: DeviceInfo
  session?: TestSession
}

// API 调用
export async function listDevices(): Promise<DeviceInfo[]> {
  return await tahpGet<DeviceInfo[]>('/api/tahp/device-self-check/devices')
}

export async function refreshDevices(): Promise<DeviceInfo[]> {
  return await tahpPost<DeviceInfo[]>(
    '/api/tahp/device-self-check/devices/refresh',
    {}
  )
}

export async function getDeviceDetail(deviceId: string): Promise<DeviceDetail> {
  return await tahpGet<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}`
  )
}

export async function setDeviceRole(
  deviceId: string,
  role: DeviceRole
): Promise<DeviceInfo> {
  return await tahpPost<DeviceInfo>(
    `/api/tahp/device-self-check/devices/${deviceId}/role`,
    { role }
  )
}

export interface StartTestFlashPayload {
  enabled: boolean
  pkgPath?: string
  rootPkgPath?: string
  stageVersion?: string
}

export async function startTest(
  deviceId: string,
  testType: 'str4' | 'week',
  flash?: StartTestFlashPayload
): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/start`,
    { testType, flash }
  )
}

export interface PickFlashPathResult {
  canceled: boolean
  path?: string
  error?: string
}

export async function pickFlashPath(): Promise<PickFlashPathResult> {
  return await tahpPost<PickFlashPathResult>(
    '/api/tahp/device-self-check/flash/pick-path',
    {}
  )
}

export async function getCaseCatalogs(): Promise<CaseCatalogGroup[]> {
  return await tahpGet<CaseCatalogGroup[]>('/api/tahp/device-self-check/case-catalogs')
}

export async function getCaseCatalogDetail(testType: string): Promise<CaseCatalogDetailItem[]> {
  return await tahpGet<CaseCatalogDetailItem[]>(
    `/api/tahp/device-self-check/case-catalogs/${testType}/detail`
  )
}

export async function startCustomTest(
  deviceId: string,
  selectedCases: string[],
  customAuxDeviceIds: string[]
): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/custom-start`,
    { selectedCases, customAuxDeviceIds }
  )
}

export async function continueTest(deviceId: string): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/continue`,
    {}
  )
}

export async function getModuleConditions(): Promise<
  Record<string, ModuleCondition>
> {
  return await tahpGet<Record<string, ModuleCondition>>(
    '/api/tahp/device-self-check/module-conditions'
  )
}

export async function endTest(deviceId: string): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/end`,
    {}
  )
}

export async function updateCaseResult(
  deviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  status: string,
  message: string
): Promise<CaseResult> {
  return await tahpPost<CaseResult>(
    `/api/tahp/device-self-check/devices/${deviceId}/case-result`,
    { testType, module, caseIndex, status, message }
  )
}

export async function submitManualDecision(
  decisionId: string,
  decision: string
): Promise<{ success: boolean }> {
  return await tahpPost<{ success: boolean }>(
    '/api/tahp/device-self-check/manual-decision',
    { decisionId, decision }
  )
}

export async function getPendingManualDecision(
  deviceId: string
): Promise<{
  decisionId: string
  message: string
  passLabel?: string
  failLabel?: string
  mode?: 'decision' | 'ack'
} | null> {
  return await tahpGet<{
    decisionId: string
    message: string
    passLabel?: string
    failLabel?: string
    mode?: 'decision' | 'ack'
  } | null>(
    `/api/tahp/device-self-check/devices/${deviceId}/pending-manual-decision`
  )
}

export async function retestCase(
  deviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  auxDeviceId?: string
): Promise<{ success: boolean; data: CaseResult }> {
  return await tahpPost<{ success: boolean; data: CaseResult }>(
    `/api/tahp/device-self-check/devices/${deviceId}/case/retest`,
    { testType, module, caseIndex, auxDeviceId }
  )
}

export interface AutoTestSettings {
  autoTestEnabled: Record<string, boolean>
  autoTestPath: Record<string, string>
  autoRetestEnabled?: Record<string, boolean>
  autoRetestCount?: Record<string, number>
}

export async function getSettings(): Promise<AutoTestSettings> {
  const data = await tahpGet<AutoTestSettings>('/api/tahp/device-self-check/settings')
  return {
    autoTestEnabled: data?.autoTestEnabled || {},
    autoTestPath: data?.autoTestPath || {},
    autoRetestEnabled: data?.autoRetestEnabled || {},
    autoRetestCount: data?.autoRetestCount || {},
  }
}

export async function updateSettings(
  settings: AutoTestSettings
): Promise<{ success: boolean }> {
  return await tahpPost<{ success: boolean }>(
    '/api/tahp/device-self-check/settings',
    settings
  )
}
