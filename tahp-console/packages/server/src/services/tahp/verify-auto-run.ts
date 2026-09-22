/**
 * 测试账号（域账号 `test-` 前缀）验测任务自动执行器。
 *
 * 流程：中心 `verify/mine?view=open` 拉本人待办 → 轮询设备列表找「该项目」的空闲机 →
 * 取最新 daily 刷机包（勾选刷 Root）→ `startTest` 启动对应测试项 → 全程把执行标签写回中心
 * （等待设备 / 验测执行中 / 等待人工确认 …）→ 报告落盘后自动关单并关联 run_id。
 *
 * 测试项策略：
 *  - 转测摸底测试（str4）/ 周版本测试（week）：**不自动执行**，仅同步到本机打「待人工执行」
 *    标签展示在「总览 → 验测任务」（不写回中心：中心白名单无此码），由人工手动执行；
 *  - GMS测试（gms）：自动执行但**不刷机、不刷 Root 包**，直接使用设备当前版本；
 *    Windows 主机不支持 GMS（无 cts/gts/vts-tradefed），自动任务标记为不支持；
 *  - 其余测试项：自动等设备 → 刷最新 daily（含 Root 包）→ 启动测试。
 *
 * 边界与安全：
 *  - 仅 `test-` 前缀账号生效（`isTestAccountName`），且需 `isLocal() && isCentralConfigured()`；
 *    `TAHP_VERIFY_AUTO_RUN_DISABLED=1` 可整体关闭，EA 界面可暂停/取消。
 *  - 串行：同一时刻只自动执行 1 个任务（按 `created_at` 先来先服务），避免与人工抢多台设备。
 *  - 人工确认用例（`manual_confirm`）**不自动应答**，只打标签等人处理。
 *  - 刷机为破坏性操作：只在设备 `status === '空闲'` 时占用；`startTest` 返回 null 视为抢占失败，下轮重试。
 *  - 中心不可达 / 老中心无 label 接口（404）时静默降级为仅本地标签，不阻塞执行。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { basename, join } from 'path'
import { logger } from '../logger'
import { tahpPaths } from './paths'
import { isCentralConfigured, isLocal } from './runtime-mode'
import { readCentralUserSession } from './central-user-session'
import { readJiraUsername, readJiraUserConfig } from './jira-user-config'
import { bindJiraToCentral } from './sync/jira-bind'
import { centralClient, type CentralVerifyTask } from './sync/central-client'
import { buildSelfCheckRunId } from './quality-run-mapper'
import {
  continueTest,
  endTest,
  getDevice,
  onEvent,
  refreshDevices,
  startTest,
  isGmsSupportedOnHost,
  type DeviceInfo,
  type StandardTestType,
  type StartTestFlashPayload,
} from './device-self-check'
import {
  extractProjectCandidates,
  resolveFlashDeviceIdentity,
  resolveLatestDailyFlashPackage,
  stopActiveFlash,
} from './device-flash'

/** 测试域账号前缀（与 client `config-navigation.ts` / 中心 `auth/test-accounts.ts` 同一约定） */
export const TEST_ACCOUNT_PREFIX = 'test-'

/** 与中心 `VERIFY_TASK_LABELS` 白名单对齐（中心不认识的码会被 400 拒绝） */
export const VERIFY_AUTO_LABELS = {
  waiting_device: '等待设备',
  resolving_flash: '解析刷机包',
  running: '验测执行中',
  waiting_human: '等待人工确认',
  precheck_blocked: '前置不满足',
  flash_failed: '刷机失败',
  run_failed: '验测失败',
  wait_timeout: '等待设备超时',
  completed_pass: '验测完成(通过)',
  completed_fail: '验测完成(失败)',
  close_failed: '关单失败·待人工',
  /** 仅本机展示（中心 VERIFY_TASK_LABELS 白名单无此码，不写回） */
  manual_only: '待人工执行',
  paused: '已暂停',
  cancelled: '已取消',
} as const

export type VerifyAutoLabelCode = keyof typeof VERIFY_AUTO_LABELS

export type VerifyAutoPhase =
  | 'waiting_device'
  | 'resolving_flash'
  | 'running'
  | 'waiting_human'
  | 'precheck_blocked'
  | 'flash_failed'
  | 'run_failed'
  | 'wait_timeout'
  | 'completing'
  | 'completed_pass'
  | 'completed_fail'
  | 'close_failed'
  | 'unsupported'
  | 'manual_only'
  | 'cancelled'
  | 'gone'

/**
 * 已收尾（不再认领、不再推进）的相位。
 * manual_only 不认领、不推进也归入此类（暂停/恢复、事件订阅均不触碰）；
 * 但它并非终态——中心侧完成后仍按 gone 清理（见 syncRemoteTasks）。
 */
