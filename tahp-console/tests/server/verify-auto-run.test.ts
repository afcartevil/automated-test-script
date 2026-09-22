import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const h = vi.hoisted(() => {
  const handlers: Record<string, Array<(data: any) => void>> = {}
  return {
    handlers,
    emit(name: string, payload: unknown) {
      for (const cb of handlers[name] || []) cb(payload)
    },
    refreshDevices: vi.fn(),
    startTest: vi.fn(),
    getDevice: vi.fn(),
    endTest: vi.fn(),
    continueTest: vi.fn(),
    isGmsSupportedOnHost: vi.fn(() => true),
    onEvent: vi.fn((name: string, cb: (data: any) => void) => {
      (handlers[name] ||= []).push(cb)
    }),
    resolveFlashDeviceIdentity: vi.fn(),
    resolveLatestDailyFlashPackage: vi.fn(),
    extractProjectCandidates: vi.fn((..._values: string[]) => [] as string[]),
    stopActiveFlash: vi.fn(),
    verifyMine: vi.fn(),
    labelVerifyTask: vi.fn(),
    completeVerifyTask: vi.fn(),
    readCentralUserSession: vi.fn(),
    readJiraUsername: vi.fn(),
    readJiraUserConfig: vi.fn(),
    bindJiraToCentral: vi.fn(),
    isLocal: vi.fn(() => true),
    isCentralConfigured: vi.fn(() => true),
  }
})

vi.mock('../../packages/server/src/services/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), debug: vi.fn(), error: vi.fn() },
}))

vi.mock('../../packages/server/src/services/tahp/paths', () => ({
  tahpPaths: { projectRoot: mkdtempSync(join(tmpdir(), 'verify-auto-paths-')) },
}))

vi.mock('../../packages/server/src/services/tahp/runtime-mode', () => ({
  isLocal: h.isLocal,
  isCentralConfigured: h.isCentralConfigured,
}))

vi.mock('../../packages/server/src/services/tahp/central-user-session', () => ({
  readCentralUserSession: h.readCentralUserSession,
}))

vi.mock('../../packages/server/src/services/tahp/jira-user-config', () => ({
  readJiraUsername: h.readJiraUsername,
  readJiraUserConfig: h.readJiraUserConfig,
}))

vi.mock('../../packages/server/src/services/tahp/sync/jira-bind', () => ({
  bindJiraToCentral: h.bindJiraToCentral,
}))

vi.mock('../../packages/server/src/services/tahp/sync/central-client', () => ({
  centralClient: {
    verifyMine: h.verifyMine,
    labelVerifyTask: h.labelVerifyTask,
    completeVerifyTask: h.completeVerifyTask,
  },
}))

vi.mock('../../packages/server/src/services/tahp/device-self-check', () => ({
  refreshDevices: h.refreshDevices,
  startTest: h.startTest,
  getDevice: h.getDevice,
  endTest: h.endTest,
  continueTest: h.continueTest,
  onEvent: h.onEvent,
  isGmsSupportedOnHost: h.isGmsSupportedOnHost,
}))

vi.mock('../../packages/server/src/services/tahp/device-flash', () => ({
  resolveFlashDeviceIdentity: h.resolveFlashDeviceIdentity,
  resolveLatestDailyFlashPackage: h.resolveLatestDailyFlashPackage,
  extractProjectCandidates: h.extractProjectCandidates,
  stopActiveFlash: h.stopActiveFlash,
}))

import {
  __testingResetVerifyAutoRun,
  __testingWriteVerifyAutoRunState,
  cancelVerifyAutoRunTask,
  getVerifyAutoRunStatus,
  isTestAccountName,
  loadVerifyAutoRunState,
  setVerifyAutoRunEnabled,
  tickVerifyAutoRun,
} from '../../packages/server/src/services/tahp/verify-auto-run'

const PKG_PATH = '\\\\10.150.98.24\\sw_ver_sh\\TECNO\\X6876\\pkg\\Open\\flash.zip'

function device(id: string, overrides: Record<string, unknown> = {}) {
  return {
    deviceId: id,
    deviceName: `TECNO ${id}`,
    role: '未分配',
    status: '空闲',
    simCards: [],
    testDuration: 0,
    isMirroredResult: false,
    ...overrides,
  }
}

