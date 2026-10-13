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
  | '待命'
  | '刷机中'
  | 'T卡升级中'

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
  testType?: 'str4' | 'week' | 'custom' | 'monkey' | 'monkey_check' | 'smoke' | 'ota_upgrade' | 'gms' | 'power' | 'power_feature' | 'thermal' | 'kernel_feature' | 'pipeline_adapt' | 'ai_generated' | 'bitflip'
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

export type AutomationMode = 'full' | 'semi' | 'manual'

/** 芯片平台标签 */
export type ChipPlatform = 'mtk' | 'qcom' | 'unisoc'

export interface CaseInfo {
  caseIndex: number
  caseName: string
  mode: string
  canReuse: boolean
  automationMode?: AutomationMode
  execMode?: 'manual' | 'nl_ui'
  platforms?: ChipPlatform[]
}

export interface ModuleCondition {
  testType: string
  module: string
  moduleLabel: string
  conditions: CaseCondition
  defaultCaseMode: string
  customOnly?: boolean
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
  automationMode?: AutomationMode
  steps: CaseStep[]
  startTime?: string
  endTime?: string
  failureLogDir?: string
  /** 测试证据/详细测量数据（如功耗测量的各项电流值） */
  evidence?: Array<{
    name: string
    expected: string
    actual: string
    ok: boolean
  }>
  /** 额外的详细数据（如原始测量结果、手势状态等） */
  detail?: Record<string, any>
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
  testType: 'str4' | 'week' | 'custom' | 'monkey' | 'monkey_check' | 'smoke' | 'ota_upgrade' | 'gms' | 'power' | 'power_feature' | 'thermal' | 'kernel_feature' | 'pipeline_adapt' | 'ai_generated' | 'bitflip'
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
  errorReason?: string
  prioritizeTddManual?: boolean
}

export interface CaseCatalogItem {
  caseIndex: number
  caseName: string
  canReuse: boolean
  automationMode: AutomationMode
  platforms?: ChipPlatform[]
  subTasks?: Array<{ caseId: string; label: string; children?: Array<{ caseId: string; label: string }> }>
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
  unavailableReason?: string
}

export interface CaseCatalogDetailItem {
  key: string
  testType: string
  module: string
  moduleLabel: string
  caseIndex: number
  caseName: string
  canReuse: boolean
  automationMode: AutomationMode
  platforms?: ChipPlatform[]
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
  enableRootPkg?: boolean
  rootPkgPath?: string
  stageVersion?: string
}

export interface StartTestTcardPayload {
  enabled: boolean
  zipPath?: string
  zipPaths?: string[]
}