const CLOSED_PHASES: VerifyAutoPhase[] = [
  'completed_pass',
  'completed_fail',
  'close_failed',
  'wait_timeout',
  'unsupported',
  'manual_only',
  'cancelled',
  'gone',
]

/** 需要向中心关单的相位（成功失败都自动关单） */
const PENDING_CLOSE_PHASES: VerifyAutoPhase[] = ['completing', 'flash_failed', 'run_failed']

/** EA「测试执行」支持的测试项（中心目录与此对齐；不在表内的不自动执行） */
const SUPPORTED_TEST_TYPES: StandardTestType[] = [
  'str4', 'week', 'monkey', 'smoke', 'gms', 'power', 'power_feature', 'thermal', 'pipeline_adapt', 'ai_generated',
]

/** 不自动执行、仅展示「待人工执行」的测试项（转测摸底 / 周版本：由人工把控刷机版本与执行范围） */
const MANUAL_ONLY_TEST_TYPES = ['str4', 'week']

/** 自动执行但跳过刷机（不刷机、不刷 Root 包），直接使用设备当前版本的测试项 */
const SKIP_FLASH_TEST_TYPES = ['gms']

/** 等待匹配设备的上限（默认 4h），超时打标签让位下一个任务 */
const DEFAULT_MAX_WAIT_MS = 4 * 60 * 60 * 1000
const DEFAULT_POLL_MS = 30_000
/** 单轮最多解析多少台设备的项目归属（adb getprop + 版本共享目录，代价高） */
const PROJECT_PROBE_PER_TICK = 5
const PROJECT_CACHE_TTL_MS = 10 * 60 * 1000
const MAX_FLASH_ATTEMPTS = 3
const MAX_CLOSE_ATTEMPTS = 5

export interface VerifyAutoTaskState {
  task_id: string
  test_type: string
  item_label: string
  project?: string
  created_at: string
  phase: VerifyAutoPhase
  label_code: VerifyAutoLabelCode
  label: string
  device_id?: string
  run_id?: string
  report_dir?: string
  waiting_since?: string
  started_at?: string
  ended_at?: string
  /** 已成功关单的时间（成功/失败都算关单） */
  closed_at?: string
  attempts: number
  close_attempts: number
  last_error?: string
  /** 标签写回中心的失败原因（与设备/执行原因分开，避免互相覆盖） */
  label_error?: string
  /** 标签已成功写回中心的时间；为空表示待重试 */
  label_synced_at?: string
  updated_at: string
}

export interface VerifyAutoRunState {
  schema_version: 1
  enabled: boolean
  account?: string
  active_task_id?: string
  updated_at: string
  tasks: VerifyAutoTaskState[]
}

export interface VerifyAutoRunStatus {
  eligible: boolean
  reason?: string
  enabled: boolean
  account?: string
  is_test_account: boolean
  active_task_id?: string
  poll_ms: number
  max_wait_device_ms: number
  tasks: VerifyAutoTaskState[]
}

/** 供 `/api/tahp/verify-tasks/mine` 富化：task_id → 本机自动化状态 */
export type VerifyAutoLabelMap = Record<string, {
  label: string
  label_code: VerifyAutoLabelCode
  phase: VerifyAutoPhase
  device_id?: string
  run_id?: string
  waiting_since?: string
  started_at?: string
  last_error?: string
  label_error?: string
  updated_at: string
}>

function pollMs(): number {
  const v = Number(process.env.TAHP_VERIFY_AUTO_RUN_POLL_MS)
  return Number.isFinite(v) && v > 0 ? v : DEFAULT_POLL_MS
}

function maxWaitMs(): number {
  const v = Number(process.env.TAHP_VERIFY_AUTO_RUN_WAIT_MS)
  return Number.isFinite(v) && v > 0 ? v : DEFAULT_MAX_WAIT_MS
}

function stateDir(): string {
  const dir = process.env.TAHP_VERIFY_AUTO_RUN_DIR
    || join(tahpPaths.projectRoot, '.tahp-config', 'verify-auto-run')
  mkdirSync(dir, { recursive: true })
  return dir
}

function statePath(): string {
  return join(stateDir(), 'state.json')
}

export function isTestAccountName(username: unknown): boolean {
  return String(username || '').trim().toLowerCase().startsWith(TEST_ACCOUNT_PREFIX)
}

/** 本机当前中心账号：中心会话优先，其次 Jira / 一键配置域账号 */
export function resolveAutoRunAccount(): string {
  const fromSession = String(readCentralUserSession()?.username || '').trim()
  if (fromSession) return fromSession
  return String(readJiraUsername() || '').trim()
}

