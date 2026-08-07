import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as deviceSelfCheck from '../../packages/server/src/services/tahp/device-self-check'
import * as casePlanner from '../../packages/server/src/services/tahp/selfcheck-case-planner'
import {
  advance,
  resetOrchestratorForTest,
  startRun,
} from '../../packages/server/src/services/tahp/adapt-pipeline/orchestrator'
import { registerStageForTest, resetRegistryForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/registry'
import {
  createRun,
  getRun,
  resetStoreForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import { resetSelfCheckSourceForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/sources/self-check'
import { resetSourcesForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/sources'
import { installSelfcheckStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/selfcheck'
import { setWorkflowOverrideForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import type { WorkflowDefinition } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

const SELFCHECK_FAIL_WF: WorkflowDefinition = {
  id: 'test-selfcheck-fail',
  version: 1,
  label: 'selfcheck-fail',
  maxIterations: 3,
  nodes: [
    { key: 'selfcheck', enabled: true, onDone: 'END', onFail: 'triage' },
    { key: 'triage', enabled: true, onDone: 'END', onFail: 'END', onUnavailable: 'skip' },
  ],
}

describe('adapt-pipeline selfcheck fail advance', () => {
  let tempDir = ''
  const deviceId = 'DUT-SELFCHECK-1'
  let eventHandlers: Record<string, Array<(data: Record<string, unknown>) => void>>

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-sc-fail-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    resetSourcesForTest()
    resetSelfCheckSourceForTest()
    setWorkflowOverrideForTest(null)
    eventHandlers = {}

    vi.spyOn(deviceSelfCheck, 'onEvent').mockImplementation((name, cb) => {
      if (!eventHandlers[name]) eventHandlers[name] = []
      eventHandlers[name].push(cb as (data: Record<string, unknown>) => void)
      return () => {
        eventHandlers[name] = (eventHandlers[name] ?? []).filter(x => x !== cb)
      }
    })
    vi.spyOn(casePlanner, 'planCases').mockResolvedValue({
      plan: { mode: 'fixed', selected_cases: ['smoke/usd/1'] },
      cases: [{ caseKey: 'smoke/usd/1', caseName: 'USD冒烟测试', score: 1 }],
      source: 'fixed',
      aiGeneratedCases: [],
    })
    vi.spyOn(deviceSelfCheck, 'startCustomTest').mockResolvedValue({
      device: {
        deviceId,
        deviceName: 'mock',
        role: '测试机',
        status: '测试中',
        simCards: [],
        testDuration: 0,
        isMirroredResult: false,
      },
      session: {
        deviceId,
        testType: 'custom',
        modules: ['usd'],
        currentModuleIndex: 0,
        moduleProgress: {},
        caseResults: {},
        isRunning: true,
        auxiliaryDevices: [],
        selectedCases: ['smoke/usd/1'],
      },
    } as never)

    installSelfcheckStage()
    registerStageForTest({
      key: 'triage',
      label: '故障分析',
      consumes: ['testresult'],
      produces: ['triage'],
      async start(ctx) {
        ctx.patchState({
          progress: {
            state: 'infra_skip',
            conclusion: 'test: triage entered after selfcheck fail',
          },
        })
      },
      evaluate(ctx) {
        const state = (ctx.state.progress as { state?: string } | undefined)?.state
        if (state === 'infra_skip') {
          return {
            status: 'waiting_human' as const,
            reason: 'infra_skip',
            message: 'test triage gate',
            actions: [{ id: 'confirm_done', label: '继续' }],
          }
        }
        return { status: 'running' as const }
      },
    })
    setWorkflowOverrideForTest(SELFCHECK_FAIL_WF)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    resetSourcesForTest()
    resetSelfCheckSourceForTest()
    setWorkflowOverrideForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('moves to triage after test_completed with failed cases (does not stick on selfcheck)', async () => {
    const run = createRun({
      project_code: 'KM9',
      device_id: deviceId,
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9',
        components: ['krn'],
        variant: 'userdebug',
      },
      test_plan: { mode: 'fixed', selected_cases: ['smoke/usd/1'] },
    })

    await startRun(run.run_id)

    let state = getRun(run.run_id)!
    expect(state.current_node).toBe('selfcheck')
    expect(state.stages.selfcheck?.status).toBe('running')
    expect(state.stages.selfcheck?.refs?.selfcheck_device_id).toBe(deviceId)

    const caseCbs = eventHandlers.case_completed ?? []
    const doneCbs = eventHandlers.test_completed ?? []
    expect(caseCbs.length).toBeGreaterThan(0)
    expect(doneCbs.length).toBeGreaterThan(0)

    for (const cb of caseCbs) {
      cb({
        deviceId,
        caseKey: 'smoke/usd/1',
        result: {
          testType: 'smoke',
          module: 'usd',
          caseIndex: 1,
          caseName: 'USD冒烟测试',
          status: '失败',
          message: 'mock fail',
          fullAutomation: true,
          steps: [],
        },
      })
    }
    for (const cb of doneCbs) {
      cb({
        deviceId,
        session: {
          deviceId,
          testType: 'custom',
          modules: ['usd'],
          currentModuleIndex: 0,
          moduleProgress: {},
          caseResults: {},
          isRunning: false,
          auxiliaryDevices: [],
        },
      })
    }

    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 15))
      state = getRun(run.run_id)!
      if (state.current_node === 'triage') break
      await advance(run.run_id)
    }

    state = getRun(run.run_id)!
    expect(state.stages.selfcheck?.status).toBe('failed')
    expect(state.stages.selfcheck?.progress?.state).toBe('case_failed')
    expect(state.current_node).toBe('triage')
    expect(state.status).toBe('waiting_human')
  })
})
