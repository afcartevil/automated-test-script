/**
 * 设备自动化自检服务
 */
import { spawn } from 'child_process'
import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'fs'
import type { ServerResponse } from 'http'
import { join, resolve } from 'path'
import AdmZip from 'adm-zip'
import {
  type DeviceFlashOptions,
  runDeviceFlash,
  waitForAdbDevice,
} from './device-flash'
import { resolvePythonSpawn, tahpPaths } from './paths'
import { buildSelfCheckDetailPayload, type SelfCheckFailedCaseItem } from './self-check-reports'
import { markPlanExecutionCompleted } from './test-plan-executions'

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

export type StandardTestType = 'str4' | 'week' | 'monkey' | 'smoke'
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
  initializedPythonModules?: string[]
  flashOptions?: DeviceFlashOptions
  scheduleKey?: string
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

export interface DeviceDetail {
  device: DeviceInfo
  session?: TestSession
}

// 内存状态存储 - 只使用一个单一的数据源，避免不一致
let devices: Record<string, DeviceInfo> = {}
let testSessions: Record<string, TestSession> = {}
let moduleConditions: Record<string, ModuleCondition> = {}

// 配置路径
const SELF_CHECK_DIR = tahpPaths.selfCheckDir
const PYTHON_DIR = join(SELF_CHECK_DIR, 'python')
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
  preconditions: string
  manualSteps: string
  expectedResult: string
}

function getAutoRetestConfig(testType: string): { enabled: boolean; count: number } {
  if (testType === 'monkey' || testType === 'smoke') {
    return { enabled: false, count: 0 }
  }
  return {
    enabled: settings.autoRetestEnabled?.[testType] ?? true,
    count: Math.max(0, settings.autoRetestCount?.[testType] ?? 1),
  }
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
    const caseKey = `${moduleKey}/${caseIndex}`
    const existing = session.caseResults[caseKey]
    if (!existing?.fullAutomation || existing.status !== '失败') continue

    for (let attempt = 0; attempt < count; attempt++) {
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
  }
}

export function updateSettings(newSettings: AutoTestSettings): void {
  settings = {
    ...newSettings,
    autoTestEnabled: newSettings.autoTestEnabled || {},
    autoTestPath: newSettings.autoTestPath || {},
    monkeyDuration: normalizeMonkeyDuration(newSettings.monkeyDuration),
    smokeUsdSkipSpdInfo: Boolean(newSettings.smokeUsdSkipSpdInfo),
  }
  saveSettings()
}

// 加载用例配置
function loadCaseConfigs(): void {
  const configFiles = [
    'str4_tdd.json', 'str4_driver_component.json', 'str4_driver_hardware.json',
    'week_tdd.json', 'week_driver.json',
    'monkey_monkey.json',
    'smoke_usd.json',
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
      moduleConditions[key] = config
      console.log(`[device-self-check] Loaded config: ${key}`)
    } catch (e) {
      console.warn(`[device-self-check] Failed to load config: ${file}`, e)
    }
  }
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

// 使用 ADB 获取设备列表
async function getAdbDevices(): Promise<string[]> {
  return new Promise((resolve) => {
    let adbProcess: any = null
    let timeoutId: NodeJS.Timeout | null = null
    
    const cleanup = () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
      if (adbProcess && !adbProcess.killed) {
        try {
          adbProcess.kill()
        } catch {
          // ignore
        }
      }
    }

    timeoutId = setTimeout(() => {
      cleanup()
      console.warn('[device-self-check] ADB command timeout - returning empty device list')
      resolve([])
    }, 5000) // 5秒超时

    try {
      adbProcess = spawn('adb', ['devices'], {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: process.platform === 'win32' // 在 Windows 上使用 shell
      })

      let stdout = ''
      let stderr = ''
      
      adbProcess.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString()
      })
      
      adbProcess.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString()
      })

      adbProcess.on('close', (code: number) => {
        cleanup()
        if (code !== 0 && stderr) {
          console.warn('[device-self-check] ADB command error:', stderr)
        }
        const lines = stdout.split('\n')
        const deviceIds: string[] = []
        for (const line of lines) {
          const trimmed = line.trim()
          if (trimmed && !trimmed.startsWith('List')) {
            const parts = trimmed.split(/\s+/)
            if (parts.length >= 2 && parts[1] === 'device') {
              deviceIds.push(parts[0])
            }
          }
        }
        resolve(deviceIds)
      })

      adbProcess.on('error', (err: Error) => {
        cleanup()
        console.warn('[device-self-check] ADB process error:', err.message)
        resolve([])
      })
    } catch (err) {
      cleanup()
      console.warn('[device-self-check] Failed to spawn ADB process:', err)
      resolve([])
    }
  })
}