export function verifyAutoRunEnabled(): boolean {
  return process.env.TAHP_VERIFY_AUTO_RUN_DISABLED !== '1'
}

function emptyState(): VerifyAutoRunState {
  return { schema_version: 1, enabled: true, updated_at: new Date().toISOString(), tasks: [] }
}

export function loadVerifyAutoRunState(): VerifyAutoRunState {
  const p = statePath()
  if (!existsSync(p)) return emptyState()
  try {
    const parsed = JSON.parse(readFileSync(p, 'utf-8')) as VerifyAutoRunState
    if (!parsed || !Array.isArray(parsed.tasks)) return emptyState()
    return {
      schema_version: 1,
      enabled: parsed.enabled !== false,
      account: parsed.account,
      active_task_id: parsed.active_task_id,
      updated_at: parsed.updated_at || new Date().toISOString(),
      tasks: parsed.tasks,
    }
  } catch {
    return emptyState()
  }
}

function saveState(state: VerifyAutoRunState): void {
  state.updated_at = new Date().toISOString()
  try {
    writeFileSync(statePath(), JSON.stringify(state, null, 2), 'utf-8')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[verify-auto-run] 状态落盘失败')
  }
}

export function isVerifyAutoRunEligible(): { eligible: boolean; reason?: string; account?: string } {
  if (!verifyAutoRunEnabled()) return { eligible: false, reason: 'disabled_by_env' }
  if (!isLocal()) return { eligible: false, reason: 'not_local_role' }
  if (!isCentralConfigured()) return { eligible: false, reason: 'central_not_configured' }
  const account = resolveAutoRunAccount()
  if (!account) return { eligible: false, reason: 'no_account' }
  if (!isTestAccountName(account)) return { eligible: false, reason: 'not_test_account', account }
  if (!loadVerifyAutoRunState().enabled) return { eligible: false, reason: 'paused', account }
  return { eligible: true, account }
}

/** 中心会话 token：优先本机已存会话，缺失时用 Jira/域凭据重新绑定（测试账号走中心旁路） */
async function ensureSessionToken(): Promise<string> {
  const existing = readCentralUserSession()?.token || ''
  if (existing) return existing
  const jira = readJiraUserConfig()
  if (!jira?.username || !jira?.password) return ''
  try {
    const bound = await bindJiraToCentral({
      username: jira.username,
      password: jira.password,
      baseUrl: jira.base_url,
    })
    return bound?.token || ''
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[verify-auto-run] 中心绑定失败')
    return ''
  }
}

// ─── 标签 ────────────────────────────────────────────────────────────────

function setLabel(
  state: VerifyAutoRunState,
  task: VerifyAutoTaskState,
  code: VerifyAutoLabelCode,
  extra?: { text?: string; phase?: VerifyAutoPhase; error?: string },
): void {
  const text = extra?.text || VERIFY_AUTO_LABELS[code]
  const changed = task.label_code !== code || task.label !== text
  task.label_code = code
  task.label = text
  if (extra?.phase) task.phase = extra.phase
  if (extra?.error !== undefined) task.last_error = extra.error || undefined
  task.updated_at = new Date().toISOString()
  if (changed) task.label_synced_at = undefined
  saveState(state)
}

/** 老中心没有 label 接口（404）时置位：不再每轮重试，避免刷请求与日志 */
let labelWriteUnsupported = false

/** 标签写回中心：失败只记待重试（老中心 404 / 中心不可达均静默降级为本地显示） */
async function pushLabel(token: string, task: VerifyAutoTaskState): Promise<void> {
  if (task.label_synced_at || labelWriteUnsupported) return
  try {
    await centralClient.labelVerifyTask(token, task.task_id, {
      label_code: task.label_code,
      label: task.label,
    })
    task.label_synced_at = new Date().toISOString()
    task.label_error = undefined
  } catch (err) {
    const message = (err as Error).message || ''
    task.label_error = `标签写回失败：${message}`.slice(0, 200)
    if (/\b404\b/.test(message)) {
      labelWriteUnsupported = true
      logger.warn('[verify-auto-run] 中心未提供标签接口（404），标签仅本机显示；升级中心后重启即恢复')
      return
    }
    logger.warn({ err: message, taskId: task.task_id }, '[verify-auto-run] 标签写回中心失败（本地仍显示）')
  }
}

// ─── 设备项目归属 ─────────────────────────────────────────────────────────

const projectCache = new Map<string, { project: string; at: number }>()

function normalizeProject(raw: string): string {
  return String(raw || '').trim().toUpperCase()
}

/**
 * 解析设备所属项目：adb getprop + 版本共享目录（权威）；失败回落到设备名里的项目代号。
 * 结果按设备缓存 10 分钟，避免每轮重复打 adb / SMB。
 */