export async function startTest(
  deviceId: string,
  testType: 'str4' | 'week' | 'monkey' | 'monkey_check' | 'smoke' | 'ota_upgrade' | 'gms' | 'power' | 'power_feature' | 'thermal' | 'kernel_feature' | 'pipeline_adapt' | 'ai_generated' | 'bitflip',
  flash?: StartTestFlashPayload,
  scheduleKey?: string,
  prioritizeTddManual?: boolean,
  tcard?: StartTestTcardPayload,
  modules?: string[],
): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/start`,
    { testType, flash, scheduleKey, prioritizeTddManual, tcard, modules },
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

export async function pickTcardZipPath(): Promise<PickFlashPathResult> {
  return await tahpPost<PickFlashPathResult>(
    '/api/tahp/device-self-check/tcard/pick-zip',
    {}
  )
}

export async function pickGmsTradefedPath(): Promise<PickFlashPathResult> {
  return await tahpPost<PickFlashPathResult>(
    '/api/tahp/device-self-check/gms/pick-tradefed-path',
    {}
  )
}

export interface DailySystemVersionOption {
  label: string
  value: string
  branchFolder: string
}

export interface DailyFlashOptions {
  deviceId: string
  brand: string
  project: string
  devRoot: string
  devProjectPath: string
  systemVersions: DailySystemVersionOption[]
}

export interface LatestDailyFlashRequest {
  deviceId: string
  /** 省略时服务端自动选择最新 tOS 分支 */
  systemVersion?: string
}

export interface LatestDailyFlashResult {
  deviceId: string
  brand: string
  project: string
  systemVersion: string
  branchFolder: string
  devRoot: string
  devProjectPath: string
  branchPath: string
  versionPath: string
  versionName: string
  releaseNotePath: string
  archivePathCq: string
  resolvedArchivePath: string
  openPath: string
  packagePath: string
  usedIdhFallback: boolean
}

export async function fetchDailyFlashOptions(deviceId: string): Promise<DailyFlashOptions> {
  return await tahpGet<DailyFlashOptions>(
    `/api/tahp/device-self-check/flash/daily-options?deviceId=${encodeURIComponent(deviceId)}`
  )
}

export async function resolveLatestDailyFlashPackage(
  payload: LatestDailyFlashRequest
): Promise<LatestDailyFlashResult> {
  return await tahpPost<LatestDailyFlashResult>(
    '/api/tahp/device-self-check/flash/latest-daily',
    payload
  )
}

export interface AndroidUpgradeStep {
  androidVersion: number
  androidLabel: string
  releaseVersionName: string
  releaseFolder: string
  channel: 'USER' | 'MR' | 'DAILY'
  packagePath: string
  fullZip?: string
  tcardZips: string[]
  sourcePath?: string
  cqTargetPath: string
  needsTransfer: boolean
  available: boolean
  selected: boolean
  unavailableReason?: string
}

export interface ReleaseUpgradePlan {
  deviceId: string
  brand: string
  model: string
  ciModels: string[]
  releaseRoot: string
  ciRoot: string
  steps: AndroidUpgradeStep[]
  dailyHighestAndroidVersion?: number
  dailyTcardOverrideApplied?: boolean
  dailyTcardPackagePath?: string
  dailyTcardSource?: 'DEV' | 'TEST'
  dailyResolveWarning?: string
}

export async function resolveReleaseUpgradePlan(deviceId: string): Promise<ReleaseUpgradePlan> {
  return await tahpPost<ReleaseUpgradePlan>(
    '/api/tahp/device-self-check/tcard/release-upgrade',
    { deviceId },
  )
}

export interface ClearFlashPackageCacheResult {
  flashPackageDir: string
  removedEntries: number
  freedBytes: number
}

export async function clearFlashPackageCache(): Promise<ClearFlashPackageCacheResult> {
  return await tahpPost<ClearFlashPackageCacheResult>(
    '/api/tahp/device-self-check/flash/clear-packages',
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
  customAuxDeviceIds: string[],
  prioritizeTddManual?: boolean,
  caseIds?: Record<string, string[]>,
): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/custom-start`,
    { selectedCases, customAuxDeviceIds, prioritizeTddManual, caseIds },
  )
}

export function deleteAiGeneratedCases(caseKeys: string[]): Promise<{ deleted: string[]; remaining: number }> {
  return tahpPost<{ deleted: string[]; remaining: number }>(
    '/api/tahp/device-self-check/ai-cases/delete',
    { caseKeys },
  )
}

export interface NlUiActionPlanStep {
  op: string
  text?: string
  desc?: string
  rid?: string
  cmd?: string
  direction?: string
  scroll?: boolean
  present?: boolean
  seconds?: number
  name?: string
  [key: string]: unknown
}

export interface CreatedNlUiCase {
  caseKey: string
  caseIndex: number
  caseName: string
  moduleLabel: string
  execMode: 'nl_ui'
  nlDescription: string
  expectedResult: string
  plan?: {
    executable: boolean
    reason?: string
    steps: NlUiActionPlanStep[]
  }
}

export function createAiNlUiCase(payload: {
  caseName: string
  nlDescription: string
  expectedResult?: string
}): Promise<CreatedNlUiCase> {
  return tahpPost<CreatedNlUiCase>(
    '/api/tahp/device-self-check/ai-cases/create',
    payload,
  )
}

export function updateAiNlUiCase(payload: {
  caseKey: string
  caseName: string
  nlDescription: string
  expectedResult?: string
}): Promise<CreatedNlUiCase> {
  return tahpPost<CreatedNlUiCase>(
    '/api/tahp/device-self-check/ai-cases/update',
    payload,
  )
}

export async function continueTest(deviceId: string): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/continue`,
    {}
  )
}

export async function resumeTest(deviceId: string): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/resume`,
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

