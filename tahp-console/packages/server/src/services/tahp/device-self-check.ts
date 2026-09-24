/**
 * 设备自动化自检服务
 */
import { spawn, spawnSync } from 'child_process'
import { readFileSync, existsSync, writeFileSync, mkdirSync, copyFileSync, cpSync, readdirSync, statSync } from 'fs'
import type { ServerResponse } from 'http'
import { homedir } from 'os'
import { join, resolve, basename, sep } from 'path'
import AdmZip from 'adm-zip'
import {
  type DeviceFlashOptions,
  runDeviceFlash,
  skipOobeForDevice,
} from './device-flash'
import {
  isTcardZipPath,
  runTcardUpdate,
  tcardZipQueue,
  type TcardUpdateOptions,
} from './device-tcard-update'
import { resolvePythonSpawn, tahpPaths } from './paths'
import { ensureMonkeyCheckTestPythonDeps, ensurePowerTestPythonDeps, ensureSddTestPythonDeps } from './self-check-python-deps'
import { applyMonkeyCheckAiReport } from './monkey-tne-report'
import {
  buildSelfCheckDetailPayload,
  formatSelfCheckTestConfigMetaRows,
  isPendingManualReportFillIn,
  openLocalPath,
  PENDING_MANUAL_REPORT_MSG,
  reportAbsoluteDir,
  type SelfCheckCaseItem,
  type SelfCheckFailedCaseItem,
  type SelfCheckTestConfig,
} from './self-check-reports'
import {
  AI_GENERATED_MODULE,
  AI_GENERATED_MODULE_LABEL,
  AI_GENERATED_TEST_TYPE,
  deleteAiGeneratedCases as deletePersistedAiGeneratedCases,
  loadAiGeneratedCaseConfig,
} from './gerrit-ai-generated-cases'
import { createManualNlUiCase, updateManualNlUiCase } from './ai-nl-ui-cases'
import {
  resolveSelfCheckProjectContext,
  uploadSelfCheckReportToCentral,
} from './quality-run-upload'

// 类型定义
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

export type StandardTestType = 'str4' | 'week' | 'monkey' | 'monkey_check' | 'smoke' | 'ota_upgrade' | 'gms' | 'power' | 'power_feature' | 'thermal' | 'kernel_feature' | 'pipeline_adapt' | 'ai_generated'
export type DeviceTestType = StandardTestType | 'custom'

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
  testType?: DeviceTestType
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

/** 用例自动化形态：全自动 / 半自动 / 人工 */
export type AutomationMode = 'full' | 'semi' | 'manual'

export interface CaseInfo {
  caseIndex: number
  caseName: string
  mode: string
  canReuse: boolean
  automationMode?: AutomationMode
  /** AI 生成用例执行方式（nl_ui=全自动，manual=半自动引导） */
  execMode?: 'manual' | 'nl_ui'
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
  /** 静态/运行时自动化形态：全自动 / 半自动 / 人工 */
  automationMode?: AutomationMode
  steps: CaseStep[]
  startTime?: string
  endTime?: string
  /** 失败时导出的设备日志目录（本机绝对路径） */
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
  testType: DeviceTestType
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
  customAuxPromotedIds?: string[]
  initializedPythonModules?: string[]
  flashOptions?: DeviceFlashOptions
  tcardOptions?: TcardUpdateOptions
  scheduleKey?: string
  errorReason?: string
  /** 通信（str4/week tdd）人工用例优先执行；报告/列表仍按原顺序 */
  prioritizeTddManual?: boolean
  /** adb getprop persist.sys.ota_version，测试开始时采集，报告落盘时刷新 */
  otaVersion?: string
  /** 测试开始前的前置配置快照（写入报告 summary/detail） */
  testConfig?: SelfCheckTestConfig
  /** 适配流水线内自检：由流水线指定上报中心的项目/战役归属（覆盖设备/日程解析） */
  qualityUploadProject?: { project_code: string; campaign_id?: string }
  /** 用例失败时待导出的日志（报告落盘后再执行，避免与 getprop 争抢 adb） */
  pendingFailureLogCaseKeys?: string[]
  /**
   * 为 true 时不上报中心 self-check（适配流水线内自检阶段使用；
   * 终态由 adapt-pipeline 整包上报）。独立自检保持默认 false/undefined。
   */
  skipQualityUpload?: boolean
}

export interface CaseCatalogItem {
  caseIndex: number
  caseName: string
  canReuse: boolean
  automationMode: AutomationMode
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
  /** 当前主机不支持启动该大类时的说明（如 Windows 上的 GMS） */
  unavailableReason?: string
}

export interface DeviceDetail {
  device: DeviceInfo
  session?: TestSession
}

// 内存状态存储 - 只使用一个单一的数据源，避免不一致
let devices: Record<string, DeviceInfo> = {}
let testSessions: Record<string, TestSession> = {}
type CaseAbortReason = 'abort' | 'skip'
const activeCaseCleanups: Record<string, (reason?: CaseAbortReason) => void> = {}
let moduleConditions: Record<string, ModuleCondition> = {}

// 配置路径
const SELF_CHECK_DIR = tahpPaths.selfCheckDir
const PYTHON_DIR = join(SELF_CHECK_DIR, 'python')
// 自检长驻进程（monkey watchdog / adb 等）的运行时目录；必须在 dist 之外，
// 否则残留进程的 cwd / 日志句柄会在 Windows 上锁定 dist/server，导致重新构建 EPERM。
const SELF_CHECK_RUNTIME_DIR = join(
  process.env.TAHP_CONSOLE_HOME?.trim() ||
  process.env.HERMES_WEB_UI_HOME?.trim() ||
  join(homedir(), '.tahp-console'),
  'self-check-runtime',
)
const CASE_CONFIG_DIR = join(SELF_CHECK_DIR, 'case_config')
const SETTINGS_PATH = join(SELF_CHECK_DIR, 'settings.json')

interface AutoTestSettings {
  autoTestEnabled: Record<string, boolean>      // key: testType/module
  autoTestPath: Record<string, string>           // key: testType/module
  autoRetestEnabled?: Record<string, boolean>   // key: testType
  autoRetestCount?: Record<string, number>      // key: testType
  monkeyDuration?: string
  /** USD 冒烟：为 true 时 si_run 传 --skip-spd-info */
  smokeUsdSkipSpdInfo?: boolean
  /** GMS：CTS/GTS/VTS 的 xxx-tradefed 可执行文件路径 */
  gmsTradefedPath?: Record<string, string>
  /** @deprecated 兼容旧配置：套件根目录，将自动解析 tools/xxx-tradefed */
  gmsTradefedRoot?: Record<string, string>
  /** GMS 每个子计划（指纹/传感器/多媒体等）超时小时数，默认 8 */
  gmsTimeoutHours?: number
  /** 运行时：当前主机是否支持启动 GMS（不落盘） */
  gmsHostSupported?: boolean
  /** 内核特性/稳定性：Android 源码根（用例 7/11-14 对照） */
  kernelFeatureCodeDir?: string
}

export const GMS_WINDOWS_UNSUPPORTED_MESSAGE = 'Windows 环境不支持 GMS 测试，请在 Linux 主机上运行 cts/gts/vts-tradefed'
const DEFAULT_GMS_TIMEOUT_HOURS = 8
const GMS_TIMEOUT_HOURS_MIN = 1
const GMS_TIMEOUT_HOURS_MAX = 72

export function isGmsSupportedOnHost(platform = process.platform): boolean {
  return platform !== 'win32'
}

export function normalizeGmsTimeoutHours(raw?: number): number {
  const n = Number(raw)
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_GMS_TIMEOUT_HOURS
  return Math.min(GMS_TIMEOUT_HOURS_MAX, Math.max(GMS_TIMEOUT_HOURS_MIN, Math.round(n)))
}

function isGmsCaseKey(caseKey: string): boolean {
  return caseKey === 'gms' || caseKey.startsWith('gms/')
}

function assertGmsRunnable(testType: string, selectedCases?: string[]): void {
  if (isGmsSupportedOnHost()) return
  if (testType === 'gms' || selectedCases?.some(isGmsCaseKey)) {
    throw new Error(GMS_WINDOWS_UNSUPPORTED_MESSAGE)
  }
}

const DEFAULT_MONKEY_DURATION = '7d'
let settings: AutoTestSettings = {
  autoTestEnabled: {},
  autoTestPath: {},
  monkeyDuration: DEFAULT_MONKEY_DURATION,
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
  preconditions: string
  manualSteps: string
  expectedResult: string
}

function normalizeGmsTradefedPath(
  paths?: Record<string, string>,
  legacyRoots?: Record<string, string>,
): Record<string, string> {
  const normalized: Record<string, string> = {}
  const merged: Record<string, string> = {}
  if (legacyRoots && typeof legacyRoots === 'object') {
    for (const suite of ['cts', 'gts', 'vts'] as const) {
      const value = String(legacyRoots[suite] || '').trim()
      if (value) merged[suite] = value
    }
  }
  if (paths && typeof paths === 'object') {
    for (const suite of ['cts', 'gts', 'vts'] as const) {
      const value = String(paths[suite] || '').trim()
      if (value) merged[suite] = value
    }
  }
  return merged
}

function getAutoRetestConfig(testType: string): { enabled: boolean; count: number } {
  if (
    testType === 'monkey' ||
    testType === 'monkey_check' ||
    testType === 'smoke' ||
    testType === 'gms' ||
    testType === 'power' ||
    testType === 'power_feature' ||
    testType === 'thermal' ||
    testType === 'kernel_feature' ||
    testType === 'ai_generated' ||
    testType === 'ota_upgrade'
  ) {
    return { enabled: false, count: 0 }
  }
  return {
    enabled: settings.autoRetestEnabled?.[testType] ?? true,
    count: Math.max(0, settings.autoRetestCount?.[testType] ?? 1),
  }
}

/** 测试启动时快照前置配置，写入报告 JSON */
function snapshotTestConfig(
  testType: DeviceTestType,
  opts: {
    flashOptions?: DeviceFlashOptions
    tcardOptions?: TcardUpdateOptions
    prioritizeTddManual?: boolean
    selectedCases?: string[]
  },
): SelfCheckTestConfig {
  const cfg: SelfCheckTestConfig = {}

  if (opts.flashOptions) {
    cfg.flashBeforeTest = {
      enabled: true,
      pkgPath: opts.flashOptions.pkgPath,
      enableRootPkg: opts.flashOptions.enableRootPkg,
      rootPkgPath: opts.flashOptions.rootPkgPath,
      stageVersion: opts.flashOptions.stageVersion,
    }
  }
  if (opts.tcardOptions) {
    const zipPaths = tcardZipQueue(opts.tcardOptions)
    cfg.tcardBeforeTest = {
      enabled: true,
      zipPath: zipPaths[0],
      zipPaths: zipPaths.length > 1 ? zipPaths : undefined,
    }
  }
  if (opts.prioritizeTddManual) cfg.prioritizeTddManual = true
  if (testType === 'custom' && opts.selectedCases?.length) {
    cfg.selectedCases = [...opts.selectedCases]
  }

  switch (testType) {
    case 'monkey':
      cfg.monkeyDuration = normalizeMonkeyDuration(settings.monkeyDuration)
      break
    case 'smoke':
      cfg.smokeUsdSkipSpdInfo = Boolean(settings.smokeUsdSkipSpdInfo)
      break
    case 'gms':
      cfg.gmsTradefedPath = normalizeGmsTradefedPath(
        settings.gmsTradefedPath,
        settings.gmsTradefedRoot,
      )
      cfg.gmsTimeoutHours = normalizeGmsTimeoutHours(settings.gmsTimeoutHours)
      break
    case 'kernel_feature':
      if (settings.kernelFeatureCodeDir?.trim()) {
        cfg.kernelFeatureCodeDir = settings.kernelFeatureCodeDir.trim()
      }
      break
    case 'custom':
    case 'ai_generated':
    case 'power':
    case 'power_feature':
    case 'thermal':
    case 'ota_upgrade':
      break
    default:
      const retest = getAutoRetestConfig(testType)
      cfg.autoRetestEnabled = retest.enabled
      cfg.autoRetestCount = retest.count
      break
  }

  return cfg
}

function loadCaseInfoList(testType: string, module: string): any[] {
  const caseInfoPath = join(PYTHON_DIR, 'cases', testType, module, 'case_info.json')
  if (!existsSync(caseInfoPath)) return []
  try {
    const list = JSON.parse(readFileSync(caseInfoPath, 'utf-8'))
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function resolveCaseInfoItem(caseInfoList: any[], caseIndex: number): any | null {
  const byIndex = caseInfoList.find(
    (x: any) => (x.case_index ?? x.caseIndex) === caseIndex
  )
  if (byIndex) return byIndex
  if (caseIndex > 0 && caseIndex <= caseInfoList.length) {
    return caseInfoList[caseIndex - 1]
  }
  return null
}

function caseInfoDisplayName(info: any | null | undefined): string {
  if (!info || typeof info !== 'object') return ''
  const name = info['用例名'] || info.case_name || info['名称'] || info.name || info.caseName
  return typeof name === 'string' ? name.trim() : ''
}

function resolveCaseDisplayName(
  testType: string,
  module: string,
  caseIndex: number,
  caseInfoItems?: any | null,
): string {
  const fromInfo = caseInfoDisplayName(caseInfoItems)
  if (fromInfo) return fromInfo
  const fromConfig = moduleConditions[`${testType}/${module}`]?.cases
    .find(c => c.caseIndex === caseIndex)?.caseName?.trim()
  if (fromConfig) return fromConfig
  return `用例${caseIndex}`
}

/**
 * 静态判定用例自动化形态（用于目录展示与筛选，不依赖运行时结果）。
 * - manual：无脚本，或脚本为「需人工测试」占位
 * - semi：脚本含 manual_confirm，或步骤关键词需人工判断（通信 tdd 模块除外）
 * - full：其余有脚本可自动执行的用例
 *
 * 说明：str4/week 通信（tdd）无半自动；跳过占位一律人工，有脚本一律全自动。
 */
export function resolveCaseAutomationMode(
  testType: string,
  module: string,
  caseIndex: number,
  options?: { manualSteps?: string; execMode?: 'manual' | 'nl_ui' },
): AutomationMode {
  if (options?.execMode === 'nl_ui') return 'full'
  if (options?.execMode === 'manual') return 'semi'

  const scriptPath = join(PYTHON_DIR, 'cases', testType, module, `case${caseIndex}.py`)
  if (!existsSync(scriptPath)) return 'manual'

  let scriptContent = ''
  try {
    scriptContent = readFileSync(scriptPath, 'utf-8')
  } catch {
    return 'manual'
  }

  if (scriptContent.includes('需人工测试')) return 'manual'

  // 通信模块（str4/week tdd）不存在半自动：有可执行脚本即全自动
  if (module === 'tdd' && (testType === 'str4' || testType === 'week')) {
    return 'full'
  }

  if (scriptContent.includes('manual_confirm')) return 'semi'

  const steps = options?.manualSteps ?? ''
  if (steps && !isFullAutomation(steps)) return 'semi'
  return 'full'
}

function automationModeLabel(mode?: AutomationMode): string {
  if (mode === 'semi') return '半自动'
  if (mode === 'manual') return '人工'
  return '全自动'
}

export interface TddPriorityCase {
  testType: string
  module: string
  caseIndex: number
  automationMode?: AutomationMode
}

export function isStr4WeekTddModule(testType: string, module: string): boolean {
  return (testType === 'str4' || testType === 'week') && module === 'tdd'
}

/**
 * 仅重排 str4/week 通信（tdd）槽位：人工用例稳定提前，其余相对顺序不变。
 * 非通信项位置不动。不修改入参数组。
 */
export function prioritizeTddManualCases<T extends TddPriorityCase>(caseList: readonly T[]): T[] {
  const result = caseList.slice()
  const tddIndices: number[] = []
  for (let i = 0; i < result.length; i++) {
    if (isStr4WeekTddModule(result[i].testType, result[i].module)) {
      tddIndices.push(i)
    }
  }
  if (tddIndices.length <= 1) return result

  const tddCases = tddIndices.map(i => result[i])
  const manuals: T[] = []
  const rest: T[] = []
  for (const item of tddCases) {
    if (item.automationMode === 'manual') manuals.push(item)
    else rest.push(item)
  }
  const reordered = manuals.concat(rest)
  tddIndices.forEach((slot, j) => {
    result[slot] = reordered[j]
  })
  return result
}

function resolveCaseAutomationModeForPriority(
  testType: string,
  module: string,
  caseIndex: number,
): AutomationMode {
  const meta = moduleConditions[`${testType}/${module}`]?.cases.find(c => c.caseIndex === caseIndex)
  if (meta?.automationMode === 'full' || meta?.automationMode === 'semi' || meta?.automationMode === 'manual') {
    return meta.automationMode
  }
  return resolveCaseAutomationMode(testType, module, caseIndex)
}

function applyTddManualPriority<T extends TddPriorityCase>(caseList: T[]): T[] {
  return prioritizeTddManualCases(
    caseList.map(item => ({
      ...item,
      automationMode: item.automationMode ?? resolveCaseAutomationModeForPriority(
        item.testType,
        item.module,
        item.caseIndex,
      ),
    })),
  )
}

export function shouldAwaitTddManualConfirm(
  prioritizeTddManual: boolean | undefined,
  testType: string,
  module: string,
  automationMode?: AutomationMode,
): boolean {
  return Boolean(prioritizeTddManual)
    && isStr4WeekTddModule(testType, module)
    && automationMode === 'manual'
}

export function buildManualCaseConfirmMessage(options: {
  caseName: string
  preconditions?: string
  manualSteps?: string
  expectedResult?: string
}): string {
  const parts = [`用例「${options.caseName}」需要人工测试。`]
  const preconditions = options.preconditions?.trim()
  if (preconditions) {
    parts.push('', '前置条件：', preconditions)
  }
  const manualSteps = options.manualSteps?.trim()
  if (manualSteps) {
    parts.push('', '测试步骤：', manualSteps)
  }
  const expectedResult = options.expectedResult?.trim()
  if (expectedResult) {
    parts.push('', '期望结果：', expectedResult)
  }
  parts.push('', '请按步骤完成测试后确认结果。')
  return parts.join('\n')
}

/** catalog 标注 manual 的用例：执行阶段不弹窗，报告里待补录 */
function applyDeferredManualCatalogCase(
  result: CaseResult,
  deviceId: string,
  caseKey: string,
  caseInfoItems: any,
  startTime: string,
): CaseResult {
  result.status = '待确认'
  result.message = PENDING_MANUAL_REPORT_MSG
  result.fullAutomation = false
  result.automationMode = 'manual'
  const manualLines = parseTestSteps(caseInfoItems?.['测试步骤'] || '')
  result.steps = [
    { stepDesc: '加载用例信息', status: '完成', timestamp: startTime },
    { stepDesc: '执行阶段已跳过（人工用例，不阻塞自动化）', status: '完成', timestamp: new Date().toISOString() },
    ...manualLines.map(line => ({
      stepDesc: line.stepDesc,
      status: '未开始' as const,
      timestamp: new Date().toISOString(),
    })),
    { stepDesc: '请在「测试报告 → 修改用例结果」中补录', status: '进行中', timestamp: new Date().toISOString() },
  ]
  result.endTime = new Date().toISOString()
  emitEvent('case_completed', { deviceId, caseKey, result })
  return result
}

function enrichModuleCasesAutomationMode(config: ModuleCondition): void {
  const caseInfoList = loadCaseInfoList(config.testType, config.module)
  for (const c of config.cases) {
    // case_config 显式标注优先（半自动等需人工配合的脚本，启发式会误判为 full）
    if (c.automationMode === 'full' || c.automationMode === 'semi' || c.automationMode === 'manual') {
      continue
    }
    const info = resolveCaseInfoItem(caseInfoList, c.caseIndex)
    c.automationMode = resolveCaseAutomationMode(config.testType, config.module, c.caseIndex, {
      manualSteps: info?.['测试步骤'] || '',
      execMode: c.execMode,
    })
  }
}

async function retestFailedAutoCasesInModule(
  deviceId: string,
  testType: string,
  module: string,
  failedCaseIndexes: number[],
  session: TestSession
): Promise<void> {
  const { enabled, count } = getAutoRetestConfig(testType)
  if (!enabled || failedCaseIndexes.length === 0 || count === 0) return

  const moduleKey = `${testType}/${module}`
  console.log(`[device-self-check] Retesting ${failedCaseIndexes.length} failed auto cases for ${moduleKey} (max ${count} attempts each)`)

  for (const caseIndex of failedCaseIndexes) {
    if (!session.isRunning) return
    const caseKey = `${moduleKey}/${caseIndex}`
    const existing = session.caseResults[caseKey]
    if (!existing?.fullAutomation || existing.status !== '失败') continue

    for (let attempt = 0; attempt < count; attempt++) {
      if (!session.isRunning) return
      const result = await runCase(deviceId, testType, module, caseIndex, session)
      session.caseResults[caseKey] = result
      if (result.status === '通过') {
        session.moduleProgress[moduleKey].passedCases++
        session.moduleProgress[moduleKey].failedCases = Math.max(0, session.moduleProgress[moduleKey].failedCases - 1)
      }
      emitEvent('case_completed', { deviceId, caseKey, result })
      if (result.status === '通过') break
    }
  }
}

function loadSettings(): void {
  try {
    if (existsSync(SETTINGS_PATH)) {
      settings = {
        ...settings,
        ...JSON.parse(readFileSync(SETTINGS_PATH, 'utf-8')),
      }
    }
  } catch (e) {
    console.warn('[device-self-check] Failed to load settings, using defaults')
  }
}

function normalizeMonkeyDuration(duration?: string): string {
  const text = String(duration || DEFAULT_MONKEY_DURATION).trim().toLowerCase()
  if (/^\d+$/.test(text)) return text
  if (/^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/.test(text) && /[dhms]/.test(text)) {
    return text
  }
  return DEFAULT_MONKEY_DURATION
}

function saveSettings(): void {
  try {
    writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2), 'utf-8')
  } catch (e) {
    console.error('[device-self-check] Failed to save settings:', e)
  }
}