async function resolveDeviceProject(device: DeviceInfo): Promise<string> {
  const cached = projectCache.get(device.deviceId)
  if (cached && Date.now() - cached.at < PROJECT_CACHE_TTL_MS) return cached.project
  let project = ''
  try {
    const identity = await resolveFlashDeviceIdentity(device.deviceId)
    project = normalizeProject(identity.project)
  } catch (err) {
    const candidates = extractProjectCandidates(device.deviceName || '', device.deviceId || '')
    project = normalizeProject(candidates[0] || '')
    logger.debug(
      { err: (err as Error).message, deviceId: device.deviceId, project },
      '[verify-auto-run] 设备项目精确解析失败，回落设备名候选',
    )
  }
  projectCache.set(device.deviceId, { project, at: Date.now() })
  return project
}

function projectMatches(taskProject: string | undefined, deviceProject: string): boolean {
  const want = normalizeProject(taskProject || '')
  if (!want) return true
  if (!deviceProject) return false
  return deviceProject === want || deviceProject.startsWith(want) || want.startsWith(deviceProject)
}

// ─── 主流程 ──────────────────────────────────────────────────────────────

function isManualOnlyTestType(testType: string): boolean {
  return MANUAL_ONLY_TEST_TYPES.includes(String(testType || '').trim())
}

function syncRemoteTasks(state: VerifyAutoRunState, remote: CentralVerifyTask[]): void {
  const known = new Map(state.tasks.map(t => [t.task_id, t]))
  for (const row of remote) {
    const existing = known.get(row.task_id)
    if (existing) {
      existing.project = row.project || existing.project
      existing.item_label = row.item_label || existing.item_label
      // 策略调整前已跟踪的 str4/week：未认领设备的转「待人工执行」（已在跑的让它跑完关单）
      if (existing.phase === 'waiting_device' && isManualOnlyTestType(existing.test_type)) {
        existing.waiting_since = undefined
        setLabel(state, existing, 'manual_only', { phase: 'manual_only', error: '' })
      }
      continue
    }
    const manualOnly = isManualOnlyTestType(String(row.test_type || '').trim())
    state.tasks.push({
      task_id: row.task_id,
      test_type: String(row.test_type || '').trim(),
      item_label: row.item_label,
      project: row.project,
      created_at: row.created_at,
      phase: manualOnly ? 'manual_only' : 'waiting_device',
      label_code: manualOnly ? 'manual_only' : 'waiting_device',
      label: manualOnly ? VERIFY_AUTO_LABELS.manual_only : VERIFY_AUTO_LABELS.waiting_device,
      waiting_since: manualOnly ? undefined : new Date().toISOString(),
      attempts: 0,
      close_attempts: 0,
      updated_at: new Date().toISOString(),
    })
  }
  // 中心已关单/改派：未收尾的本地任务停止跟踪（manual_only 虽不收尾，中心完成后同样移除）
  const remoteIds = new Set(remote.map(r => r.task_id))
  for (const task of state.tasks) {
    if (remoteIds.has(task.task_id)) continue
    if (CLOSED_PHASES.includes(task.phase) && task.phase !== 'manual_only') continue
    task.phase = 'gone'
    task.updated_at = new Date().toISOString()
    if (state.active_task_id === task.task_id) state.active_task_id = undefined
  }
}

function isSupportedTestType(testType: string): testType is StandardTestType {
  return (SUPPORTED_TEST_TYPES as string[]).includes(testType)
}

