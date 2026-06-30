import { describe, expect, it } from 'vitest'
import {
  collectOrderedCaseResults,
  formatCaseResultKey,
  type CaseResult,
  type TestSession,
} from '../../packages/server/src/services/tahp/device-self-check'

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
    startTime: '2026-06-25T10:00:00.000Z',
    isRunning: false,
    auxiliaryDevices: [],
    ...partial,
  }
}

describe('device self-check report collection', () => {
  it('collects custom results by selectedCases order', () => {
    const session = makeSession({
      testType: 'custom',
      selectedCases: ['week/tdd/2', 'str4/tdd/1'],
      caseResults: {
        'str4/tdd/1': makeResult('str4', 'tdd', 1),
        'week/tdd/2': makeResult('week', 'tdd', 2),
      },
    })

    const ordered = collectOrderedCaseResults(session)
    expect(ordered.map(r => formatCaseResultKey(r.testType, r.module, r.caseIndex)))
      .toEqual(['week/tdd/2', 'str4/tdd/1'])
  })

  it('falls back to caseResults when selectedCases cannot be resolved', () => {
    const session = makeSession({
      testType: 'custom',
      selectedCases: ['missing/key/1'],
      caseResults: {
        'str4/tdd/1': makeResult('str4', 'tdd', 1),
        'week/driver/3': makeResult('week', 'driver', 3, '失败'),
      },
    })

    const ordered = collectOrderedCaseResults(session)
    expect(ordered).toHaveLength(2)
    expect(ordered.some(r => r.status === '失败')).toBe(true)
  })

  it('collects standard test results from caseResults', () => {
    const session = makeSession({
      testType: 'str4',
      caseResults: {
        'str4/tdd/1': makeResult('str4', 'tdd', 1),
        'str4/driver_component/2': makeResult('str4', 'driver_component', 2),
      },
    })

    const ordered = collectOrderedCaseResults(session)
    expect(ordered).toHaveLength(2)
    expect(formatCaseResultKey(ordered[0].testType, ordered[0].module, ordered[0].caseIndex))
      .toBe('str4/driver_component/2')
  })
})