export function getSettings(): AutoTestSettings {
  return {
    ...settings,
    monkeyDuration: normalizeMonkeyDuration(settings.monkeyDuration),
    smokeUsdSkipSpdInfo: settings.smokeUsdSkipSpdInfo ?? false,
    gmsTradefedPath: normalizeGmsTradefedPath(
      settings.gmsTradefedPath,
      settings.gmsTradefedRoot,
    ),
    gmsTimeoutHours: normalizeGmsTimeoutHours(settings.gmsTimeoutHours),
    gmsHostSupported: isGmsSupportedOnHost(),
    kernelFeatureCodeDir: String(settings.kernelFeatureCodeDir || '').trim(),
  }
}

export function updateSettings(newSettings: AutoTestSettings): void {
  const { gmsHostSupported: _gmsHostSupported, ...persistable } = newSettings
  settings = {
    ...persistable,
    autoTestEnabled: persistable.autoTestEnabled || {},
    autoTestPath: persistable.autoTestPath || {},
    monkeyDuration: normalizeMonkeyDuration(persistable.monkeyDuration),
    smokeUsdSkipSpdInfo: Boolean(persistable.smokeUsdSkipSpdInfo),
    gmsTradefedPath: normalizeGmsTradefedPath(persistable.gmsTradefedPath),
    gmsTimeoutHours: normalizeGmsTimeoutHours(persistable.gmsTimeoutHours),
    kernelFeatureCodeDir: String(persistable.kernelFeatureCodeDir || '').trim(),
  }
  saveSettings()
}

// 加载用例配置
function loadCaseConfigs(): void {
  const configFiles = [
    'str4_tdd.json', 'str4_driver_component.json', 'str4_driver_hardware.json',
    'week_tdd.json', 'week_driver.json',
    'monkey_monkey.json',
    'monkey_check_tne.json',
    'smoke_usd.json',
    'ota_upgrade_ota.json',
    'gms_cts.json',
    'gms_cts_tele.json',
    'gms_gts.json',
    'gms_vts.json',
    'power_current_analysis.json',
    'power_feature_wbs.json',
    'power_feature_p1_check.json',
    'thermal_scheme.json',
    'kernel_feature_stability.json',
    'kernel_feature_memory.json',
    'kernel_feature_sched.json',
    'pipeline_adapt_tp.json',
    'pipeline_adapt_vibrator.json',
    'pipeline_adapt_audio.json',
    'pipeline_adapt_lcm.json',
    'pipeline_adapt_fingerprint.json',
    'pipeline_adapt_tdd.json',
  ]
  
  for (const file of configFiles) {
    const filePath = join(CASE_CONFIG_DIR, file)
    if (!existsSync(filePath)) {
      console.warn(`[device-self-check] Config file not found: ${filePath}`)
      continue
    }
    try {
      const content = readFileSync(filePath, 'utf-8')
      const config = JSON.parse(content) as ModuleCondition
      const key = `${config.testType}/${config.module}`
      enrichModuleCasesAutomationMode(config)
      moduleConditions[key] = config
      console.log(`[device-self-check] Loaded config: ${key}`)
    } catch (e) {
      console.warn(`[device-self-check] Failed to load config: ${file}`, e)
    }
  }
  syncAiGeneratedCaseConfig()
}

function syncAiGeneratedCaseConfig(): void {
  const key = `${AI_GENERATED_TEST_TYPE}/${AI_GENERATED_MODULE}`
  const config = loadAiGeneratedCaseConfig() ?? {
    testType: AI_GENERATED_TEST_TYPE,
    module: AI_GENERATED_MODULE,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 },
    defaultCaseMode: 'solo',
    cases: [],
  }
  // loadAiGeneratedCaseConfig 已 bootstrap 权威目录并镜像到运行时
  enrichModuleCasesAutomationMode(config)
  moduleConditions[key] = config
}

// 跟踪设备是否已经初始化过 SIM 信息
let initializedDeviceIds: Set<string> = new Set()

// 获取默认 SIM 卡信息
function getDefaultSimCards(): SimCardInfo[] {
  return [
    { slotIndex: 0, operator: '', phoneNumber: '', present: false },
    { slotIndex: 1, operator: '', phoneNumber: '', present: false }
  ]
}

// 简单的事件通知
type EventCallback = (data: any) => void
const eventListeners: Record<string, EventCallback[]> = {}
// SSE 客户端列表
const sseClients: Set<ServerResponse> = new Set()

export function onEvent(eventName: string, callback: EventCallback) {
  if (!eventListeners[eventName]) {
    eventListeners[eventName] = []
  }
  eventListeners[eventName].push(callback)
}

export function addSseClient(res: ServerResponse) {
  sseClients.add(res)
  res.on('close', () => sseClients.delete(res))
}

export function removeSseClient(res: ServerResponse) {
  sseClients.delete(res)
}

function emitEvent(eventName: string, data: any) {
  if (eventListeners[eventName]) {
    eventListeners[eventName].forEach((cb) => cb(data))
  }
  // 推送到所有 SSE 客户端
  const payload = `event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`
  for (const res of sseClients) {
    res.write(payload)
  }
}

const ADB_PROBE_TIMEOUT_MS = 12_000
const ADB_LIST_TIMEOUT_MS = 8_000
const ADB_DEFAULT_TIMEOUT_MS = 10_000

const deviceAdbTail = new Map<string, Promise<unknown>>()

function withDeviceAdbLock<T>(deviceId: string, fn: () => Promise<T>): Promise<T> {
  const prev = deviceAdbTail.get(deviceId) ?? Promise.resolve()
  const run = prev.catch(() => undefined).then(fn)
  const done = run.then(
    () => undefined,
    () => undefined,
  )
  deviceAdbTail.set(deviceId, done)
  return run.finally(() => {
    if (deviceAdbTail.get(deviceId) === done) {
      deviceAdbTail.delete(deviceId)
    }
  })
}

async function execAdbCommand(
  args: string[],
  options: { timeoutMs?: number; label?: string } = {},
): Promise<string> {
  const timeoutMs = options.timeoutMs ?? ADB_DEFAULT_TIMEOUT_MS
  return new Promise((resolve) => {
    let proc: ReturnType<typeof spawn> | null = null
    let timeoutId: NodeJS.Timeout | null = null
    let settled = false

    const finish = (value: string) => {
      if (settled) return
      settled = true
      if (timeoutId) clearTimeout(timeoutId)
      if (proc && !proc.killed) {
        try { proc.kill() } catch { /* ignore */ }
      }
      resolve(value)
    }

    timeoutId = setTimeout(() => {
      if (options.label) {
        console.warn(`[device-self-check] ADB ${options.label} timeout after ${timeoutMs}ms`)
      }
      finish('')
    }, timeoutMs)

    try {
      proc = spawn('adb', args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      })

      let stdout = ''
      let stderr = ''
      proc.stdout?.on('data', (data: Buffer) => { stdout += data.toString() })
      proc.stderr?.on('data', (data: Buffer) => { stderr += data.toString() })

      proc.on('close', (code: number) => {
        if (code !== 0 && stderr && options.label) {
          console.warn(`[device-self-check] ADB ${options.label} stderr:`, stderr.trim())
        }
        finish(stdout.trim())
      })
      proc.on('error', (err: Error) => {
        if (options.label) {
          console.warn(`[device-self-check] ADB ${options.label} error:`, err.message)
        }
        finish('')
      })
    } catch (err) {
      console.warn('[device-self-check] Failed to spawn ADB process:', err)
      finish('')
    }
  })
}

/** 刷新设备列表时会重新 ADB 探测 SIM 的状态（含「不满足前置条件」，便于插卡后刷新） */
export const DEVICE_STATUSES_REFRESH_SIM: readonly DeviceStatus[] = [
  '空闲',
  '完成(通过)',
  '完成(失败)',
  '错误',
  '不满足前置条件',
]

export function shouldRefreshSimOnListRefresh(status: string): boolean {
  return (DEVICE_STATUSES_REFRESH_SIM as readonly string[]).includes(status)
}

export function countPresentSimCards(simCards: SimCardInfo[] | undefined): number {
  return (simCards || []).filter(s => s.present).length
}

export function parseDeviceProbeOutput(
  output: string,
  deviceId: string,
): { deviceName: string; simCards: SimCardInfo[] } {
  const simCards: SimCardInfo[] = [
    { slotIndex: 0, operator: '', phoneNumber: '', present: false },
    { slotIndex: 1, operator: '', phoneNumber: '', present: false },
  ]
  const lines = output.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  const model = lines[0] || ''
  const simState = lines[1] || ''
  if (simState) {
    const states = simState.split(',')
    if (states.length >= 1 && states[0].toUpperCase() === 'LOADED') {
      simCards[0].present = true
    }
    if (states.length >= 2 && states[1].toUpperCase() === 'LOADED') {
      simCards[1].present = true
    }
  }
  return {
    deviceName: model || deviceId,
    simCards,
  }
}

/** 重新 ADB 探测并写回设备名称 / SIM；继续测试与前置检查前调用，避免插卡后仍用缓存 */
export async function refreshDeviceProbeInfo(deviceId: string): Promise<DeviceInfo | null> {
  const device = devices[deviceId]
  if (!device) return null
  try {
    const { deviceName, simCards } = await probeDeviceInfo(deviceId)
    device.deviceName = deviceName
    device.simCards = simCards
    initializedDeviceIds.add(deviceId)
    emitEvent('device_updated', { device })
    return device
  } catch (e) {
    console.warn('[device-self-check] Failed to refresh device probe:', deviceId, e)
    return device
  }
}

async function probeDeviceInfo(deviceId: string): Promise<{ deviceName: string; simCards: SimCardInfo[] }> {
  return withDeviceAdbLock(deviceId, async () => {
    let output = await execAdbCommand(
      ['-s', deviceId, 'shell', 'getprop ro.product.model; getprop gsm.sim.state'],
      { timeoutMs: ADB_PROBE_TIMEOUT_MS, label: `probe ${deviceId}` },
    )

    if (!output) {
      const model = await execAdbCommand(
        ['-s', deviceId, 'shell', 'getprop', 'ro.product.model'],
        { timeoutMs: ADB_PROBE_TIMEOUT_MS, label: `getprop model ${deviceId}` },
      )
      const simState = await execAdbCommand(
        ['-s', deviceId, 'shell', 'getprop', 'gsm.sim.state'],
        { timeoutMs: ADB_PROBE_TIMEOUT_MS, label: `getprop sim ${deviceId}` },
      )
      output = [model, simState].filter(Boolean).join('\n')
    }

    const parsed = parseDeviceProbeOutput(output, deviceId)
    const detectedCount = parsed.simCards.filter(c => c.present).length
    console.log(
      `[device-self-check] Device ${deviceId} probe: name=${parsed.deviceName}, `
      + `SIM: ${detectedCount} card(s), Slot0=${parsed.simCards[0].present}, Slot1=${parsed.simCards[1].present}`,
    )
    return parsed
  })
}

// 使用 ADB 获取设备列表
async function getAdbDevices(): Promise<string[]> {
  const stdout = await execAdbCommand(['devices'], {
    timeoutMs: ADB_LIST_TIMEOUT_MS,
    label: 'devices',
  })
  if (!stdout) return []

  const deviceIds: string[] = []
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim()
    if (trimmed && !trimmed.startsWith('List')) {
      const parts = trimmed.split(/\s+/)
      if (parts.length >= 2 && parts[1] === 'device') {
        deviceIds.push(parts[0])
      }
    }
  }
  return deviceIds
}

// 简单的 ADB 命令执行
async function execAdbSimple(args: string[]): Promise<string> {
  return execAdbCommand(args, { timeoutMs: ADB_DEFAULT_TIMEOUT_MS })
}

const OTA_VERSION_PROP = 'persist.sys.ota_version'
const OTA_VERSION_FALLBACK_PROP = 'ro.build.display.id'

/** 设备 OTA 版本（质量验测报告 summary/detail.version） */
async function fetchDeviceOtaVersion(deviceId: string): Promise<string> {
  return withDeviceAdbLock(deviceId, async () => {
    const primary = await execAdbCommand(
      ['-s', deviceId, 'shell', 'getprop', OTA_VERSION_PROP],
      { timeoutMs: ADB_PROBE_TIMEOUT_MS, label: `getprop ${OTA_VERSION_PROP} ${deviceId}` },
    )
    if (primary.trim()) return primary.trim()
    const fallback = await execAdbCommand(
      ['-s', deviceId, 'shell', 'getprop', OTA_VERSION_FALLBACK_PROP],
      { timeoutMs: ADB_PROBE_TIMEOUT_MS, label: `getprop ${OTA_VERSION_FALLBACK_PROP} ${deviceId}` },
    )
    return fallback.trim()
  })
}

/** 报告落盘用：优先实时 getprop，失败则回退 session 缓存（测试开始时采集） */
async function resolveReportOtaVersion(deviceId: string, session: TestSession): Promise<string> {
  const live = await fetchDeviceOtaVersion(deviceId)
  if (live) {
    session.otaVersion = live
    return live
  }
  const cached = session.otaVersion?.trim() || ''
  if (!cached) {
    console.warn(`[device-self-check] OTA version empty (${OTA_VERSION_PROP}) for ${deviceId}`)
  }
  return cached
}

function scheduleTestReportIfNeeded(
  deviceId: string,
  session: TestSession,
  options?: { reportStatus?: string },
): void {
  if (Object.keys(session.caseResults).length === 0) return

  const device = devices[deviceId]
  if (!device) return

  session.isRunning = false
  const testDuration = Math.round(
    (Date.now() - new Date(device.testStartTime || Date.now()).getTime()) / 1000,
  )
  device.testDuration = testDuration

  const reportStatus: DeviceStatus = options?.reportStatus
    ? (options.reportStatus as DeviceStatus)
    : (Object.values(session.caseResults).every(r => r.status === '通过' || r.status === '跳过')
      ? '完成(通过)'
      : '完成(失败)')
  device.status = reportStatus

  emitEvent('device_updated', { device })
  emitEvent('test_completed', { deviceId, session })

  if (session.endTime) {
    resetDeviceToIdleAfterTest(deviceId)
    return
  }

  session.endTime = new Date().toISOString()

  void generateTestReport(deviceId, session, undefined, { reportStatus, testDuration })
    .catch((e) => {
      console.warn('[device-self-check] Failed to generate report:', e)
    })
    .finally(() => {
      resetDeviceToIdleAfterTest(deviceId)
    })
}

function getSessionResultDir(deviceId: string, session: TestSession): string {
  return join(
    tahpPaths.reportsDir,
    'self-check',
    deviceId,
    session.startTime?.replace(/[:.]/g, '-') || '',
  )
}