export async function skipCurrentCase(deviceId: string): Promise<DeviceDetail> {
  return await tahpPost<DeviceDetail>(
    `/api/tahp/device-self-check/devices/${deviceId}/test/skip-case`,
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
  deviceId?: string
  deviceName?: string
  message: string
  passLabel?: string
  failLabel?: string
  mode?: 'decision' | 'ack'
} | null> {
  return await tahpGet<{
    decisionId: string
    deviceId?: string
    deviceName?: string
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
  monkeyDuration?: string
  smokeUsdSkipSpdInfo?: boolean
  gmsTradefedPath?: Record<string, string>
  gmsTimeoutHours?: number
  gmsHostSupported?: boolean
  /** 内核特性/稳定性：Android 源码根（用例 7/11-14） */
  kernelFeatureCodeDir?: string
  /** bitflip 压测：遍历条件下每项重复测试次数（BAT -r 参数），默认 5 */
  bitflipRepeatCount?: number
}

export async function getSettings(): Promise<AutoTestSettings> {
  const data = await tahpGet<AutoTestSettings>('/api/tahp/device-self-check/settings')
  return {
    autoTestEnabled: data?.autoTestEnabled || {},
    autoTestPath: data?.autoTestPath || {},
    autoRetestEnabled: data?.autoRetestEnabled || {},
    autoRetestCount: data?.autoRetestCount || {},
    monkeyDuration: data?.monkeyDuration || '7d',
    smokeUsdSkipSpdInfo: Boolean(data?.smokeUsdSkipSpdInfo),
    gmsTradefedPath: data?.gmsTradefedPath || {},
    gmsTimeoutHours: Number(data?.gmsTimeoutHours) > 0 ? Number(data.gmsTimeoutHours) : 8,
    gmsHostSupported: data?.gmsHostSupported !== false,
    kernelFeatureCodeDir: String(data?.kernelFeatureCodeDir || '').trim(),
    bitflipRepeatCount: Number(data?.bitflipRepeatCount) > 0 ? Number(data.bitflipRepeatCount) : 1,
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

export type PipelineStageStatus = 'idle' | 'queued' | 'running' | 'done' | 'attention'

export interface PipelineStage {
  key: string
  label: string
  status: PipelineStageStatus
  hint?: string
}

export interface SelfCheckPipelineView {
  stages: PipelineStage[]
  updatedAt: string
  runningTests: number
  pendingManual: number
  pendingReports: number
}

export function fetchSelfCheckPipeline(): Promise<SelfCheckPipelineView> {
  return tahpGet<SelfCheckPipelineView>('/api/tahp/device-self-check/pipeline')
}

export type SelfCheckReviewStatus = 'pending' | 'reviewed' | 'retest'

export interface SelfCheckFailedCaseItem {
  caseKey: string
  caseName: string
  module: string
  status: string
  message: string
}

export interface SelfCheckFlashBeforeTestConfig {
  enabled: boolean
  pkgPath?: string
  enableRootPkg?: boolean
  rootPkgPath?: string
  stageVersion?: string
}

export interface SelfCheckTcardBeforeTestConfig {
  enabled: boolean
  zipPath?: string
  zipPaths?: string[]
}

export interface SelfCheckTestConfig {
  monkeyDuration?: string
  smokeUsdSkipSpdInfo?: boolean
  gmsTradefedPath?: Record<string, string>
  gmsTimeoutHours?: number
  kernelFeatureCodeDir?: string
  bitflipRepeatCount?: number
  /** bitflip 生效超时上限（小时）= 20h × -r */
  bitflipTimeoutHours?: number
  autoRetestEnabled?: boolean
  autoRetestCount?: number
  flashBeforeTest?: SelfCheckFlashBeforeTestConfig
  tcardBeforeTest?: SelfCheckTcardBeforeTestConfig
  prioritizeTddManual?: boolean
  selectedCases?: string[]
}

export interface SelfCheckReportSummary {
  reportId: string
  deviceId: string
  deviceName: string
  testType: string
  /** persist.sys.ota_version */
  version?: string
  startTime: string
  endTime?: string
  status: string
  totalCases: number
  passedCases: number
  failedCases: number
  skippedCases: number
  /** 人工待报告补录；通过率分母不含此类 */
  pendingManualCases?: number
  reviewStatus: SelfCheckReviewStatus
  completedAt: string
  reportPath: string
  aiPlanned?: boolean
  scheduleKey?: string
  testConfig?: SelfCheckTestConfig
}

/** bitflip 压测逐轮结果表（CaseResult.detail.bitflip / SelfCheckCaseItem.detail.bitflip） */
export interface BitflipResultDetail {
  columns: string[]
  rows: any[][]
  totalRounds: number
  passedRounds: number
  failedRounds: number
  overallResult: string
  logDir?: string
  xlsxPath?: string
  bstLogPath?: string
  archivedXlsxPath?: string
  archivedBstLogPath?: string
  repeatCount?: number
  javaExitCode?: number
  durationSec?: number
  failureComments?: string[]
}

export interface SelfCheckCaseItem {
  caseKey: string
  caseName: string
  module: string
  testType: string
  caseIndex: number
  status: string
  message: string
  fullAutomation?: boolean
  automationMode?: AutomationMode
  steps?: { stepDesc: string; status: string; timestamp: string }[]
  failureLogDir?: string
  /** 测试证据/详细测量数据（如功耗测量的各项电流值） */
  evidence?: Array<{
    name: string
    expected: string
    actual: string
    ok: boolean
  }>
  /** 用例附加结构化数据（如 bitflip 压测逐轮结果表 detail.bitflip） */
  detail?: Record<string, any>
}

export interface SelfCheckReportDetail extends SelfCheckReportSummary {
  aiSummary: string
  failedCaseItems: SelfCheckFailedCaseItem[]
  allCaseItems: SelfCheckCaseItem[]
  reviewNote?: string
  reviewedAt?: string
}

export function listSelfCheckReports(params?: {
  sinceHours?: number
  pendingOnly?: boolean
}): Promise<SelfCheckReportSummary[]> {
  const qs = new URLSearchParams()
  if (params?.sinceHours != null) qs.set('sinceHours', String(params.sinceHours))
  if (params?.pendingOnly) qs.set('pendingOnly', '1')
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return tahpGet<SelfCheckReportSummary[]>(`/api/tahp/device-self-check/reports${suffix}`)
}

export function getSelfCheckReportDetail(reportId: string): Promise<SelfCheckReportDetail> {
  return tahpGet<SelfCheckReportDetail>(`/api/tahp/device-self-check/reports/${encodeURIComponent(reportId)}`)
}

export function openSelfCheckReportFile(reportId: string): Promise<{ filePath: string }> {
  return tahpPost<{ filePath: string }>(
    `/api/tahp/device-self-check/reports/${encodeURIComponent(reportId)}/open`,
    {},
  )
}

export function openSelfCheckCaseFailureLogs(
  reportId: string,
  caseKey: string,
): Promise<{ dirPath: string }> {
  return tahpPost<{ dirPath: string }>(
    `/api/tahp/device-self-check/reports/${encodeURIComponent(reportId)}/cases/${encodeURIComponent(caseKey)}/open-logs`,
    {},
  )
}

export function openDeviceCaseFailureLogs(
  deviceId: string,
  caseKey: string,
): Promise<{ dirPath: string }> {
  return tahpPost<{ dirPath: string }>(
    `/api/tahp/device-self-check/devices/${encodeURIComponent(deviceId)}/cases/${encodeURIComponent(caseKey)}/open-logs`,
    {},
  )
}

export function submitSelfCheckReportReview(
  reportId: string,
  payload: { status: SelfCheckReviewStatus; note?: string },
): Promise<SelfCheckReportDetail> {
  return tahpPost<SelfCheckReportDetail>(
    `/api/tahp/device-self-check/reports/${encodeURIComponent(reportId)}/review`,
    payload,
  )
}

export function updateReportCaseResult(
  reportId: string,
  payload: { caseKey: string; status: string; message?: string },
): Promise<SelfCheckReportDetail> {
  return tahpPost<SelfCheckReportDetail>(
    `/api/tahp/device-self-check/reports/${encodeURIComponent(reportId)}/case-result`,
    payload,
  )
}

export function retestReportCase(
  reportId: string,
  payload: { caseKey: string; auxDeviceId?: string },
): Promise<{ result: CaseResult; detail: SelfCheckReportDetail }> {
  return tahpPost<{ result: CaseResult; detail: SelfCheckReportDetail }>(
    `/api/tahp/device-self-check/reports/${encodeURIComponent(reportId)}/retest`,
    payload,
  )
}

export interface TPowerStatus {
  connected: boolean
  adbSerial?: string
  label?: string
  message: string
  checkedAt: string
}

export interface TPowerConfig {
  adbSerial?: string
  label?: string
}

export function fetchTPowerStatus(): Promise<TPowerStatus> {
  return tahpGet<TPowerStatus>('/api/tahp/device-self-check/tpower/status')
}

export function fetchTPowerConfig(): Promise<TPowerConfig> {
  return tahpGet<TPowerConfig>('/api/tahp/device-self-check/tpower/config')
}

export function saveTPowerConfig(config: TPowerConfig): Promise<TPowerConfig> {
  return tahpPost<TPowerConfig>('/api/tahp/device-self-check/tpower/config', config)
}