function centralTask(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'vt_1',
    test_type: 'smoke',
    item_label: '冒烟测试',
    owner: 'test-qa01',
    project: 'X6876',
    status: 'pending',
    created_by: 'admin',
    created_at: '2026-09-17T00:00:00.000Z',
    ...overrides,
  }
}

function sessionFor(username: string) {
  h.readCentralUserSession.mockReturnValue({ username, role: 'business_owner', token: 'tok' })
}

let workDir = ''

/** 事件回调里的 tick 是 fire-and-forget，等它落地后再断言 */
async function settle(ms = 30) {
  await new Promise(resolve => setTimeout(resolve, ms))
}

beforeEach(() => {
  vi.clearAllMocks()
  for (const key of Object.keys(h.handlers)) delete h.handlers[key]
  h.onEvent.mockImplementation((name: string, cb: (data: any) => void) => {
    (h.handlers[name] ||= []).push(cb)
  })
  workDir = mkdtempSync(join(tmpdir(), 'verify-auto-run-'))
  process.env.TAHP_VERIFY_AUTO_RUN_DIR = workDir
  delete process.env.TAHP_VERIFY_AUTO_RUN_DISABLED
  delete process.env.TAHP_VERIFY_AUTO_RUN_WAIT_MS
  h.isLocal.mockReturnValue(true)
  h.isCentralConfigured.mockReturnValue(true)
  h.readJiraUsername.mockReturnValue('test-qa01')
  h.readJiraUserConfig.mockReturnValue({ username: 'test-qa01', password: '12345678' })
  h.resolveFlashDeviceIdentity.mockImplementation(async (id: string) => ({
    deviceId: id,
    brand: 'TECNO',
    project: id === 'SER_MATCH' ? 'X6876' : 'KM8',
    devRoot: '',
    devProjectPath: '',
  }))
  h.resolveLatestDailyFlashPackage.mockResolvedValue({ deviceId: 'SER_MATCH', packagePath: PKG_PATH })
  h.startTest.mockResolvedValue({ device: device('SER_MATCH', { status: '刷机中' }), session: {} })
  h.isGmsSupportedOnHost.mockReturnValue(true)
  h.labelVerifyTask.mockResolvedValue({})
  h.completeVerifyTask.mockResolvedValue({})
  __testingResetVerifyAutoRun()
})

describe('isTestAccountName', () => {
  it('matches only the test- prefix, case-insensitively', () => {
    expect(isTestAccountName('test-qa01')).toBe(true)
    expect(isTestAccountName('  TEST-qa01 ')).toBe(true)
    expect(isTestAccountName('qa.test-01')).toBe(false)
    expect(isTestAccountName('')).toBe(false)
  })
})

describe('tickVerifyAutoRun 资格门禁', () => {
  it('does nothing for a normal (non test-) account', async () => {
    sessionFor('alice')
    const result = await tickVerifyAutoRun()
    expect(result).toEqual({ eligible: false, reason: 'not_test_account' })
    expect(h.refreshDevices).not.toHaveBeenCalled()
    expect(h.verifyMine).not.toHaveBeenCalled()
  })

  it('does nothing when the central is not configured', async () => {
    sessionFor('test-qa01')
    h.isCentralConfigured.mockReturnValue(false)
    const result = await tickVerifyAutoRun()
    expect(result.reason).toBe('central_not_configured')
  })

  it('does nothing when disabled by env', async () => {
    sessionFor('test-qa01')
    process.env.TAHP_VERIFY_AUTO_RUN_DISABLED = '1'
    const result = await tickVerifyAutoRun()
    expect(result.reason).toBe('disabled_by_env')
  })

  it('does nothing while paused from the UI', async () => {
    sessionFor('test-qa01')
    setVerifyAutoRunEnabled(false)
    const result = await tickVerifyAutoRun()
    expect(result.reason).toBe('paused')
    expect(getVerifyAutoRunStatus().enabled).toBe(false)
  })
})