function sanitizeCaseKeyForPath(caseKey: string): string {
  return caseKey.replace(/[\\/:"*?<>|]+/g, '_')
}

function queueFailureLogExport(session: TestSession, caseKey: string): void {
  if (!session.pendingFailureLogCaseKeys) session.pendingFailureLogCaseKeys = []
  if (!session.pendingFailureLogCaseKeys.includes(caseKey)) {
    session.pendingFailureLogCaseKeys.push(caseKey)
  }
}

async function attachExportedCaseLogDir(
  deviceId: string,
  session: TestSession,
  caseKey: string,
  exportedDir: string,
  notePrefix = '执行日志已导出',
): Promise<void> {
  const latest = session.caseResults[caseKey]
    || Object.values(session.caseResults).find(
      r => formatCaseResultKey(r.testType, r.module, r.caseIndex) === caseKey,
    )
  if (!latest) return
  latest.failureLogDir = exportedDir
  const alreadyNoted = (latest.steps || []).some(
    s => s.stepDesc?.startsWith('执行日志已导出:') || s.stepDesc?.startsWith('失败日志已导出:'),
  )
  if (!alreadyNoted) {
    latest.steps.push({
      stepDesc: `${notePrefix}: ${exportedDir}`,
      status: '完成',
      timestamp: new Date().toISOString(),
    })
  }
  emitEvent('case_completed', { deviceId, caseKey, result: latest })
}

/** @deprecated 兼容旧名 */
async function attachExportedFailureLogDir(
  deviceId: string,
  session: TestSession,
  caseKey: string,
  exportedDir: string,
): Promise<void> {
  await attachExportedCaseLogDir(deviceId, session, caseKey, exportedDir, '失败日志已导出')
}

/** 用例结束后立刻导出，避免只能等整轮报告结束才能「打开日志」 */
async function exportCaseLogsSoon(
  deviceId: string,
  session: TestSession,
  caseKey: string,
  mode: 'execution' | 'failure' = 'failure',
): Promise<void> {
  try {
    const exportedDir = await exportCaseLogsForCase(deviceId, session, caseKey, mode)
    if (!exportedDir) return
    if (session.pendingFailureLogCaseKeys?.length) {
      session.pendingFailureLogCaseKeys = session.pendingFailureLogCaseKeys.filter(k => k !== caseKey)
    }
    await attachExportedCaseLogDir(
      deviceId,
      session,
      caseKey,
      exportedDir,
      mode === 'failure' ? '失败日志已导出' : '执行日志已导出',
    )
  } catch (e) {
    console.warn('[device-self-check] Immediate case log export failed:', caseKey, e)
  }
}

async function exportFailureLogsSoon(
  deviceId: string,
  session: TestSession,
  caseKey: string,
): Promise<void> {
  await exportCaseLogsSoon(deviceId, session, caseKey, 'failure')
}

async function flushPendingFailureLogExports(deviceId: string, session: TestSession): Promise<void> {
  const keys = session.pendingFailureLogCaseKeys
  if (!keys?.length) return
  session.pendingFailureLogCaseKeys = []
  for (const caseKey of keys) {
    try {
      const exportedDir = await exportCaseLogsForCase(deviceId, session, caseKey, 'failure')
      if (!exportedDir) continue
      await attachExportedCaseLogDir(deviceId, session, caseKey, exportedDir, '失败日志已导出')
    } catch (e) {
      console.warn('[device-self-check] Background failure log export failed:', caseKey, e)
    }
  }
}

/**
 * 导出用例日志（成功/失败策略一致）：
 * - case_result.txt 执行摘要
 * - 内核稳定性：checker 本地 evidence + 用例工作目录产物
 * - 不再从设备额外 pull logcat / mobilelog / netlog / TNE
 */
async function exportCaseLogsForCase(
  deviceId: string,
  session: TestSession,
  caseKey: string,
  mode: 'execution' | 'failure' = 'failure',
): Promise<string | null> {
  try {
    const logRoot = mode === 'failure' ? 'failure-logs' : 'case-logs'
    const caseDir = join(getSessionResultDir(deviceId, session), logRoot, sanitizeCaseKeyForPath(caseKey))
    mkdirSync(caseDir, { recursive: true })

    const result = session.caseResults[caseKey]
      || Object.values(session.caseResults).find(
        r => formatCaseResultKey(r.testType, r.module, r.caseIndex) === caseKey,
      )
    if (result) {
      const summary = [
        `caseKey=${caseKey}`,
        `status=${result.status}`,
        `message=${result.message || ''}`,
        `startTime=${result.startTime || ''}`,
        `endTime=${result.endTime || ''}`,
        '',
        '--- steps ---',
        ...(result.steps || []).map(
          s => `[${s.timestamp || ''}] ${s.status || ''} ${s.stepDesc || ''}`,
        ),
      ].join('\n')
      writeFileSync(join(caseDir, 'case_result.txt'), `${summary}\n`, 'utf-8')
    }

    // 内核稳定性：保留执行期本地产物（不依赖设备仍在线，也不再二次拉全机日志）
    const parts = caseKey.split('/')
    if (parts[0] === 'kernel_feature' && parts[2]) {
      const caseId = String(parts[2])
      const workspaceRoot = join(PYTHON_DIR, 'tools', 'stability_checker', 'workspace')
      const evidenceSrc = join(workspaceRoot, 'evidence', caseId)
      const evidenceDest = join(caseDir, 'stability-evidence')
      try {
        if (existsSync(evidenceSrc)) {
          mkdirSync(evidenceDest, { recursive: true })
          cpSync(evidenceSrc, evidenceDest, { recursive: true })
        }
      } catch (e) {
        console.warn('[device-self-check] copy stability evidence failed:', e)
      }

      // case8 / case11 / case19_hung 等执行工作目录
      for (const name of [`case${caseId}`, `case${caseId}_hung`]) {
        const workSrc = join(workspaceRoot, name)
        if (!existsSync(workSrc)) continue
        const workDest = join(caseDir, 'stability-workdir', name)
        try {
          mkdirSync(join(caseDir, 'stability-workdir'), { recursive: true })
          cpSync(workSrc, workDest, { recursive: true })
        } catch (e) {
          console.warn('[device-self-check] copy stability workdir failed:', name, e)
        }
      }
    }

    return caseDir
  } catch (e) {
    console.warn('[device-self-check] Failed to export case logs:', deviceId, caseKey, e)
    return null
  }
}

async function exportFailureLogsForCase(
  deviceId: string,
  session: TestSession,
  caseKey: string,
): Promise<string | null> {
  return exportCaseLogsForCase(deviceId, session, caseKey, 'failure')
}

// 获取 SIM 卡运营商
async function getSimOperator(deviceId: string, slot: number): Promise<string> {
  return withDeviceAdbLock(deviceId, async () => {
    const operator = await execAdbCommand(
      ['-s', deviceId, 'shell', 'getprop', 'gsm.sim.operator.alpha'],
      { timeoutMs: ADB_PROBE_TIMEOUT_MS, label: `getprop operator ${deviceId}` },
    )
    return operator || '未知运营商'
  })
}

// 异步更新设备信息（不阻塞主流程）
async function updateDeviceInfoAsync(deviceId: string): Promise<void> {
  try {
    // 异步获取设备名称和 SIM 卡信息，不阻塞
    const { deviceName, simCards } = await probeDeviceInfo(deviceId)
    // 更新设备信息
    if (devices[deviceId]) {
      devices[deviceId].deviceName = deviceName
      devices[deviceId].simCards = simCards
      initializedDeviceIds.add(deviceId)
      emitEvent('device_updated', { device: devices[deviceId] })
    }
    console.log('[device-self-check] Device info updated:', deviceId)
  } catch (e) {
    console.warn('[device-self-check] Failed to update device info:', deviceId, e)
  }
}

// 设备管理
export async function listDevices(): Promise<DeviceInfo[]> {
  try {
    // 优先返回已有设备，快速响应
    if (Object.keys(devices).length > 0) {
      return Object.values(devices)
    }
    
    console.log('[device-self-check] Initial load devices...')
    const adbDeviceIds = await getAdbDevices()
    console.log('[device-self-check] Found ADB devices:', adbDeviceIds)
    
    // 首次加载：并行获取所有设备信息
    const deviceInfos = await Promise.all(
      adbDeviceIds.map(async (deviceId) => {
        const { deviceName, simCards } = await probeDeviceInfo(deviceId)
        return { deviceId, deviceName, simCards }
      })
    )

    const newDevices: Record<string, DeviceInfo> = {}
    for (const info of deviceInfos) {
      newDevices[info.deviceId] = {
        deviceId: info.deviceId,
        deviceName: info.deviceName,
        role: '未分配',
        status: '空闲',
        simCards: info.simCards,
        testDuration: 0,
        isMirroredResult: false
      }
      initializedDeviceIds.add(info.deviceId)
    }

    devices = newDevices
    console.log('[device-self-check] Device list updated, total devices:', Object.values(devices).length)
  } catch (e) {
    console.error('[device-self-check] Error listing devices:', e)
  }
  return Object.values(devices)
}

export async function refreshDevices(): Promise<DeviceInfo[]> {
  console.log('[device-self-check] Forced refresh devices...')
  try {
    const adbDeviceIds = await getAdbDevices()
    console.log('[device-self-check] Found ADB devices:', adbDeviceIds)

    // 并行获取所有新设备的名称和 SIM 信息
    const newDeviceIds = adbDeviceIds.filter(id => !devices[id])
    const newDeviceInfos = await Promise.all(
      newDeviceIds.map(async (deviceId) => {
        const { deviceName, simCards } = await probeDeviceInfo(deviceId)
        return { deviceId, deviceName, simCards }
      })
    )

    // 并行更新可刷新状态设备的名称与 SIM（含「不满足前置条件」，便于插卡后刷新）
    const existingIds = adbDeviceIds.filter(
      id => devices[id] && shouldRefreshSimOnListRefresh(devices[id].status),
    )
    const existingUpdates = await Promise.all(
      existingIds.map(async (deviceId) => {
        const { deviceName, simCards } = await probeDeviceInfo(deviceId)
        return { deviceId, deviceName, simCards }
      })
    )

    const newDevices: Record<string, DeviceInfo> = {}

    for (const info of newDeviceInfos) {
      newDevices[info.deviceId] = {
        deviceId: info.deviceId,
        deviceName: info.deviceName,
        role: '未分配',
        status: '空闲',
        simCards: info.simCards,
        testDuration: 0,
        isMirroredResult: false
      }
      initializedDeviceIds.add(info.deviceId)
    }

    for (const update of existingUpdates) {
      if (devices[update.deviceId]) {
        newDevices[update.deviceId] = {
          ...devices[update.deviceId],
          deviceName: update.deviceName,
          simCards: update.simCards,
        }
      }
    }

    for (const id of adbDeviceIds) {
      if (devices[id] && !newDevices[id]) {
        newDevices[id] = devices[id]
      }
    }

    // 保留正在测试中的设备
    for (const [id, device] of Object.entries(devices)) {
      if (['测试中', '初始化中', '刷机中', '等待测试开始', '待命', '占用中'].includes(device.status)) {
        newDevices[id] = device
      }
    }

    devices = newDevices
    console.log('[device-self-check] Device list refreshed, total devices:', Object.values(devices).length)
  } catch (e) {
    console.error('[device-self-check] Error refreshing devices:', e)
  }

  const result = Object.values(devices)
  emitEvent('device_list_updated', { devices: result })
  return result
}

export async function setDeviceRole(
  deviceId: string,
  role: DeviceRole
): Promise<DeviceInfo | null> {
  try {
    if (devices[deviceId]) {
      devices[deviceId].role = role
      emitEvent('device_updated', { device: devices[deviceId] })
      return devices[deviceId]
    }
    return null
  } catch (e) {
    console.error('Error setting device role:', e)
    return null
  }
}

// 测试控制

// 前置条件检查
async function checkPreconditions(
  deviceId: string,
  moduleKey: string
): Promise<{ status: 'passed' | 'waiting_aux' | 'failed'; reason: string; auxDeviceIds?: string[] }> {
  const config = moduleConditions[moduleKey]
  if (!config) {
    return { status: 'failed', reason: `未知模块: ${moduleKey}` }
  }

  const device = devices[deviceId]
  if (!device) {
    return { status: 'failed', reason: '设备不存在' }
  }

  const cond = config.conditions

  // 检查 SIM 卡数量（先重新探测，避免插卡后仍用内存缓存）
  if (cond.dutSimCount > 0) {
    await refreshDeviceProbeInfo(deviceId)
    const refreshed = devices[deviceId] || device
    const simCount = countPresentSimCards(refreshed.simCards)
    if (simCount < cond.dutSimCount) {
      return { status: 'failed', reason: `需要${cond.dutSimCount}张SIM卡，当前${simCount}张` }
    }
  }

  // 检查辅测机
  if (cond.auxRequired > 0) {
    // 优先查找显式标记为辅测机的设备
    const explicitAux = Object.values(devices).filter(
      d => d.deviceId !== deviceId && d.role === '辅测机' && (d.status === '空闲' || d.status === '占用中' || d.status === '待命')
    )

    // 查找同为测试机且等待同一模块的设备（互相作为辅测机）
    const peerTesters = Object.values(devices).filter(
      d => d.deviceId !== deviceId && d.role === '测试机' && d.status === '等待测试开始' && d.currentModule === config.module
    )

    const allCandidates = [...explicitAux, ...peerTesters]

    if (allCandidates.length < cond.auxRequired) {
      return { status: 'waiting_aux', reason: `等待辅测机（需要${cond.auxRequired}台，当前${allCandidates.length}台）` }
    }
    return { status: 'passed', reason: '前置条件满足', auxDeviceIds: allCandidates.slice(0, cond.auxRequired).map(d => d.deviceId) }
  }

  return { status: 'passed', reason: '前置条件满足' }
}

// 获取模块列表
function getModulesForTestType(testType: StandardTestType): string[] {
  if (testType === 'str4') return ['driver_component', 'driver_hardware', 'tdd']
  if (testType === 'monkey') return ['monkey']
  if (testType === 'monkey_check') return ['tne']
  if (testType === 'smoke') return ['usd']
  if (testType === 'ota_upgrade') return ['ota']
  if (testType === 'gms') return ['cts', 'gts', 'vts']
  if (testType === 'power') return ['current_analysis']
  if (testType === 'power_feature') return ['wbs', 'p1_check']
  if (testType === 'thermal') return ['scheme']
  if (testType === 'kernel_feature') return ['stability', 'memory', 'sched']
  if (testType === 'pipeline_adapt') return ['tp', 'vibrator', 'audio', 'lcm', 'fingerprint', 'tdd']
  if (testType === 'ai_generated') return [AI_GENERATED_MODULE]
  return ['driver', 'tdd']
}

// 执行单个用例
async function runCase(
  deviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  session: TestSession
): Promise<CaseResult> {
  const caseKey = `${testType}/${module}/${caseIndex}`
  const startTime = new Date().toISOString()
  const result: CaseResult = {
    testType,
    module,
    caseIndex,
    caseName: resolveCaseDisplayName(testType, module, caseIndex),
    status: '进行中',
    message: '',
    fullAutomation: false,
    automationMode: 'manual',
    steps: [{
      stepDesc: '正在加载用例...',
      status: '进行中',
      timestamp: startTime
    }],
    startTime
  }

  if (!session.isRunning) {
    result.status = '跳过'
    result.message = '测试已终止'
    result.steps = [{
      stepDesc: '测试已终止',
      status: '跳过',
      timestamp: startTime,
    }]
    result.endTime = new Date().toISOString()
    session.caseResults[caseKey] = result
    emitEvent('case_completed', { deviceId, caseKey, result })
    return result
  }

  // 立即存入 session，让前端实时可见
  session.caseResults[caseKey] = result
  // 推送初始状态
  emitEvent('case_completed', { deviceId, caseKey, result })

  console.log(`[device-self-check] Running case: ${caseKey}`)

  // 加载用例信息
  let caseInfoItems: any = null
  const caseInfoPath = join(PYTHON_DIR, 'cases', testType, module, 'case_info.json')
  if (existsSync(caseInfoPath)) {
    try {
      const caseInfoList = JSON.parse(readFileSync(caseInfoPath, 'utf-8'))
      if (Array.isArray(caseInfoList)) {
        caseInfoItems = resolveCaseInfoItem(caseInfoList, caseIndex)
        if (caseInfoItems) {
          result.caseName = resolveCaseDisplayName(testType, module, caseIndex, caseInfoItems)
          const testSteps = caseInfoItems['测试步骤'] || ''
          if (testSteps) {
            result.steps = parseTestSteps(testSteps)
          }
        }
      }
    } catch {}
  }

  const caseMeta = moduleConditions[`${testType}/${module}`]?.cases.find(c => c.caseIndex === caseIndex)
  result.automationMode = caseMeta?.automationMode ?? resolveCaseAutomationMode(testType, module, caseIndex, {
    manualSteps: caseInfoItems?.['测试步骤'] || '',
    execMode: caseMeta?.execMode,
  })
  result.fullAutomation = result.automationMode === 'full'

  if (caseMeta?.automationMode === 'manual') {
    return applyDeferredManualCatalogCase(result, deviceId, caseKey, caseInfoItems, startTime)
  }

  if (shouldAwaitTddManualConfirm(session.prioritizeTddManual, testType, module, result.automationMode)) {
    const message = buildManualCaseConfirmMessage({
      caseName: result.caseName,
      preconditions: caseInfoItems?.['前置条件'] || '',
      manualSteps: caseInfoItems?.['测试步骤'] || '',
      expectedResult: caseInfoItems?.['期望结果'] || '',
    })
    result.steps = [
      { stepDesc: '加载用例信息', status: '完成', timestamp: startTime },
      { stepDesc: '等待人工测试确认', status: '进行中', timestamp: new Date().toISOString() },
    ]
    await awaitTddManualConfirm({ deviceId, caseKey, result, message })
    return result
  }

  // 检查是否有对应的 .py 脚本
  const caseScript = join(PYTHON_DIR, 'cases', testType, module, `case${caseIndex}.py`)
  if (!existsSync(caseScript)) {
    if (result.automationMode === 'manual') {
      return applyDeferredManualCatalogCase(result, deviceId, caseKey, caseInfoItems, startTime)
    }
    result.status = '待确认'
    result.message = '需人工测试'
    result.automationMode = 'manual'
    result.fullAutomation = false
    result.steps = [
      { stepDesc: '加载用例信息', status: '完成', timestamp: startTime },
      { stepDesc: '此用例无自动化脚本', status: '未开始', timestamp: new Date().toISOString() },
    ]
    emitEvent('case_completed', { deviceId, caseKey, result })

    // 暂停等待人工确认（非 catalog manual 的无脚本用例）
    const decisionId = `pending_${caseKey}_${Date.now()}`
    const pendingPromise = new Promise<string>((res) => {
      pendingManualDecisions[decisionId] = {
        deviceId,
        caseKey,
        message: `用例"${result.caseName}"需要人工测试。\n请手动完成测试后确认结果。`,
        resolve: (decision: string) => {
          res(decision)
          delete pendingManualDecisions[decisionId]
          applyManualDecisionToResult(result, decision, {
            passMessage: '人工测试通过',
            failMessage: '人工测试失败',
          })
          result.steps.push({
            stepDesc: `人工确认: ${result.message}`,
            status: result.status,
            timestamp: new Date().toISOString()
          })
          result.endTime = new Date().toISOString()
          emitEvent('case_completed', { deviceId, caseKey, result })
        }
      }
    })
    emitEvent('manual_confirm', {
      decisionId,
      deviceId,
      deviceName: devices[deviceId]?.deviceName || deviceId,
      caseKey,
      message: `用例"${result.caseName}"需要人工测试。\n请手动完成测试后确认结果。`
    })
    await pendingPromise
    return result
  }

  result.steps.push({ stepDesc: '正在执行用例脚本...', status: '进行中', timestamp: new Date().toISOString() })
  emitEvent('case_completed', { deviceId, caseKey, result })

  // 构建 device_info 传给 Python 脚本
  const deviceInfo = buildDeviceInfo(deviceId, testType, module, session)

  // 监听实时步骤更新（Python 每次推送完整累计步骤）
  const stepHandler = (data: any) => {
    if (data.caseKey === caseKey && data.step) {
      const rawSteps = data.step.split('\n').filter((s: string) => s.trim())
      if (rawSteps.length === 0) return

      // 保留前2条固定步骤（加载用例、执行脚本），后面为实时步骤
      result.steps = result.steps.slice(0, 2)

      for (let i = 0; i < rawSteps.length; i++) {
        const raw = rawSteps[i]
        const isLast = i === rawSteps.length - 1
        // 解析 "标题-成功" 或 "标题-失败" 或 "标题"（无后缀=进行中）
        let label: string
        let stepStatus: string
        if (raw.endsWith('-成功')) {
          label = raw.slice(0, -3)
          stepStatus = '完成'
        } else if (raw.endsWith('-失败')) {
          label = raw.slice(0, -3)
          stepStatus = '失败'
        } else {
          label = raw
          stepStatus = isLast ? '进行中' : '完成'
        }
        const suffix = stepStatus === '完成' ? ' ✓' : stepStatus === '失败' ? ' ✗' : ''
        result.steps.push({
          stepDesc: label + suffix,
          status: stepStatus as '进行中' | '完成' | '失败' | '错误' | '未开始',
          timestamp: new Date().toISOString()
        })
      }
      emitEvent('case_completed', { deviceId, caseKey, result })
    }
  }
  onEvent('step_update', stepHandler)

  try {
    const pythonResult = await execPythonCase(deviceId, testType, module, caseIndex, deviceInfo)

    result.status = pythonResult.status === 'pass' ? '通过'
      : pythonResult.status === '部分pass' ? '部分通过'
      : pythonResult.status === 'fail' ? '失败'
      : pythonResult.status === 'pending' ? '待确认'
      : pythonResult.status === 'na' ? 'NA'
      : pythonResult.status === 'skip' ? '跳过'
      : '失败'
    result.message = pythonResult.message || ''
    // 传递测试证据/详细测量数据（如功耗测量的各项电流值）
    if (pythonResult.evidence) {
      result.evidence = pythonResult.evidence
    }
    if (pythonResult.detail) {
      result.detail = pythonResult.detail
    }
    // monkey结果检查：Python 已完成 TNE 采集/解压，Node 侧用 AI 对 native crash 归类并合成最终汇报
    if (testType === 'monkey_check' && result.status !== '失败') {
      await applyMonkeyCheckAiReport(getSessionResultDir(deviceId, session), result)
    }
    if (
      result.status === '待确认'
      && (result.message.includes('报告中补录') || result.message.includes('需人工测试'))
    ) {
      // 与 catalog 人工项一致：执行阶段不弹窗，报告里补录
      result.automationMode = 'manual'
      result.fullAutomation = false
    } else if ((pythonResult.message || '').includes('需人工测试')) {
      result.automationMode = 'manual'
      result.fullAutomation = false
    } else if (
      pythonResult.fullAutomation === false
      && result.automationMode === 'full'
      && !(module === 'tdd' && (testType === 'str4' || testType === 'week'))
    ) {
      result.automationMode = 'semi'
      result.fullAutomation = false
    } else {
      result.fullAutomation = result.automationMode === 'full' && pythonResult.fullAutomation !== false
    }
    result.steps.push({
      // 结论字段已含完整明细；子步骤只记一行摘要，避免把「预期 vs 实际」再贴一遍
      stepDesc: `结果: ${result.status}${(result.message || '').includes('\n') ? ` — ${(result.message || '').split('\n')[0]}` : (result.message ? ` — ${result.message}` : '')}`,
      status: result.status,
      timestamp: new Date().toISOString()
    })
    // 待确认且非「报告补录」类：暂停测试，等待前端人工决策
    if (result.status === '待确认' && !isPendingManualReportFillIn(result)) {
      const decisionId = `pending_${caseKey}_${Date.now()}`
      const pendingMessage = result.message || '需人工评判'
      const isSupportConfirm = /是否支持|请判断是否支持/.test(pendingMessage)
      const passLabel = isSupportConfirm ? '支持' : undefined
      const failLabel = isSupportConfirm ? '不支持' : undefined
      const pendingPromise = new Promise<string>((res) => {
        const handler = (decision: string) => {
          res(decision)
          delete pendingManualDecisions[decisionId]
        }
        pendingManualDecisions[decisionId] = {
          deviceId,
          caseKey,
          message: pendingMessage,
          passLabel,
          failLabel,
          resolve: (decision: string) => {
            handler(decision)
            if (decision === 'skip') {
              applyUserSkipToResult(result)
            } else if (isSupportConfirm && decision !== 'pass') {
              // 更新结果：支持确认选「不支持」记为 NA
              result.status = 'NA'
              result.message = '设备不支持（NA）'
            } else {
              result.status = decision === 'pass' ? '通过' : '失败'
              result.message = decision === 'pass' ? '人工确认通过' : '人工确认失败'
            }
            result.steps.push({
              stepDesc: `人工确认: ${result.message}`,
              status: result.status,
              timestamp: new Date().toISOString()
            })
            emitEvent('case_completed', { deviceId, caseKey, result })
          }
        }
      })
      emitEvent('manual_confirm', {
        decisionId,
        deviceId,
        deviceName: devices[deviceId]?.deviceName || deviceId,
        caseKey,
        message: pendingMessage,
        passLabel,
        failLabel,
      })
      await pendingPromise
    }
  } catch (e: any) {
    result.status = '失败'
    result.message = e?.message || '执行异常'
    result.steps.push({ stepDesc: `执行异常: ${e?.message || '未知错误'}`, status: '错误', timestamp: new Date().toISOString() })
  } finally {
    // 移除 step_update 监听器
    const idx = eventListeners['step_update']?.indexOf(stepHandler)
    if (idx !== undefined && idx >= 0) {
      eventListeners['step_update']?.splice(idx, 1)
    }
  }

  result.endTime = new Date().toISOString()
  if (result.status === '失败') {
    queueFailureLogExport(session, caseKey)
    void exportCaseLogsSoon(deviceId, session, caseKey, 'failure')
  } else if (result.status === '通过' || result.status === '部分通过') {
    void exportCaseLogsSoon(deviceId, session, caseKey, 'execution')
  }
  emitEvent('case_completed', { deviceId, caseKey, result })
  return result
}

// 解析测试步骤文本为子步骤
function parseTestSteps(stepsText: string): CaseStep[] {
  const now = new Date().toISOString()
  const lines = stepsText.split('\n').filter((l: string) => l.trim())
  if (lines.length <= 1) {
    return [{ stepDesc: stepsText.trim(), status: '未开始', timestamp: now }]
  }
  return lines.map((line: string) => ({
    stepDesc: line.replace(/^\d+[\.\、\s]+/, '').trim(),
    status: '未开始' as const,
    timestamp: now
  }))
}

// 构建设备信息传给 Python 脚本
function buildDeviceInfo(
  deviceId: string,
  testType?: string,
  module?: string,
  session?: TestSession
): any {
  const dut = devices[deviceId]
  if (!dut) return { DUT: [] }

  const config = testType && module ? moduleConditions[`${testType}/${module}`] : undefined
  const auxDevices: any[] = []

  const pushAuxDevice = (id: string) => {
    const dev = devices[id]
    if (!dev) return
    auxDevices.push({
      device_id: id,
      sim_cards: dev.simCards.map(s => ({
        slot_index: s.slotIndex,
        present: s.present,
        operator: s.operator,
        phone_number: s.phoneNumber,
        subscription_id: 0
      }))
    })
  }

  if (session?.auxiliaryDevices && session.auxiliaryDevices.length > 0) {
    for (const auxId of session.auxiliaryDevices) {
      pushAuxDevice(auxId)
    }
  } else if (config && config.conditions.auxRequired > 0) {
    for (const [id, dev] of Object.entries(devices)) {
      if (
        id !== deviceId &&
        dev.role === '辅测机' &&
        (dev.status === '空闲' || dev.status === '待命' || dev.status === '占用中')
      ) {
        pushAuxDevice(id)
        if (auxDevices.length >= config.conditions.auxRequired) break
      }
    }
  }

  return {
    DUT: [{
      device_id: deviceId,
      sim_cards: dut.simCards.map(s => ({
        slot_index: s.slotIndex,
        present: s.present,
        operator: s.operator,
        phone_number: s.phoneNumber,
        subscription_id: 0
      }))
    }],
    Auxiliary: auxDevices,
    monkeyDuration: normalizeMonkeyDuration(settings.monkeyDuration),
    smokeUsdSkipSpdInfo: Boolean(settings.smokeUsdSkipSpdInfo),
    gmsTradefedPath: normalizeGmsTradefedPath(
      settings.gmsTradefedPath,
      settings.gmsTradefedRoot,
    ),
    ...(testType === 'kernel_feature' && settings.kernelFeatureCodeDir?.trim()
      ? { code_dir: settings.kernelFeatureCodeDir.trim() }
      : {}),
    module_init_done: Boolean(
      testType &&
      module &&
      session?.initializedPythonModules?.includes(`${testType}/${module}`)
    ),
    ...(session?.startTime
      ? (() => {
          const resultDir = getSessionResultDir(deviceId, session)
          const thermalLogParentDir = join(resultDir, 'thermal')
          try {
            mkdirSync(thermalLogParentDir, { recursive: true })
          } catch {
            // ignore
          }
          return { resultDir, thermalLogParentDir, thermLogParentDir: thermalLogParentDir }
        })()
      : {}),
  }
}

/** Windows 上 kill() 只杀直接子进程，用例常再 spawn adb/monkey/tradefed，须杀整棵进程树 */
function killProcessTree(proc: { pid?: number; killed?: boolean; kill: (signal?: NodeJS.Signals | number) => boolean } | null): void {
  if (!proc || proc.killed) return
  const pid = proc.pid
  if (pid && process.platform === 'win32') {
    let taskkillOk = false
    try {
      const result = spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore',
        timeout: 8_000,
      })
      taskkillOk = result.status === 0
    } catch { /* ignore */ }
    if (!taskkillOk) {
      try { proc.kill() } catch { /* ignore */ }
    }
    return
  }
  try {
    proc.kill('SIGKILL')
  } catch {
    try { proc.kill() } catch { /* ignore */ }
  }
}