/** 选中空闲设备 → 按测试项策略刷最新 daily 包或直接用设备当前版本 → 启动测试 */
async function claimAndStart(state: VerifyAutoRunState, task: VerifyAutoTaskState, token: string): Promise<void> {
  let devices: DeviceInfo[] = []
  try {
    devices = await refreshDevices()
  } catch (err) {
    setLabel(state, task, 'waiting_device', {
      phase: 'waiting_device',
      error: `设备列表刷新失败：${(err as Error).message}`,
    })
    return
  }
  const idle = devices.filter(d => d.status === '空闲' && d.role !== '辅测机')
  if (!idle.length) {
    setLabel(state, task, 'waiting_device', { phase: 'waiting_device', error: '无空闲设备' })
    markWaitTimeout(state, task)
    return
  }

  let matched: DeviceInfo | null = null
  let probed = 0
  for (const device of idle) {
    if (probed >= PROJECT_PROBE_PER_TICK) break
    probed += 1
    if (projectMatches(task.project, await resolveDeviceProject(device))) {
      matched = device
      break
    }
  }
  if (!matched) {
    setLabel(state, task, 'waiting_device', {
      phase: 'waiting_device',
      error: `无项目 ${task.project || '—'} 的空闲设备`,
    })
    markWaitTimeout(state, task)
    return
  }

  if (!isSupportedTestType(task.test_type)) {
    setLabel(state, task, 'precheck_blocked', {
      text: '测试项不支持自动执行',
      phase: 'unsupported',
      error: `未知测试项: ${task.test_type}`,
    })
    task.ended_at = new Date().toISOString()
    return
  }

  if (task.test_type === 'gms' && !isGmsSupportedOnHost()) {
    setLabel(state, task, 'precheck_blocked', {
      text: '测试项不支持自动执行',
      phase: 'unsupported',
      error: 'Windows 环境不支持 GMS 测试，请在 Linux 主机上运行',
    })
    task.ended_at = new Date().toISOString()
    return
  }

  // GMS 等测试项：不刷机、不刷 Root 包，直接使用设备当前版本执行
  const skipFlash = SKIP_FLASH_TEST_TYPES.includes(task.test_type)
  let flashPayload: StartTestFlashPayload = { enabled: false }
  if (!skipFlash) {
    setLabel(state, task, 'resolving_flash', { phase: 'resolving_flash', error: '' })
    let packagePath = ''
    try {
      packagePath = (await resolveLatestDailyFlashPackage({ deviceId: matched.deviceId })).packagePath
    } catch (err) {
      task.attempts += 1
      const message = (err as Error).message || '未知错误'
      if (task.attempts >= MAX_FLASH_ATTEMPTS) {
        setLabel(state, task, 'flash_failed', {
          phase: 'flash_failed',
          error: `最新 daily 刷机包解析失败（已试 ${task.attempts} 次）：${message}`,
        })
        task.ended_at = new Date().toISOString()
        // 失败也自动关单（无报告则不关联 run_id）
        await closeTask(state, task, token)
        return
      }
      setLabel(state, task, 'waiting_device', {
        phase: 'waiting_device',
        error: `刷机包解析失败：${message}`,
      })
      return
    }
    flashPayload = { enabled: true, pkgPath: packagePath, enableRootPkg: true, stageVersion: 'Open' }
  }

  const detail = await startTest(matched.deviceId, task.test_type, flashPayload, {})
  if (!detail) {
    // 设备被人工或其它流程抢走：下一轮重新匹配
    task.attempts += 1
    setLabel(state, task, 'waiting_device', {
      phase: 'waiting_device',
      error: `设备 ${matched.deviceId} 已非空闲，重新等待`,
    })
    return
  }

  task.device_id = matched.deviceId
  task.started_at = new Date().toISOString()
  task.attempts = 0
  state.active_task_id = task.task_id
  setLabel(state, task, 'running', { phase: 'running', error: '' })
  logger.info(
    { taskId: task.task_id, deviceId: matched.deviceId, testType: task.test_type, packagePath: flashPayload.pkgPath },
    skipFlash
      ? '[verify-auto-run] 已自动启动验测（不刷机，使用设备当前版本）'
      : '[verify-auto-run] 已自动启动验测（刷最新 daily + Root 包）',
  )
}

function markWaitTimeout(state: VerifyAutoRunState, task: VerifyAutoTaskState): void {
  if (!task.waiting_since) return
  if (Date.now() - Date.parse(task.waiting_since) <= maxWaitMs()) return
  setLabel(state, task, 'wait_timeout', {
    phase: 'wait_timeout',
    error: `等待设备超过 ${Math.round(maxWaitMs() / 3600_000)} 小时`,
  })
  task.ended_at = new Date().toISOString()
}

/** 已启动任务的相位推进（事件驱动为主，这里做兜底与关单重试） */
async function advanceActive(state: VerifyAutoRunState, task: VerifyAutoTaskState, token: string): Promise<void> {
  if (!task.device_id) return
  const device = getDevice(task.device_id)
  if (!device) {
    // 服务端重启或设备掉线：回到等待设备重新排队
    task.device_id = undefined
    task.started_at = undefined
    if (state.active_task_id === task.task_id) state.active_task_id = undefined
    setLabel(state, task, 'waiting_device', { phase: 'waiting_device', error: '设备状态丢失，重新排队' })
    return
  }
  if (device.status === '不满足前置条件') {
    setLabel(state, task, 'precheck_blocked', {
      phase: 'precheck_blocked',
      error: device.currentModule ? `模块 ${device.currentModule} 前置条件不满足` : '前置条件不满足',
    })
    return
  }
  if (device.status === '等待测试开始') {
    // 等辅测机就绪：非人工判定项，自动继续
    try {
      await continueTest(task.device_id)
      setLabel(state, task, 'running', { phase: 'running', error: '' })
    } catch (err) {
      setLabel(state, task, 'precheck_blocked', { error: `继续测试失败：${(err as Error).message}` })
    }
    return
  }
  if (device.status === '错误') {
    setLabel(state, task, 'run_failed', { phase: 'run_failed', error: '设备进入错误状态' })
    task.ended_at = new Date().toISOString()
    if (state.active_task_id === task.task_id) state.active_task_id = undefined
    await closeTask(state, task, token)
    return
  }
  if (device.status === '空闲') {
    // 会话已结束（人工结束或流程收尾）：未产出报告则按失败关单
    if (!task.closed_at) {
      setLabel(state, task, 'run_failed', { phase: 'run_failed', error: '测试已结束但未产出报告' })
      task.ended_at = new Date().toISOString()
      if (state.active_task_id === task.task_id) state.active_task_id = undefined
      await closeTask(state, task, token)
    }
    return
  }
  if (device.status === '完成(通过)' || device.status === '完成(失败)') {
    // 等 report_ready 事件带出 resultDir；这里只做兜底
    task.phase = task.phase === 'waiting_human' ? task.phase : 'completing'
    return
  }
  if (task.phase !== 'waiting_human' && task.phase !== 'precheck_blocked') {
    setLabel(state, task, 'running', { phase: 'running' })
  }
}

