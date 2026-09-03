import { existsSync, mkdtempSync, readFileSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  appendStages,
  computeAppendCandidates,
  resetOrchestratorForTest,
  startRun,
} from '../../packages/server/src/services/tahp/adapt-pipeline/orchestrator'
import { registerStage, resetRegistryForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/registry'
import {
  createRun,
  getRun,
  resetStoreForTest,
  saveRun,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import { buildTimelineView } from '../../packages/server/src/services/tahp/adapt-pipeline/timeline'
import {
  resetSourcesForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/sources'
import {
  resetSelfCheckSourceForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/sources/self-check'
import {
  setWorkflowOverrideForTest,
  workflowConfigPath,
} from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import type { WorkflowDefinition } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

const PARTIAL_WF: WorkflowDefinition = {
  id: 'test-append-partial',
  version: 1,
  label: 'partial',
  maxIterations: 3,
  nodes: [
    { key: 'prereq', enabled: true },
    { key: 'adapt', enabled: true },
    { key: 'build', enabled: true, onDone: 'END' },
    { key: 'flash', enabled: false, onUnavailable: 'manual_gate' },
    { key: 'selfcheck', enabled: false, onUnavailable: 'manual_gate', onDone: 'gerrit' },
    { key: 'gerrit', enabled: false, onUnavailable: 'manual_gate', onDone: 'END' },
  ],
}

const FULL_WF: WorkflowDefinition = {
  id: 'test-append-full',
  version: 1,
  label: 'full',
  maxIterations: 3,
  nodes: [
    { key: 'prereq', enabled: true },
    { key: 'adapt', enabled: true },
    { key: 'build', enabled: true },
    { key: 'flash', enabled: true },
    { key: 'selfcheck', enabled: true, onDone: 'gerrit' },
    { key: 'gerrit', enabled: true, onDone: 'END' },
  ],
}

function registerInstantStages(keys: string[]): void {
  for (const key of keys) {
    registerStage({
      key,
      label: key,
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })
  }
}

describe('adapt-pipeline append stages', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-append-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    resetSourcesForTest()
    resetSelfCheckSourceForTest()
    setWorkflowOverrideForTest(null)
  })

  afterEach(() => {
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    resetSourcesForTest()
    resetSelfCheckSourceForTest()
    setWorkflowOverrideForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('lists append candidates after partial pipeline passed', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    expect(Object.keys(run.stages).sort()).toEqual(['adapt', 'build', 'prereq'])

    await startRun(run.run_id)
    const passed = getRun(run.run_id)!
    expect(passed.status).toBe('passed')

    const candidates = computeAppendCandidates(passed)
    expect(candidates.eligible).toBe(true)
    expect(candidates.available).toEqual(['flash', 'selfcheck', 'gerrit'])
    expect(candidates.present).toEqual([])
  })

  it('appends flash+selfcheck, keeps done stages, does not rewrite workflow.json', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    expect(getRun(run.run_id)!.status).toBe('passed')

    const wfPath = workflowConfigPath()
    const beforeWf = existsSync(wfPath) ? readFileSync(wfPath, 'utf-8') : null

    await appendStages(run.run_id, { stages: ['flash', 'selfcheck'], device_id: 'DEV001' })
    const updated = getRun(run.run_id)!
    expect(updated.device_id).toBe('DEV001')
    expect(updated.stages.prereq.status).toBe('done')
    expect(updated.stages.adapt.status).toBe('done')
    expect(updated.stages.build.status).toBe('done')
    expect(updated.stages.flash).toBeTruthy()
    expect(updated.stages.selfcheck).toBeTruthy()
    expect(updated.stages.gerrit).toBeUndefined()
    expect(updated.status).toBe('passed')

    const tl = buildTimelineView(updated)
    expect(tl.nodes.map(n => n.key)).toEqual(['prereq', 'adapt', 'build', 'flash', 'selfcheck'])

    const afterWf = existsSync(wfPath) ? readFileSync(wfPath, 'utf-8') : null
    expect(afterWf).toBe(beforeWf)

    const note = updated.iterations[updated.iterations.length - 1]?.note ?? ''
    expect(note).toContain('追加后续阶段: flash,selfcheck')
  })

  it('auto-includes flash when only selfcheck requested', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    await appendStages(run.run_id, { stages: ['selfcheck'], device_id: 'DEV001' })

    const updated = getRun(run.run_id)!
    expect(updated.stages.flash).toBeTruthy()
    expect(updated.stages.selfcheck).toBeTruthy()
  })

  it('rejects flash/selfcheck append without device_id', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    await expect(appendStages(run.run_id, { stages: ['flash'] }))
      .rejects.toThrow(/设备 ID/)
  })

  it('allows gerrit-only with gerrit_skip_flash', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    await appendStages(run.run_id, { stages: ['gerrit'], gerrit_skip_flash: true })

    const updated = getRun(run.run_id)!
    expect(updated.stages.gerrit).toBeTruthy()
    expect(updated.stages.flash).toBeUndefined()
    expect(updated.status).toBe('passed')
  })

  it('rejects gerrit-only without risk flag', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    await expect(appendStages(run.run_id, { stages: ['gerrit'] }))
      .rejects.toThrow(/gerrit_skip_flash/)
  })

  it('rejects append when not passed', async () => {
    registerInstantStages(['prereq', 'adapt', 'build'])
    setWorkflowOverrideForTest(PARTIAL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    // draft
    await expect(appendStages(run.run_id, { stages: ['flash'] }))
      .rejects.toThrow(/当前状态/)

    const draft = getRun(run.run_id)!
    draft.status = 'failed'
    saveRun(draft, { immediate: true })
    await expect(appendStages(run.run_id, { stages: ['flash'] }))
      .rejects.toThrow(/当前状态/)
  })

  it('marks ineligible when run already has all appendable stages', async () => {
    registerInstantStages(['prereq', 'adapt', 'build', 'flash', 'selfcheck', 'gerrit'])
    setWorkflowOverrideForTest(FULL_WF)

    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    const passed = getRun(run.run_id)!
    expect(passed.status).toBe('passed')

    const candidates = computeAppendCandidates(passed)
    expect(candidates.eligible).toBe(false)
    expect(candidates.available).toEqual([])
    expect(candidates.present).toEqual(['flash', 'selfcheck', 'gerrit'])
  })
})