function spawnPythonProcess(
  args: string[],
  options: {
    cwd?: string
    label?: string
    timeoutMs?: number
    onStdout?: (chunk: Buffer) => void
    onStderr?: (chunk: Buffer) => void
    onClose?: (code: number) => void
    onError?: (err: Error) => void
  } = {}
): { proc: ReturnType<typeof spawn>; cleanup: () => void } {
  const { command, prefixArgs } = resolvePythonSpawn()
  let proc: ReturnType<typeof spawn> | null = null
  let timeoutId: NodeJS.Timeout | null = null

  const cleanup = () => {
    if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
    killProcessTree(proc)
  }

  if (options.timeoutMs && options.timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      if (options.label) {
        console.warn(`[device-self-check] ${options.label} timeout after ${options.timeoutMs}ms`)
      }
      cleanup()
      options.onClose?.(-1)
    }, options.timeoutMs)
  }

  proc = spawn(command, [...prefixArgs, ...args], {
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: false,
    cwd: options.cwd || PYTHON_DIR,
    env: {
      ...process.env,
      PYTHONPATH: PYTHON_DIR,
      PYTHONUTF8: '1',
      TAHP_SELF_CHECK_RUNTIME_DIR: SELF_CHECK_RUNTIME_DIR,
    },
    windowsHide: true,
  })

  proc.stdout?.on('data', (data: Buffer) => options.onStdout?.(data))
  proc.stderr?.on('data', (data: Buffer) => options.onStderr?.(data))
  proc.on('close', (code: number) => {
    cleanup()
    options.onClose?.(code ?? -1)
  })
  proc.on('error', (err: Error) => {
    cleanup()
    options.onError?.(err)
    options.onClose?.(-1)
  })

  return { proc, cleanup }
}

// 执行 Python 内联脚本
async function execPythonScript(
  script: string,
  args: string[],
  timeoutMs = 60000,
  label = 'python-script'
): Promise<void> {
  return new Promise((resolve) => {
    try {
      spawnPythonProcess(['-c', script, ...args], {
        label,
        timeoutMs,
        onStderr: (data) => {
          const msg = data.toString().trim()
          if (msg) console.warn(`[device-self-check] ${label} stderr: ${msg}`)
        },
        onClose: () => resolve(),
        onError: () => resolve(),
      })
    } catch {
      resolve()
    }
  })
}

async function stopMonkeyForDevice(deviceId: string): Promise<void> {
  const script = join(PYTHON_DIR, 'tools', 'monkey_usd', 'monkey_test.py')
  if (!existsSync(script)) return

  return new Promise((resolve) => {
    try {
      spawnPythonProcess([script, '-s', deviceId, 'stop'], {
        cwd: join(PYTHON_DIR, 'tools', 'monkey_usd'),
        label: `monkey-stop/${deviceId}`,
        timeoutMs: 30_000,
        onStderr: (data) => {
          const msg = data.toString().trim()
          if (msg) console.warn(`[device-self-check] monkey-stop stderr: ${msg}`)
        },
        onClose: () => resolve(),
        onError: () => resolve(),
      })
    } catch {
      resolve()
    }
  })
}

const POWER_TOOLS_DIR = join(PYTHON_DIR, 'tools', 'tpower_auto')
const POWER_OUTPUT_DIR = join(POWER_TOOLS_DIR, 'output')
const THERM_TOOLS_DIR = join(PYTHON_DIR, 'tools', 'tpytest_dzppt_therm')
const THERM_DEFAULT_RUNTIME_LOG = join(THERM_TOOLS_DIR, '.runtime', 'log')
const POWER_EXEC_TIMEOUT_MS = 86_400_000 // 24h，功耗任务由飞书表驱动，长时间运行
const POWER_FEATURE_EXEC_TIMEOUT_MS = 30 * 60_000 // 功耗特性自检（含 APK 安装）
const KERNEL_FEATURE_EXEC_TIMEOUT_MS = 60 * 60_000 // 稳定性 checklist（case8 fulldump+开机等待+pull）
const KERNEL_FEATURE_SPD_EXEC_TIMEOUT_MS = 10 * 60_000 // 内存/调度 SPD 分项（短时 adb 检查）
const THERM_EXEC_TIMEOUT_MS = 86_400_000 // 24h，温升方案用例集较长

function summarizePowerReportFromXlsx(): {
  ok: boolean
  total: number
  failed: number
  passed: number
  message: string
  path?: string
} | null {
  const script = join(POWER_TOOLS_DIR, 'run_power_env.py')
  if (!existsSync(script)) return null
  const { command, prefixArgs } = resolvePythonSpawn()
  const result = spawnSync(
    command,
    [...prefixArgs, script, 'summarize-xlsx'],
    { cwd: POWER_TOOLS_DIR, encoding: 'utf-8', windowsHide: true },
  )
  const stdout = (result.stdout || '').trim()
  if (!stdout) return null
  try {
    const line = stdout.split('\n').filter(Boolean).pop() || ''
    return JSON.parse(line)
  } catch {
    return null
  }
}

function finalizePowerCaseResults(deviceId: string, session: TestSession): void {
  if (session.testType !== 'power') return
  const summary = summarizePowerReportFromXlsx()
  if (!summary) return

  for (const [caseKey, result] of Object.entries(session.caseResults)) {
    if (!caseKey.startsWith('power/current_analysis/')) continue
    if (result.status !== '进行中' && result.endTime) continue

    const failed = summary.failed ?? 0
    const total = summary.total ?? 0
    const message = summary.message || result.message
    result.status = total > 0 && failed === 0 ? '通过' : '失败'
    result.message = message
    result.endTime = new Date().toISOString()
    if (summary.path) {
      result.steps.push({
        stepDesc: `报告: ${summary.path}`,
        status: '完成',
        timestamp: result.endTime,
      })
    }
    result.steps.push({
      stepDesc: `结果: ${message}`,
      status: result.status,
      timestamp: result.endTime,
    })
    emitEvent('case_completed', { deviceId, caseKey, result })
  }
}

function findLatestPowerReportXlsx(): string | null {
  if (!existsSync(POWER_OUTPUT_DIR)) return null
  let latest: { path: string; mtime: number } | null = null
  for (const name of readdirSync(POWER_OUTPUT_DIR)) {
    if (!name.toLowerCase().endsWith('.xlsx')) continue
    const filePath = join(POWER_OUTPUT_DIR, name)
    try {
      const mtime = statSync(filePath).mtimeMs
      if (!latest || mtime > latest.mtime) {
        latest = { path: filePath, mtime }
      }
    } catch {
      // skip unreadable files
    }
  }
  return latest?.path ?? null
}

function listThermSessionDirs(parent: string): string[] {
  if (!existsSync(parent)) return []
  return readdirSync(parent)
    .map(name => join(parent, name))
    .filter(full => {
      try {
        return statSync(full).isDirectory() && /_therm_/i.test(basename(full))
      } catch {
        return false
      }
    })
    .sort((a, b) => {
      try {
        return statSync(b).mtimeMs - statSync(a).mtimeMs
      } catch {
        return 0
      }
    })
}

function copyThermArtifactsToReport(resultDir: string): string | null {
  const destParent = join(resultDir, 'thermal')
  mkdirSync(destParent, { recursive: true })

  let sessions = [
    ...listThermSessionDirs(destParent),
    ...listThermSessionDirs(join(resultDir, 'therm')),
  ]
  if (!sessions.length) {
    const latest = listThermSessionDirs(THERM_DEFAULT_RUNTIME_LOG)[0]
    if (latest) {
      const dest = join(destParent, basename(latest))
      try {
        cpSync(latest, dest, { recursive: true })
      } catch (err) {
        console.warn('[device-self-check] copy therm runtime failed:', err)
      }
      sessions = listThermSessionDirs(destParent)
    }
  }

  const latestSession = sessions[0]
  if (!latestSession) return null

  const xlsx = join(latestSession, 'testReport.xlsx')
  if (existsSync(xlsx)) {
    try {
      copyFileSync(xlsx, join(resultDir, 'thermal_testReport.xlsx'))
    } catch {
      // ignore
    }
  }
  return latestSession
}

function sessionHasThermCases(session: TestSession): boolean {
  const testType = String(session.testType)
  if (testType === 'thermal' || testType === 'therm') return true
  return Object.keys(session.caseResults).some(key => key.startsWith('thermal/') || key.startsWith('therm/'))
}

function copyPowerArtifactToReport(resultDir: string): string | null {
  const latest = findLatestPowerReportXlsx()
  if (!latest) return null
  const dest = join(resultDir, 'test_report.xlsx')
  copyFileSync(latest, dest)
  return dest
}

async function stopPowerForDevice(deviceId: string): Promise<void> {
  const script = join(POWER_TOOLS_DIR, 'run_power_env.py')
  if (!existsSync(script)) return

  return new Promise((resolve) => {
    try {
      spawnPythonProcess([script, 'stop', '-s', deviceId], {
        cwd: POWER_TOOLS_DIR,
        label: `power-stop/${deviceId}`,
        timeoutMs: 30_000,
        onStderr: (data) => {
          const msg = data.toString().trim()
          if (msg) console.warn(`[device-self-check] power-stop stderr: ${msg}`)
        },
        onClose: () => resolve(),
        onError: () => resolve(),
      })
    } catch {
      resolve()
    }
  })
}

/**
 * BFF 关闭兜底：停止所有已知设备的 monkey / power 后台进程。
 * 避免 EA 退出后 watchdog / adb 成为孤儿继续运行（锁定构建产物、设备侧测试失控）。
 */
export async function stopSelfCheckBackgroundProcesses(): Promise<void> {
  const deviceIds = new Set<string>([...Object.keys(devices), ...Object.keys(testSessions)])
  if (!deviceIds.size) return
  const tasks: Promise<void>[] = []
  for (const deviceId of deviceIds) {
    tasks.push(stopMonkeyForDevice(deviceId))
    tasks.push(stopPowerForDevice(deviceId))
  }
  await Promise.allSettled(tasks)
}

const MODULE_INIT_RUNNER = `
import importlib.util
import json
import sys

init_path = sys.argv[1]
device_info = json.loads(sys.argv[2])
spec = importlib.util.spec_from_file_location("module_init", init_path)
if spec is None or spec.loader is None:
    sys.exit(0)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if hasattr(mod, "run"):
    mod.run(device_info=device_info)
`

const DEVICE_INIT_RUNNER = `
import json
import sys
from utils.device_init import init_devices_for_test

device_info = json.loads(sys.argv[1])
init_devices_for_test(device_info)
`

// 设备初始化：亮屏解锁、设置亮屏时间等
async function execDeviceInit(deviceId: string, session?: TestSession): Promise<void> {
  const device = devices[deviceId]
  if (!device) return

  const deviceInfo = buildDeviceInfo(deviceId, undefined, undefined, session)
  const allIds = [
    ...(deviceInfo.DUT || []).map((d: { device_id: string }) => d.device_id),
    ...(deviceInfo.Auxiliary || []).map((d: { device_id: string }) => d.device_id),
  ].filter(Boolean)

  await Promise.all(
    allIds.map(id =>
      execAdbSimple(['-s', id, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '1800000'])
    )
  )

  console.log(`[device-self-check] Device init: ${deviceId}, devices=${allIds.join(', ')}`)
  await execPythonScript(DEVICE_INIT_RUNNER, [JSON.stringify(deviceInfo)], 60000, 'device-init')
}

// 执行 Python 模块初始化
function markPythonModuleInitialized(
  session: TestSession | undefined,
  testType: string,
  module: string
): void {
  if (!session) return
  const key = `${testType}/${module}`
  if (!session.initializedPythonModules) {
    session.initializedPythonModules = []
  }
  if (!session.initializedPythonModules.includes(key)) {
    session.initializedPythonModules.push(key)
  }
}

async function execPythonInit(
  deviceId: string,
  testType: string,
  module: string,
  session?: TestSession
): Promise<void> {
  const initScript = join(PYTHON_DIR, 'cases', testType, module, 'init.py')
  if (!existsSync(initScript)) {
    markPythonModuleInitialized(session, testType, module)
    return
  }

  if (!devices[deviceId]) return

  const deviceInfo = buildDeviceInfo(deviceId, testType, module, session)
  console.log(`[device-self-check] Module init: ${testType}/${module}`)
  await execPythonScript(
    MODULE_INIT_RUNNER,
    [initScript, JSON.stringify(deviceInfo)],
    180000,
    `module-init/${testType}/${module}`
  )
  markPythonModuleInitialized(session, testType, module)
}

const CASE_EXEC_TIMEOUT_MS = 5 * 60_000
const SMOKE_USD_EXEC_TIMEOUT_MS = 3_600_000
const MANUAL_CONFIRM_TIMEOUT_MS = 30 * 60_000