function readReportStatus(resultDir: string): { status: string; failedCases: number } | null {
  try {
    const summaryPath = join(resultDir, 'summary.json')
    if (!existsSync(summaryPath)) return null
    const summary = JSON.parse(readFileSync(summaryPath, 'utf-8')) as { status?: string; failedCases?: number }
    return { status: String(summary.status || ''), failedCases: Number(summary.failedCases || 0) }
  } catch {
    return null
  }
}

/** 关单：关联本人验测报告（run_id）并写终态标签；中心未同步好则按轮次重试 */
async function closeTask(state: VerifyAutoRunState, task: VerifyAutoTaskState, token: string): Promise<void> {
  if (task.closed_at) return
  if (!task.run_id && task.report_dir && task.device_id) {
    task.run_id = buildSelfCheckRunId(task.device_id, basename(task.report_dir))
  }
  task.close_attempts += 1
  const report = task.report_dir ? readReportStatus(task.report_dir) : null
  const passed = !!report && report.status.includes('通过') && report.failedCases === 0
  const terminalCode: VerifyAutoLabelCode = task.phase === 'flash_failed'
    ? 'flash_failed'
    : !report && task.phase === 'run_failed'
      ? 'run_failed'
      : passed ? 'completed_pass' : 'completed_fail'
  try {
    await centralClient.completeVerifyTask(token, task.task_id, {
      run_id: task.run_id || undefined,
      label_code: terminalCode,
      label: VERIFY_AUTO_LABELS[terminalCode],
    })
    task.phase = terminalCode
    task.label_code = terminalCode
    task.label = VERIFY_AUTO_LABELS[terminalCode]
    task.label_synced_at = new Date().toISOString()
    task.closed_at = task.label_synced_at
    task.ended_at = task.ended_at || task.closed_at
    if (state.active_task_id === task.task_id) state.active_task_id = undefined
    logger.info(
      { taskId: task.task_id, runId: task.run_id, label: task.label },
      '[verify-auto-run] 验测任务已自动关单',
    )
  } catch (err) {
    const message = (err as Error).message || ''
    if (task.close_attempts >= MAX_CLOSE_ATTEMPTS) {
      setLabel(state, task, 'close_failed', { phase: 'close_failed', error: `关单失败：${message}` })
      task.ended_at = new Date().toISOString()
      if (state.active_task_id === task.task_id) state.active_task_id = undefined
      saveState(state)
      return
    }
    task.phase = 'completing'
    task.last_error = `关单重试中（${task.close_attempts}/${MAX_CLOSE_ATTEMPTS}）：${message}`
    logger.warn({ err: message, taskId: task.task_id }, '[verify-auto-run] 关单失败，稍后重试')
  }
  saveState(state)
}

function trackedTask(state: VerifyAutoRunState, deviceId: string): VerifyAutoTaskState | undefined {
  return state.tasks.find(t => t.device_id === deviceId && !CLOSED_PHASES.includes(t.phase))
}

let ticking = false

