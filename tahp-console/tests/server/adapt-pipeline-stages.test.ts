import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskStream } from '../../packages/server/src/services/tahp/task-stream'
import {
  advance,
  resetOrchestratorForTest,
  startRun,
  submitHumanAction,
} from '../../packages/server/src/services/tahp/adapt-pipeline/orchestrator'
import { getStage, registerStageForTest, resetRegistryForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/registry'
import {
  createRun,
  getRun,
  resetStoreForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import { collectInvalidPaths, installPrereqStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/prereq'
import { installAdaptStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/adapt'
import { resetSourcesForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/sources'
import { installGerritStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/gerrit'
import { installBuildStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/build'
import { installFlashStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/flash'
import { installSelfcheckStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/selfcheck'
import { installTriageStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/triage'
import { installHumanReviewStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/human-review'
import {
  DEFAULT_WORKFLOW,
  setWorkflowOverrideForTest,
  validateWorkflow,
} from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import type { WorkflowDefinition } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

const resolveMock = vi.fn()
const startAdaptMock = vi.fn()
const isCentralMock = vi.fn()
const getLayoutMock = vi.fn()

vi.mock('../../packages/server/src/services/tahp/sync/central-client', () => ({
  centralClient: {
    resolveAdaptPrereqs: (...args: unknown[]) => resolveMock(...args),
  },
}))

vi.mock('../../packages/server/src/services/tahp/adapt-agent', () => ({
  startAdaptAgentRun: (...args: unknown[]) => startAdaptMock(...args),
  cancelAdaptAgentRun: vi.fn().mockResolvedValue({ ok: true }),
}))

vi.mock('../../packages/server/src/services/tahp/runtime-mode', () => ({
  isCentralConfigured: () => isCentralMock(),
}))

vi.mock('../../packages/server/src/services/tahp/adapt-layout/service', () => ({
  getAdaptDomainLayout: (...args: unknown[]) => getLayoutMock(...args),
}))

vi.mock('../../packages/server/src/services/tahp/git-snapshot', () => ({
  takeSnapshot: vi.fn().mockResolvedValue([]),
  diffSnapshots: vi.fn().mockReturnValue(['vendor/mock.c']),
  fingerprint: vi.fn().mockReturnValue('mock-fp'),
}))

vi.mock('../../packages/server/src/services/tahp/gerrit-submit', () => ({
  probeGerritSubmit: vi.fn().mockResolvedValue({ available: false, reason: 'test: gerrit unavailable' }),
  detectDomainFileConflicts: vi.fn().mockReturnValue([]),
  buildConflictChanges: vi.fn().mockReturnValue([]),
  startGerritDomainSubmit: vi.fn().mockReturnValue({ ok: false, error: 'mocked' }),
  parseGerritSubmitResult: vi.fn().mockReturnValue({}),
  getGerritSubmitTask: vi.fn(),
}))

const PREREQ_ADAPT_WF: WorkflowDefinition = {
  id: 'test-prereq-adapt',
  version: 1,
  label: 'prereq+adapt',
  maxIterations: 3,
  nodes: [
    { key: 'prereq', enabled: true, onUnavailable: 'fail' },
    { key: 'adapt', enabled: true, onDone: 'END', onFail: 'ABORT' },
  ],
}

function baseInput() {
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

function stubOtherStages() {
  for (const key of ['build', 'flash', 'selfcheck', 'triage', 'human_review', 'gerrit']) {
    registerStageForTest({
      key,
      label: key,
      async start() {},
      evaluate() {
        return { status: 'running' as const }
      },
    })
  }
}

describe('adapt-pipeline stages', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-stages-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    resetSourcesForTest()
    setWorkflowOverrideForTest(null)
    resolveMock.mockReset()
    startAdaptMock.mockReset()
    isCentralMock.mockReset()
    getLayoutMock.mockReset()

    isCentralMock.mockReturnValue(true)
    getLayoutMock.mockResolvedValue({
      domain_id: 'tp',
      fields: [{ name: 'old_dts', label: '升级前dts文件', type: 'text', required: true }],
      related_skills: ['tp-adapt-bringup'],
      revision: 1,
      updated_at: new Date().toISOString(),
      source: 'user',
      schema_version: 1,
    })

    stubOtherStages()
    installPrereqStage()
    installAdaptStage()
    setWorkflowOverrideForTest(PREREQ_ADAPT_WF)
  })

  afterEach(() => {
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    resetSourcesForTest()
    setWorkflowOverrideForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('prereq resolves domains from central', async () => {
    resolveMock.mockResolvedValue({
      project_code: 'KM9',
      campaign_id: 'camp-1',
      from_os: '15',
      to_os: '16',
      domains: [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        revision: 1,
        schema: [],
        form_data: { note: 'ok' },
        stale_fields: [],
        incomplete_required: [],
      }],
    })
    startAdaptMock.mockReturnValue({ ok: true, taskId: 'task-tp-1' })

    const run = createRun(baseInput())
    await startRun(run.run_id)

    const updated = getRun(run.run_id)!
    expect(resolveMock).toHaveBeenCalledWith({ project_code: 'KM9', campaign_id: undefined })
    expect(updated.domains).toHaveLength(1)
    expect(updated.domains[0].domain_id).toBe('tp')
    expect(updated.domains[0].related_skills).toEqual(['tp-adapt-bringup'])
    expect(updated.from_os).toBe('15')
    expect(updated.to_os).toBe('16')
  })

  it('stops at waiting_human when incomplete_required is non-empty', async () => {
    resolveMock.mockResolvedValue({
      project_code: 'KM9',
      campaign_id: 'camp-1',
      from_os: '15',
      to_os: '16',
      domains: [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        revision: 1,
        schema: [],
        form_data: {},
        stale_fields: [],
        incomplete_required: ['debug_project'],
      }],
    })

    const run = createRun(baseInput())
    await startRun(run.run_id)

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.current_node).toBe('prereq')
    expect(updated.stages.prereq?.human?.reason).toBe('incomplete_required')
    expect(startAdaptMock).not.toHaveBeenCalled()
  })

  it('collectInvalidPaths rejects paths outside mapped_root', () => {
    const invalid = collectInvalidPaths(
      [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        domain_label: 'TP',
        module: 'kernel-driver',
        related_skills: ['tp-adapt-bringup'],
        form_data: { old_dts: 'D:\\other\\touch.dtsi' },
        incomplete_required: [],
        enabled: true,
        status: 'pending',
      }],
      'Z:\\',
      new Map([['tp', [{ name: 'old_dts', label: '升级前dts文件', type: 'text', required: true }]]]),
    )
    expect(invalid).toHaveLength(1)
    expect(invalid[0].field).toBe('old_dts')
  })

  it('prereq blocks when path is outside mapped_root', async () => {
    resolveMock.mockResolvedValue({
      project_code: 'KM9',
      campaign_id: 'camp-1',
      from_os: '15',
      to_os: '16',
      domains: [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        revision: 1,
        schema: [],
        form_data: { old_dts: 'D:\\outside\\file.dtsi' },
        stale_fields: [],
        incomplete_required: [],
      }],
    })

    const run = createRun(baseInput())
    await startRun(run.run_id)

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.stages.prereq?.human?.reason).toBe('invalid_paths')
  })

  it('adapt runs domains serially and auto-starts domain 2 after domain 1 completes', async () => {
    resolveMock.mockResolvedValue({
      project_code: 'KM9',
      campaign_id: 'camp-1',
      from_os: '15',
      to_os: '16',
      domains: [
        {
          workspace_id: 'adapt-debug',
          domain_id: 'tp',
          revision: 1,
          schema: [],
          form_data: { debug_project: 'A' },
          stale_fields: [],
          incomplete_required: [],
        },
        {
          workspace_id: 'adapt-debug',
          domain_id: 'lcm',
          revision: 1,
          schema: [],
          form_data: { PROJECT_NAME: 'B' },
          stale_fields: [],
          incomplete_required: [],
        },
      ],
    })

    getLayoutMock.mockImplementation(async (domainId: string) => ({
      domain_id: domainId,
      fields: [{ name: 'x', label: 'x', type: 'text', required: false }],
      related_skills: domainId === 'tp' ? ['tp-adapt-bringup'] : ['display_analyser'],
      revision: 1,
      updated_at: new Date().toISOString(),
      source: 'user',
      schema_version: 1,
    }))

    startAdaptMock
      .mockReturnValueOnce({ ok: true, taskId: 'task-tp' })
      .mockReturnValueOnce({ ok: true, taskId: 'task-lcm' })

    const run = createRun(baseInput())
    await startRun(run.run_id)

    expect(startAdaptMock).toHaveBeenCalledTimes(1)
    expect(startAdaptMock.mock.calls[0][0].domainId).toBe('tp')

    getTaskStream().publish({
      type: 'task.completed',
      task_id: 'task-tp',
      payload: { task_id: 'task-tp' },
      ts: Date.now(),
    })

    await advance(run.run_id)
    await new Promise(r => setTimeout(r, 80))

    expect(startAdaptMock).toHaveBeenCalledTimes(2)
    expect(startAdaptMock.mock.calls[1][0].domainId).toBe('lcm')

    getTaskStream().publish({
      type: 'task.completed',
      task_id: 'task-lcm',
      payload: { task_id: 'task-lcm' },
      ts: Date.now(),
    })
    for (let i = 0; i < 5; i++) {
      await advance(run.run_id)
      if (getRun(run.run_id)?.status !== 'running') break
    }

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('passed')
    expect(updated.domains.every(d => d.status === 'done')).toBe(true)
  })

  it('confirm_done on prereq advances past incomplete gate', async () => {
    resolveMock.mockResolvedValue({
      project_code: 'KM9',
      campaign_id: 'camp-1',
      from_os: '15',
      to_os: '16',
      domains: [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        revision: 1,
        schema: [],
        form_data: {},
        stale_fields: [],
        incomplete_required: ['debug_project'],
      }],
    })
    startAdaptMock.mockReturnValue({ ok: true, taskId: 'task-tp' })

    const run = createRun(baseInput())
    await startRun(run.run_id)
    await submitHumanAction(run.run_id, 'prereq', 'confirm_done')

    expect(startAdaptMock).toHaveBeenCalled()
    expect(getRun(run.run_id)?.current_node).toBe('adapt')
  })
})

const ARTIFACT_TABLE: Array<{
  key: string
  consumes?: string[]
  produces?: string[]
}> = [
  { key: 'prereq', produces: ['prereq'] },
  { key: 'adapt', consumes: ['prereq'], produces: ['source'] },
  { key: 'build', consumes: ['source'], produces: ['build'] },
  { key: 'flash', consumes: ['build'], produces: ['flashed'] },
  { key: 'selfcheck', consumes: ['flashed'], produces: ['testresult'] },
  { key: 'triage', consumes: ['testresult'], produces: ['triage'] },
  { key: 'human_review', consumes: ['triage'], produces: ['source'] },
  { key: 'gerrit', consumes: ['source', 'testresult'] },
]

function stubManualGateStage(key: string, label: string): void {
  registerStageForTest({
    key,
    label,
    async probe() {
      return { available: false, reason: 'test stub unavailable' }
    },
    async start() {},
    evaluate() {
      return { status: 'running' as const }
    },
  })
}

function installAllStages(): void {
  installPrereqStage()
  installAdaptStage()
  installBuildStage()
  installFlashStage()
  installSelfcheckStage()
  installTriageStage()
  installHumanReviewStage()
  installGerritStage()
}

function mockPrereqAndAdaptSingleDomain(taskId = 'task-tp') {
  resolveMock.mockResolvedValue({
    project_code: 'KM9',
    campaign_id: 'camp-1',
    from_os: '15',
    to_os: '16',
    domains: [{
      workspace_id: 'adapt-debug',
      domain_id: 'tp',
      revision: 1,
      schema: [],
      form_data: { note: 'ok' },
      stale_fields: [],
      incomplete_required: [],
    }],
  })
  startAdaptMock.mockReturnValue({ ok: true, taskId })
}

describe('adapt-pipeline F3', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-f3-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    resetSourcesForTest()
    setWorkflowOverrideForTest(null)
    resolveMock.mockReset()
    startAdaptMock.mockReset()
    isCentralMock.mockReset()
    getLayoutMock.mockReset()
    isCentralMock.mockReturnValue(true)
    getLayoutMock.mockResolvedValue({
      domain_id: 'tp',
      fields: [{ name: 'note', label: '备注', type: 'text', required: true }],
      related_skills: ['tp-adapt-bringup'],
      revision: 1,
      updated_at: new Date().toISOString(),
      source: 'user',
      schema_version: 1,
    })
    installAllStages()
    setWorkflowOverrideForTest(DEFAULT_WORKFLOW)
  })

  afterEach(() => {
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    resetSourcesForTest()
    setWorkflowOverrideForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('registers 8 stages and validateWorkflow(DEFAULT_WORKFLOW) passes', () => {
    for (const row of ARTIFACT_TABLE) {
      expect(getStage(row.key), `missing stage ${row.key}`).toBeDefined()
    }
    expect(validateWorkflow(DEFAULT_WORKFLOW)).toEqual({ ok: true })
  })

  it('declares consumes/produces per reference artifact table', () => {
    for (const row of ARTIFACT_TABLE) {
      const stage = getStage(row.key)!
      expect(stage.consumes ?? []).toEqual(row.consumes ?? [])
      expect(stage.produces ?? []).toEqual(row.produces ?? [])
    }
  })

  it('runs end-to-end through manual_gate nodes to passed', async () => {
    stubManualGateStage('flash', '烧录')
    stubManualGateStage('selfcheck', 'AI 自检')
    mockPrereqAndAdaptSingleDomain()
    const run = createRun(baseInput())
    await startRun(run.run_id)

    getTaskStream().publish({
      type: 'task.completed',
      task_id: 'task-tp',
      payload: { task_id: 'task-tp' },
      ts: Date.now(),
    })
    for (let i = 0; i < 8; i++) {
      await advance(run.run_id)
      if (getRun(run.run_id)?.current_node === 'build') break
    }

    let state = getRun(run.run_id)!
    expect(state.current_node).toBe('build')
    expect(state.stages.build?.human?.reason).toBe('capability_unavailable')

    await submitHumanAction(run.run_id, 'build', 'confirm_done')
    state = getRun(run.run_id)!
    expect(state.current_node).toBe('flash')

    await submitHumanAction(run.run_id, 'flash', 'confirm_done')
    state = getRun(run.run_id)!
    expect(state.current_node).toBe('selfcheck')

    await submitHumanAction(run.run_id, 'selfcheck', 'skip')
    state = getRun(run.run_id)!
    expect(state.current_node).toBe('gerrit')
    expect(state.stages.triage?.status).not.toBe('running')

    await submitHumanAction(run.run_id, 'gerrit', 'confirm_done')
    state = getRun(run.run_id)!
    expect(state.status).toBe('passed')
    expect(state.current_node).toBeNull()
  })

  it('selfcheck skip goes to gerrit not triage', async () => {
    stubManualGateStage('flash', '烧录')
    stubManualGateStage('selfcheck', 'AI 自检')
    mockPrereqAndAdaptSingleDomain()
    const run = createRun(baseInput())
    await startRun(run.run_id)

    getTaskStream().publish({
      type: 'task.completed',
      task_id: 'task-tp',
      payload: { task_id: 'task-tp' },
      ts: Date.now(),
    })
    for (let i = 0; i < 10; i++) {
      await advance(run.run_id)
    }

    await submitHumanAction(run.run_id, 'build', 'confirm_done')
    await submitHumanAction(run.run_id, 'flash', 'confirm_done')
    await submitHumanAction(run.run_id, 'selfcheck', 'skip')

    const state = getRun(run.run_id)!
    expect(state.current_node).toBe('gerrit')
    expect(state.stages.selfcheck?.status).toBe('skipped')
    expect(state.stages.triage?.status).toBe('pending')
  })
})
