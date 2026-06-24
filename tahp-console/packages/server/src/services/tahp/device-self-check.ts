/**
 * 设备自动化自检服务
 */
import { spawn } from 'child_process'
import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'fs'
import type { ServerResponse } from 'http'
import { join, resolve } from 'path'
import { tahpPaths } from './paths'

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
  testType?: 'str4' | 'week'
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
  testType: 'str4' | 'week'
  modules: string[]
  currentModuleIndex: number
  moduleProgress: Record<string, ModuleProgress>
  caseResults: Record<string, CaseResult>
  startTime?: string
  endTime?: string
  isRunning: boolean
  auxiliaryDevices: string[]
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

// 加载用例配置
function loadCaseConfigs(): void {
  const configFiles = [
    'str4_tdd.json', 'str4_driver_component.json', 'str4_driver_hardware.json',
    'week_tdd.json', 'week_driver.json'
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
        role: '测试机',
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
        role: '测试机',
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
      if (['测试中', '初始化中', '等待测试开始', '待命', '占用中'].includes(device.status)) {
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
    const auxDevices = Object.values(devices).filter(
      d => d.deviceId !== deviceId && d.role === '辅测机' && (d.status === '空闲' || d.status === '占用中' || d.status === '待命')
    )
    if (auxDevices.length < cond.auxRequired) {
      return { status: 'waiting_aux', reason: `等待辅测机（需要${cond.auxRequired}台，当前${auxDevices.length}台）` }
    }
    return { status: 'passed', reason: '前置条件满足', auxDeviceIds: auxDevices.slice(0, cond.auxRequired).map(d => d.deviceId) }
  }

  return { status: 'passed', reason: '前置条件满足' }
}

// 获取模块列表
function getModulesForTestType(testType: 'str4' | 'week'): string[] {
  return testType === 'str4'
    ? ['driver_component', 'driver_hardware', 'tdd']
    : ['driver', 'tdd']
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
      caseKey,
      message: `用例"${result.caseName}"需要人工测试。\n请手动完成测试后确认结果。`
    })
    await pendingPromise
    return result
  }

  result.steps.push({ stepDesc: '正在执行用例脚本...', status: '进行中', timestamp: new Date().toISOString() })
  emitEvent('case_completed', { deviceId, caseKey, result })

  // 构建 device_info 传给 Python 脚本
  const deviceInfo = buildDeviceInfo(deviceId, testType, module)

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
function buildDeviceInfo(deviceId: string, testType: string, module: string): any {
  const dut = devices[deviceId]
  if (!dut) return { DUT: [] }

  // 查找辅测机
  const config = moduleConditions[`${testType}/${module}`]
  const auxDevices: any[] = []
  if (config?.conditions.auxRequired > 0) {
    for (const [id, dev] of Object.entries(devices)) {
      if (id !== deviceId && dev.role === '辅测机' && (dev.status === '空闲' || dev.status === '待命')) {
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
    Auxiliary: auxDevices
  }
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

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    let proc: any = null
    let timeoutId: NodeJS.Timeout | null = null

    const cleanup = () => {
      if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
      if (proc && !proc.killed) { try { proc.kill() } catch {} }
    }

    timeoutId = setTimeout(() => {
      cleanup()
      resolve({ status: 'fail', message: '用例执行超时(120s)', steps: [] })
    }, 120000)

    try {
      proc = spawn(pythonCmd, [
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
      let pendingManualResolve: ((decision: string) => void) | null = null

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
            // 需要人工确认：暂停，发送事件到前端，等待回复
            const decisionId = `manual_${caseKey}_${Date.now()}`
            const pendingPromise = new Promise<string>((res) => {
              pendingManualResolve = res
            })
            pendingManualDecisions[decisionId] = {
              deviceId,
              caseKey,
              message: parsed.message || '需人工确认',
              resolve: (decision: string) => {
                if (pendingManualResolve) {
                  pendingManualResolve(decision)
                  pendingManualResolve = null
                }
                delete pendingManualDecisions[decisionId]
              }
            }
            emitEvent('manual_confirm', {
              decisionId,
              caseKey,
              message: parsed.message || '需人工确认'
            })
            // 等待前端回复后写入 stdin
            pendingPromise.then((decision) => {
              if (proc && proc.stdin && !proc.stdin.destroyed) {
                try {
                  proc.stdin.write(decision + '\n')
                } catch {}
              }
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
        cleanup()
        try {
          const resultLine = lastResultLine || (() => {
            const lines = stdout.split('\n').filter((l: string) => l.trim().startsWith('{'))
            return lines[lines.length - 1] || ''
          })()

          const trimmed = resultLine.trim()
          if (trimmed.startsWith('{')) {
            const parsed = JSON.parse(trimmed)
            resolve({
              status: parsed.status || 'fail',
              message: parsed.message || stderr.trim(),
              steps: parsed.steps || [],
              fullAutomation: parsed.full_automation
            })
          } else {
            resolve({
              status: code === 0 ? 'pass' : 'fail',
              message: stdout.trim() || stderr.trim() || `退出码: ${code}`,
              steps: []
            })
          }
        } catch {
          resolve({
            status: code === 0 ? 'pass' : 'fail',
            message: stdout.trim() || stderr.trim() || `退出码: ${code}`,
            steps: []
          })
        }
      })

      proc.on('error', (err: any) => {
        cleanup()
        resolve({ status: 'fail', message: `启动Python失败: ${err.message}`, steps: [] })
      })
    } catch (err: any) {
      cleanup()
      resolve({ status: 'fail', message: `启动Python失败: ${err.message}`, steps: [] })
    }
  })
}

// 等待人工决策
const pendingManualDecisions: Record<string, {
  caseKey: string
  message: string
  resolve: (decision: string) => void
  deviceId: string
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
export function getPendingManualDecision(deviceId: string): { decisionId: string; message: string } | null {
  for (const [id, decision] of Object.entries(pendingManualDecisions)) {
    if (decision.deviceId === deviceId) {
      return { decisionId: id, message: decision.message }
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
  testType: 'str4' | 'week',
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

  // 分配辅测机（标记为占用中）
  if (precheck.auxDeviceIds && precheck.auxDeviceIds.length > 0) {
    session.auxiliaryDevices = precheck.auxDeviceIds
    for (const auxId of precheck.auxDeviceIds) {
      if (devices[auxId]) {
        devices[auxId].status = '占用中'
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

  // 自动复测：全自动失败项重试一次
  if (failedAutoCases.length > 0) {
    console.log(`[device-self-check] Retesting ${failedAutoCases.length} failed auto cases for ${moduleKey}`)
    for (const caseIndex of failedAutoCases) {
      const caseKey = `${moduleKey}/${caseIndex}`
      const result = await runCase(deviceId, testType, module, caseIndex, session)
      if (result.status === '通过') {
        session.moduleProgress[moduleKey].passedCases++
        session.moduleProgress[moduleKey].failedCases = Math.max(0, session.moduleProgress[moduleKey].failedCases - 1)
      }
      session.caseResults[caseKey] = result
      emitEvent('case_completed', { deviceId, caseKey, result })
    }
  }

  // 释放辅测机（回到待命状态）
  for (const auxId of session.auxiliaryDevices) {
    if (devices[auxId] && devices[auxId].status === '占用中') {
      devices[auxId].status = '待命'
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

// 启动测试
export async function startTest(
  deviceId: string,
  testType: 'str4' | 'week'
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

    // 更新设备状态
    device.status = '初始化中'
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
      auxiliaryDevices: []
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

// 异步执行测试流程
async function runTestFlow(
  deviceId: string,
  testType: 'str4' | 'week',
  session: TestSession
): Promise<void> {
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

  // 生成 xlsx 报告
  generateTestReport(deviceId, session).catch(e => {
    console.warn('[device-self-check] Failed to generate report:', e)
  })
}

// 生成测试报告
async function generateTestReport(deviceId: string, session: TestSession): Promise<void> {
  try {
    const device = devices[deviceId]
    if (!device) return

    const resultDir = join(tahpPaths.reportsDir, 'self-check', deviceId, session.startTime?.replace(/[:.]/g, '-') || '')
    mkdirSync(resultDir, { recursive: true })

    // 生成 CSV 报告（xlsx 替代方案）
    const rows: string[] = ['模块,用例编号,用例名称,结果,全自动化,备注']
    for (const [key, result] of Object.entries(session.caseResults)) {
      rows.push([
        result.module,
        result.caseIndex,
        result.caseName,
        result.status,
        result.fullAutomation ? '是' : '否',
        result.message
      ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
    }

    const reportPath = join(resultDir, 'test_report.csv')
    writeFileSync(reportPath, '\ufeff' + rows.join('\n'), 'utf-8')

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
    }
    writeFileSync(join(resultDir, 'summary.json'), JSON.stringify(summary, null, 2), 'utf-8')

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

// 结束测试（释放所有资源）
export function endTest(deviceId: string): DeviceDetail | null {
  const device = devices[deviceId]
  const session = testSessions[deviceId]
  if (!device) return null

  // 辅测机待命状态：直接回到空闲
  if (device.status === '待命' && device.role === '辅测机') {
    device.status = '空闲'
    device.testType = undefined
    device.testStartTime = undefined
    device.testDuration = 0
    emitEvent('device_updated', { device })
    emitEvent('test_ended', { deviceId })
    return { device }
  }

  // 释放辅测机
  if (session?.auxiliaryDevices) {
    for (const auxId of session.auxiliaryDevices) {
      if (devices[auxId] && devices[auxId].status === '占用中') {
        devices[auxId].status = '待命'
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
  return { device }
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

export function getTestSession(deviceId: string): TestSession | undefined {
  return testSessions[deviceId]
}

export function getModuleConditions(): Record<string, ModuleCondition> {
  return moduleConditions
}

// 初始化
export function initDeviceSelfCheck(): void {
  loadCaseConfigs()
}
