import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  __testingResetDevices,
  __testingUpsertDevice,
  endTest,
  getTestSession,
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

function makeDevice(deviceId = 'ut-end-1'): DeviceInfo {
  return {
    deviceId,
    deviceName: 'UT Phone',
    role: '测试机',
    status: '测试中',
    testType: 'ai_generated',
    testStartTime: new Date().toISOString(),
    testDuration: 0,
    simCards: [],
    isMirroredResult: false,
  }
}

function makeSession(deviceId: string, caseResults: Record<string, CaseResult>): TestSession {
  return {
    deviceId,
    testType: 'ai_generated',
    modules: ['generated'],
    currentModuleIndex: 0,
    moduleProgress: {
      'ai_generated/generated': {
        module: 'ai_generated/generated',
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

describe('endTest abort semantics', () => {
  beforeEach(() => {
    __testingResetDevices()
  })

  afterEach(() => {
    __testingResetDevices()
  })

  it('marks in-progress cases as failed and returns to idle without waiting report', async () => {
    const deviceId = 'ut-end-1'
    const caseKey = 'ai_generated/generated/1'
    const session = makeSession(deviceId, {
      [caseKey]: {
        testType: 'ai_generated',
        module: 'generated',
        caseIndex: 1,
        caseName: '拨号',
        status: '进行中',
        message: '',
        fullAutomation: true,
        steps: [{ stepDesc: '正在执行', status: '进行中', timestamp: new Date().toISOString() }],
        startTime: new Date().toISOString(),
      },
    })
    __testingUpsertDevice(makeDevice(deviceId), session)

    const started = Date.now()
    const detail = await endTest(deviceId)
    const elapsed = Date.now() - started

    expect(detail?.device.status).toBe('空闲')
    expect(getTestSession(deviceId)).toBeUndefined()
    expect(elapsed).toBeLessThan(3_000)

    // session 对象仍持有失败结果（报告异步读同一引用）
    expect(session.caseResults[caseKey]?.status).toBe('失败')
    expect(session.caseResults[caseKey]?.message).toBe('用户结束测试')
    expect(session.moduleProgress['ai_generated/generated']?.failedCases).toBe(1)
  })

  it('keeps already-passed cases and only fails unfinished ones', async () => {
    const deviceId = 'ut-end-2'
    const session = makeSession(deviceId, {
      'ai_generated/generated/1': {
        testType: 'ai_generated',
        module: 'generated',
        caseIndex: 1,
        caseName: '已通过',
        status: '通过',
        message: 'ok',
        fullAutomation: true,
        steps: [],
        endTime: new Date().toISOString(),
      },
      'ai_generated/generated/2': {
        testType: 'ai_generated',
        module: 'generated',
        caseIndex: 2,
        caseName: '进行中',
        status: '进行中',
        message: '',
        fullAutomation: true,
        steps: [],
        startTime: new Date().toISOString(),
      },
    })
    __testingUpsertDevice(makeDevice(deviceId), session)

    await endTest(deviceId)

    expect(session.caseResults['ai_generated/generated/1']?.status).toBe('通过')
    expect(session.caseResults['ai_generated/generated/2']?.status).toBe('失败')
    expect(session.caseResults['ai_generated/generated/2']?.message).toBe('用户结束测试')
  })
})
