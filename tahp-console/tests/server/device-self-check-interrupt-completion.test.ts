import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  __testingResetDevices,
  __testingScheduleTestReportIfNeeded,
  __testingUpsertDevice,
  getDevice,
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

function makeDevice(deviceId = 'ut-smoke-1'): DeviceInfo {
  return {
    deviceId,
    deviceName: 'UT Phone',
    role: '测试机',
    status: '测试中',
    testType: 'smoke',
    testStartTime: new Date().toISOString(),
    testDuration: 0,
    simCards: [],
    isMirroredResult: false,
  }
}

function makeFailedSmokeSession(deviceId: string): TestSession {
  const caseKey = 'smoke/usd/1'
  const caseResults: Record<string, CaseResult> = {
    [caseKey]: {
      testType: 'smoke',
      module: 'usd',
      caseIndex: 1,
      caseName: 'USD冒烟测试',
      status: '失败',
      message: '子项失败',
      fullAutomation: true,
      steps: [{ stepDesc: '失败', status: '失败', timestamp: new Date().toISOString() }],
      startTime: new Date().toISOString(),
      endTime: new Date().toISOString(),
    },
  }
  return {
    deviceId,
    testType: 'smoke',
    modules: ['usd'],
    currentModuleIndex: 0,
    moduleProgress: {
      'smoke/usd': {
        module: 'smoke/usd',
        totalCases: 1,
        completedCases: 1,
        passedCases: 0,
        failedCases: 1,
      },
    },
    caseResults,
    startTime: new Date().toISOString(),
    isRunning: true,
    auxiliaryDevices: [],
  }
}

describe('device self-check interrupted completion', () => {
  beforeEach(() => {
    __testingResetDevices()
  })

  afterEach(() => {
    __testingResetDevices()
  })

  it('scheduleTestReportIfNeeded marks completion and returns device to idle', async () => {
    const deviceId = 'ut-smoke-1'
    const session = makeFailedSmokeSession(deviceId)
    __testingUpsertDevice(makeDevice(deviceId), session)

    __testingScheduleTestReportIfNeeded(deviceId, session, { reportStatus: '完成(失败)' })

    expect(session.isRunning).toBe(false)
    expect(session.endTime).toBeTruthy()
    expect(getDevice(deviceId)?.status).toBe('完成(失败)')

    await vi.waitFor(() => {
      expect(getDevice(deviceId)?.status).toBe('空闲')
    }, { timeout: 15_000 })
  })

  it('does not duplicate report when endTime already set', async () => {
    const deviceId = 'ut-smoke-2'
    const session = makeFailedSmokeSession(deviceId)
    session.endTime = new Date().toISOString()
    __testingUpsertDevice(makeDevice(deviceId), session)

    __testingScheduleTestReportIfNeeded(deviceId, session, { reportStatus: '完成(失败)' })

    await vi.waitFor(() => {
      expect(getDevice(deviceId)?.status).toBe('空闲')
    }, { timeout: 5_000 })
  })
})