describe('等待设备', () => {
  it('labels 等待设备 when no idle device matches the task project', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_OTHER'), device('SER_BUSY', { status: '测试中' })])

    await tickVerifyAutoRun()

    expect(h.labelVerifyTask).toHaveBeenCalledWith('tok', 'vt_1', {
      label_code: 'waiting_device',
      label: '等待设备',
    })
    expect(h.startTest).not.toHaveBeenCalled()
    const state = loadVerifyAutoRunState()
    expect(state.tasks[0].phase).toBe('waiting_device')
    expect(state.tasks[0].last_error).toContain('X6876')
  })

  it('falls back to device-name candidates when the version share is unreachable', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.resolveFlashDeviceIdentity.mockRejectedValue(new Error('无法访问共享目录'))
    h.extractProjectCandidates.mockReturnValue(['X6876'])
    h.refreshDevices.mockResolvedValue([device('SER_NAME')])

    await tickVerifyAutoRun()

    expect(h.startTest).toHaveBeenCalled()
    expect(h.startTest.mock.calls[0][0]).toBe('SER_NAME')
  })

  it('marks 等待设备超时 after the wait limit', async () => {
    sessionFor('test-qa01')
    process.env.TAHP_VERIFY_AUTO_RUN_WAIT_MS = '1'
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([])

    await tickVerifyAutoRun()
    const state = loadVerifyAutoRunState()
    state.tasks[0].waiting_since = new Date(Date.now() - 10_000).toISOString()
    __testingWriteVerifyAutoRunState(state)

    await tickVerifyAutoRun()

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('wait_timeout')
    expect(h.labelVerifyTask).toHaveBeenCalledWith('tok', 'vt_1', {
      label_code: 'wait_timeout',
      label: '等待设备超时',
    })
  })
})

describe('自动启动（刷机 + 刷 Root）', () => {
  it('flashes the latest daily with the root package and starts the test item', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])

    const result = await tickVerifyAutoRun()

    expect(h.resolveLatestDailyFlashPackage).toHaveBeenCalledWith({ deviceId: 'SER_MATCH' })
    expect(h.startTest).toHaveBeenCalledWith(
      'SER_MATCH',
      'smoke',
      { enabled: true, pkgPath: PKG_PATH, enableRootPkg: true, stageVersion: 'Open' },
      {},
    )
    expect(result.active_task_id).toBe('vt_1')
    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('running')
    expect(task.label).toBe('验测执行中')
    expect(task.device_id).toBe('SER_MATCH')
  })

  it('keeps waiting when the device was claimed by someone else', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])
    h.startTest.mockResolvedValue(null)

    await tickVerifyAutoRun()

    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('waiting_device')
    expect(task.attempts).toBe(1)
    expect(task.last_error).toContain('已非空闲')
  })

  it('does not auto-start an unsupported test item', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'not_a_test' })])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])

    await tickVerifyAutoRun()

    expect(h.startTest).not.toHaveBeenCalled()
    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('unsupported')
  })

  it('gives up with 刷机失败 after repeated package resolution failures and closes the task', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])
    h.resolveLatestDailyFlashPackage.mockRejectedValue(new Error('未在刷机包路径下找到 user_root 小包'))

    await tickVerifyAutoRun()
    await tickVerifyAutoRun()
    await tickVerifyAutoRun()

    expect(h.startTest).not.toHaveBeenCalled()
    expect(h.completeVerifyTask).toHaveBeenCalledWith('tok', 'vt_1', {
      run_id: undefined,
      label_code: 'flash_failed',
      label: '刷机失败',
    })
    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('flash_failed')
  })
})

