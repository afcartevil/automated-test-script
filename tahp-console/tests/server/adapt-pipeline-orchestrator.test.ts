import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as deviceSelfCheck from '../../packages/server/src/services/tahp/device-self-check'
import {
  advance,
  computeResumePoints,
  refreshArtifacts,
  resetOrchestratorForTest,
  resumeFrom,
  setSourceChangedCheckerForTest,
  startRun,
  submitHumanAction,
} from '../../packages/server/src/services/tahp/adapt-pipeline/orchestrator'
import { registerStage, resetRegistryForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/registry'
import {
  createRun,
  getRun,
  resetStoreForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import {
  resetSelfCheckSourceForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/sources/self-check'
import {
  resetSourcesForTest,
  setPipelineEventHandler,
  startSources,
} from '../../packages/server/src/services/tahp/adapt-pipeline/sources'
import {
  setWorkflowOverrideForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import type {
  ArtifactKind,
  StageDefinition,
  WorkflowDefinition,
  WorkflowNode,
} from '../../packages/server/src/services/tahp/adapt-pipeline/types'

const MINIMAL_WF: WorkflowDefinition = {
  id: 'test-minimal',
  version: 1,
  label: 'minimal',
  maxIterations: 2,
  nodes: [
    { key: 'step_a', enabled: true },
    { key: 'step_b', enabled: true, onDone: 'END' },
  ],
}

const LOOP_WF: WorkflowDefinition = {
  id: 'test-loop',
  version: 1,
  label: 'loop',
  maxIterations: 2,
  nodes: [
    { key: 'step_a', enabled: true },
    {
      key: 'human_review',
      enabled: true,
      onDone: 'step_a',
      onDoneEffect: 'increment_iteration',
    },
  ],
}

const ARTIFACT_WF: WorkflowDefinition = {
  id: 'test-artifacts',
  version: 1,
  label: 'artifacts',
  maxIterations: 3,
  nodes: [
    { key: 'adapt', enabled: true },
    { key: 'build', enabled: true },
    { key: 'flash', enabled: true },
    { key: 'selfcheck', enabled: true, onDone: 'END' },
  ],
}

function baseRunInput() {
  return {
    project_code: 'KM9',
    build_context: {
      mapped_root: 'Z:\\',
      workspace: 'project/KM9_NEW',
      components: ['krn'],
      variant: 'userdebug',
    },
  }
}

function registerMinimalStages(): void {
  registerStage({
    key: 'step_a',
    label: 'Step A',
    async start() {},
    evaluate() {
      return { status: 'done' as const }
    },
  })
  registerStage({
    key: 'step_b',
    label: 'Step B',
    async start() {},
    evaluate() {
      return {
        status: 'waiting_human' as const,
        reason: 'test',
        message: 'need human',
        actions: [{ id: 'confirm_done', label: '继续' }],
      }
    },
  })
}

function registerLoopStages(): void {
  registerStage({
    key: 'step_a',
    label: 'Step A',
    async start() {},
    evaluate() {
      return { status: 'done' as const }
    },
  })
  registerStage({
    key: 'human_review',
    label: '人工审核',
    isHumanGate: true,
    produces: ['source'],
    async start() {},
    evaluate() {
      return {
        status: 'waiting_human' as const,
        reason: 'awaiting_review',
        message: '审核',
        actions: [{ id: 'confirm_done', label: '继续' }],
      }
    },
  })
}

function registerArtifactStages(): void {
  const defs: Array<{
    key: string
    consumes?: ArtifactKind[]
    produces?: ArtifactKind[]
  }> = [
    { key: 'adapt', produces: ['source'] },
    { key: 'build', consumes: ['source'], produces: ['build'] },
    { key: 'flash', consumes: ['build'], produces: ['flashed'] },
    { key: 'selfcheck', consumes: ['flashed'], produces: ['testresult'] },
  ]
  for (const d of defs) {
    registerStage({
      key: d.key,
      label: d.key,
      consumes: d.consumes,
      produces: d.produces,
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })
  }
}

function registerUnavailableStage(): void {
  registerStage({
    key: 'step_a',
    label: 'Unavailable',
    async probe() {
      return { available: false, reason: '能力尚未接入' }
    },
    async start() {},
    evaluate() {
      return { status: 'running' as const }
    },
  })
  registerStage({
    key: 'step_b',
    label: 'Step B',
    async start() {},
    evaluate() {
      return { status: 'done' as const }
    },
  })
}

describe('adapt-pipeline orchestrator', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-orch-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    resetSourcesForTest()
    resetSelfCheckSourceForTest()
    setSourceChangedCheckerForTest(null)
    setWorkflowOverrideForTest(null)
  })

  afterEach(() => {
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    resetSourcesForTest()
    resetSelfCheckSourceForTest()
    setWorkflowOverrideForTest(null)
    setSourceChangedCheckerForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('runs enter → advance → transition with immediate done + waiting_human', async () => {
    registerMinimalStages()
    setWorkflowOverrideForTest(MINIMAL_WF)

    const run = createRun(baseRunInput())
    await startRun(run.run_id)

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.current_node).toBe('step_b')
    expect(updated.stages.step_a?.status).toBe('done')
    expect(updated.stages.step_b?.status).toBe('waiting_human')
  })

  it('manual_gate stops with correct actions when probe unavailable', async () => {
    registerUnavailableStage()
    setWorkflowOverrideForTest({
      ...MINIMAL_WF,
      nodes: [
        { key: 'step_a', enabled: true, onUnavailable: 'manual_gate' },
        { key: 'step_b', enabled: true, onDone: 'END' },
      ],
    })

    const run = createRun(baseRunInput())
    await startRun(run.run_id)

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.stages.step_a?.human?.reason).toBe('capability_unavailable')
    expect(updated.stages.step_a?.human?.actions?.map(a => a.id)).toEqual(['confirm_done', 'skip'])
  })

  it('confirm_done advances to next node', async () => {
    registerMinimalStages()
    setWorkflowOverrideForTest(MINIMAL_WF)

    const run = createRun(baseRunInput())
    await startRun(run.run_id)
    await submitHumanAction(run.run_id, 'step_b', 'confirm_done')

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('passed')
    expect(updated.stages.step_b?.status).toBe('done')
  })

  it('increments iteration on loop only when source changed', async () => {
    registerLoopStages()
    setWorkflowOverrideForTest(LOOP_WF)

    const run = createRun(baseRunInput())
    await startRun(run.run_id)
    await submitHumanAction(run.run_id, 'human_review', 'confirm_done')

    let updated = getRun(run.run_id)!
    expect(updated.iteration).toBe(1)
    expect(updated.status).toBe('waiting_human')

    setSourceChangedCheckerForTest(() => true)
    await submitHumanAction(run.run_id, 'human_review', 'confirm_done')
    updated = getRun(run.run_id)!
    expect(updated.iteration).toBe(2)
  })

  it('stops at max_iterations with extend action', async () => {
    registerLoopStages()
    setWorkflowOverrideForTest(LOOP_WF)
    setSourceChangedCheckerForTest(() => true)

    const run = createRun({ ...baseRunInput(), max_iterations: 1 })
    await startRun(run.run_id)
    await submitHumanAction(run.run_id, 'human_review', 'confirm_done')

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.stages.human_review?.human?.reason).toBe('max_iterations_exceeded')
    expect(updated.stages.human_review?.human?.actions?.map(a => a.id)).toContain('extend')
  })

  it('serializes concurrent advance calls', async () => {
    let evalCount = 0
    registerStage({
      key: 'step_a',
      label: 'slow',
      async start() {},
      evaluate() {
        evalCount++
        return { status: 'running' as const, progress: { percent: evalCount } }
      },
    })
    registerStage({
      key: 'step_b',
      label: 'b',
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })
    setWorkflowOverrideForTest(MINIMAL_WF)

    const run = createRun(baseRunInput())
    await startRun(run.run_id)

    const promises = Array.from({ length: 10 }, () => advance(run.run_id))
    await Promise.all(promises)

    const updated = getRun(run.run_id)!
    expect(updated.stages.step_a?.progress).toBeDefined()
    expect(evalCount).toBeGreaterThan(0)
  })

  it('startSources is idempotent for self-check events', () => {
    const handler = vi.fn()
    const onEventSpy = vi.spyOn(deviceSelfCheck, 'onEvent')
    setPipelineEventHandler(handler)
    startSources()
    startSources()

    const flashLogCalls = onEventSpy.mock.calls.filter(([name]) => name === 'flash_log')
    expect(flashLogCalls.length).toBe(1)

    const flashCb = flashLogCalls[0][1] as (data: Record<string, unknown>) => void
    flashCb({ deviceId: 'dev-1', line: 'ok' })
    expect(handler).toHaveBeenCalledTimes(1)
    onEventSpy.mockRestore()
  })

  it('marks downstream artifacts stale after produce refresh', () => {
    registerArtifactStages()
    setWorkflowOverrideForTest(ARTIFACT_WF)

    const run = createRun(baseRunInput())
    const wfNode = (key: string): WorkflowNode => ({ key, enabled: true })

    run.artifacts = {
      flashed: {
        kind: 'flashed',
        produced_by: 'flash',
        produced_at: '2020-01-01T00:00:00.000Z',
        stale: false,
      },
      testresult: {
        kind: 'testresult',
        produced_by: 'selfcheck',
        produced_at: '2020-01-01T00:00:00.000Z',
        stale: false,
      },
    }

    refreshArtifacts(run, wfNode('build'), ['build'])

    expect(run.artifacts.build?.stale).toBe(false)
    expect(run.artifacts.flashed?.stale).toBe(true)
    expect(run.artifacts.testresult?.stale).toBe(true)
  })

  it('computeResumePoints: flash safe when build fresh; unsafe after source stale', async () => {
    registerArtifactStages()
    setWorkflowOverrideForTest(ARTIFACT_WF)

    const run = createRun(baseRunInput())
    run.artifacts = {
      source: {
        kind: 'source',
        produced_by: 'adapt',
        produced_at: new Date().toISOString(),
        stale: false,
      },
      build: {
        kind: 'build',
        produced_by: 'build',
        produced_at: new Date().toISOString(),
        stale: false,
      },
      flashed: {
        kind: 'flashed',
        produced_by: 'flash',
        produced_at: new Date().toISOString(),
        stale: false,
      },
      testresult: {
        kind: 'testresult',
        produced_by: 'selfcheck',
        produced_at: new Date().toISOString(),
        stale: false,
      },
    }

    let { points, recommended } = computeResumePoints(run)
    const flashPoint = points.find(p => p.node === 'flash')
    expect(flashPoint?.safety).toBe('safe')
    expect(recommended).toBeNull()

    run.artifacts.source = {
      kind: 'source',
      produced_by: 'human_review',
      produced_at: new Date().toISOString(),
      stale: false,
    }
    run.artifacts.build = { ...run.artifacts.build!, stale: true, stale_reason: 'source 已更新' }
    run.artifacts.flashed = { ...run.artifacts.flashed!, stale: true, stale_reason: 'build 已更新' }
    run.artifacts.testresult = { ...run.artifacts.testresult!, stale: true, stale_reason: 'flashed 已更新' }

    ;({ points, recommended } = computeResumePoints(run))
    const flashAfter = points.find(p => p.node === 'flash')
    const selfcheckAfter = points.find(p => p.node === 'selfcheck')
    expect(flashAfter?.safety).toBe('unsafe')
    expect(flashAfter?.missing?.some(m => m.kind === 'build')).toBe(true)
    expect(selfcheckAfter?.safety).toBe('unsafe')
    expect(recommended).toBe('build')
  })

  it('resumeFrom rejects unsafe without force and allows with force', async () => {
    registerArtifactStages()
    setWorkflowOverrideForTest(ARTIFACT_WF)

    const run = createRun(baseRunInput())
    run.status = 'waiting_human'
    run.current_node = 'selfcheck'
    run.artifacts = {
      source: {
        kind: 'source',
        produced_by: 'adapt',
        produced_at: new Date().toISOString(),
        stale: true,
        stale_reason: 'changed',
      },
    }

    await expect(resumeFrom(run.run_id, { node: 'selfcheck' })).rejects.toThrow(/不安全/)

    await resumeFrom(run.run_id, { node: 'selfcheck', force: true })
    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('passed')
    expect(updated.stages.selfcheck?.status).toBe('done')
  })

  it('resume without source change does not increment iteration', async () => {
    registerArtifactStages()
    setWorkflowOverrideForTest({
      ...ARTIFACT_WF,
      nodes: [
        ...ARTIFACT_WF.nodes.slice(0, 3),
        { key: 'human_review', enabled: true, isHumanGate: true, onDone: 'flash' } as WorkflowNode,
      ],
    })
    registerStage({
      key: 'human_review',
      label: '人工审核',
      isHumanGate: true,
      produces: ['source'],
      async start() {},
      evaluate() {
        return {
          status: 'waiting_human' as const,
          reason: 'review',
          message: 'review',
          actions: [{ id: 'confirm_done', label: '继续' }],
        }
      },
    })

    const run = createRun(baseRunInput())
    run.status = 'waiting_human'
    run.current_node = 'human_review'
    run.iteration = 1
    run.artifacts = {
      build: {
        kind: 'build',
        produced_by: 'build',
        produced_at: new Date().toISOString(),
        stale: false,
      },
    }

    await resumeFrom(run.run_id, { node: 'flash' })
    expect(getRun(run.run_id)?.iteration).toBe(1)
  })
})
