import { describe, expect, it } from 'vitest'
import {
  buildManualCaseConfirmMessage,
  collectOrderedCaseResults,
  formatCaseResultKey,
  prioritizeTddManualCases,
  shouldAwaitTddManualConfirm,
  type CaseResult,
  type TestSession,
  type TddPriorityCase,
} from '../../packages/server/src/services/tahp/device-self-check'

function item(
  testType: string,
  module: string,
  caseIndex: number,
  automationMode: TddPriorityCase['automationMode'] = 'full',
): TddPriorityCase {
  return { testType, module, caseIndex, automationMode }
}

function makeResult(
  testType: string,
  module: string,
  caseIndex: number,
  status: CaseResult['status'] = '通过',
): CaseResult {
  return {
    testType,
    module,
    caseIndex,
    caseName: `用例${caseIndex}`,
    status,
    message: status,
    fullAutomation: true,
    steps: [],
  }
}

function makeSession(partial: Partial<TestSession> & Pick<TestSession, 'testType' | 'caseResults'>): TestSession {
  return {
    deviceId: 'dev-1',
    modules: [],
    currentModuleIndex: 0,
    moduleProgress: {},
    startTime: '2026-08-13T10:00:00.000Z',
    isRunning: false,
    auxiliaryDevices: [],
    ...partial,
  }
}

describe('prioritizeTddManualCases', () => {
  it('moves str4/week tdd manuals ahead within tdd slots only', () => {
    const input = [
      item('week', 'driver', 1, 'full'),
      item('week', 'tdd', 1, 'full'),
      item('week', 'tdd', 15, 'manual'),
      item('week', 'tdd', 2, 'full'),
    ]
    const ordered = prioritizeTddManualCases(input)
    expect(ordered.map(c => `${c.module}/${c.caseIndex}`)).toEqual([
      'driver/1',
      'tdd/15',
      'tdd/1',
      'tdd/2',
    ])
  })

  it('keeps non-tdd positions when tdd cases are interleaved', () => {
    const input = [
      item('week', 'tdd', 1, 'full'),
      item('week', 'driver', 1, 'full'),
      item('week', 'tdd', 15, 'manual'),
    ]
    const ordered = prioritizeTddManualCases(input)
    expect(ordered.map(c => `${c.module}/${c.caseIndex}`)).toEqual([
      'tdd/15',
      'driver/1',
      'tdd/1',
    ])
  })

  it('preserves relative order of manuals and of remaining tdd cases', () => {
    const input = [
      item('str4', 'tdd', 13, 'manual'),
      item('str4', 'tdd', 1, 'full'),
      item('str4', 'tdd', 14, 'manual'),
      item('str4', 'tdd', 2, 'full'),
    ]
    const ordered = prioritizeTddManualCases(input)
    expect(ordered.map(c => c.caseIndex)).toEqual([13, 14, 1, 2])
  })

  it('does not reorder smoke or other modules labeled tdd-like', () => {
    const input = [
      item('smoke', 'usd', 1, 'manual'),
      item('week', 'driver', 1, 'full'),
    ]
    expect(prioritizeTddManualCases(input)).toEqual(input)
  })

  it('does not mutate the input array', () => {
    const input = [
      item('week', 'tdd', 1, 'full'),
      item('week', 'tdd', 15, 'manual'),
    ]
    const snapshot = input.map(c => ({ ...c }))
    prioritizeTddManualCases(input)
    expect(input).toEqual(snapshot)
  })
})

describe('collectOrderedCaseResults with tdd manual execution reorder', () => {
  it('keeps custom report order as selectedCases even if execution ran manuals first', () => {
    const selectedCases = ['week/driver/1', 'week/tdd/1', 'week/tdd/15']
    const session = makeSession({
      testType: 'custom',
      selectedCases,
      prioritizeTddManual: true,
      caseResults: {
        'week/tdd/15': makeResult('week', 'tdd', 15),
        'week/driver/1': makeResult('week', 'driver', 1),
        'week/tdd/1': makeResult('week', 'tdd', 1),
      },
    })

    const ordered = collectOrderedCaseResults(session)
    expect(ordered.map(r => formatCaseResultKey(r.testType, r.module, r.caseIndex)))
      .toEqual(selectedCases)
  })
})

describe('tdd manual confirm prompt', () => {
  it('awaits confirm only for prioritized str4/week tdd manuals', () => {
    expect(shouldAwaitTddManualConfirm(true, 'week', 'tdd', 'manual')).toBe(true)
    expect(shouldAwaitTddManualConfirm(true, 'str4', 'tdd', 'manual')).toBe(true)
    expect(shouldAwaitTddManualConfirm(false, 'week', 'tdd', 'manual')).toBe(false)
    expect(shouldAwaitTddManualConfirm(true, 'week', 'tdd', 'full')).toBe(false)
    expect(shouldAwaitTddManualConfirm(true, 'week', 'driver', 'manual')).toBe(false)
    expect(shouldAwaitTddManualConfirm(undefined, 'week', 'tdd', 'manual')).toBe(false)
  })

  it('builds confirm message with steps and expected result', () => {
    const message = buildManualCaseConfirmMessage({
      caseName: '骚扰拦截',
      preconditions: '插入有效SIM卡',
      manualSteps: '1. 打开拨号盘\n2. 拨打拦截号码',
      expectedResult: '来电被拦截',
    })
    expect(message).toContain('用例「骚扰拦截」需要人工测试')
    expect(message).toContain('前置条件：')
    expect(message).toContain('插入有效SIM卡')
    expect(message).toContain('测试步骤：')
    expect(message).toContain('打开拨号盘')
    expect(message).toContain('期望结果：')
    expect(message).toContain('来电被拦截')
    expect(message).toContain('请按步骤完成测试后确认结果')
  })
})
