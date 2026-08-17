import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  __testingResetDevices,
  __testingUpsertDevice,
  getTestSession,
  skipCurrentCase,
  type CaseResult,
  type DeviceInfo,
  type TestSession,
} from '../../packages/server/src/services/tahp/device-self-check'

vi.mock('../../packages/server/src/services/tahp/quality-run-upload', () => ({
  resolveSelfCheckProjectContext: vi.fn(async () => ({
    project_code: 'UT_PROJECT',
    source: 'unassigned',
  })),
  uploadSelfCheckReportToCentral: vi.fn(async () => undefined),
}))

function makeDevice(deviceId = 'ut-skip-1'): DeviceInfo {
  return {
    deviceId,
    deviceName: 'UT Phone',
    role: '测试机',
    status: '测试中',
    testType: 'week',
    testStartTime: new Date().toISOString(),
    testDuration: 0,
    simCards: [],
    isMirroredResult: false,
  }
}

function makeSession(deviceId: string, caseResults: Record<string, CaseResult>): TestSession {
  return {
    deviceId,
    testType: 'week',
    modules: ['driver'],
    currentModuleIndex: 0,
    moduleProgress: {
      'week/driver': {
        module: 'week/driver',
        totalCases: Object.keys(caseResults).length,
        completedCases: 0,
        passedCases: 0,
        failedCases: 0,
      },
    },
    caseResults,
    startTime: new Date().toISOString(),
    isRunning: true,
    auxiliaryDevices: [],
  }
}

function makeCase(partial: Partial<CaseResult> & Pick<CaseResult, 'caseIndex' | 'status'>): CaseResult {
  return {
    testType: 'week',
    module: 'driver',
    caseName: `用例${partial.caseIndex}`,
    message: '',
    fullAutomation: true,
    steps: [],
    startTime: new Date().toISOString(),
    ...partial,
  }
}

describe('skipCurrentCase', () => {
  beforeEach(() => {
    __testingResetDevices()
  })

  afterEach(() => {
    __testingResetDevices()
  })

  it('marks the in-progress case as skipped and keeps the session running', () => {
    const deviceId = 'ut-skip-1'
    const caseKey = 'week/driver/1'
    const session = makeSession(deviceId, {
      [caseKey]: makeCase({
        caseIndex: 1,
        status: '进行中',
        steps: [{ stepDesc: '正在执行', status: '进行中', timestamp: new Date().toISOString() }],
      }),
    })
    __testingUpsertDevice(makeDevice(deviceId), session)

    const detail = skipCurrentCase(deviceId)

    expect(detail.device.status).toBe('测试中')
    expect(detail.session?.isRunning).toBe(true)
    expect(getTestSession(deviceId)?.isRunning).toBe(true)
    expect(session.caseResults[caseKey]?.status).toBe('跳过')
    expect(session.caseResults[caseKey]?.message).toBe('用户跳过')
  })

  it('keeps already-passed cases and only skips the current one', () => {
    const deviceId = 'ut-skip-2'
    const session = makeSession(deviceId, {
      'week/driver/1': makeCase({
        caseIndex: 1,
        caseName: '已通过',
        status: '通过',
        message: 'ok',
        endTime: new Date().toISOString(),
      }),
      'week/driver/2': makeCase({
        caseIndex: 2,
        caseName: '进行中',
        status: '进行中',
        startTime: new Date().toISOString(),
      }),
    })
    __testingUpsertDevice(makeDevice(deviceId), session)

    skipCurrentCase(deviceId)

    expect(session.caseResults['week/driver/1']?.status).toBe('通过')
    expect(session.caseResults['week/driver/1']?.message).toBe('ok')
    expect(session.caseResults['week/driver/2']?.status).toBe('跳过')
    expect(session.caseResults['week/driver/2']?.message).toBe('用户跳过')
    expect(session.isRunning).toBe(true)
  })

  it('throws when there is no in-progress or pending case', () => {
    const deviceId = 'ut-skip-3'
    const session = makeSession(deviceId, {
      'week/driver/1': makeCase({
        caseIndex: 1,
        status: '通过',
        message: 'ok',
        endTime: new Date().toISOString(),
      }),
    })
    __testingUpsertDevice(makeDevice(deviceId), session)

    expect(() => skipCurrentCase(deviceId)).toThrow('当前没有可跳过的用例')
    expect(session.caseResults['week/driver/1']?.status).toBe('通过')
    expect(session.isRunning).toBe(true)
  })

  it('skips a pending manual-confirm case and keeps the session running', () => {
    const deviceId = 'ut-skip-4'
    const session = makeSession(deviceId, {
      'week/driver/1': makeCase({
        caseIndex: 1,
        status: '待确认',
        message: '需人工测试',
      }),
    })
    __testingUpsertDevice(makeDevice(deviceId), session)

    skipCurrentCase(deviceId)

    expect(session.caseResults['week/driver/1']?.status).toBe('跳过')
    expect(session.caseResults['week/driver/1']?.message).toBe('用户跳过')
    expect(session.isRunning).toBe(true)
  })

  it('throws when the device does not exist', () => {
    expect(() => skipCurrentCase('missing')).toThrow('设备不存在')
  })
})