// 获取设备名称
async function getDeviceName(deviceId: string): Promise<string> {
  return new Promise((resolve) => {
    let adbProcess: any = null
    let timeoutId: NodeJS.Timeout | null = null
    
    const cleanup = () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
      if (adbProcess && !adbProcess.killed) {
        try {
          adbProcess.kill()
        } catch {
          // ignore
        }
      }
    }

    timeoutId = setTimeout(() => {
      cleanup()
      console.warn('[device-self-check] ADB get device name timeout - using deviceId as name')
      resolve(deviceId)
    }, 3000) // 3秒超时

    try {
      adbProcess = spawn('adb', ['-s', deviceId, 'shell', 'getprop', 'ro.product.model'], {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: process.platform === 'win32' // 在 Windows 上使用 shell
      })

      let stdout = ''
      
      adbProcess.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString()
      })

      adbProcess.on('close', () => {
        cleanup()
        resolve(stdout.trim() || deviceId)
      })

      adbProcess.on('error', () => {
        cleanup()
        resolve(deviceId)
      })
    } catch (err) {
      cleanup()
      console.warn('[device-self-check] Failed to spawn ADB getprop process:', err)
      resolve(deviceId)
    }
  })
}

// 获取设备 SIM 卡信息（仅用 getprop gsm.sim.state 判断）
async function getSimInfo(deviceId: string): Promise<SimCardInfo[]> {
  const simCards: SimCardInfo[] = [
    { slotIndex: 0, operator: '', phoneNumber: '', present: false },
    { slotIndex: 1, operator: '', phoneNumber: '', present: false }
  ]

  try {
    const simState = await execAdbSimple(['-s', deviceId, 'shell', 'getprop', 'gsm.sim.state'])
    // 格式: "LOADED,LOADED" / "LOADED,ABSENT" / "ABSENT,ABSENT" / "NOT_READY,NOT_READY"
    if (simState) {
      const states = simState.trim().split(',')
      if (states.length >= 1 && states[0].toUpperCase() === 'LOADED') {
        simCards[0].present = true
      }
      if (states.length >= 2 && states[1].toUpperCase() === 'LOADED') {
        simCards[1].present = true
      }
    }
  } catch (e) {
    console.warn('[device-self-check] Failed to get SIM info:', e)
  }

  const detectedCount = simCards.filter(c => c.present).length
  console.log(`[device-self-check] Device ${deviceId} SIM: ${detectedCount} card(s), ` +
    `Slot0=${simCards[0].present}, Slot1=${simCards[1].present}`)

  return simCards
}

// 简单的 ADB 命令执行
async function execAdbSimple(args: string[]): Promise<string> {
  return new Promise((resolve) => {
    let adbProcess: any = null
    let timeoutId: NodeJS.Timeout | null = null
    
    const cleanup = () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
      if (adbProcess && !adbProcess.killed) {
        try { adbProcess.kill() } catch { /* ignore */ }
      }
    }

    timeoutId = setTimeout(() => { cleanup(); resolve('') }, 2000)

    try {
      adbProcess = spawn('adb', args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: process.platform === 'win32'
      })
      
      let stdout = ''
      
      adbProcess.stdout?.on('data', (data: Buffer) => { stdout += data.toString() })
      
      adbProcess.on('close', () => { cleanup(); resolve(stdout.trim()) })
      adbProcess.on('error', () => { cleanup(); resolve('') })
    } catch (err) {
      cleanup(); resolve('')
    }
  })
}