/** 一轮调度：同步中心待办 → 补推标签 → 关单 → 推进在跑任务 → 串行认领下一个 */
export async function tickVerifyAutoRun(): Promise<{ eligible: boolean; reason?: string; active_task_id?: string }> {
  if (ticking) return { eligible: false, reason: 'busy' }
  ticking = true
  // 事件订阅与调度器解耦：任何入口（定时器 / 手动 tick / 单测）都保证已订阅
  bindDeviceEvents()
  try {
    const gate = isVerifyAutoRunEligible()
    if (!gate.eligible) return { eligible: false, reason: gate.reason }
    const state = loadVerifyAutoRunState()
    state.account = gate.account
    const token = await ensureSessionToken()
    if (!token) {
      saveState(state)
      return { eligible: false, reason: 'no_central_session' }
    }
    let remote: CentralVerifyTask[] = []
    try {
      remote = await centralClient.verifyMine(token)
    } catch (err) {
      saveState(state)
      return { eligible: true, reason: (err as Error).message }
    }
    syncRemoteTasks(state, remote)

    for (const task of state.tasks) {
      // manual_only 标签仅本机展示：中心 VERIFY_TASK_LABELS 白名单无此码，写回会被 400 拒绝
      if (task.phase === 'gone' || task.phase === 'manual_only' || task.label_synced_at) continue
      await pushLabel(token, task)
    }

    for (const task of state.tasks) {
      if (task.closed_at || !PENDING_CLOSE_PHASES.includes(task.phase)) continue
      await closeTask(state, task, token)
    }

    const active = state.active_task_id
      ? state.tasks.find(t => t.task_id === state.active_task_id)
      : undefined
    if (active && !CLOSED_PHASES.includes(active.phase) && !PENDING_CLOSE_PHASES.includes(active.phase)) {
      await advanceActive(state, active, token)
    } else if (active && !PENDING_CLOSE_PHASES.includes(active.phase)) {
      state.active_task_id = undefined
    }

    if (!state.active_task_id) {
      const next = state.tasks
        .filter(t => t.phase === 'waiting_device' && !t.closed_at)
        .sort((a, b) => a.created_at.localeCompare(b.created_at))[0]
      if (next) {
        await claimAndStart(state, next, token)
        if (!next.label_synced_at) await pushLabel(token, next)
      }
    }

    saveState(state)
    return { eligible: true, active_task_id: state.active_task_id }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[verify-auto-run] tick 失败')
    return { eligible: false, reason: (err as Error).message }
  } finally {
    ticking = false
  }
}

// ─── 事件订阅（一次注册，按 deviceId 过滤） ───────────────────────────────

let eventsBound = false

function bindDeviceEvents(): void {
  if (eventsBound) return
  eventsBound = true

  const withTask = (
    deviceId: unknown,
    handle: (state: VerifyAutoRunState, task: VerifyAutoTaskState) => void,
    after?: () => void,
  ) => {
    const id = String(deviceId || '').trim()
    if (!id) return
    const state = loadVerifyAutoRunState()
    const task = trackedTask(state, id)
    if (!task) return
    handle(state, task)
    saveState(state)
    after?.()
  }

  onEvent('flash_completed', (data: any) => {
    if (data?.success !== false) return
    withTask(data?.deviceId, (state, task) => {
      setLabel(state, task, 'flash_failed', { phase: 'flash_failed', error: String(data?.error || '刷机失败') })
      task.ended_at = new Date().toISOString()
      if (state.active_task_id === task.task_id) state.active_task_id = undefined
    }, () => void tickVerifyAutoRun())
  })

  onEvent('manual_confirm', (data: any) => {
    // 不自动应答：打标签等人在 EA 界面确认
    withTask(data?.deviceId, (state, task) => {
      setLabel(state, task, 'waiting_human', {
        phase: 'waiting_human',
        error: String(data?.message || '等待人工确认'),
      })
    }, () => void tickVerifyAutoRun())
  })

  onEvent('precheck_failed', (data: any) => {
    withTask(data?.deviceId, (state, task) => {
      setLabel(state, task, 'precheck_blocked', {
        phase: 'precheck_blocked',
        error: String(data?.reason || '前置条件不满足'),
      })
    })
  })

  onEvent('test_error', (data: any) => {
    withTask(data?.deviceId, (state, task) => {
      setLabel(state, task, 'run_failed', { phase: 'run_failed', error: String(data?.message || '执行错误') })
    })
  })

  onEvent('report_ready', (data: any) => {
    withTask(data?.deviceId, (state, task) => {
      const resultDir = String(data?.resultDir || '')
      task.report_dir = resultDir || task.report_dir
      if (task.report_dir) {
        task.run_id = buildSelfCheckRunId(String(data?.deviceId || task.device_id || ''), basename(task.report_dir))
      }
      task.phase = 'completing'
      task.updated_at = new Date().toISOString()
    }, () => void tickVerifyAutoRun())
  })

  onEvent('test_ended', (data: any) => {
    withTask(data?.deviceId, (state, task) => {
      task.device_id = undefined
      if (state.active_task_id === task.task_id) state.active_task_id = undefined
      if (!task.closed_at && !CLOSED_PHASES.includes(task.phase) && task.phase !== 'completing') {
        setLabel(state, task, 'run_failed', { phase: 'run_failed', error: '测试结束但未产出报告' })
      }
    }, () => void tickVerifyAutoRun())
  })
}