describe('人工执行测试项（str4 / week 不自动执行）', () => {
  it('str4 任务仅打本机「待人工执行」标签，不认领设备、不写回中心', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'str4', item_label: '转测摸底测试' })])

    await tickVerifyAutoRun()

    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('manual_only')
    expect(task.label).toBe('待人工执行')
    expect(h.refreshDevices).not.toHaveBeenCalled()
    expect(h.startTest).not.toHaveBeenCalled()
    // 中心白名单无 manual_only 码：标签仅本机展示，不写回
    expect(h.labelVerifyTask).not.toHaveBeenCalled()
  })

  it('week 任务同样不自动执行', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'week', item_label: '周版本测试' })])

    await tickVerifyAutoRun()

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('manual_only')
    expect(h.refreshDevices).not.toHaveBeenCalled()
  })

  it('策略调整前已在等待设备的 str4 任务转为待人工执行', async () => {
    sessionFor('test-qa01')
    __testingWriteVerifyAutoRunState({
      schema_version: 1,
      enabled: true,
      updated_at: new Date().toISOString(),
      tasks: [{
        task_id: 'vt_1',
        test_type: 'str4',
        item_label: '转测摸底测试',
        project: 'X6876',
        created_at: '2026-09-17T00:00:00.000Z',
        phase: 'waiting_device',
        label_code: 'waiting_device',
        label: '等待设备',
        waiting_since: new Date().toISOString(),
        attempts: 0,
        close_attempts: 0,
        updated_at: new Date().toISOString(),
      }],
    })
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'str4', item_label: '转测摸底测试' })])

    await tickVerifyAutoRun()

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('manual_only')
    expect(h.refreshDevices).not.toHaveBeenCalled()
  })

  it('中心完成后 manual_only 任务按 gone 清理', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'str4', item_label: '转测摸底测试' })])
    await tickVerifyAutoRun()
    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('manual_only')

    // 人工在中心完成：下一轮 verify/mine?view=open 不再返回该任务
    h.verifyMine.mockResolvedValue([])
    await tickVerifyAutoRun()

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('gone')
  })
})

describe('GMS 自动执行（不刷机 / 不刷 Root 包）', () => {
  it('uses the device current build: no package resolution, startTest with flash disabled', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'gms', item_label: 'GMS测试' })])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])

    const result = await tickVerifyAutoRun()

    expect(h.resolveLatestDailyFlashPackage).not.toHaveBeenCalled()
    expect(h.startTest).toHaveBeenCalledWith('SER_MATCH', 'gms', { enabled: false }, {})
    expect(result.active_task_id).toBe('vt_1')
    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('running')
    expect(task.device_id).toBe('SER_MATCH')
  })

  it('marks GMS unsupported on Windows hosts without starting the test', async () => {
    h.isGmsSupportedOnHost.mockReturnValue(false)
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask({ test_type: 'gms', item_label: 'GMS测试' })])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])

    await tickVerifyAutoRun()

    expect(h.startTest).not.toHaveBeenCalled()
    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('unsupported')
    expect(task.last_error).toContain('Windows 环境不支持 GMS')
  })
})