function resolveCaseExecTimeoutMs(testType: string, module: string): number {
  if (testType === 'smoke' && module === 'usd') {
    const raw = Number(process.env.TAHP_SMOKE_USD_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : SMOKE_USD_EXEC_TIMEOUT_MS
  }
  if (testType === 'gms' && ['cts', 'cts_tele', 'gts', 'vts'].includes(module)) {
    const raw = Number(process.env.TAHP_GMS_TIMEOUT_MS)
    if (Number.isFinite(raw) && raw > 0) return raw
    return normalizeGmsTimeoutHours(settings.gmsTimeoutHours) * 3_600_000
  }
  if (testType === 'power' && module === 'current_analysis') {
    const raw = Number(process.env.TAHP_POWER_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : POWER_EXEC_TIMEOUT_MS
  }
  if (testType === 'power_feature' && module === 'wbs') {
    const raw = Number(process.env.TAHP_POWER_FEATURE_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : POWER_FEATURE_EXEC_TIMEOUT_MS
  }
  if (testType === 'power_feature' && module === 'p1_check') {
    const raw = Number(process.env.TAHP_POWER_FEATURE_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : POWER_FEATURE_EXEC_TIMEOUT_MS
  }
  if (testType === 'kernel_feature' && module === 'stability') {
    const raw = Number(process.env.TAHP_KERNEL_FEATURE_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : KERNEL_FEATURE_EXEC_TIMEOUT_MS
  }
  if (testType === 'kernel_feature' && (module === 'memory' || module === 'sched')) {
    const raw = Number(process.env.TAHP_KERNEL_FEATURE_SPD_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : KERNEL_FEATURE_SPD_EXEC_TIMEOUT_MS
  }
  if ((testType === 'thermal' || testType === 'therm') && module === 'scheme') {
    const raw = Number(process.env.TAHP_THERMAL_TIMEOUT_MS || process.env.TAHP_THERM_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : THERM_EXEC_TIMEOUT_MS
  }
  if (testType === 'ai_generated' && module === AI_GENERATED_MODULE) {
    const raw = Number(process.env.TAHP_NL_UI_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : 180_000
  }
  if (testType === 'monkey_check' && module === 'tne') {
    const raw = Number(process.env.TAHP_MONKEY_CHECK_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : 10 * 60_000
  }
  return CASE_EXEC_TIMEOUT_MS
}

// 执行 Python 用例脚本
async function execPythonCase(
  deviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  deviceInfo: any
): Promise<{ status: string; message: string; steps: CaseStep[]; fullAutomation?: boolean; evidence?: CaseResult['evidence']; detail?: Record<string, any> }> {
  return new Promise((resolve) => {
    const runCaseScript = join(PYTHON_DIR, 'run_case.py')
    const deviceInfoJson = JSON.stringify(deviceInfo)
    const caseKey = `${testType}/${module}/${caseIndex}`

    const { command, prefixArgs } = resolvePythonSpawn()
    let proc: any = null
    let timeoutId: NodeJS.Timeout | null = null
    let settled = false
    let abortReason: CaseAbortReason | undefined

    const abortFinishResult = () => ({
      status: abortReason === 'skip' ? 'skip' : 'fail',
      message: abortReason === 'skip' ? '用户跳过' : '测试已终止',
      steps: [] as CaseStep[],
    })

    const finish = (result: { status: string; message: string; steps: CaseStep[]; fullAutomation?: boolean; evidence?: CaseResult['evidence']; detail?: Record<string, any> }) => {
      if (settled) return
      settled = true
      if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
      if (testType === 'power' && module === 'current_analysis') {
        void stopPowerForDevice(deviceId)
      }
      killProcessTree(proc)
      delete activeCaseCleanups[deviceId]
      resolve(result)
    }

    /** 结束测试 / 跳过 / 超时杀进程：先杀树，再保留短超时兜底 settle（避免清掉长超时后 Promise 永久挂起） */
    const cleanup = (reason?: CaseAbortReason) => {
      if (reason) abortReason = reason
      if (testType === 'power' && module === 'current_analysis') {
        void stopPowerForDevice(deviceId)
      }
      killProcessTree(proc)
      if (settled) {
        if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
        return
      }
      if (timeoutId) clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        finish(abortFinishResult())
      }, 5_000)
    }

    activeCaseCleanups[deviceId] = cleanup

    const caseTimeoutMs = resolveCaseExecTimeoutMs(testType, module)

    const scheduleTimeout = (ms: number, message: string) => {
      if (timeoutId) clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        finish({ status: 'fail', message, steps: [] })
      }, ms)
    }

    scheduleTimeout(caseTimeoutMs, `用例执行超时(${Math.round(caseTimeoutMs / 1000)}s)`)

    try {
      proc = spawn(command, [
        ...prefixArgs,
        runCaseScript,
        '--test-type', testType,
        '--module', module,
        '--case-index', String(caseIndex),
        '--device-info', deviceInfoJson
      ], {
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: false,
        cwd: PYTHON_DIR,
        env: { ...process.env, PYTHONPATH: PYTHON_DIR, PYTHONUTF8: '1' },
        windowsHide: true,
      })

      let stdout = ''
      let stderr = ''
      let lastResultLine = ''

      const handleLine = (line: string) => {
        if (!line.trim()) return
        try {
          const parsed = JSON.parse(line.trim())
          if (parsed.type === 'step' && parsed.step) {
            emitEvent('step_update', {
              caseKey,
              step: parsed.step
            })
          } else if (parsed.type === 'manual_confirm') {
            // 需要人工确认：延长超时，阻塞 Python stdin 直到前端提交决策
            scheduleTimeout(MANUAL_CONFIRM_TIMEOUT_MS, '人工确认超时(30min)')
            const decisionId = `manual_${caseKey}_${Date.now()}`
            const passLabel = typeof parsed.pass_label === 'string' ? parsed.pass_label : ''
            const failLabel = typeof parsed.fail_label === 'string' ? parsed.fail_label : ''
            const mode = parsed.mode === 'ack' ? 'ack' as const : 'decision' as const
            pendingManualDecisions[decisionId] = {
              deviceId,
              caseKey,
              message: parsed.message || '需人工确认',
              passLabel: passLabel || undefined,
              failLabel: failLabel || undefined,
              mode,
              resolve: (decision: string) => {
                delete pendingManualDecisions[decisionId]
                scheduleTimeout(caseTimeoutMs, `用例执行超时(${Math.round(caseTimeoutMs / 1000)}s)`)
                if (proc?.stdin && !proc.stdin.destroyed) {
                  try {
                    proc.stdin.write(`${decision}\n`, 'utf-8')
                  } catch (err) {
                    console.warn('[device-self-check] Failed to write manual decision to stdin:', err)
                  }
                }
              }
            }
            emitEvent('manual_confirm', {
              decisionId,
              deviceId,
              deviceName: devices[deviceId]?.deviceName || deviceId,
              caseKey,
              message: parsed.message || '需人工确认',
              passLabel: passLabel || undefined,
              failLabel: failLabel || undefined,
              mode,
            })
          } else if (parsed.status) {
            lastResultLine = line.trim()
          }
        } catch {
          // 非 JSON 行，忽略
        }
      }

      let lineBuffer = ''
      proc.stdout?.on('data', (data: Buffer) => {
        const text = data.toString('utf-8')
        stdout += text
        lineBuffer += text
        const lines = lineBuffer.split('\n')
        lineBuffer = lines.pop() || ''
        for (const line of lines) {
          handleLine(line)
        }
      })
      proc.stderr?.on('data', (data: Buffer) => { stderr += data.toString() })

      proc.on('close', (code: number) => {
        // 处理剩余缓冲
        if (lineBuffer.trim()) {
          handleLine(lineBuffer)
        }
        if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
        if (abortReason) {
          finish(abortFinishResult())
          return
        }
        try {
          const resultLine = lastResultLine || (() => {
            const lines = stdout.split('\n').filter((l: string) => l.trim().startsWith('{'))
            return lines[lines.length - 1] || ''
          })()

          const trimmed = resultLine.trim()
          if (trimmed.startsWith('{')) {
            const parsed = JSON.parse(trimmed)
            finish({
              status: parsed.status || 'fail',
              message: parsed.message || stderr.trim(),
              steps: parsed.steps || [],
              fullAutomation: parsed.full_automation,
              evidence: parsed.evidence,
              detail: parsed.detail,
            })
          } else {
            finish({
              status: code === 0 ? 'pass' : 'fail',
              message: stdout.trim() || stderr.trim() || `退出码: ${code}`,
              steps: []
            })
          }
        } catch {
          finish({
            status: code === 0 ? 'pass' : 'fail',
            message: stdout.trim() || stderr.trim() || `退出码: ${code}`,
            steps: []
          })
        }
      })

      proc.on('error', (err: any) => {
        if (abortReason) {
          finish(abortFinishResult())
          return
        }
        finish({ status: 'fail', message: `启动Python失败: ${err.message}`, steps: [] })
      })
    } catch (err: any) {
      finish({ status: 'fail', message: `启动Python失败: ${err.message}`, steps: [] })
    }
  })
}

// 等待人工决策
const pendingManualDecisions: Record<string, {
  caseKey: string
  message: string
  resolve: (decision: string) => void
  deviceId: string
  passLabel?: string
  failLabel?: string
  mode?: 'decision' | 'ack'
}> = {}

async function awaitTddManualConfirm(options: {
  deviceId: string
  caseKey: string
  result: CaseResult
  message: string
}): Promise<void> {
  const { deviceId, caseKey, result, message } = options
  result.status = '待确认'
  result.message = message
  result.automationMode = 'manual'
  result.fullAutomation = false
  emitEvent('case_completed', { deviceId, caseKey, result })

  const decisionId = `pending_${caseKey}_${Date.now()}`
  const pendingPromise = new Promise<string>((res) => {
    pendingManualDecisions[decisionId] = {
      deviceId,
      caseKey,
      message,
      resolve: (decision: string) => {
        res(decision)
        delete pendingManualDecisions[decisionId]
        applyManualDecisionToResult(result, decision, {
          passMessage: '人工测试通过',
          failMessage: '人工测试失败',
        })
        result.steps.push({
          stepDesc: `人工确认: ${result.message}`,
          status: result.status,
          timestamp: new Date().toISOString(),
        })
        result.endTime = new Date().toISOString()
        emitEvent('case_completed', { deviceId, caseKey, result })
      },
    }
  })
  emitEvent('manual_confirm', {
    decisionId,
    deviceId,
    deviceName: devices[deviceId]?.deviceName || deviceId,
    caseKey,
    message,
  })
  await pendingPromise
}

export function submitManualDecision(decisionId: string, decision: string): boolean {
  const pending = pendingManualDecisions[decisionId]
  if (pending) {
    pending.resolve(decision)
    return true
  }
  return false
}

// 获取设备的待处理人工决策
export function getPendingManualDecision(deviceId: string): {
  decisionId: string
  deviceId: string
  deviceName: string
  message: string
  passLabel?: string
  failLabel?: string
  mode?: 'decision' | 'ack'
} | null {
  for (const [id, decision] of Object.entries(pendingManualDecisions)) {
    if (decision.deviceId === deviceId) {
      return {
        decisionId: id,
        deviceId,
        deviceName: devices[deviceId]?.deviceName || deviceId,
        message: decision.message,
        passLabel: decision.passLabel,
        failLabel: decision.failLabel,
        mode: decision.mode,
      }
    }
  }
  return null
}

// 判断用例是否全自动化
function isFullAutomation(steps: string): boolean {
  if (!steps) return false
  const lower = steps.toLowerCase()
  // 半自动：需要人工判断结果的（听/看/观察/手感等）
  const semiAutoKeywords = [
    '听到', '听电话', '听筒', '听到声音', '音质', '音量大小',
    '肉眼', '眼睛看', '视觉检查', '目视',
    '手感', '触感', '震动感',
    '花屏', '色阶', '颜色是否',
    '插拔sim', '插入sim', '拔出sim', '热插拔',
    '覆盖传感器', '遮挡'
  ]
  for (const kw of semiAutoKeywords) {
    if (lower.includes(kw)) return false
  }
  // 全自动：ADB命令、工模操作、UI自动化等
  return true
}

// 执行模块测试
async function runModule(
  deviceId: string,
  testType: StandardTestType,
  module: string,
  session: TestSession
): Promise<void> {
  const moduleKey = `${testType}/${module}`
  const config = moduleConditions[moduleKey]
  if (!config) {
    console.warn(`[device-self-check] No config for module: ${moduleKey}`)
    return
  }

  console.log(`[device-self-check] Starting module: ${moduleKey}`)

  if (testType === 'power') {
    const powerDeps = ensurePowerTestPythonDeps()
    if (!powerDeps.ok && !powerDeps.skipped) {
      const reason = powerDeps.error || '功耗自动化 Python 依赖安装失败'
      console.error(`[device-self-check] Power deps failed: ${reason}`)
      devices[deviceId].status = '错误'
      devices[deviceId].currentModule = module
      session.errorReason = reason
      session.isRunning = false
      emitEvent('device_updated', { device: devices[deviceId] })
      return
    }
  }

  if (testType === 'smoke') {
    const sddDeps = ensureSddTestPythonDeps()
    if (!sddDeps.ok && !sddDeps.skipped) {
      const reason = sddDeps.error || '冒烟 USD Python 依赖安装失败'
      console.error(`[device-self-check] Smoke USD deps failed: ${reason}`)
      devices[deviceId].status = '错误'
      devices[deviceId].currentModule = module
      session.errorReason = reason
      session.isRunning = false
      emitEvent('device_updated', { device: devices[deviceId] })
      return
    }
  }

  if (testType === 'monkey_check') {
    const tneDeps = ensureMonkeyCheckTestPythonDeps()
    if (!tneDeps.ok && !tneDeps.skipped) {
      const reason = tneDeps.error || 'TNE 解压 Python 依赖安装失败'
      console.error(`[device-self-check] monkey_check deps failed: ${reason}`)
      devices[deviceId].status = '错误'
      devices[deviceId].currentModule = module
      session.errorReason = reason
      session.isRunning = false
      emitEvent('device_updated', { device: devices[deviceId] })
      return
    }
  }

  // 前置条件检查
  const precheck = await checkPreconditions(deviceId, moduleKey)
  if (precheck.status === 'failed') {
    console.log(`[device-self-check] Precheck failed for ${moduleKey}: ${precheck.reason}`)
    devices[deviceId].status = '不满足前置条件'
    devices[deviceId].currentModule = module
    emitEvent('device_updated', { device: devices[deviceId] })
    emitEvent('precheck_failed', { deviceId, module: moduleKey, reason: precheck.reason, type: 'failed' })
    return
  }
  if (precheck.status === 'waiting_aux') {
    console.log(`[device-self-check] Waiting for aux for ${moduleKey}: ${precheck.reason}`)
    devices[deviceId].status = '等待测试开始'
    devices[deviceId].currentModule = module
    emitEvent('device_updated', { device: devices[deviceId] })
    emitEvent('precheck_failed', { deviceId, module: moduleKey, reason: precheck.reason, type: 'waiting_aux' })
    return
  }

  // 分配辅测机（根据角色决定状态变更）
  if (precheck.auxDeviceIds && precheck.auxDeviceIds.length > 0) {
    session.auxiliaryDevices = precheck.auxDeviceIds
    for (const auxId of precheck.auxDeviceIds) {
      if (devices[auxId]) {
        if (devices[auxId].role === '测试机') {
          // 测试机互相作为辅测机：角色不变，状态变为测试中，建立双向绑定
          devices[auxId].status = '测试中'
          const peerSession = testSessions[auxId]
          if (peerSession) {
            peerSession.auxiliaryDevices = [deviceId]
          }
        } else {
          // 显式辅测机：变为占用中
          devices[auxId].status = '占用中'
        }
        devices[auxId].isMirroredResult = true
        emitEvent('device_updated', { device: devices[auxId] })
      }
    }
    console.log(`[device-self-check] Aux devices allocated: ${precheck.auxDeviceIds.join(', ')}`)
  }

  // 更新状态
  devices[deviceId].status = '测试中'
  devices[deviceId].currentModule = module
  emitEvent('device_updated', { device: devices[deviceId] })

  // 模块初始化（安装 APK、设置权限、亮屏解锁等）
  await execPythonInit(deviceId, testType, module, session)
  if (!session.isRunning) return

  // 加载用例列表
  const caseInfoPath = join(PYTHON_DIR, 'cases', testType, module, 'case_info.json')
  let cases: any[] = []
  if (existsSync(caseInfoPath)) {
    try {
      const content = readFileSync(caseInfoPath, 'utf-8')
      cases = JSON.parse(content)
    } catch (e) {
      console.warn(`[device-self-check] Failed to load case info: ${caseInfoPath}`)
    }
  }
  if (!cases.length && config.cases?.length) {
    cases = config.cases.map(c => ({ case_index: c.caseIndex, 用例名: c.caseName }))
  }

  if (
    session.prioritizeTddManual
    && isStr4WeekTddModule(testType, module)
    && cases.length > 1
  ) {
    const mapped = cases.map((c: { case_index?: number; caseIndex?: number }, i: number) => {
      const caseIndex = Number(c?.case_index ?? c?.caseIndex ?? (i + 1))
      return {
        testType,
        module,
        caseIndex,
        automationMode: resolveCaseAutomationModeForPriority(testType, module, caseIndex),
        raw: c,
      }
    })
    cases = prioritizeTddManualCases(mapped).map(item => item.raw)
  }

  const totalCases = cases.length || 0
  session.moduleProgress[moduleKey] = {
    module: moduleKey,
    totalCases,
    completedCases: 0,
    passedCases: 0,
    failedCases: 0
  }

  // 逐个执行用例
  const failedAutoCases: number[] = []
  for (let i = 0; i < totalCases; i++) {
    if (!session.isRunning) return

    // Prefer explicit case_index/caseIndex so catalog order can diverge from script numbers
    // (e.g. kernel_feature: 解析expdb case11 runs after 黑屏定屏 case19).
    const caseIndex = Number(cases[i]?.case_index ?? cases[i]?.caseIndex ?? (i + 1))
    session.moduleProgress[moduleKey].currentCaseIndex = caseIndex

    const caseKey = `${moduleKey}/${caseIndex}`

    // 先创建初始结果并存入 session，让前端实时可见
    const initialResult: CaseResult = {
      testType,
      module,
      caseIndex,
      caseName: resolveCaseDisplayName(testType, module, caseIndex),
      status: '进行中',
      message: '',
      fullAutomation: false,
      steps: [{ stepDesc: '正在加载用例...', status: '进行中', timestamp: new Date().toISOString() }],
      startTime: new Date().toISOString()
    }
    session.caseResults[caseKey] = initialResult
    emitEvent('case_completed', { deviceId, caseKey, result: initialResult })

    const result = await runCase(deviceId, testType, module, caseIndex, session)
    session.caseResults[caseKey] = result
    session.moduleProgress[moduleKey].completedCases = i + 1

    if (result.status === '通过' || result.status === 'NA') {
      session.moduleProgress[moduleKey].passedCases++
    } else if (
      result.status === '失败'
      || result.status === '部分通过'
      || (result.status === '待确认' && !isPendingManualReportFillIn(result))
    ) {
      session.moduleProgress[moduleKey].failedCases++
      if (result.fullAutomation) {
        failedAutoCases.push(caseIndex)
      }
      if (testType === 'ai_generated') {
        console.log(`[device-self-check] AI用例 ${caseKey} 失败，终止后续用例执行`)
        break
      }
    }

    emitEvent('case_completed', { deviceId, caseKey, result })

    if (!session.isRunning) return

    // 结果复用：可复用用例的通过结果镜像到辅测机
    if (result.status === '通过' && session.auxiliaryDevices.length > 0) {
      const caseItem = config.cases.find(c => c.caseIndex === caseIndex)
      if (caseItem?.canReuse) {
        for (const auxId of session.auxiliaryDevices) {
          mirrorResult(auxId, testType, module, caseIndex, result, session)
        }
      }
    }
  }

  if (!session.isRunning) return

  // 处理 can_reuse=false 的双向执行：互为测试机的设备需各自执行不可复用用例
  const peerTesters = session.auxiliaryDevices.filter(
    auxId => devices[auxId]?.role === '测试机'
  )
  for (const peerId of peerTesters) {
    if (!session.isRunning) return
    const peerSession = testSessions[peerId]
    if (!peerSession) continue

    const nonReusableCases: number[] = []
    for (const caseItem of config.cases) {
      if (!caseItem.canReuse && caseItem.caseIndex > 0) {
        const caseKey = `${moduleKey}/${caseItem.caseIndex}`
        if (peerSession.caseResults[caseKey]?.message?.includes('镜像自')) {
          nonReusableCases.push(caseItem.caseIndex)
        }
      }
    }

    if (nonReusableCases.length > 0) {
      console.log(`[device-self-check] Executing ${nonReusableCases.length} non-reusable cases for peer ${peerId}`)
      for (const caseIndex of nonReusableCases) {
        if (!session.isRunning || !peerSession.isRunning) return
        const result = await runCase(peerId, testType, module, caseIndex, peerSession)
        const caseKey = `${moduleKey}/${caseIndex}`
        peerSession.caseResults[caseKey] = result
        if (result.status === '通过') {
          peerSession.moduleProgress[moduleKey].passedCases++
        } else if (result.status === '失败') {
          peerSession.moduleProgress[moduleKey].failedCases++
          peerSession.moduleProgress[moduleKey].passedCases = Math.max(0, peerSession.moduleProgress[moduleKey].passedCases - 1)
        }
        emitEvent('case_completed', { deviceId: peerId, caseKey, result })
      }
    }
  }

  if (!session.isRunning) return
  await retestFailedAutoCasesInModule(deviceId, testType, module, failedAutoCases, session)

  if (!session.isRunning) return

  // 释放辅测机（根据角色恢复状态）
  for (const auxId of session.auxiliaryDevices) {
    if (devices[auxId]) {
      if (devices[auxId].role === '测试机') {
        // 测试机互相作为辅测机：恢复为等待测试开始，等待下一模块
        devices[auxId].status = '等待测试开始'
      } else if (devices[auxId].status === '占用中') {
        // 显式辅测机：恢复待命
        devices[auxId].status = '待命'
      }
      devices[auxId].isMirroredResult = false
      emitEvent('device_updated', { device: devices[auxId] })
    }
  }
  session.auxiliaryDevices = []

  console.log(`[device-self-check] Module completed: ${moduleKey}`)
}

// 结果复用：镜像结果到辅测机
function mirrorResult(
  auxDeviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  sourceResult: CaseResult,
  sourceSession: TestSession
): void {
  const auxSession = testSessions[auxDeviceId]
  if (!auxSession) {
    // 辅测机没有独立 session，结果存到源 session 中标记
    return
  }
  const caseKey = `${testType}/${module}/${caseIndex}`
  auxSession.caseResults[caseKey] = {
    ...sourceResult,
    message: `${sourceResult.message}（镜像自 ${sourceSession.deviceId}）`,
  }
  if (!auxSession.moduleProgress[`${testType}/${module}`]) {
    auxSession.moduleProgress[`${testType}/${module}`] = {
      module: `${testType}/${module}`,
      totalCases: 0,
      completedCases: 0,
      passedCases: 0,
      failedCases: 0,
    }
  }
  auxSession.moduleProgress[`${testType}/${module}`].passedCases++
  auxSession.moduleProgress[`${testType}/${module}`].completedCases++
  console.log(`[device-self-check] Mirrored result for ${auxDeviceId}: ${caseKey}`)
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

function buildFlashOptionsFromPayload(payload?: StartTestFlashPayload): DeviceFlashOptions | undefined {
  if (!payload?.enabled || !payload.pkgPath?.trim()) return undefined
  return {
    pkgPath: payload.pkgPath.trim(),
    enableRootPkg: payload.enableRootPkg === true,
    rootPkgPath: payload.rootPkgPath?.trim() || undefined,
    stageVersion: payload.stageVersion?.trim() || undefined,
  }
}

function buildTcardOptionsFromPayload(payload?: StartTestTcardPayload): TcardUpdateOptions | undefined {
  if (!payload?.enabled) return undefined
  const zipPaths = tcardZipQueue({
    zipPath: payload.zipPath || '',
    zipPaths: payload.zipPaths,
  })
  if (!zipPaths.length) return undefined
  if (zipPaths.some((path) => !isTcardZipPath(path))) {
    throw new Error('T卡升级仅支持 ZIP 文件')
  }
  return { zipPath: zipPaths[0]!, zipPaths }
}

function pretestStatus(session: Pick<TestSession, 'flashOptions' | 'tcardOptions'> & { currentModuleIndex?: number }): DeviceStatus {
  if ((session.currentModuleIndex ?? 0) !== 0) return '初始化中'
  if (session.flashOptions) return '刷机中'
  if (session.tcardOptions) return 'T卡升级中'
  return '初始化中'
}

async function runFlashBeforeTest(deviceId: string, session: TestSession): Promise<boolean> {
  if (!session.flashOptions) return true

  const device = devices[deviceId]
  if (!device) return false

  device.status = '刷机中'
  device.currentModule = '刷机'
  emitEvent('device_updated', { device })
  emitEvent('flash_log', { deviceId, line: '[刷机] 开始准备刷机环境…' })

  const result = await runDeviceFlash([deviceId], session.flashOptions, (line) => {
    emitEvent('flash_log', { deviceId, line })
  })

  if (!result.success) {
    device.status = '错误'
    session.isRunning = false
    session.errorReason = result.error || '刷机失败'
    device.currentModule = '刷机'
    emitEvent('device_updated', { device })
    emitEvent('flash_completed', {
      deviceId,
      success: false,
      returnCode: result.returnCode,
      error: result.error,
    })
    return false
  }

  emitEvent('flash_log', { deviceId, line: '[刷机] 刷机完成，开始跳过 OOBE…' })
  const oobeOk = await skipOobeForDevice(deviceId, (line) => {
    emitEvent('flash_log', { deviceId, line })
  }, {
    shouldAbort: () => !session.isRunning,
  })
  if (!session.isRunning) return false
  if (!oobeOk) {
    device.status = '错误'
    session.isRunning = false
    session.errorReason = '刷机后跳过 OOBE 失败（设备未重新连接）'
    device.currentModule = '刷机'
    emitEvent('device_updated', { device })
    emitEvent('flash_completed', {
      deviceId,
      success: false,
      returnCode: result.returnCode,
      error: session.errorReason,
    })
    return false
  }

  emitEvent('flash_completed', {
    deviceId,
    success: true,
    returnCode: result.returnCode,
    continuePretest: Boolean(session.tcardOptions),
  })
  return true
}

async function runTcardBeforeTest(deviceId: string, session: TestSession): Promise<boolean> {
  if (!session.tcardOptions) return true

  const device = devices[deviceId]
  if (!device) return false
  const zipPaths = tcardZipQueue(session.tcardOptions)
  if (!zipPaths.length) return true

  device.status = 'T卡升级中'
  device.currentModule = 'T卡升级'
  emitEvent('device_updated', { device })
  emitEvent('flash_log', { deviceId, line: `[T卡升级] 开始连续升级，共 ${zipPaths.length} 个升级包…` })

  for (let index = 0; index < zipPaths.length; index += 1) {
    if (!session.isRunning) return false
    const zipPath = zipPaths[index]!
    emitEvent('flash_log', {
      deviceId,
      line: `[T卡升级] (${index + 1}/${zipPaths.length}) ${basename(zipPath)}`,
    })
    const result = await runTcardUpdate(
      deviceId,
      { zipPath },
      (line) => emitEvent('flash_log', { deviceId, line }),
      () => !session.isRunning,
    )
    if (!result.success) {
      device.status = '错误'
      session.isRunning = false
      session.errorReason = result.error || 'T卡升级失败'
      device.currentModule = 'T卡升级'
      emitEvent('device_updated', { device })
      emitEvent('flash_completed', {
        deviceId,
        success: false,
        error: result.error,
      })
      return false
    }
  }

  emitEvent('flash_completed', { deviceId, success: true })
  return true
}

export interface StartTestOptions {
  prioritizeTddManual?: boolean
  tcard?: StartTestTcardPayload
  /** 仅跑所选模块；须为该 testType 合法子集，缺省/空则跑全部 */
  modules?: string[]
}

/** 解析标准测试启动时的模块列表（保持 getModulesForTestType 顺序） */
export function resolveStartModules(
  testType: StandardTestType,
  requested?: string[] | null,
): string[] {
  const all = getModulesForTestType(testType)
  if (!requested || requested.length === 0) return all
  const wanted = new Set(requested)
  const selected = all.filter(m => wanted.has(m))
  if (selected.length === 0) {
    throw new Error('请至少选择一个有效的测试模块')
  }
  return selected
}

function bindCustomAuxDevices(auxIds: string[], dutId: string, session: TestSession): void {
  const now = new Date().toISOString()
  if (!session.customAuxPromotedIds) {
    session.customAuxPromotedIds = []
  }
  for (const auxId of auxIds) {
    if (auxId === dutId) continue
    const aux = devices[auxId]
    if (!aux) continue
    if (aux.role === '未分配') {
      session.customAuxPromotedIds.push(auxId)
      aux.role = '辅测机'
    }
    aux.testType = 'custom'
    aux.testStartTime = aux.testStartTime || now
    aux.status = aux.role === '测试机' ? '测试中' : '占用中'
    aux.isMirroredResult = false
    emitEvent('device_updated', { device: aux })
  }
}

function releaseCustomAuxDevices(session: TestSession): void {
  const promoted = new Set(session.customAuxPromotedIds ?? [])
  for (const auxId of session.auxiliaryDevices ?? []) {
    const aux = devices[auxId]
    if (!aux) continue
    aux.status = '空闲'
    aux.testType = undefined
    aux.testStartTime = undefined
    aux.testDuration = 0
    aux.currentModule = undefined
    aux.isMirroredResult = false
    if (promoted.has(auxId)) {
      aux.role = '未分配'
    }
    emitEvent('device_updated', { device: aux })
  }
  session.auxiliaryDevices = []
  session.customAuxPromotedIds = []
}

// 启动测试
export async function startTest(
  deviceId: string,
  testType: StandardTestType,
  flash?: StartTestFlashPayload,
  options?: StartTestOptions,
): Promise<DeviceDetail | null> {
  assertGmsRunnable(testType)
  if (testType === 'ota_upgrade' && !buildFlashOptionsFromPayload(flash)) {
    throw new Error('连续OTA升级需要先获取外发版本并选择 Android 版本')
  }
  try {
    const device = devices[deviceId]
    if (!device || device.status !== '空闲') {
      return null
    }

    // 辅测机：进入待命状态，等待测试机调用
    if (device.role === '辅测机') {
      device.status = '待命'
      device.testType = testType
      device.testStartTime = new Date().toISOString()
      emitEvent('device_updated', { device })
      console.log(`[device-self-check] Auxiliary device standing by: ${deviceId} for ${testType}`)
      return { device }
    }

    const flashOptions = buildFlashOptionsFromPayload(flash)
    const tcardOptions = buildTcardOptionsFromPayload(options?.tcard)

    // 更新设备状态
    device.status = pretestStatus({ flashOptions, tcardOptions })
    device.testType = testType
    device.testStartTime = new Date().toISOString()
    emitEvent('device_updated', { device })

    // 创建测试会话（可按 UI 勾选过滤模块）
    const modules = resolveStartModules(testType, options?.modules)

    const session: TestSession = {
      deviceId,
      testType,
      modules,
      currentModuleIndex: 0,
      moduleProgress: {},
      caseResults: {},
      startTime: device.testStartTime,
      isRunning: true,
      auxiliaryDevices: [],
      initializedPythonModules: [],
      flashOptions,
      tcardOptions,
      prioritizeTddManual: Boolean(options?.prioritizeTddManual),
      testConfig: snapshotTestConfig(testType, {
        flashOptions,
        tcardOptions,
        prioritizeTddManual: Boolean(options?.prioritizeTddManual),
      }),
    }

    testSessions[deviceId] = session
    emitEvent('test_started', { deviceId, testType, session })

    await resolveReportOtaVersion(deviceId, session).catch(() => undefined)

    // 初始化：设置亮屏时间为30分钟
    execAdbSimple(['-s', deviceId, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '1800000'])
      .catch(() => {})
    // 异步执行测试流程
    runTestFlow(deviceId, testType, session).catch(e => {
      markTestFlowError(deviceId, e, testType)
    })

    return { device, session }
  } catch (e) {
    console.error('Error starting test:', e)
    return null
  }
}

export async function startCustomTest(
  deviceId: string,
  selectedCases: string[],
  customAuxDeviceIds: string[],
  options?: {
    prioritizeTddManual?: boolean
    skipQualityUpload?: boolean
    /** 适配流水线内自检：指定上报中心的项目/战役归属 */
    qualityUploadProject?: { project_code: string; campaign_id?: string }
  },
): Promise<DeviceDetail | null> {
  assertGmsRunnable('custom', selectedCases)
  try {
    const device = devices[deviceId]
    if (!device || device.status !== '空闲') return null

    const auxIds = customAuxDeviceIds.filter(id => id !== deviceId)
    for (const auxId of auxIds) {
      const aux = devices[auxId]
      if (!aux || aux.status !== '空闲') {
        console.warn(`[device-self-check] Custom test: aux ${auxId} not idle`)
        return null
      }
    }

    device.status = '初始化中'
    device.testType = 'custom'
    if (device.role === '未分配') {
      device.role = '测试机'
    }
    device.testStartTime = new Date().toISOString()
    emitEvent('device_updated', { device })

    const modulesSet = new Set<string>()
    const caseList: { testType: string; module: string; caseIndex: number }[] = []
    for (const caseKey of selectedCases) {
      const parts = caseKey.split('/')
      const caseIndex = parseInt(parts.pop() || '1', 10)
      const module = parts.pop() || ''
      const testType = parts.join('/')
      modulesSet.add(module)
      caseList.push({ testType, module, caseIndex })
    }
    const modules = Array.from(modulesSet)
    const prioritizeTddManual = Boolean(options?.prioritizeTddManual)
    const executionCaseList = prioritizeTddManual
      ? applyTddManualPriority(caseList)
      : caseList

    const session: TestSession = {
      deviceId,
      testType: 'custom',
      modules,
      currentModuleIndex: 0,
      moduleProgress: {},
      caseResults: {},
      startTime: device.testStartTime,
      isRunning: true,
      auxiliaryDevices: auxIds,
      selectedCases,
      customAuxDevices: auxIds,
      initializedPythonModules: [],
      prioritizeTddManual,
      skipQualityUpload: options?.skipQualityUpload === true,
      qualityUploadProject: options?.qualityUploadProject,
      testConfig: snapshotTestConfig('custom', {
        prioritizeTddManual,
        selectedCases,
      }),
    }

    testSessions[deviceId] = session
    bindCustomAuxDevices(auxIds, deviceId, session)
    emitEvent('test_started', { deviceId, testType: 'custom', session })

    await resolveReportOtaVersion(deviceId, session).catch(() => undefined)

    execAdbSimple(['-s', deviceId, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '1800000'])
      .catch(() => {})
    runCustomTestFlow(deviceId, session, executionCaseList).catch(e => {
      markTestFlowError(deviceId, e, 'custom')
    })

    return { device, session }
  } catch (e) {
    console.error('Error starting custom test:', e)
    return null
  }
}

// 异步执行测试流程
function markTestFlowError(
  deviceId: string,
  err: unknown,
  testType?: string,
): void {
  const device = devices[deviceId]
  const session = testSessions[deviceId]
  if (!device || !session) return
  if (device.status === '错误') return

  session.isRunning = false
  const msg = err instanceof Error ? err.message : String(err)
  session.errorReason = msg || '测试流程异常'

  const moduleName = session.modules[session.currentModuleIndex]
  if (moduleName) {
    const tt = testType || session.testType
    const moduleKey = `${tt}/${moduleName}`
    device.currentModule = moduleConditions[moduleKey]?.moduleLabel || moduleName
  }

  device.status = '错误'
  emitEvent('device_updated', { device })
  emitEvent('test_error', { deviceId, message: session.errorReason, module: device.currentModule })
  scheduleTestReportIfNeeded(deviceId, session, { reportStatus: '完成(失败)' })
}

function parseCustomCaseKeys(selectedCases: string[]): { testType: string; module: string; caseIndex: number }[] {
  const caseList: { testType: string; module: string; caseIndex: number }[] = []
  for (const caseKey of selectedCases) {
    const parts = caseKey.split('/')
    const caseIndex = parseInt(parts.pop() || '1', 10)
    const module = parts.pop() || ''
    const tt = parts.join('/')
    caseList.push({ testType: tt, module, caseIndex })
  }
  return caseList
}

export function formatCaseResultKey(testType: string, module: string, caseIndex: number): string {
  return `${testType}/${module}/${caseIndex}`
}

function resolveCaseResult(
  caseResults: Record<string, CaseResult>,
  rawKey: string,
): CaseResult | undefined {
  const direct = caseResults[rawKey]
  if (direct) return direct
  const parsed = parseCustomCaseKeys([rawKey])[0]
  if (!parsed) return undefined
  return caseResults[formatCaseResultKey(parsed.testType, parsed.module, parsed.caseIndex)]
}

/** 按执行顺序收集报告用例结果；自定义测试在 selectedCases 映射失败时回退到 caseResults */
export function collectOrderedCaseResults(session: TestSession): CaseResult[] {
  const allResults = Object.values(session.caseResults)
  if (allResults.length === 0) return []

  const sortResults = (results: CaseResult[]) =>
    [...results].sort((a, b) =>
      formatCaseResultKey(a.testType, a.module, a.caseIndex)
        .localeCompare(formatCaseResultKey(b.testType, b.module, b.caseIndex), undefined, { numeric: true }),
    )

  if (session.testType === 'custom' && session.selectedCases?.length) {
    const ordered: CaseResult[] = []
    const seen = new Set<string>()
    for (const rawKey of session.selectedCases) {
      const result = resolveCaseResult(session.caseResults, rawKey)
      if (!result) continue
      const key = formatCaseResultKey(result.testType, result.module, result.caseIndex)
      if (seen.has(key)) continue
      seen.add(key)
      ordered.push(result)
    }
    if (ordered.length > 0) return ordered
  }

  return sortResults(allResults)
}

const TERMINAL_CASE_STATUSES = new Set(['通过', '失败', '部分通过', 'NA', '跳过'])

function applyUserSkipToResult(result: CaseResult): void {
  if (result.status === '跳过' && result.message === '用户跳过') return
  const now = new Date().toISOString()
  result.status = '跳过'
  result.message = '用户跳过'
  result.endTime = now
  result.steps = [
    ...(result.steps || []),
    { stepDesc: '用户跳过', status: '跳过', timestamp: now },
  ]
}

function applyManualDecisionToResult(
  result: CaseResult,
  decision: string,
  labels: { passMessage: string; failMessage: string },
): void {
  if (decision === 'skip') {
    applyUserSkipToResult(result)
    return
  }
  result.status = decision === 'pass' ? '通过' : '失败'
  result.message = decision === 'pass' ? labels.passMessage : labels.failMessage
}

function findSkippableCaseEntries(session: TestSession): Array<[string, CaseResult]> {
  return Object.entries(session.caseResults).filter(
    ([, result]) => result.status === '进行中' || result.status === '待确认',
  )
}

/** 用户点「结束测试」时：未终态用例一律记为失败，保证报告呈现失败 */
function markCasesFailedOnUserAbort(deviceId: string, session: TestSession): void {
  const now = new Date().toISOString()
  for (const [caseKey, result] of Object.entries(session.caseResults)) {
    if (TERMINAL_CASE_STATUSES.has(result.status)) continue
    result.status = '失败'
    result.message = '用户结束测试'
    result.endTime = now
    result.steps = [
      ...(result.steps || []),
      { stepDesc: '用户结束测试', status: '失败', timestamp: now },
    ]
    emitEvent('case_completed', { deviceId, caseKey, result })
  }
  // 按结果重算模块失败/通过计数，避免「进行中」中止后统计不准
  for (const [moduleKey, prog] of Object.entries(session.moduleProgress)) {
    let passed = 0
    let failed = 0
    let completed = 0
    for (const result of Object.values(session.caseResults)) {
      if (`${result.testType}/${result.module}` !== moduleKey) continue
      if (!TERMINAL_CASE_STATUSES.has(result.status) && result.status !== '待确认') continue
      completed++
      if (result.status === '通过' || result.status === 'NA') passed++
      else if (result.status === '失败' || result.status === '部分通过' || result.status === '待确认') failed++
    }
    prog.passedCases = passed
    prog.failedCases = failed
    prog.completedCases = Math.max(prog.completedCases, completed)
  }
}

// 跳过当前用例（杀进程 / 解除人工确认，会话继续下一例）
export function skipCurrentCase(deviceId: string): DeviceDetail {
  const device = devices[deviceId]
  const session = testSessions[deviceId]
  if (!device) {
    throw new Error('设备不存在')
  }
  if (!session?.isRunning) {
    throw new Error('当前没有可跳过的用例')
  }

  const skippable = findSkippableCaseEntries(session)
  if (skippable.length === 0) {
    throw new Error('当前没有可跳过的用例')
  }

  for (const [caseKey, result] of skippable) {
    applyUserSkipToResult(result)
    emitEvent('case_completed', { deviceId, caseKey, result })
  }

  for (const [id, pending] of Object.entries(pendingManualDecisions)) {
    if (pending.deviceId !== deviceId) continue
    if (id.startsWith('manual_')) {
      // Python stdin 确认：不写 skip 给脚本，由 cleanup 杀进程
      delete pendingManualDecisions[id]
      continue
    }
    try { pending.resolve('skip') } catch { /* ignore */ }
    delete pendingManualDecisions[id]
  }

  if (activeCaseCleanups[deviceId]) {
    activeCaseCleanups[deviceId]('skip')
    delete activeCaseCleanups[deviceId]
  }

  return { device, session }
}

// 结束测试（终止当前执行、释放资源，并停止后台 Monkey）
export async function endTest(deviceId: string): Promise<DeviceDetail | null> {
  const device = devices[deviceId]
  const session = testSessions[deviceId]
  if (!device) return null

  const endedTestType = device.testType || session?.testType

  // 先打断调度循环，再杀进程，避免 close 回调后仍启动下一例
  if (session) {
    session.isRunning = false
  }

  if (activeCaseCleanups[deviceId]) {
    activeCaseCleanups[deviceId]('abort')
    delete activeCaseCleanups[deviceId]
  }

  // 取消该设备上挂起的人工确认，避免结束后弹窗仍阻塞
  for (const [id, pending] of Object.entries(pendingManualDecisions)) {
    if (pending.deviceId === deviceId) {
      try { pending.resolve('fail') } catch { /* ignore */ }
      delete pendingManualDecisions[id]
    }
  }

  // 不阻塞结束路径：monkey/power 停止最多各 30s
  void stopMonkeyForDevice(deviceId)
  void stopPowerForDevice(deviceId)

  if (session) {
    finalizePowerCaseResults(deviceId, session)
  }

  if (session && Object.keys(session.caseResults).length > 0) {
    markCasesFailedOnUserAbort(deviceId, session)
    session.endTime = new Date().toISOString()
    const testDuration = Math.round(
      (Date.now() - new Date(device.testStartTime || Date.now()).getTime()) / 1000
    )
    device.testDuration = testDuration
    const reportSession = session
    void generateTestReport(deviceId, reportSession, undefined, {
      reportStatus: '完成(失败)',
      testDuration,
    }).catch((e) => {
      console.warn('[device-self-check] Failed to generate partial report on end:', e)
    })
    emitEvent('test_completed', { deviceId, session: reportSession })
  }

  // 清理与其他测试机的双向绑定：从其他 session 的 auxiliaryDevices 中移除本设备
  for (const [, sess] of Object.entries(testSessions)) {
    if (sess.auxiliaryDevices?.includes(deviceId)) {
      sess.auxiliaryDevices = sess.auxiliaryDevices.filter(aid => aid !== deviceId)
    }
  }

  // 辅测机待命状态：直接回到空闲
  if (device.status === '待命' && device.role === '辅测机') {
    device.status = '空闲'
    device.testType = undefined
    device.testStartTime = undefined
    device.testDuration = 0
    delete testSessions[deviceId]
    emitEvent('device_updated', { device })
    emitEvent('test_ended', { deviceId })
    if (endedTestType) {
      releaseAuxDevicesIfNoActiveDut(endedTestType)
    }
    return { device }
  }

  // 释放辅测机（根据角色恢复状态）
  if (session?.auxiliaryDevices?.length) {
    if (session.testType === 'custom') {
      releaseCustomAuxDevices(session)
    } else {
      for (const auxId of session.auxiliaryDevices) {
        if (devices[auxId]) {
          if (devices[auxId].role === '测试机') {
            devices[auxId].status = '等待测试开始'
          } else if (devices[auxId].status === '占用中') {
            devices[auxId].status = '待命'
          }
          devices[auxId].isMirroredResult = false
          emitEvent('device_updated', { device: devices[auxId] })
        }
      }
    }
  }

  // 重置测试机状态（立刻空闲，不等待报告）
  device.status = '空闲'
  device.testType = undefined
  device.currentModule = undefined
  device.testStartTime = undefined
  device.testDuration = 0
  device.isMirroredResult = false
  delete testSessions[deviceId]

  emitEvent('device_updated', { device })
  emitEvent('test_ended', { deviceId })

  if (endedTestType) {
    releaseAuxDevicesIfNoActiveDut(endedTestType)
  }

  return { device }
}

async function runTestFlow(
  deviceId: string,
  testType: StandardTestType,
  session: TestSession,
  startModuleIndex = 0,
): Promise<void> {
  try {
    if (session.flashOptions && startModuleIndex === 0) {
      const flashOk = await runFlashBeforeTest(deviceId, session)
      if (!flashOk || !session.isRunning) return
    }

    if (session.tcardOptions && startModuleIndex === 0) {
      const tcardOk = await runTcardBeforeTest(deviceId, session)
      if (!tcardOk || !session.isRunning) return
    }

    const device = devices[deviceId]
    if (device && startModuleIndex === 0) {
      device.status = '初始化中'
      emitEvent('device_updated', { device })
      await execDeviceInit(deviceId, session)
    }

    const modules = session.modules

    for (let idx = startModuleIndex; idx < modules.length; idx++) {
      const module = modules[idx]
      session.currentModuleIndex = idx

      await runModule(deviceId, testType, module, session)

      const dev = devices[deviceId]
      if (!dev || !session.isRunning) {
        scheduleTestReportIfNeeded(deviceId, session, { reportStatus: '完成(失败)' })
        return
      }

      if (dev.status === '不满足前置条件') {
        return
      }
      if (dev.status === '等待测试开始') {
        return
      }
    }

    finishTest(deviceId, session)
  } catch (e) {
    console.error(`[device-self-check] Test flow error for ${deviceId}:`, e)
    markTestFlowError(deviceId, e, testType)
  }
}

// 自定义测试：按勾选用例列表执行
async function runCustomTestFlow(
  deviceId: string,
  session: TestSession,
  caseList: { testType: string; module: string; caseIndex: number }[],
  options: { skipDeviceInit?: boolean } = {},
): Promise<void> {
  try {
  const device = devices[deviceId]
  if (!device) return

  const moduleKeys = new Set(caseList.map(c => `${c.testType}/${c.module}`))
  for (const mk of moduleKeys) {
    const moduleCases = caseList.filter(c => `${c.testType}/${c.module}` === mk)
    if (!session.moduleProgress[mk]) {
      session.moduleProgress[mk] = {
        module: mk,
        totalCases: moduleCases.length,
        completedCases: 0,
        passedCases: 0,
        failedCases: 0,
      }
    }
  }

  for (const auxId of session.auxiliaryDevices) {
    if (devices[auxId]) {
      if (devices[auxId].role === '测试机') {
        devices[auxId].status = '测试中'
      } else if (devices[auxId].status !== '占用中') {
        devices[auxId].status = '占用中'
      }
      if (!devices[auxId].testType) {
        devices[auxId].testType = 'custom'
      }
      emitEvent('device_updated', { device: devices[auxId] })
    }
  }

  device.status = '初始化中'
  emitEvent('device_updated', { device })
  if (!options.skipDeviceInit) {
    await execDeviceInit(deviceId, session)
  }

  if (!session.isRunning) return

  device.status = '测试中'
  device.currentModule = '自定义测试'
  emitEvent('device_updated', { device })

  const failedAutoCases: { testType: string; module: string; caseIndex: number }[] = []
  const initializedModules = new Set<string>()

  for (const item of caseList) {
    const { testType, module, caseIndex } = item
    const moduleKey = `${testType}/${module}`
    const caseKey = `${moduleKey}/${caseIndex}`

    if (!initializedModules.has(moduleKey)) {
      device.currentModule = moduleConditions[moduleKey]?.moduleLabel || module
      emitEvent('device_updated', { device })
      if (testType === 'power') {
        const powerDeps = ensurePowerTestPythonDeps()
        if (!powerDeps.ok && !powerDeps.skipped) {
          const reason = powerDeps.error || '功耗自动化 Python 依赖安装失败'
          markTestFlowError(deviceId, new Error(reason), 'custom')
          return
        }
      }
      if (testType === 'smoke') {
        const sddDeps = ensureSddTestPythonDeps()
        if (!sddDeps.ok && !sddDeps.skipped) {
          const reason = sddDeps.error || '冒烟 USD Python 依赖安装失败'
          markTestFlowError(deviceId, new Error(reason), 'custom')
          return
        }
      }
      await execPythonInit(deviceId, testType, module, session)
      initializedModules.add(moduleKey)
      if (!session.isRunning) return
    }

    const cond = moduleConditions[moduleKey]
    if (cond) {
      const simCount = device.simCards.filter(s => s.present).length
      if (cond.conditions.dutSimCount > 0 && simCount < cond.conditions.dutSimCount) {
        console.warn(`[device-self-check] Custom test: SIM count warning for ${moduleKey}`)
      }
    }

    session.moduleProgress[moduleKey].currentCaseIndex = caseIndex

    const result = await runCase(deviceId, testType, module, caseIndex, session)
    session.caseResults[caseKey] = result
    session.moduleProgress[moduleKey].completedCases++

    if (result.status === '通过' || result.status === 'NA') {
      session.moduleProgress[moduleKey].passedCases++
    } else if (result.status === '失败') {
      session.moduleProgress[moduleKey].failedCases++
      if (result.fullAutomation) {
        failedAutoCases.push({ testType, module, caseIndex })
      }
    }

    emitEvent('case_completed', { deviceId, caseKey, result })

    if (!session.isRunning) return
  }

  const failedByModule = new Map<string, number[]>()
  for (const item of failedAutoCases) {
    const moduleKey = `${item.testType}/${item.module}`
    if (!failedByModule.has(moduleKey)) {
      failedByModule.set(moduleKey, [])
    }
    failedByModule.get(moduleKey)!.push(item.caseIndex)
  }
  for (const [moduleKey, caseIndexes] of failedByModule) {
    const [testType, module] = moduleKey.split('/')
    await retestFailedAutoCasesInModule(deviceId, testType, module, caseIndexes, session)
  }

  releaseCustomAuxDevices(session)

  finishTest(deviceId, session)
  } catch (e) {
    console.error(`[device-self-check] Custom test flow error for ${deviceId}:`, e)
    markTestFlowError(deviceId, e, 'custom')
  }
}

// 完成测试
function finishTest(deviceId: string, session: TestSession): void {
  const device = devices[deviceId]
  if (!device) return

  const allPassed = Object.values(session.caseResults)
    .every(r => r.status === '通过' || r.status === '跳过')
  const finalStatus = allPassed ? '完成(通过)' : '完成(失败)'
  device.testDuration = Math.round(
    (Date.now() - new Date(device.testStartTime || Date.now()).getTime()) / 1000
  )
  session.isRunning = false
  device.status = finalStatus

  emitEvent('device_updated', { device })
  emitEvent('test_completed', { deviceId, session })

  if (session.endTime) {
    resetDeviceToIdleAfterTest(deviceId)
    return
  }

  session.endTime = new Date().toISOString()

  void generateTestReport(deviceId, session)
    .catch(e => {
      console.warn('[device-self-check] Failed to generate report:', e)
    })
    .finally(() => {
      resetDeviceToIdleAfterTest(deviceId)
    })
}

function resetDeviceToIdleAfterTest(deviceId: string): void {
  const device = devices[deviceId]
  if (!device) return
  device.status = '空闲'
  device.testType = undefined
  device.currentModule = undefined
  device.testStartTime = undefined
  device.testDuration = 0
  device.isMirroredResult = false
  delete testSessions[deviceId]
  emitEvent('device_updated', { device })
  emitEvent('test_ended', { deviceId })
}

// 生成测试报告
// 生成 xlsx 报告（使用 adm-zip + 原生 XML，无需额外依赖）
function generateXlsx(sheets: { name: string; rows: string[][]; styles: ('green' | 'red' | 'yellow' | '')[] }[]): Buffer {
  const sharedStrings: string[] = []
  const ssIndex = new Map<string, number>()
  const getSS = (s: string): number => {
    if (!ssIndex.has(s)) {
      ssIndex.set(s, sharedStrings.length)
      sharedStrings.push(s)
    }
    return ssIndex.get(s)!
  }

  const escXml = (s: string): string =>
    String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

  // sharedStrings.xml
  const ssXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${sharedStrings.length}" uniqueCount="${sharedStrings.length}">
${sharedStrings.map(s => `<si><t>${escXml(s)}</t></si>`).join('\n')}
</sst>`

  // styles.xml
  const stylesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3">
  <font><sz val="11"/><name val="Calibri"/></font>
  <font><b/><sz val="11"/><name val="Calibri"/></font>
  <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
</fonts>
<fills count="6">
  <fill><patternFill patternType="none"/></fill>
  <fill><patternFill patternType="gray125"/></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFDDDDDD"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF00CC66"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFFF4444"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFFFAA00"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
  <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  <xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>
  <xf numFmtId="0" fontId="2" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  <xf numFmtId="0" fontId="0" fillId="5" borderId="0" xfId="0" applyFill="1"/>
</cellXfs>
</styleSheet>`

  // sheets.xml
  let sheetsXml = '<sheets xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
  sheets.forEach((_, i) => {
    sheetsXml += `<sheet name="${escXml(sheets[i].name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`
  })
  sheetsXml += '</sheets>'

  // workbook.xml
  const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
${sheetsXml}
</workbook>`

  // workbook.xml.rels
  let relsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
  sheets.forEach((_, i) => {
    relsXml += `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`
  })
  relsXml += `<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId${sheets.length + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>`

  // [Content_Types].xml
  let contentTypesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>`
  sheets.forEach((_, i) => {
    contentTypesXml += `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`
  })
  contentTypesXml += '</Types>'

  // .rels
  const rootRelsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`

  const zip = new AdmZip()
  zip.addFile('[Content_Types].xml', Buffer.from(contentTypesXml, 'utf-8'))
  zip.addFile('_rels/.rels', Buffer.from(rootRelsXml, 'utf-8'))
  zip.addFile('xl/workbook.xml', Buffer.from(workbookXml, 'utf-8'))
  zip.addFile('xl/_rels/workbook.xml.rels', Buffer.from(relsXml, 'utf-8'))
  zip.addFile('xl/styles.xml', Buffer.from(stylesXml, 'utf-8'))
  zip.addFile('xl/sharedStrings.xml', Buffer.from(ssXml, 'utf-8'))

  // 每个 sheet 生成 worksheet XML
  sheets.forEach((sheet, si) => {
    const cols = '<cols>' + sheet.rows[0].map((_, ci) => `<col min="${ci + 1}" max="${ci + 1}" width="${Math.max(12, sheet.rows[0][ci].length * 1.5)}" customWidth="1"/>`).join('') + '</cols>'
    let rowsXml = ''
    sheet.rows.forEach((row, ri) => {
      const rowStyle = ri === 0 ? 1 : sheet.styles[ri] || ''
      let cellsXml = ''
      row.forEach((cell, ci) => {
        const ssIdx = getSS(cell)
        const styleIdx = ri === 0 ? 1 : (rowStyle === 'green' ? 2 : rowStyle === 'red' ? 3 : rowStyle === 'yellow' ? 4 : 0)
        cellsXml += `<c r="${String.fromCharCode(65 + ci)}${ri + 1}" t="s" s="${styleIdx}"><v>${ssIdx}</v></c>`
      })
      rowsXml += `<row r="${ri + 1}">${cellsXml}</row>`
    })
    const sheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
${cols}
<sheetData>${rowsXml}</sheetData>
</worksheet>`
    zip.addFile(`xl/worksheets/sheet${si + 1}.xml`, Buffer.from(sheetXml, 'utf-8'))
  })

  return zip.toBuffer()
}

async function generateTestReport(
  deviceId: string,
  session: TestSession,
  existingResultDir?: string,
  options?: { reportStatus?: string; testDuration?: number },
): Promise<void> {
  try {
    const device = devices[deviceId]
    if (!device) return

    const resultDir = existingResultDir ?? getSessionResultDir(deviceId, session)
    mkdirSync(resultDir, { recursive: true })

    if (session.testType === 'power') {
      finalizePowerCaseResults(deviceId, session)
    }

    const orderedResults = collectOrderedCaseResults(session)

    // 尽早采集 OTA 版本（避免后续 xlsx/UNC 耗时导致设备离线后读不到）
    const otaVersion = await resolveReportOtaVersion(deviceId, session)

    const sheets: { name: string; rows: string[][]; styles: ('green' | 'red' | 'yellow' | '')[] }[] = []

    const metaRows: string[][] = [
      ['设备', `${device.deviceName} (${deviceId})`],
      ['测试类型', session.testType],
      ['OTA 版本 (persist.sys.ota_version)', otaVersion || '(未获取)'],
      ['开始时间', session.startTime || ''],
      ['结束时间', session.endTime || ''],
      ...formatSelfCheckTestConfigMetaRows(session.testConfig),
    ]
    sheets.push({
      name: '摘要',
      rows: metaRows,
      styles: metaRows.map(() => ''),
    })

    if (session.testType === 'custom') {
      const rows: string[][] = [['序号', '用例名称', '所属模块', '状态', '结论', '自动化类型', '执行时间']]
      const styles: ('green' | 'red' | 'yellow' | '')[] = ['']

      for (const c of orderedResults) {
        const moduleKey = `${c.testType}/${c.module}`
        const moduleLabel = moduleConditions[moduleKey]?.moduleLabel || c.module
        const duration = c.startTime && c.endTime
          ? `${Math.round((new Date(c.endTime).getTime() - new Date(c.startTime).getTime()) / 1000)}s`
          : ''
        rows.push([
          String(c.caseIndex),
          c.caseName,
          moduleLabel,
          c.status,
          c.message,
          automationModeLabel(c.automationMode ?? (c.fullAutomation ? 'full' : 'manual')),
          duration,
        ])
        const statusStyle = c.status === '通过' ? 'green' : c.status === '失败' ? 'red' : c.status === '部分通过' ? 'yellow' : ''
        styles.push(statusStyle)
      }
      sheets.push({ name: '自定义测试', rows, styles })
    } else {
      const moduleCases = new Map<string, CaseResult[]>()
      for (const result of orderedResults) {
        const moduleKey = `${result.testType}/${result.module}`
        if (!moduleCases.has(moduleKey)) moduleCases.set(moduleKey, [])
        moduleCases.get(moduleKey)!.push(result)
      }
      for (const [moduleKey, cases] of moduleCases) {
        cases.sort((a, b) => a.caseIndex - b.caseIndex)
        const sheetName = (moduleConditions[moduleKey]?.moduleLabel || moduleKey.split('/').pop() || moduleKey)
          .slice(0, 31)
        const rows: string[][] = [['序号', '用例名称', '状态', '结论', '自动化类型', '执行时间']]
        const styles: ('green' | 'red' | 'yellow' | '')[] = ['']
        for (const c of cases) {
          const duration = c.startTime && c.endTime
            ? `${Math.round((new Date(c.endTime).getTime() - new Date(c.startTime).getTime()) / 1000)}s`
            : ''
          rows.push([
            String(c.caseIndex),
            c.caseName,
            c.status,
            c.message,
            automationModeLabel(c.automationMode ?? (c.fullAutomation ? 'full' : 'manual')),
            duration,
          ])
          const statusStyle = c.status === '通过' ? 'green' : c.status === '失败' ? 'red' : c.status === '部分通过' ? 'yellow' : ''
          styles.push(statusStyle)
        }
        sheets.push({ name: sheetName, rows, styles })
      }
    }

    const buffer = generateXlsx(sheets)
    const reportPath = join(resultDir, 'test_report.xlsx')
    writeFileSync(reportPath, buffer)

    let powerArtifactPath: string | null = null
    if (session.testType === 'power') {
      powerArtifactPath = copyPowerArtifactToReport(resultDir)
    }

    let thermalArtifactPath: string | null = null
    if (sessionHasThermCases(session)) {
      thermalArtifactPath = copyThermArtifactsToReport(resultDir)
    }

    // 写入摘要（含项目归属，供中心看板上报 / 事后补传）
    const projectCtx: import('./quality-run-upload').ResolvedProjectContext = session.qualityUploadProject
      ? {
        project_code: session.qualityUploadProject.project_code,
        campaign_id: session.qualityUploadProject.campaign_id,
        source: 'pipeline',
      }
      : await Promise.race([
        resolveSelfCheckProjectContext({
          deviceId,
          deviceName: device.deviceName,
          scheduleKey: session.scheduleKey,
        }).catch((): import('./quality-run-upload').ResolvedProjectContext => ({
          project_code: '_unassigned',
          source: 'unassigned',
        })),
        new Promise<import('./quality-run-upload').ResolvedProjectContext>((resolve) => {
          setTimeout(() => resolve({ project_code: '_unassigned', source: 'unassigned' }), 3_000)
        }),
      ])

    const reportStatus = options?.reportStatus ?? device.status
    const reportDuration = options?.testDuration ?? device.testDuration

    const summary = {
      deviceId,
      deviceName: device.deviceName,
      testType: session.testType,
      version: otaVersion,
      startTime: session.startTime,
      endTime: session.endTime,
      duration: reportDuration,
      status: reportStatus,
      modules: session.moduleProgress,
      totalCases: orderedResults.length,
      passedCases: orderedResults.filter(r => r.status === '通过' || r.status === 'NA').length,
      failedCases: orderedResults.filter(
        r => r.status === '失败'
          || r.status === '部分通过'
          || (r.status === '待确认' && !isPendingManualReportFillIn(r)),
      ).length,
      skippedCases: orderedResults.filter(r => r.status === '跳过').length,
      pendingManualCases: orderedResults.filter(r => isPendingManualReportFillIn(r)).length,
      project_code: projectCtx.project_code,
      ...(projectCtx.campaign_id ? { campaign_id: projectCtx.campaign_id } : {}),
      ...(projectCtx.brand ? { brand: projectCtx.brand } : {}),
      project_source: projectCtx.source,
      ...(session.scheduleKey
        ? { aiPlanned: true, scheduleKey: session.scheduleKey }
        : {}),
      ...(session.testType === 'custom' && session.selectedCases?.length
        ? { selectedCases: session.selectedCases }
        : {}),
      ...(powerArtifactPath ? { powerArtifactPath } : {}),
      ...(thermalArtifactPath ? { thermalArtifactPath } : {}),
      ...(session.testConfig ? { testConfig: session.testConfig } : {}),
    }
    writeFileSync(join(resultDir, 'summary.json'), JSON.stringify(summary, null, 2), 'utf-8')

    const failedCaseItems: SelfCheckFailedCaseItem[] = []

    for (const c of orderedResults) {
      if (isPendingManualReportFillIn(c)) continue
      if (c.status !== '失败' && c.status !== '部分通过' && c.status !== '待确认') continue
      const caseKey = formatCaseResultKey(c.testType, c.module, c.caseIndex)
      failedCaseItems.push({
        caseKey,
        caseName: c.caseName,
        module: c.module,
        status: c.status,
        message: c.message,
      })
    }

    const allCaseItems: SelfCheckCaseItem[] = orderedResults.map(c => ({
      caseKey: formatCaseResultKey(c.testType, c.module, c.caseIndex),
      caseName: c.caseName,
      module: c.module,
      testType: c.testType,
      caseIndex: c.caseIndex,
      status: c.status,
      message: c.message,
      fullAutomation: c.fullAutomation,
      automationMode: c.automationMode ?? (c.fullAutomation ? 'full' : 'manual'),
      steps: c.steps,
      failureLogDir: c.failureLogDir,
    }))

    const detailPayload = buildSelfCheckDetailPayload(summary, failedCaseItems, allCaseItems)
    writeFileSync(join(resultDir, 'detail.json'), JSON.stringify(detailPayload, null, 2), 'utf-8')

    device.resultDir = resultDir
    console.log(`[device-self-check] Report generated: ${resultDir}`)
    emitEvent('report_ready', { deviceId, resultDir })

    // 自动上报中心质量看板（失败不影响本地报告；流水线内自检跳过旁路上报）
    const reportRelPath = join('self-check', deviceId, basename(resultDir)).replace(/\\/g, '/')
    if (session.skipQualityUpload) {
      console.log('[device-self-check] skip quality upload (pipeline origin)')
    } else {
      void uploadSelfCheckReportToCentral({
        summary: {
          deviceId: summary.deviceId,
          deviceName: summary.deviceName,
          testType: summary.testType,
          version: summary.version,
          startTime: summary.startTime,
          endTime: summary.endTime,
          status: summary.status,
          totalCases: summary.totalCases,
          passedCases: summary.passedCases,
          failedCases: summary.failedCases,
          skippedCases: summary.skippedCases,
          aiSummary: detailPayload.aiSummary,
          aiPlanned: summary.aiPlanned,
          scheduleKey: summary.scheduleKey,
          project_code: summary.project_code,
          campaign_id: summary.campaign_id,
          brand: summary.brand,
          testConfig: summary.testConfig,
        },
        detail: detailPayload,
        resultDir,
        reportRelPath,
      }).catch(err => {
        console.warn('[device-self-check] quality upload failed:', (err as Error).message)
      })
    }

    void flushPendingFailureLogExports(deviceId, session).catch((e) => {
      console.warn('[device-self-check] Deferred failure log export failed:', e)
    })
  } catch (e) {
    console.error('[device-self-check] Report generation error:', e)
  }
}

export async function continueTest(deviceId: string): Promise<DeviceDetail | null> {
  try {
    const device = devices[deviceId]
    const session = testSessions[deviceId]
    if (!device || !session) {
      return null
    }

    // 插卡/换卡后继续：先刷新 SIM，再进入 runModule 前置检查
    await refreshDeviceProbeInfo(deviceId)

    device.status = '测试中'
    session.errorReason = undefined
    emitEvent('device_updated', { device })

    const testType = session.testType
    if (testType === 'custom') {
      return { device, session }
    }
    session.isRunning = true

    runTestFlow(deviceId, testType, session, session.currentModuleIndex).catch(e => {
      markTestFlowError(deviceId, e, testType)
    })

    return { device, session }
  } catch (e) {
    console.error('Error continuing test:', e)
    return null
  }
}

export async function resumeTest(deviceId: string): Promise<DeviceDetail | null> {
  try {
    const device = devices[deviceId]
    const session = testSessions[deviceId]
    if (!device || !session || device.status !== '错误') {
      return null
    }

    session.isRunning = true
    session.errorReason = undefined
    device.status = pretestStatus(session)
    emitEvent('device_updated', { device })

    const testType = session.testType
    if (testType === 'custom') {
      const allCases = parseCustomCaseKeys(session.selectedCases || [])
      const remaining = allCases.filter(item => {
        const caseKey = `${item.testType}/${item.module}/${item.caseIndex}`
        const result = session.caseResults[caseKey]
        return !result || !TERMINAL_CASE_STATUSES.has(result.status)
      })
      if (remaining.length === 0) {
        finishTest(deviceId, session)
        return { device: devices[deviceId]!, session }
      }
      const executionRemaining = session.prioritizeTddManual
        ? applyTddManualPriority(remaining)
        : remaining
      bindCustomAuxDevices(session.auxiliaryDevices, deviceId, session)
      runCustomTestFlow(deviceId, session, executionRemaining, { skipDeviceInit: false }).catch(e => {
        markTestFlowError(deviceId, e, 'custom')
      })
    } else {
      runTestFlow(deviceId, testType, session, session.currentModuleIndex).catch(e => {
        markTestFlowError(deviceId, e, testType)
      })
    }

    return { device, session }
  } catch (e) {
    console.error('Error resuming test:', e)
    return null
  }
}

// 判断测试机是否仍处于某类测试流程中（含已完成待用户结束）
function isActiveDutDevice(device: DeviceInfo): boolean {
  if (device.role === '辅测机') return false
  if (!device.testType) return false
  return [
    '初始化中',
    '等待测试开始',
    '测试中',
    '不满足前置条件',
    '完成(通过)',
    '完成(失败)',
    '错误',
  ].includes(device.status)
}

function hasActiveDutForTestType(testType: string, excludeDeviceId?: string): boolean {
  return Object.values(devices).some(
    d => d.deviceId !== excludeDeviceId && isActiveDutDevice(d) && d.testType === testType
  )
}

// 同类测试无测试机时，自动释放待命/占用中的辅测机
function releaseAuxDevicesIfNoActiveDut(testType: string): void {
  if (hasActiveDutForTestType(testType)) {
    return
  }

  for (const dev of Object.values(devices)) {
    if (dev.role !== '辅测机') continue
    if (dev.testType !== testType) continue
    if (dev.status !== '待命' && dev.status !== '占用中') continue

    const stillBound = Object.values(testSessions).some(
      s => s.auxiliaryDevices?.includes(dev.deviceId)
    )
    if (stillBound) continue

    dev.status = '空闲'
    dev.testType = undefined
    dev.testStartTime = undefined
    dev.testDuration = 0
    dev.isMirroredResult = false
    delete testSessions[dev.deviceId]
    emitEvent('device_updated', { device: dev })
    console.log(
      `[device-self-check] Auto-released aux ${dev.deviceId} (no active DUT for ${testType})`
    )
  }
}

// 复测单个用例
export async function retestCase(
  deviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  auxDeviceId?: string
): Promise<CaseResult | null> {
  const session = testSessions[deviceId]
  if (!session) return null

  const device = devices[deviceId]
  if (!device) return null

  // 如果需要辅测机，分配之
  if (auxDeviceId && devices[auxDeviceId]) {
    if (!session.auxiliaryDevices.includes(auxDeviceId)) {
      session.auxiliaryDevices.push(auxDeviceId)
    }
    if (devices[auxDeviceId].role === '测试机') {
      devices[auxDeviceId].status = '测试中'
      const peerSession = testSessions[auxDeviceId]
      if (peerSession) {
        peerSession.auxiliaryDevices = [deviceId]
      }
    } else {
      devices[auxDeviceId].status = '占用中'
    }
    emitEvent('device_updated', { device: devices[auxDeviceId] })
  }

  // 重新执行模块初始化
  await execPythonInit(deviceId, testType, module, session)

  // 重新执行用例
  const result = await runCase(deviceId, testType, module, caseIndex, session)
  const moduleKey = `${testType}/${module}`
  const caseKey = `${moduleKey}/${caseIndex}`
  session.caseResults[caseKey] = result

  // 更新模块进度
  if (session.moduleProgress[moduleKey]) {
    if (result.status === '通过' || result.status === 'NA') {
      session.moduleProgress[moduleKey].passedCases++
    } else if (result.status === '失败') {
      session.moduleProgress[moduleKey].failedCases++
    }
  }

  emitEvent('case_completed', { deviceId, caseKey, result })

  // 释放辅测机
  if (auxDeviceId && devices[auxDeviceId]) {
    if (devices[auxDeviceId].role === '测试机') {
      devices[auxDeviceId].status = '等待测试开始'
    } else {
      devices[auxDeviceId].status = '待命'
    }
    devices[auxDeviceId].isMirroredResult = false
    emitEvent('device_updated', { device: devices[auxDeviceId] })
  }
  session.auxiliaryDevices = session.auxiliaryDevices.filter(id => id !== auxDeviceId)

  return result
}

function caseItemToResult(item: SelfCheckCaseItem): CaseResult {
  const automationMode = item.automationMode
    ?? (item.fullAutomation === false ? 'manual' : 'full')
  return {
    testType: item.testType,
    module: item.module,
    caseIndex: item.caseIndex,
    caseName: item.caseName,
    status: item.status as CaseResult['status'],
    message: item.message,
    fullAutomation: item.fullAutomation ?? automationMode === 'full',
    automationMode,
    steps: (item.steps as CaseStep[]) ?? [],
    failureLogDir: item.failureLogDir,
  }
}

function buildSessionFromReport(
  deviceId: string,
  summary: { testType: string; startTime?: string; endTime?: string; scheduleKey?: string },
  allCaseItems: SelfCheckCaseItem[],
): TestSession {
  const caseResults: Record<string, CaseResult> = {}
  const moduleProgress: Record<string, ModuleProgress> = {}
  const modules: string[] = []
  for (const item of allCaseItems) {
    const moduleKey = `${item.testType}/${item.module}`
    if (!moduleProgress[moduleKey]) {
      modules.push(item.module)
      moduleProgress[moduleKey] = {
        module: item.module,
        totalCases: 0,
        completedCases: 0,
        passedCases: 0,
        failedCases: 0,
      }
    }
    const result = caseItemToResult(item)
    caseResults[item.caseKey] = result
    const prog = moduleProgress[moduleKey]
    prog.totalCases++
    prog.completedCases++
    if (result.status === '通过' || result.status === 'NA') prog.passedCases++
    if (result.status === '失败' || result.status === '部分通过') prog.failedCases++
  }
  return {
    deviceId,
    testType: summary.testType as DeviceTestType,
    modules,
    currentModuleIndex: 0,
    moduleProgress,
    caseResults,
    startTime: summary.startTime,
    endTime: summary.endTime,
    isRunning: true,
    auxiliaryDevices: [],
    selectedCases: summary.testType === 'custom'
      ? ((summary as { selectedCases?: string[] }).selectedCases?.length
        ? (summary as { selectedCases?: string[] }).selectedCases
        : allCaseItems.map(i => i.caseKey))
      : undefined,
    scheduleKey: summary.scheduleKey,
    otaVersion: (summary as { version?: string }).version,
    testConfig: (summary as { testConfig?: SelfCheckTestConfig }).testConfig,
  }
}

export async function retestReportCase(
  reportId: string,
  caseKey: string,
  auxDeviceId?: string,
): Promise<CaseResult | null> {
  const absDir = reportAbsoluteDir(reportId)
  const detailPath = join(absDir, 'detail.json')
  const summaryPath = join(absDir, 'summary.json')
  if (!existsSync(detailPath) || !existsSync(summaryPath)) return null

  const detailJson = JSON.parse(readFileSync(detailPath, 'utf-8')) as {
    allCaseItems?: SelfCheckCaseItem[]
    failedCaseItems?: SelfCheckFailedCaseItem[]
    deviceId: string
    testType: string
    startTime?: string
    endTime?: string
    scheduleKey?: string
  }
  const summaryJson = JSON.parse(readFileSync(summaryPath, 'utf-8')) as {
    deviceId: string
    testType: string
    startTime?: string
    endTime?: string
    scheduleKey?: string
  }

  const allCaseItems = detailJson.allCaseItems?.length
    ? detailJson.allCaseItems
    : (detailJson.failedCaseItems ?? []).map(item => ({
        caseKey: item.caseKey,
        caseName: item.caseName,
        module: item.module,
        testType: item.caseKey.split('/')[0] || summaryJson.testType,
        caseIndex: Number.parseInt(item.caseKey.split('/').pop() || '1', 10),
        status: item.status,
        message: item.message,
      }))

  const target = allCaseItems.find(c => c.caseKey === caseKey)
  if (!target) return null

  const deviceId = summaryJson.deviceId
  const device = devices[deviceId]
  if (!device || device.status !== '空闲') {
    throw new Error('设备非空闲，无法从报告复测')
  }

  const session = buildSessionFromReport(deviceId, summaryJson, allCaseItems)
  testSessions[deviceId] = session
  device.status = '测试中'
  device.testType = session.testType
  emitEvent('device_updated', { device })

  try {
    const result = await retestCase(
      deviceId,
      target.testType,
      target.module,
      target.caseIndex,
      auxDeviceId,
    )
    if (result) {
      const allPassed = Object.values(session.caseResults)
        .every(r => r.status === '通过' || r.status === '跳过')
      device.status = allPassed ? '完成(通过)' : '完成(失败)'
      await generateTestReport(deviceId, session, absDir)
    }
    return result
  } finally {
    resetDeviceToIdleAfterTest(deviceId)
  }
}

// 修改用例结果
export function updateCaseResult(
  deviceId: string,
  testType: string,
  module: string,
  caseIndex: number,
  newStatus: string,
  newMessage: string
): CaseResult | null {
  const session = testSessions[deviceId]
  if (!session) return null

  const caseKey = `${testType}/${module}/${caseIndex}`
  const result = session.caseResults[caseKey]
  if (!result) return null

  result.status = newStatus as any
  result.message = newMessage
  emitEvent('case_completed', { deviceId, caseKey, result })
  return result
}

// 结果和详情
export function getDevice(deviceId: string): DeviceInfo | undefined {
  return devices[deviceId]
}

/** @internal 单测注入设备内存态 */
export function __testingUpsertDevice(device: DeviceInfo, session?: TestSession): void {
  devices[device.deviceId] = {
    ...device,
    simCards: (device.simCards || getDefaultSimCards()).map(s => ({ ...s })),
  }
  if (session) {
    testSessions[device.deviceId] = session
  }
}

/** @internal 单测：报告 OTA 版本解析 */
export async function __testingResolveReportOtaVersion(
  deviceId: string,
  session: TestSession,
): Promise<string> {
  return resolveReportOtaVersion(deviceId, session)
}

export const __testingOtaVersionProp = OTA_VERSION_PROP
export const __testingOtaVersionFallbackProp = OTA_VERSION_FALLBACK_PROP

/** @internal 单测：用例展示名解析（catalog + case_info 名称字段） */
export function __testingResolveCaseDisplayName(
  testType: string,
  module: string,
  caseIndex: number,
  caseInfoItems?: any | null,
): string {
  return resolveCaseDisplayName(testType, module, caseIndex, caseInfoItems)
}

/** @internal 单测：前置配置快照 */
export function __testingSnapshotTestConfig(
  testType: DeviceTestType,
  opts: {
    flashOptions?: DeviceFlashOptions
    tcardOptions?: TcardUpdateOptions
    prioritizeTddManual?: boolean
    selectedCases?: string[]
  },
): SelfCheckTestConfig {
  return snapshotTestConfig(testType, opts)
}

/** @internal 单测：中断路径生成报告并释放设备 */
export function __testingScheduleTestReportIfNeeded(
  deviceId: string,
  session: TestSession,
  options?: { reportStatus?: string },
): void {
  scheduleTestReportIfNeeded(deviceId, session, options)
}

/** @internal 单测清空设备内存态 */
export function __testingResetDevices(): void {
  devices = {}
  testSessions = {}
  initializedDeviceIds = new Set()
}

export function snapshotDevices(): DeviceInfo[] {
  return Object.values(devices)
}

export function countPendingManualDecisions(): number {
  return Object.keys(pendingManualDecisions).length
}

export function getTestSession(deviceId: string): TestSession | undefined {
  return testSessions[deviceId]
}

/** 打开设备会话中某用例的日志目录（若不存在则按结果即时导出） */
export async function openDeviceCaseFailureLogs(deviceId: string, caseKey: string): Promise<string> {
  const session = testSessions[deviceId]
  if (!session) {
    throw new Error('设备无测试会话')
  }
  const result = session.caseResults[caseKey]
    || Object.values(session.caseResults).find(
      r => formatCaseResultKey(r.testType, r.module, r.caseIndex) === caseKey,
    )
  const safeKey = sanitizeCaseKeyForPath(caseKey)
  const sessionDir = getSessionResultDir(deviceId, session)
  let candidate = result?.failureLogDir
    || join(sessionDir, 'case-logs', safeKey)
  if (!result?.failureLogDir && !existsSync(candidate)) {
    candidate = join(sessionDir, 'failure-logs', safeKey)
  }
  const reportsRoot = resolve(tahpPaths.reportsDir, 'self-check')
  let abs = resolve(candidate)
  const rootPrefix = reportsRoot.endsWith(sep) ? reportsRoot : reportsRoot + sep
  if (
    abs.toLowerCase() !== reportsRoot.toLowerCase()
    && !abs.toLowerCase().startsWith(rootPrefix.toLowerCase())
  ) {
    throw new Error('非法日志路径')
  }
  if (!existsSync(abs)) {
    const mode = result?.status === '失败' ? 'failure' : 'execution'
    const exported = await exportCaseLogsForCase(deviceId, session, caseKey, mode)
    if (exported) {
      await attachExportedCaseLogDir(
        deviceId,
        session,
        caseKey,
        exported,
        mode === 'failure' ? '失败日志已导出' : '执行日志已导出',
      )
      abs = resolve(exported)
    }
  }
  if (!existsSync(abs)) {
    throw new Error('日志目录不存在（用例可能尚未执行完成，或会话结果目录未创建）')
  }
  openLocalPath(abs)
  return abs
}

export function getModuleConditions(): Record<string, ModuleCondition> {
  syncAiGeneratedCaseConfig()
  return moduleConditions
}

export function getAllCaseCatalogs(): CaseCatalogGroup[] {
  syncAiGeneratedCaseConfig()
  const TEST_TYPE_LABELS: Record<string, string> = {
    str4: '转测摸底测试',
    week: '周版本测试',
    monkey: 'monkey测试',
    monkey_check: 'monkey结果检查',
    smoke: '冒烟测试',
    ota_upgrade: '连续OTA升级',
    gms: 'GMS测试',
    power: '功耗自动化测试',
    power_feature: '功耗特性自检',
    thermal: '温升方案自检',
    therm: '温升方案自检',
    kernel_feature: '内核特性自检',
    pipeline_adapt: '流水线适配自动化测试',
    ai_generated: 'AI用例',
  }
  const MODULE_ORDER: Record<string, number> = {
    driver: 0,
    driver_component: 0,
    driver_hardware: 1,
    monkey: 2,
    tne: 3,
    usd: 4,
    ota: 5,
    cts: 10,
    gts: 11,
    vts: 12,
    cts_tele: 13,
    current_analysis: 14,
    wbs: 15,
    scheme: 16,
    stability: 17,
    memory: 18,
    sched: 19,
    tp: 30,
    vibrator: 31,
    audio: 32,
    lcm: 33,
    fingerprint: 34,
    charger: 35,
    [AI_GENERATED_MODULE]: 20,
    tdd: 99,
  }

  const modulesByType: Record<string, CaseCatalog[]> = {}
  for (const [key, cond] of Object.entries(moduleConditions)) {
    const [testType, module] = key.split('/')
    if (!modulesByType[testType]) {
      modulesByType[testType] = []
    }
    modulesByType[testType].push({
      key,
      testType,
      module,
      moduleLabel: cond.moduleLabel,
      conditions: {
        dutSimCount: cond.conditions?.dutSimCount ?? 0,
        auxRequired: cond.conditions?.auxRequired ?? 0,
        auxSimCount: cond.conditions?.auxSimCount ?? 0,
      },
      cases: cond.cases.map(c => ({
        caseIndex: c.caseIndex,
        caseName: c.caseName,
        canReuse: c.canReuse,
        automationMode: c.automationMode ?? resolveCaseAutomationMode(testType, module, c.caseIndex, {
          execMode: c.execMode,
        }),
      })),
    })
  }

  const typeOrder = ['str4', 'week', 'monkey', 'monkey_check', 'smoke', 'ota_upgrade', 'gms', 'power', 'power_feature', 'thermal', 'kernel_feature', 'pipeline_adapt', AI_GENERATED_TEST_TYPE]
  const allTypes = [
    ...typeOrder.filter(tt => modulesByType[tt]?.length),
    ...Object.keys(modulesByType).filter(tt => !typeOrder.includes(tt)),
  ]

  return allTypes.map(testType => ({
    testType,
    label: TEST_TYPE_LABELS[testType] || testType,
    modules: modulesByType[testType].sort(
      (a, b) => (MODULE_ORDER[a.module] ?? 50) - (MODULE_ORDER[b.module] ?? 50)
    ),
    ...(testType === 'gms' && !isGmsSupportedOnHost()
      ? { unavailableReason: GMS_WINDOWS_UNSUPPORTED_MESSAGE }
      : {}),
  }))
}

export function getCaseCatalogDetail(testType: string): CaseCatalogDetailItem[] {
  syncAiGeneratedCaseConfig()
  const group = getAllCaseCatalogs().find(g => g.testType === testType)
  if (!group) return []

  const items: CaseCatalogDetailItem[] = []
  for (const mod of group.modules) {
    const moduleKey = `${testType}/${mod.module}`
    if (moduleConditions[moduleKey]?.customOnly) continue
    const caseInfoList = loadCaseInfoList(testType, mod.module)
    for (const c of mod.cases) {
      const info = resolveCaseInfoItem(caseInfoList, c.caseIndex)
      items.push({
        key: `${testType}/${mod.module}/${c.caseIndex}`,
        testType,
        module: mod.module,
        moduleLabel: mod.moduleLabel,
        caseIndex: c.caseIndex,
        caseName: c.caseName,
        canReuse: c.canReuse,
        automationMode: c.automationMode,
        preconditions: info?.['前置条件'] || '',
        manualSteps: info?.['测试步骤'] || '',
        expectedResult: info?.['期望结果'] || '',
      })
    }
  }
  return items
}

export function deleteAiGeneratedCases(caseKeys: string[]): { deleted: string[]; remaining: number } {
  const result = deletePersistedAiGeneratedCases(caseKeys)
  syncAiGeneratedCaseConfig()
  emitEvent('case_catalog_updated', {
    testType: AI_GENERATED_TEST_TYPE,
    module: AI_GENERATED_MODULE,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    deleted: result.deleted,
    remaining: result.remaining,
  })
  return result
}

export async function createAiNlUiCase(payload: {
  caseName: string
  nlDescription: string
  expectedResult?: string
}) {
  const created = await createManualNlUiCase(payload)
  syncAiGeneratedCaseConfig()
  emitEvent('case_catalog_updated', {
    testType: AI_GENERATED_TEST_TYPE,
    module: AI_GENERATED_MODULE,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    created: created.caseKey,
  })
  return created
}

export async function updateAiNlUiCase(payload: {
  caseKey: string
  caseName: string
  nlDescription: string
  expectedResult?: string
}) {
  const updated = await updateManualNlUiCase(payload)
  syncAiGeneratedCaseConfig()
  emitEvent('case_catalog_updated', {
    testType: AI_GENERATED_TEST_TYPE,
    module: AI_GENERATED_MODULE,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    updated: updated.caseKey,
  })
  return updated
}

// 初始化
export function initDeviceSelfCheck(): void {
  loadCaseConfigs()
  loadSettings()
}