// ─── 生命周期与外部控制 ───────────────────────────────────────────────────

let timer: ReturnType<typeof setInterval> | null = null

export function startVerifyAutoRun(): void {
  if (timer) return
  bindDeviceEvents()
  const gate = isVerifyAutoRunEligible()
  if (!gate.eligible) {
    logger.info({ reason: gate.reason }, '[verify-auto-run] 当前不满足自动执行条件')
  }
  void tickVerifyAutoRun()
  timer = setInterval(() => void tickVerifyAutoRun(), pollMs())
  if (typeof timer.unref === 'function') timer.unref()
  logger.info({ pollMs: pollMs(), maxWaitMs: maxWaitMs() }, '[verify-auto-run] 调度器已启动')
}

export function stopVerifyAutoRun(): void {
  if (timer) clearInterval(timer)
  timer = null
}

export function getVerifyAutoRunStatus(): VerifyAutoRunStatus {
  const gate = isVerifyAutoRunEligible()
  const state = loadVerifyAutoRunState()
  const account = gate.account || resolveAutoRunAccount()
  return {
    eligible: gate.eligible,
    reason: gate.reason,
    enabled: state.enabled,
    account: account || undefined,
    is_test_account: isTestAccountName(account),
    active_task_id: state.active_task_id,
    poll_ms: pollMs(),
    max_wait_device_ms: maxWaitMs(),
    tasks: state.tasks,
  }
}

export function getVerifyAutoLabelMap(): VerifyAutoLabelMap {
  const out: VerifyAutoLabelMap = {}
  for (const task of loadVerifyAutoRunState().tasks) {
    if (task.phase === 'gone') continue
    out[task.task_id] = {
      label: task.label,
      label_code: task.label_code,
      phase: task.phase,
      device_id: task.device_id,
      run_id: task.run_id,
      waiting_since: task.waiting_since,
      started_at: task.started_at,
      last_error: task.last_error,
      label_error: task.label_error,
      updated_at: task.updated_at,
    }
  }
  return out
}

export function setVerifyAutoRunEnabled(enabled: boolean): VerifyAutoRunStatus {
  const state = loadVerifyAutoRunState()
  state.enabled = enabled
  for (const task of state.tasks) {
    if (CLOSED_PHASES.includes(task.phase) || task.closed_at) continue
    if (enabled) {
      if (task.phase === 'waiting_device' || task.label_code === 'paused') {
        setLabel(state, task, 'waiting_device', { phase: 'waiting_device', error: '' })
      }
    } else {
      setLabel(state, task, 'paused', { error: '自动化已暂停' })
    }
  }
  saveState(state)
  if (enabled) void tickVerifyAutoRun()
  return getVerifyAutoRunStatus()
}

/** 取消某个任务的自动执行；正在跑则结束测试（刷机中额外杀掉刷机进程） */
export async function cancelVerifyAutoRunTask(taskId: string): Promise<{ cancelled: boolean; error?: string }> {
  const state = loadVerifyAutoRunState()
  const task = state.tasks.find(t => t.task_id === taskId)
  if (!task) return { cancelled: false, error: '任务不在本机自动化列表' }
  const deviceId = task.device_id
  if (deviceId) {
    try {
      const device = getDevice(deviceId)
      if (device?.status === '刷机中' || device?.status === 'T卡升级中') stopActiveFlash()
      await endTest(deviceId)
    } catch (err) {
      logger.warn({ err: (err as Error).message, deviceId }, '[verify-auto-run] 结束测试失败')
    }
  }
  task.device_id = undefined
  task.ended_at = new Date().toISOString()
  if (state.active_task_id === task.task_id) state.active_task_id = undefined
  setLabel(state, task, 'cancelled', { phase: 'cancelled', error: '本机取消自动执行' })
  saveState(state)
  const token = await ensureSessionToken()
  if (token) await pushLabel(token, task)
  return { cancelled: true }
}

/** @internal 单测用：停调度、清缓存与状态文件（并允许重新订阅事件） */
export function __testingResetVerifyAutoRun(): void {
  stopVerifyAutoRun()
  projectCache.clear()
  ticking = false
  eventsBound = false
  labelWriteUnsupported = false
  try {
    writeFileSync(statePath(), JSON.stringify(emptyState(), null, 2), 'utf-8')
  } catch { /* ignore */ }
}

/** @internal 单测用：直接写入状态 */
export function __testingWriteVerifyAutoRunState(state: VerifyAutoRunState): void {
  saveState(state)
}

/** @internal 单测用：清空设备项目缓存 */
export function __testingClearProjectCache(): void {
  projectCache.clear()
}
