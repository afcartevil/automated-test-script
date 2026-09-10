import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskStream } from '../../packages/server/src/services/tahp/task-stream'
import {
  appendPipelineLog,
  readPipelineLogs,
} from '../../packages/server/src/services/tahp/adapt-pipeline/events'
import {
  advance,
  computeResumePoints,
  recover,
  refreshArtifacts,
  resetOrchestratorForTest,
  resumeFrom,
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
  DEFAULT_WORKFLOW,
  setWorkflowOverrideForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import type { WorkflowDefinition } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

vi.mock('../../packages/server/src/services/tahp/adapt-agent', () => ({
  getAdaptAgentTask: vi.fn(() => undefined),
  startAdaptAgentRun: vi.fn(),
  cancelAdaptAgentRun: vi.fn(),
}))

function baseInput(workspace = 'project/KM9_NEW') {
  return {
    project_code: 'KM9',
    build_context: {
      mapped_root: 'Z:\\',
      workspace,
      components: ['krn'],
      variant: 'userdebug' as const,
    },
  }
}

describe('adapt-pipeline F4', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-f4-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    setWorkflowOverrideForTest(DEFAULT_WORKFLOW)
  })

  afterEach(() => {
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    setWorkflowOverrideForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('buildTimelineView projects run into TimelineView', () => {
    const run = createRun(baseInput())
    run.status = 'waiting_human'
    run.current_node = 'build'
    run.stages.build = {
      key: 'build',
      status: 'waiting_human',
      attempt: 1,
      refs: {},
      human: {
        reason: 'capability_unavailable',
        message: '能力尚未接入',
        actions: [{ id: 'confirm_done', label: '继续' }],
      },
    }
    saveRun(run, { immediate: true })

    const timeline = buildTimelineView(run)
    expect(timeline.run_id).toBe(run.run_id)
    expect(timeline.nodes.length).toBe(DEFAULT_WORKFLOW.nodes.filter(n => n.enabled).length)
    expect(timeline.pending_human_count).toBe(1)
    expect(timeline.can_fail_current_stage).toBe(false)
    expect(timeline.nodes.find(n => n.key === 'build')?.human?.reason).toBe('capability_unavailable')
    expect(timeline.nodes.find(n => n.key === 'gerrit')).toBeTruthy()
  })

  it('buildTimelineView includes adapt domains and stage error', () => {
    const run = createRun(baseInput())
    run.domains = [{
      workspace_id: 'adapt-debug',
      domain_id: 'comm-framework',
      domain_label: '通信框架',
      module: 'telephony',
      related_skills: ['comm-framework-agent-test'],
      form_data: {},
      incomplete_required: [],
      enabled: true,
      status: 'failed',
      error: '当前大模型不可用',
    }]
    run.stages.adapt = {
      key: 'adapt',
      status: 'failed',
      attempt: 1,
      refs: {},
      error: '当前大模型不可用',
      progress: { percent: 0, text: '0/1 域' },
    }
    saveRun(run, { immediate: true })

    const timeline = buildTimelineView(run)
    const adaptNode = timeline.nodes.find(n => n.key === 'adapt')
    expect(adaptNode?.error).toBe('当前大模型不可用')
    expect(adaptNode?.progress?.domains).toHaveLength(1)
    expect(adaptNode?.progress?.domains?.[0].domain_id).toBe('comm-framework')
  })

  it('buildTimelineView forwards selfcheck pass/fail counts', () => {
    const run = createRun(baseInput())
    run.stages.selfcheck = {
      key: 'selfcheck',
      status: 'done',
      attempt: 1,
      refs: {},
      progress: {
        state: 'success',
        total: 2,
        passed: 2,
        failed: 0,
        running: 0,
        text: '0 通过 / 0 失败',
      },
      summary: { total: 2, passed: 2, failed: 0 },
    }
    saveRun(run, { immediate: true })

    const timeline = buildTimelineView(run)
    const node = timeline.nodes.find(n => n.key === 'selfcheck')
    expect(node?.progress?.passed).toBe(2)
    expect(node?.progress?.failed).toBe(0)
    expect(node?.progress?.total).toBe(2)
    expect(node?.summary_line).toBe('2 通过 / 0 失败')
  })

  it('appendPipelineLog writes tail lines for logs endpoint', () => {
    const run = createRun(baseInput())
    appendPipelineLog(run.run_id, 'build', 'line-1')
    appendPipelineLog(run.run_id, 'build', 'line-2')
    expect(readPipelineLogs(run.run_id, 'build', 10)).toEqual(
      expect.arrayContaining([
        expect.stringContaining('line-1'),
        expect.stringContaining('line-2'),
      ]),
    )
  })

  it('resume unsafe without force is rejected by resumeFrom', async () => {
    registerStage({
      key: 'adapt',
      label: 'adapt',
      produces: ['source'],
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })
    registerStage({
      key: 'build',
      label: 'build',
      consumes: ['source'],
      produces: ['build'],
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })
    registerStage({
      key: 'flash',
      label: 'flash',
      consumes: ['build'],
      produces: ['flashed'],
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })

    const wf: WorkflowDefinition = {
      id: 'resume-test',
      version: 1,
      label: 'resume',
      maxIterations: 3,
      nodes: [
        { key: 'adapt', enabled: true },
        { key: 'build', enabled: true },
        { key: 'flash', enabled: true, onDone: 'END' },
      ],
    }
    setWorkflowOverrideForTest(wf)

    const run = createRun(baseInput())
    const wfNode = wf.nodes.find(n => n.key === 'adapt')!
    refreshArtifacts(run, wfNode, ['source'])
    run.stages.adapt = { key: 'adapt', status: 'done', attempt: 1, refs: {} }
    run.artifacts.source = {
      kind: 'source',
      produced_by: 'adapt',
      produced_at: run.created_at,
      stale: true,
      stale_reason: 'test',
    }
    run.current_node = 'flash'
    run.status = 'failed'
    saveRun(run, { immediate: true })

    const { recommended } = computeResumePoints(run)
    expect(recommended).toBe('adapt')

    await expect(resumeFrom(run.run_id, { node: 'flash' })).rejects.toMatchObject({
      message: expect.stringContaining('不安全'),
    })
  })

  it('recover marks lost adapt task as lost_after_restart', async () => {
    registerStage({
      key: 'adapt',
      label: 'adapt',
      async start() {},
      evaluate() {
        return { status: 'running' as const }
      },
    })
    setWorkflowOverrideForTest({
      id: 'recover-test',
      version: 1,
      label: 'recover',
      maxIterations: 3,
      nodes: [{ key: 'adapt', enabled: true, onDone: 'END' }],
    })

    const run = createRun(baseInput())
    run.status = 'running'
    run.current_node = 'adapt'
    run.domains = [{
      workspace_id: 'adapt-debug',
      domain_id: 'tp',
      domain_label: 'TP',
      module: 'kernel-driver',
      related_skills: ['tp-adapt'],
      form_data: {},
      incomplete_required: [],
      enabled: true,
      status: 'running',
      adapt_task_id: 'task-missing',
    }]
    run.stages.adapt = {
      key: 'adapt',
      status: 'running',
      attempt: 1,
      refs: { adapt_task_ids: ['task-missing'] },
    }
    saveRun(run, { immediate: true })

    await recover()

    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.stages.adapt?.human?.reason).toBe('lost_after_restart')
  })

  it('emits pipeline.run_started on startRun', async () => {
    const events: string[] = []
    getTaskStream().on('event', ev => {
      if (ev.type.startsWith('pipeline.')) events.push(ev.type)
    })

    registerStage({
      key: 'prereq',
      label: 'prereq',
      async start() {},
      evaluate() {
        return { status: 'done' as const }
      },
    })
    setWorkflowOverrideForTest({
      id: 'emit-test',
      version: 1,
      label: 'emit',
      maxIterations: 1,
      nodes: [{ key: 'prereq', enabled: true, onDone: 'END' }],
    })

    const run = createRun(baseInput())
    await startRun(run.run_id)
    await advance(run.run_id)

    expect(events).toContain('pipeline.run_started')
    expect(events).toContain('pipeline.node_changed')
  })

  it('registers adapt-pipeline REST routes', async () => {
    const { tahpAdaptPipelineRoutes } = await import('../../packages/server/src/routes/tahp/adapt-pipeline')
    const paths = tahpAdaptPipelineRoutes.stack.map((entry: { path: string }) => entry.path)
    expect(paths).toEqual(expect.arrayContaining([
      '/api/tahp/adapt-pipeline/parse-path-params',
      '/api/tahp/adapt-pipeline/runs',
      '/api/tahp/adapt-pipeline/runs/:runId/timeline',
      '/api/tahp/adapt-pipeline/runs/:runId/start',
      '/api/tahp/adapt-pipeline/runs/:runId/human-action',
      '/api/tahp/adapt-pipeline/runs/:runId/resume-points',
      '/api/tahp/adapt-pipeline/runs/:runId/fail-current-stage',
      '/api/tahp/adapt-pipeline/workflow',
      '/api/tahp/adapt-pipeline/capabilities',
      '/api/tahp/adapt-pipeline/domain-catalog',
    ]))
  })
})