describe('执行期标签与关单', () => {
  async function startRunning() {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])
    await tickVerifyAutoRun()
    h.labelVerifyTask.mockClear()
    h.completeVerifyTask.mockClear()
  }

  it('labels 等待人工确认 on manual_confirm without answering it', async () => {
    await startRunning()
    h.emit('manual_confirm', { deviceId: 'SER_MATCH', message: '请确认音频效果' })

    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('waiting_human')
    expect(task.label).toBe('等待人工确认')
    expect(task.last_error).toContain('请确认音频效果')
  })

  it('labels 刷机失败 when flashing fails', async () => {
    await startRunning()
    h.emit('flash_completed', { deviceId: 'SER_MATCH', success: false, error: 'device_update 退出码 1' })

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('flash_failed')
  })

  it('closes the task with the report run_id and a pass label', async () => {
    await startRunning()
    const reportDir = join(workDir, 'report-1')
    mkdirSync(reportDir, { recursive: true })
    writeFileSync(join(reportDir, 'summary.json'), JSON.stringify({ status: '完成(通过)', failedCases: 0 }))

    h.emit('report_ready', { deviceId: 'SER_MATCH', resultDir: reportDir })
    await settle()
    await tickVerifyAutoRun()

    const call = h.completeVerifyTask.mock.calls.at(-1)
    expect(call?.[0]).toBe('tok')
    expect(call?.[1]).toBe('vt_1')
    expect(call?.[2].label_code).toBe('completed_pass')
    expect(call?.[2].run_id).toMatch(/^sc-SER_MATCH-report-1$/)
    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('completed_pass')
  })

  it('closes a failed report with the fail label', async () => {
    await startRunning()
    const reportDir = join(workDir, 'report-2')
    mkdirSync(reportDir, { recursive: true })
    writeFileSync(join(reportDir, 'summary.json'), JSON.stringify({ status: '完成(失败)', failedCases: 3 }))

    h.emit('report_ready', { deviceId: 'SER_MATCH', resultDir: reportDir })
    await settle()
    await tickVerifyAutoRun()

    expect(h.completeVerifyTask.mock.calls.at(-1)?.[2].label_code).toBe('completed_fail')
  })

  it('retries closing while the report is not yet ingested centrally', async () => {
    await startRunning()
    const reportDir = join(workDir, 'report-3')
    mkdirSync(reportDir, { recursive: true })
    writeFileSync(join(reportDir, 'summary.json'), JSON.stringify({ status: '完成(通过)', failedCases: 0 }))
    h.completeVerifyTask.mockRejectedValue(new Error('关联的验测报告不存在'))

    h.emit('report_ready', { deviceId: 'SER_MATCH', resultDir: reportDir })
    await settle()
    await tickVerifyAutoRun()

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('completing')
    // 事件触发的 tick 与显式 tick 都会重试关单
    expect(loadVerifyAutoRunState().tasks[0].close_attempts).toBeGreaterThanOrEqual(1)
  })

  it('returns to 等待设备 when the device state disappears (BFF restart)', async () => {
    await startRunning()
    h.getDevice.mockReturnValue(undefined)
    h.refreshDevices.mockResolvedValue([])

    await tickVerifyAutoRun()

    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('waiting_device')
    expect(getVerifyAutoRunStatus().active_task_id).toBeUndefined()
  })
})

describe('降级与人工干预', () => {
  it('keeps running locally when the central label endpoint is missing (old BFF)', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([])
    h.labelVerifyTask.mockRejectedValue(new Error('中心返回 404'))

    await tickVerifyAutoRun()

    const task = loadVerifyAutoRunState().tasks[0]
    expect(task.phase).toBe('waiting_device')
    expect(task.label_synced_at).toBeUndefined()
    expect(task.label_error).toContain('标签写回失败')
    expect(task.last_error).toContain('无空闲设备')

    // 老中心无 label 接口：不再每轮重试
    const callsAfterFirst = h.labelVerifyTask.mock.calls.length
    await tickVerifyAutoRun()
    expect(h.labelVerifyTask.mock.calls.length).toBe(callsAfterFirst)
  })

  it('cancelling a running task ends the test and labels 已取消', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])
    h.getDevice.mockReturnValue(device('SER_MATCH', { status: '测试中' }))
    await tickVerifyAutoRun()

    const result = await cancelVerifyAutoRunTask('vt_1')

    expect(result.cancelled).toBe(true)
    expect(h.endTest).toHaveBeenCalledWith('SER_MATCH')
    expect(loadVerifyAutoRunState().tasks[0].phase).toBe('cancelled')
    expect(h.labelVerifyTask).toHaveBeenCalledWith('tok', 'vt_1', {
      label_code: 'cancelled',
      label: '已取消',
    })
  })

  it('kills an in-flight flash when cancelling during 刷机中', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([device('SER_MATCH')])
    h.getDevice.mockReturnValue(device('SER_MATCH', { status: '刷机中' }))
    await tickVerifyAutoRun()

    await cancelVerifyAutoRunTask('vt_1')

    expect(h.stopActiveFlash).toHaveBeenCalled()
    expect(h.endTest).toHaveBeenCalledWith('SER_MATCH')
  })

  it('pausing labels in-flight tasks and stops claiming devices', async () => {
    sessionFor('test-qa01')
    h.verifyMine.mockResolvedValue([centralTask()])
    h.refreshDevices.mockResolvedValue([])
    await tickVerifyAutoRun()

    setVerifyAutoRunEnabled(false)

    expect(loadVerifyAutoRunState().tasks[0].label).toBe('已暂停')
    h.refreshDevices.mockClear()
    await tickVerifyAutoRun()
    expect(h.refreshDevices).not.toHaveBeenCalled()
  })
})