// 获取 SIM 卡运营商
async function getSimOperator(deviceId: string, slot: number): Promise<string> {
  return new Promise((resolve) => {
    let adbProcess: any = null
    let timeoutId: NodeJS.Timeout | null = null
    
    const cleanup = () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
      if (adbProcess && !adbProcess.killed) {
        try {
          adbProcess.kill()
        } catch {
          // ignore
        }
      }
    }

    timeoutId = setTimeout(() => {
      cleanup()
      resolve('')
    }, 3000)

    try {
      adbProcess = spawn('adb', ['-s', deviceId, 'shell', 'getprop', 'gsm.sim.operator.alpha'], {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: process.platform === 'win32'
      })

      let stdout = ''
      
      adbProcess.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString()
      })

      adbProcess.on('close', () => {
        cleanup()
        const operator = stdout.trim()
        resolve(operator || '未知运营商')
      })

      adbProcess.on('error', () => {
        cleanup()
        resolve('')
      })
    } catch (err) {
      cleanup()
      resolve('')
    }
  })
}

// 异步更新设备信息（不阻塞主流程）
async function updateDeviceInfoAsync(deviceId: string): Promise<void> {
  try {
    // 异步获取设备名称和 SIM 卡信息，不阻塞
    const [deviceName, simCards] = await Promise.all([
      getDeviceName(deviceId),
      getSimInfo(deviceId)
    ])
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
        const [deviceName, simCards] = await Promise.all([
          getDeviceName(deviceId),
          getSimInfo(deviceId)
        ])
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
        const [deviceName, simCards] = await Promise.all([
          getDeviceName(deviceId),
          getSimInfo(deviceId)
        ])
        return { deviceId, deviceName, simCards }
      })
    )

    // 并行更新已有设备的 SIM 信息
    const existingIds = adbDeviceIds.filter(id => devices[id] && ['空闲', '完成(通过)', '完成(失败)', '错误'].includes(devices[id].status))
    const existingUpdates = await Promise.all(
      existingIds.map(async (deviceId) => {
        const simCards = await getSimInfo(deviceId)
        return { deviceId, simCards }
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
        newDevices[update.deviceId] = { ...devices[update.deviceId], simCards: update.simCards }
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

  // 检查 SIM 卡数量
  if (cond.dutSimCount > 0) {
    const simCount = device.simCards.filter(s => s.present).length
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
  if (testType === 'smoke') return ['usd']
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
    caseName: `用例${caseIndex}`,
    status: '进行中',
    message: '',
    fullAutomation: false,
    steps: [{
      stepDesc: '正在加载用例...',
      status: '进行中',
      timestamp: startTime
    }],
    startTime
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
      if (Array.isArray(caseInfoList) && caseIndex > 0 && caseIndex <= caseInfoList.length) {
        caseInfoItems = caseInfoList[caseIndex - 1]
        result.caseName = caseInfoItems['用例名'] || caseInfoItems.case_name || `用例${caseIndex}`
        result.fullAutomation = isFullAutomation(caseInfoItems['测试步骤'] || '')
        // 解析测试步骤到子步骤
        const testSteps = caseInfoItems['测试步骤'] || ''
        if (testSteps) {
          result.steps = parseTestSteps(testSteps)
        }
      }
    } catch {}
  }

  // 检查是否有对应的 .py 脚本
  const caseScript = join(PYTHON_DIR, 'cases', testType, module, `case${caseIndex}.py`)
  if (!existsSync(caseScript)) {
    result.status = '待确认'
    result.message = '需人工测试'
    result.steps = [
      { stepDesc: '加载用例信息', status: '完成', timestamp: startTime },
      { stepDesc: '此用例无自动化脚本', status: '未开始', timestamp: new Date().toISOString() },
    ]
    emitEvent('case_completed', { deviceId, caseKey, result })

    // 暂停等待人工确认
    const decisionId = `pending_${caseKey}_${Date.now()}`
    const pendingPromise = new Promise<string>((res) => {
      pendingManualDecisions[decisionId] = {
        deviceId,
        caseKey,
        message: `用例"${result.caseName}"需要人工测试。\n请手动完成测试后确认结果。`,
        resolve: (decision: string) => {
          res(decision)
          delete pendingManualDecisions[decisionId]
          result.status = decision === 'pass' ? '通过' : '失败'
          result.message = decision === 'pass' ? '人工测试通过' : '人工测试失败'
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
      : pythonResult.status === 'skip' ? '跳过'
      : '跳过'
    result.message = pythonResult.message || ''
    result.fullAutomation = pythonResult.fullAutomation !== false
    result.steps.push({
      stepDesc: `结果: ${result.message || result.status}`,
      status: result.status,
      timestamp: new Date().toISOString()
    })
    // 待确认的用例：暂停测试，等待前端人工决策
    if (result.status === '待确认') {
      const decisionId = `pending_${caseKey}_${Date.now()}`
      const pendingPromise = new Promise<string>((res) => {
        const handler = (decision: string) => {
          res(decision)
          delete pendingManualDecisions[decisionId]
        }
        pendingManualDecisions[decisionId] = {
          deviceId,
          caseKey,
          message: result.message || '需人工评判',
          resolve: (decision: string) => {
            handler(decision)
            // 更新结果
            result.status = decision === 'pass' ? '通过' : '失败'
            result.message = decision === 'pass' ? '人工确认通过' : '人工确认失败'
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
        message: result.message || '需人工评判'
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
    module_init_done: Boolean(
      testType &&
      module &&
      session?.initializedPythonModules?.includes(`${testType}/${module}`)
    ),
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
    if (proc && !proc.killed) { try { proc.kill() } catch {} }
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
    env: { ...process.env, PYTHONPATH: PYTHON_DIR, PYTHONUTF8: '1' },
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

const CASE_EXEC_TIMEOUT_MS = 120_000
const SMOKE_USD_EXEC_TIMEOUT_MS = 3_600_000
const MANUAL_CONFIRM_TIMEOUT_MS = 30 * 60_000

function resolveCaseExecTimeoutMs(testType: string, module: string): number {
  if (testType === 'smoke' && module === 'usd') {
    const raw = Number(process.env.TAHP_SMOKE_USD_TIMEOUT_MS)
    return Number.isFinite(raw) && raw > 0 ? raw : SMOKE_USD_EXEC_TIMEOUT_MS
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
): Promise<{ status: string; message: string; steps: CaseStep[]; fullAutomation?: boolean }> {
  return new Promise((resolve) => {
    const runCaseScript = join(PYTHON_DIR, 'run_case.py')
    const deviceInfoJson = JSON.stringify(deviceInfo)
    const caseKey = `${testType}/${module}/${caseIndex}`

    const { command, prefixArgs } = resolvePythonSpawn()
    let proc: any = null
    let timeoutId: NodeJS.Timeout | null = null
    let settled = false

    const finish = (result: { status: string; message: string; steps: CaseStep[]; fullAutomation?: boolean }) => {
      if (settled) return
      settled = true
      cleanup()
      resolve(result)
    }

    const cleanup = () => {
      if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
      if (proc && !proc.killed) { try { proc.kill() } catch {} }
    }

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
        env: { ...process.env, PYTHONPATH: PYTHON_DIR, PYTHONUTF8: '1' }
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
              fullAutomation: parsed.full_automation
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
    const caseIndex = cases[i]?.case_index || (i + 1)
    session.moduleProgress[moduleKey].currentCaseIndex = caseIndex

    const caseKey = `${moduleKey}/${caseIndex}`

    // 先创建初始结果并存入 session，让前端实时可见
    const initialResult: CaseResult = {
      testType,
      module,
      caseIndex,
      caseName: `用例${caseIndex}`,
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

    if (result.status === '通过') {
      session.moduleProgress[moduleKey].passedCases++
    } else if (result.status === '失败') {
      session.moduleProgress[moduleKey].failedCases++
      if (result.fullAutomation) {
        failedAutoCases.push(caseIndex)
      }
    }

    emitEvent('case_completed', { deviceId, caseKey, result })

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

  // 处理 can_reuse=false 的双向执行：互为测试机的设备需各自执行不可复用用例
  const peerTesters = session.auxiliaryDevices.filter(
    auxId => devices[auxId]?.role === '测试机'
  )
  for (const peerId of peerTesters) {
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

  await retestFailedAutoCasesInModule(deviceId, testType, module, failedAutoCases, session)

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

function buildFlashOptionsFromPayload(payload?: StartTestFlashPayload): DeviceFlashOptions | undefined {
  if (!payload?.enabled || !payload.pkgPath?.trim()) return undefined
  return {
    pkgPath: payload.pkgPath.trim(),
    enableRootPkg: payload.enableRootPkg === true,
    rootPkgPath: payload.rootPkgPath?.trim() || undefined,
    stageVersion: payload.stageVersion?.trim() || undefined,
  }
}

async function runFlashBeforeTest(deviceId: string, session: TestSession): Promise<boolean> {
  if (!session.flashOptions) return true

  const device = devices[deviceId]
  if (!device) return false

  device.status = '刷机中'
  emitEvent('device_updated', { device })
  emitEvent('flash_log', { deviceId, line: '[刷机] 开始准备刷机环境…' })

  const result = await runDeviceFlash([deviceId], session.flashOptions, (line) => {
    emitEvent('flash_log', { deviceId, line })
  })

  if (!result.success) {
    device.status = '错误'
    session.isRunning = false
    emitEvent('device_updated', { device })
    emitEvent('flash_completed', {
      deviceId,
      success: false,
      returnCode: result.returnCode,
      error: result.error,
    })
    return false
  }

  emitEvent('flash_completed', { deviceId, success: true, returnCode: result.returnCode })
  const reconnected = await waitForAdbDevice(deviceId)
  if (!reconnected) {
    device.status = '错误'
    session.isRunning = false
    emitEvent('device_updated', { device })
    return false
  }
  return true
}

export interface StartTestOptions {
  scheduleKey?: string
}

// 启动测试
export async function startTest(
  deviceId: string,
  testType: StandardTestType,
  flash?: StartTestFlashPayload,
  options?: StartTestOptions,
): Promise<DeviceDetail | null> {
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

    // 更新设备状态
    device.status = flashOptions ? '刷机中' : '初始化中'
    device.testType = testType
    device.testStartTime = new Date().toISOString()
    emitEvent('device_updated', { device })

    // 创建测试会话
    const modules = getModulesForTestType(testType)

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
      scheduleKey: options?.scheduleKey,
    }

    testSessions[deviceId] = session
    emitEvent('test_started', { deviceId, testType, session })

    // 初始化：设置亮屏时间为30分钟
    execAdbSimple(['-s', deviceId, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '1800000'])
      .catch(() => {})

    // 异步执行测试流程
    runTestFlow(deviceId, testType, session).catch(e => {
      console.error(`[device-self-check] Test flow error:`, e)
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
  customAuxDeviceIds: string[]
): Promise<DeviceDetail | null> {
  try {
    const device = devices[deviceId]
    if (!device || device.status !== '空闲') return null

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

    const session: TestSession = {
      deviceId,
      testType: 'custom',
      modules,
      currentModuleIndex: 0,
      moduleProgress: {},
      caseResults: {},
      startTime: device.testStartTime,
      isRunning: true,
      auxiliaryDevices: customAuxDeviceIds,
      selectedCases,
      customAuxDevices: customAuxDeviceIds,
      initializedPythonModules: [],
    }

    testSessions[deviceId] = session
    emitEvent('test_started', { deviceId, testType: 'custom', session })

    execAdbSimple(['-s', deviceId, 'shell', 'settings', 'put', 'system', 'screen_off_timeout', '1800000'])
      .catch(() => {})

    runCustomTestFlow(deviceId, session, caseList).catch(e => {
      console.error('[device-self-check] Custom test flow error:', e)
    })

    return { device, session }
  } catch (e) {
    console.error('Error starting custom test:', e)
    return null
  }
}

// 异步执行测试流程
async function runTestFlow(
  deviceId: string,
  testType: StandardTestType,
  session: TestSession
): Promise<void> {
  if (session.flashOptions) {
    const flashOk = await runFlashBeforeTest(deviceId, session)
    if (!flashOk || !session.isRunning) return
  }

  const device = devices[deviceId]
  if (device) {
    device.status = '初始化中'
    emitEvent('device_updated', { device })
    await execDeviceInit(deviceId, session)
  }

  const modules = session.modules

  for (let idx = 0; idx < modules.length; idx++) {
    const module = modules[idx]
    session.currentModuleIndex = idx

    await runModule(deviceId, testType, module, session)

    const device = devices[deviceId]
    if (!device || !session.isRunning) {
      return
    }

    // 不满足前置条件 → 停止
    if (device.status === '不满足前置条件') {
      return
    }
    // 等待辅测机 → 暂停，等待 continueTest
    if (device.status === '等待测试开始') {
      return
    }
  }

  // 测试完成
  finishTest(deviceId, session)
}

// 自定义测试：按勾选用例列表执行
async function runCustomTestFlow(
  deviceId: string,
  session: TestSession,
  caseList: { testType: string; module: string; caseIndex: number }[]
): Promise<void> {
  const device = devices[deviceId]
  if (!device) return

  const moduleKeys = new Set(caseList.map(c => `${c.testType}/${c.module}`))
  for (const mk of moduleKeys) {
    const moduleCases = caseList.filter(c => `${c.testType}/${c.module}` === mk)
    session.moduleProgress[mk] = {
      module: mk,
      totalCases: moduleCases.length,
      completedCases: 0,
      passedCases: 0,
      failedCases: 0,
    }
  }

  for (const auxId of session.auxiliaryDevices) {
    if (devices[auxId]) {
      if (devices[auxId].role === '测试机') {
        devices[auxId].status = '测试中'
      } else {
        devices[auxId].status = '占用中'
      }
      emitEvent('device_updated', { device: devices[auxId] })
    }
  }

  device.status = '初始化中'
  emitEvent('device_updated', { device })
  await execDeviceInit(deviceId, session)

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

    if (result.status === '通过') {
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
  session.auxiliaryDevices = []

  finishTest(deviceId, session)
}

// 完成测试
function finishTest(deviceId: string, session: TestSession): void {
  const device = devices[deviceId]
  if (!device) return

  const allPassed = Object.values(session.caseResults)
    .every(r => r.status === '通过' || r.status === '跳过')
  device.status = allPassed ? '完成(通过)' : '完成(失败)'
  device.testDuration = Math.round(
    (Date.now() - new Date(device.testStartTime || Date.now()).getTime()) / 1000
  )
  session.endTime = new Date().toISOString()
  session.isRunning = false

  emitEvent('device_updated', { device })
  emitEvent('test_completed', { deviceId, session })

  if (session.scheduleKey) {
    void markPlanExecutionCompleted(session.scheduleKey).catch(err => {
      console.warn('[device-self-check] Failed to mark plan completed:', session.scheduleKey, err)
    })
  }

  // 生成 xlsx 报告
  generateTestReport(deviceId, session).catch(e => {
    console.warn('[device-self-check] Failed to generate report:', e)
  })
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
<fills count="5">
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

async function generateTestReport(deviceId: string, session: TestSession): Promise<void> {
  try {
    const device = devices[deviceId]
    if (!device) return

    const resultDir = join(tahpPaths.reportsDir, 'self-check', deviceId, session.startTime?.replace(/[:.]/g, '-') || '')
    mkdirSync(resultDir, { recursive: true })

    // 按模块分组
    const moduleCases: Record<string, CaseResult[]> = {}
    for (const result of Object.values(session.caseResults)) {
      if (!moduleCases[result.module]) moduleCases[result.module] = []
      moduleCases[result.module].push(result)
    }
    for (const cases of Object.values(moduleCases)) {
      cases.sort((a, b) => a.caseIndex - b.caseIndex)
    }

    const sheets: { name: string; rows: string[][]; styles: ('green' | 'red' | 'yellow' | '')[] }[] = []

    if (session.testType === 'custom') {
      const rows: string[][] = [['序号', '用例名称', '所属模块', '状态', '结论', '是否全自动', '执行时间']]
      const styles: ('green' | 'red' | 'yellow' | '')[] = ['']
      const orderedResults: CaseResult[] = []

      if (session.selectedCases) {
        for (const caseKey of session.selectedCases) {
          const result = session.caseResults[caseKey]
          if (result) orderedResults.push(result)
        }
      } else {
        orderedResults.push(...Object.values(session.caseResults))
      }

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
          c.fullAutomation ? '是' : '否',
          duration,
        ])
        const statusStyle = c.status === '通过' ? 'green' : c.status === '失败' ? 'red' : c.status === '部分通过' ? 'yellow' : ''
        styles.push(statusStyle)
      }
      sheets.push({ name: '自定义测试', rows, styles })
    } else {
      for (const [module, cases] of Object.entries(moduleCases)) {
        const rows: string[][] = [['序号', '用例名称', '状态', '结论', '是否全自动', '执行时间']]
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
            c.fullAutomation ? '是' : '否',
            duration,
          ])
          const statusStyle = c.status === '通过' ? 'green' : c.status === '失败' ? 'red' : c.status === '部分通过' ? 'yellow' : ''
          styles.push(statusStyle)
        }
        sheets.push({ name: module, rows, styles })
      }
    }

    if (sheets.length === 0) {
      sheets.push({ name: '摘要', rows: [['无测试数据'], []], styles: [''] })
    }

    const buffer = generateXlsx(sheets)
    const reportPath = join(resultDir, 'test_report.xlsx')
    writeFileSync(reportPath, buffer)

    // 写入摘要
    const summary = {
      deviceId,
      deviceName: device.deviceName,
      testType: session.testType,
      startTime: session.startTime,
      endTime: session.endTime,
      duration: device.testDuration,
      status: device.status,
      modules: session.moduleProgress,
      totalCases: Object.keys(session.caseResults).length,
      passedCases: Object.values(session.caseResults).filter(r => r.status === '通过').length,
      failedCases: Object.values(session.caseResults).filter(r => r.status === '失败').length,
      skippedCases: Object.values(session.caseResults).filter(r => r.status === '跳过').length,
      ...(session.scheduleKey
        ? { aiPlanned: true, scheduleKey: session.scheduleKey }
        : {}),
    }
    writeFileSync(join(resultDir, 'summary.json'), JSON.stringify(summary, null, 2), 'utf-8')

    const failedCaseItems: SelfCheckFailedCaseItem[] = []
    const orderedResults: CaseResult[] = session.testType === 'custom' && session.selectedCases
      ? session.selectedCases
          .map(caseKey => session.caseResults[caseKey])
          .filter((r): r is CaseResult => Boolean(r))
      : Object.values(session.caseResults)

    for (const c of orderedResults) {
      if (c.status !== '失败' && c.status !== '部分通过' && c.status !== '待确认') continue
      const caseKey = `${c.testType}/${c.module}/${c.caseIndex}`
      failedCaseItems.push({
        caseKey,
        caseName: c.caseName,
        module: c.module,
        status: c.status,
        message: c.message,
      })
    }

    const detailPayload = buildSelfCheckDetailPayload(summary, failedCaseItems)
    writeFileSync(join(resultDir, 'detail.json'), JSON.stringify(detailPayload, null, 2), 'utf-8')

    device.resultDir = resultDir
    console.log(`[device-self-check] Report generated: ${resultDir}`)
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

    device.status = '测试中'
    emitEvent('device_updated', { device })

    // 重新检查前置条件并继续未完成的模块
    const testType = session.testType
    if (testType === 'custom') {
      return { device, session }
    }
    const remainingModules = session.modules.slice(session.currentModuleIndex)
    session.isRunning = true

    runTestFlow(deviceId, testType, session).catch(e => {
      console.error(`[device-self-check] Continue test flow error:`, e)
    })

    return { device, session }
  } catch (e) {
    console.error('Error continuing test:', e)
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

// 结束测试（释放所有资源，并停止后台 Monkey）
export async function endTest(deviceId: string): Promise<DeviceDetail | null> {
  const device = devices[deviceId]
  const session = testSessions[deviceId]
  if (!device) return null

  const endedTestType = device.testType || session?.testType

  await stopMonkeyForDevice(deviceId)

  if (session) {
    session.isRunning = false
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
  if (session?.auxiliaryDevices) {
    for (const auxId of session.auxiliaryDevices) {
      if (devices[auxId]) {
        if (devices[auxId].role === '测试机') {
          // 测试机互相作为辅测机：恢复为等待测试开始
          devices[auxId].status = '等待测试开始'
        } else if (devices[auxId].status === '占用中') {
          // 显式辅测机：恢复待命
          devices[auxId].status = '待命'
        }
        devices[auxId].isMirroredResult = false
        emitEvent('device_updated', { device: devices[auxId] })
      }
    }
  }

  // 重置测试机状态
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
    if (result.status === '通过') {
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

export function snapshotDevices(): DeviceInfo[] {
  return Object.values(devices)
}

export function countPendingManualDecisions(): number {
  return Object.keys(pendingManualDecisions).length
}

export function getTestSession(deviceId: string): TestSession | undefined {
  return testSessions[deviceId]
}

export function getModuleConditions(): Record<string, ModuleCondition> {
  return moduleConditions
}

export function getAllCaseCatalogs(): CaseCatalogGroup[] {
  const TEST_TYPE_LABELS: Record<string, string> = {
    str4: '转测摸底测试',
    week: '周版本测试',
    monkey: 'monkey测试',
    smoke: '冒烟测试',
  }
  const MODULE_ORDER: Record<string, number> = {
    driver: 0,
    driver_component: 0,
    driver_hardware: 1,
    monkey: 2,
    usd: 3,
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
      })),
    })
  }

  const typeOrder = ['str4', 'week', 'monkey', 'smoke']
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
  }))
}

export function getCaseCatalogDetail(testType: string): CaseCatalogDetailItem[] {
  const group = getAllCaseCatalogs().find(g => g.testType === testType)
  if (!group) return []

  const items: CaseCatalogDetailItem[] = []
  for (const mod of group.modules) {
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
        preconditions: info?.['前置条件'] || '',
        manualSteps: info?.['测试步骤'] || '',
        expectedResult: info?.['期望结果'] || '',
      })
    }
  }
  return items
}

// 初始化
export function initDeviceSelfCheck(): void {
  loadCaseConfigs()
  loadSettings()
}
