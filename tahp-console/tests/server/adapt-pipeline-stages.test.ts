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
  saveRun,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import { installPrereqStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/prereq'
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
const { startGerritSubmitMock } = vi.hoisted(() => ({
  startGerritSubmitMock: vi.fn().mockReturnValue({ ok: false, error: 'mocked' }),
}))

vi.mock('../../packages/server/src/services/tahp/sync/central-client', () => ({
  centralClient: {
    resolveAdaptPrereqs: (...args: unknown[]) => resolveMock(...args),
  },
}))

vi.mock('../../packages/server/src/services/tahp/adapt-agent', () => ({
  startAdaptAgentRun: (...args: unknown[]) => startAdaptMock(...args),
  cancelAdaptAgentRun: vi.fn().mockResolvedValue({ ok: true }),
  getAdaptAgentTask: vi.fn().mockReturnValue(undefined),
}))

vi.mock('../../packages/server/src/services/tahp/runtime-mode', () => ({
  isCentralConfigured: () => isCentralMock(),
}))

vi.mock('../../packages/server/src/services/tahp/adapt-layout/service', () => ({
  getAdaptDomainLayout: (...args: unknown[]) => getLayoutMock(...args),
}))

vi.mock('../../packages/server/src/services/tahp/gerrit-submit', () => ({
  probeGerritSubmit: vi.fn().mockResolvedValue({ available: false, reason: 'test: gerrit unavailable' }),
  detectDomainFileConflicts: vi.fn().mockReturnValue([]),
  buildConflictChanges: vi.fn().mockReturnValue([]),
  startGerritDomainSubmit: (...args: unknown[]) => startGerritSubmitMock(...args),
  parseGerritSubmitResult: vi.fn().mockReturnValue({}),
  getGerritSubmitTask: vi.fn(),
}))
vi.mock('../../packages/server/src/services/tahp/adapt-pipeline/build-capability', () => ({
  buildCapability: {
    id: 'harness-build-agent',
    probe: vi.fn().mockResolvedValue({ available: false, reason: 'test: build unavailable' }),
    start: vi.fn(),
    getStatus: vi.fn(),
    cancel: vi.fn(),
  },
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

  it('injects path_params into each adapt domain formData including manual overrides', async () => {
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
        form_data: { debug_project: 'A' },
        stale_fields: [],
        incomplete_required: [],
      }],
    })
    startAdaptMock.mockReturnValue({ ok: true, taskId: 'task-tp-path' })

    const run = createRun({
      ...baseInput(),
      path_params: {
        inputs: {
          project_code: 'KM9',
          OLD_VENDOR_ROOT: 'Z:\\old\\vendor',
          NEW_VENDOR_ROOT: 'Z:\\new\\vendor',
          NEW_SYSTEM_ROOT: 'Z:\\sys',
        },
        fields: [
          {
            key: 'PROJECT_FULL',
            label: 'PROJECT_FULL',
            kind: 'select',
            ok: true,
            value: 'km9_h1',
            parsed_value: 'km9_h1',
          },
          {
            key: 'OLD_KERNEL_DWS_PATH',
            label: 'OLD_KERNEL_DWS_PATH',
            kind: 'text',
            ok: false,
            value: 'Z:\\manual\\a.dws',
            error: '文件不存在',
          },
        ],
        parsed_at: new Date().toISOString(),
      },
    })
    await startRun(run.run_id)

    expect(startAdaptMock).toHaveBeenCalled()
    const formData = startAdaptMock.mock.calls[0][0].formData as Record<string, string>
    expect(formData.NEW_VENDOR_ROOT).toBe('Z:\\new\\vendor')
    expect(formData.NEW_SYSTEM_ROOT).toBe('Z:\\sys')
    expect(formData.PROJECT_FULL).toBe('km9_h1')
    expect(formData.OLD_KERNEL_DWS_PATH).toBe('Z:\\manual\\a.dws')
    expect(formData.debug_project).toBe('A')
  })

  it('prereq keeps user-selected multi-workspace domains and merges central form_data', async () => {
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
        form_data: { debug_project: 'from-central', old_dts: 'Z:\\touch.dtsi' },
        stale_fields: [],
        incomplete_required: [],
      }],
    })
    getLayoutMock.mockImplementation(async (domainId: string) => ({
      domain_id: domainId,
      fields: [],
      related_skills: domainId === 'tp' ? ['tp-adapt-bringup'] : ['feature-skill'],
      revision: 1,
      updated_at: new Date().toISOString(),
      source: 'user',
      schema_version: 1,
    }))
    startAdaptMock.mockReturnValue({ ok: true, taskId: 'task-1' })

    const run = createRun({
      ...baseInput(),
      domains: [
        {
          workspace_id: 'adapt-debug',
          domain_id: 'tp',
          domain_label: 'TP触摸屏',
          module: 'kernel-driver',
          related_skills: [],
          form_data: { debug_project: 'user-override' },
          incomplete_required: [],
          enabled: true,
          status: 'pending',
        },
        {
          workspace_id: 'feature-adapt',
          domain_id: 'tp',
          domain_label: 'TP触摸屏',
          module: 'kernel-driver',
          related_skills: [],
          form_data: { feature_checklist: 'feat-a' },
          incomplete_required: [],
          enabled: true,
          status: 'pending',
        },
        {
          workspace_id: 'carrier-config',
          domain_id: 'ecc-config',
          domain_label: 'ECC配置',
          module: 'telephony',
          related_skills: [],
          form_data: {},
          incomplete_required: [],
          enabled: false,
          status: 'pending',
        },
      ],
    })
    await startRun(run.run_id)

    const updated = getRun(run.run_id)!
    expect(updated.domains).toHaveLength(3)
    const debugTp = updated.domains.find(d => d.workspace_id === 'adapt-debug' && d.domain_id === 'tp')
    const featureTp = updated.domains.find(d => d.workspace_id === 'feature-adapt' && d.domain_id === 'tp')
    const ecc = updated.domains.find(d => d.domain_id === 'ecc-config')
    expect(debugTp?.form_data.debug_project).toBe('user-override')
    expect(debugTp?.form_data.old_dts).toBe('Z:\\touch.dtsi')
    expect(debugTp?.related_skills).toEqual(['tp-adapt-bringup'])
    expect(featureTp?.enabled).toBe(true)
    expect(featureTp?.form_data.feature_checklist).toBe('feat-a')
    expect(ecc?.enabled).toBe(false)
    expect(ecc?.module).toBe('telephony')
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

  it('adapt accumulates absolute changed_files from task.file_change and files_modified', async () => {
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
        form_data: { debug_project: 'A' },
        stale_fields: [],
        incomplete_required: [],
      }],
    })
    getLayoutMock.mockResolvedValue({
      domain_id: 'tp',
      fields: [{ name: 'x', label: 'x', type: 'text', required: false }],
      related_skills: ['tp-adapt-bringup'],
      revision: 1,
      updated_at: new Date().toISOString(),
      source: 'user',
      schema_version: 1,
    })
    startAdaptMock.mockReturnValue({ ok: true, taskId: 'task-tp' })

    const run = createRun(baseInput())
    await startRun(run.run_id)

    const wsFile = 'Z:\\project\\KM9_NEW\\kernel\\drivers\\tp.c'
    getTaskStream().publish({
      type: 'task.file_change',
      task_id: 'task-tp',
      payload: { path: wsFile, action: 'modify' },
      ts: Date.now(),
    })
    await advance(run.run_id)

    getTaskStream().publish({
      type: 'task.completed',
      task_id: 'task-tp',
      payload: {
        task_id: 'task-tp',
        files_modified: ['vendor/mediatek/foo.c', 'D:\\outside\\skip.c'],
      },
      ts: Date.now(),
    })
    for (let i = 0; i < 5; i++) {
      await advance(run.run_id)
      if (getRun(run.run_id)?.domains[0]?.status === 'done') break
    }

    const files = getRun(run.run_id)!.domains[0].changed_files ?? []
    const normalized = files.map(f => f.replace(/\\/g, '/').toLowerCase())
    expect(normalized).toEqual(
      expect.arrayContaining([
        wsFile.replace(/\\/g, '/').toLowerCase(),
        'd:/outside/skip.c',
      ]),
    )
    expect(normalized.some(f => f.includes('vendor/mediatek'))).toBe(false)
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
    startGerritSubmitMock.mockReset()
    startGerritSubmitMock.mockReturnValue({ ok: false, error: 'mocked' })
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
    expect(state.stages.triage).toBeUndefined()
    expect(state.stages.human_review).toBeUndefined()
  })

  it('gerrit submit_all_repos clears waiting_human and starts domain submit', async () => {
    startGerritSubmitMock.mockReturnValue({ ok: true, taskId: 'task-gerrit-1' })
    installAllStages()

    const run = createRun({
      ...baseInput(),
      domains: [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        domain_label: 'TP',
        module: 'kernel-driver',
        related_skills: ['tp-adapt-bringup'],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'done',
        changed_files: ['Z:\\project\\KM9_NEW\\kernel\\tp.c'],
      }],
      build_context: {
        ...baseInput().build_context,
        gerrit_issue_id: 'TOS1501-1',
      },
    })
    run.status = 'waiting_human'
    run.current_node = 'gerrit'
    const repo = 'Z:\\project\\KM9_NEW\\kernel'
    run.stages.gerrit = {
      key: 'gerrit',
      status: 'waiting_human',
      attempt: 1,
      refs: {},
      progress: {
        state: 'awaiting_repo_selection',
        repos: [{
          repo,
          repo_label: 'kernel',
          files: ['Z:\\project\\KM9_NEW\\kernel\\tp.c'],
          domain_ids: ['tp'],
        }],
      },
      human: {
        reason: 'select_repos',
        message: '请勾选仓库',
        actions: [
          { id: 'submit_all_repos', label: '全部仓库入库' },
          { id: 'submit_selected_repos', label: '提交所选仓库' },
        ],
      },
    }
    saveRun(run, { immediate: true })

    await submitHumanAction(run.run_id, 'gerrit', 'submit_all_repos')

    const updated = getRun(run.run_id)!
    expect(updated.gerrit_selected_repos?.length).toBeGreaterThan(0)
    expect(updated.stages.gerrit?.status).toBe('running')
    expect(updated.stages.gerrit?.human).toBeUndefined()
    expect(updated.status).toBe('running')
    expect(startGerritSubmitMock).toHaveBeenCalled()
    expect(updated.stages.gerrit?.refs?.gerrit_task_id).toBe('task-gerrit-1')
    expect((updated.stages.gerrit?.progress as { state?: string })?.state).toBe('submitting')
  })
})
