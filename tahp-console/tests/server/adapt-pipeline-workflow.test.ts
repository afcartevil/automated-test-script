import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { getStage, registerStage, resetRegistryForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/registry'
import {
  adaptPipelineConfigDir,
  buildRunPreview,
  createRun,
  deleteDraftRun,
  findResourceConflict,
  getRun,
  resetStoreForTest,
  saveRun,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import {
  DEFAULT_WORKFLOW,
  loadWorkflow,
  validateWorkflow,
  workflowConfigPath,
} from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import type { StageDefinition, WorkflowDefinition } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

const STAGE_KEYS = [
  'prereq',
  'adapt',
  'build',
  'flash',
  'selfcheck',
  'triage',
  'human_review',
  'gerrit',
] as const

function stubStage(key: string, overrides: Partial<StageDefinition> = {}): StageDefinition {
  return {
    key,
    label: key,
    isHumanGate: key === 'human_review',
    async start() {},
    evaluate() {
      return { status: 'running' as const }
    },
    ...overrides,
  }
}

function registerDefaultStubStages(): void {
  resetRegistryForTest()
  for (const key of STAGE_KEYS) {
    registerStage(stubStage(key))
  }
}

describe('adapt-pipeline workflow', () => {
  beforeEach(() => {
    registerDefaultStubStages()
  })

  afterEach(() => {
    resetRegistryForTest()
  })

  it('validateWorkflow(DEFAULT_WORKFLOW) passes with stub stages', () => {
    const result = validateWorkflow(DEFAULT_WORKFLOW)
    expect(result).toEqual({ ok: true })
  })

  it('rejects duplicate node keys', () => {
    const wf: WorkflowDefinition = {
      ...DEFAULT_WORKFLOW,
      nodes: [
        { key: 'prereq', enabled: true },
        { key: 'prereq', enabled: true },
      ],
    }
    const result = validateWorkflow(wf)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors.some(e => e.includes('重复'))).toBe(true)
    }
  })

  it('rejects unregistered stage', () => {
    resetRegistryForTest()
    const result = validateWorkflow(DEFAULT_WORKFLOW)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors.some(e => e.includes('未注册'))).toBe(true)
    }
  })

  it('rejects dangling onDone target', () => {
    const wf: WorkflowDefinition = {
      ...DEFAULT_WORKFLOW,
      nodes: DEFAULT_WORKFLOW.nodes.map(n =>
        n.key === 'build' ? { ...n, onDone: 'not_a_node' } : n,
      ),
    }
    const result = validateWorkflow(wf)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors.some(e => e.includes('onDone') && e.includes('not_a_node'))).toBe(true)
    }
  })

  it('rejects loop edge without increment_iteration', () => {
    const wf: WorkflowDefinition = {
      ...DEFAULT_WORKFLOW,
      nodes: DEFAULT_WORKFLOW.nodes.map(n =>
        n.key === 'human_review'
          ? { ...n, enabled: true, onDone: 'build', onDoneEffect: undefined }
          : n,
      ),
    }
    const result = validateWorkflow(wf)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors.some(e => e.includes('increment_iteration'))).toBe(true)
    }
  })

  it('rejects loop edge when source is not human gate', () => {
    resetRegistryForTest()
    for (const key of STAGE_KEYS) {
      registerStage(stubStage(key, { isHumanGate: key === 'human_review' }))
    }
    const wf: WorkflowDefinition = {
      ...DEFAULT_WORKFLOW,
      nodes: DEFAULT_WORKFLOW.nodes.map(n =>
        n.key === 'selfcheck'
          ? { ...n, onFail: 'build', onDone: 'gerrit' }
          : n.key === 'human_review' || n.key === 'triage'
            ? { ...n, enabled: false }
            : n,
      ),
    }
    const result = validateWorkflow(wf)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors.some(e => e.includes('人工门'))).toBe(true)
    }
  })

  it('default workflow disables triage and human_review', () => {
    const triage = DEFAULT_WORKFLOW.nodes.find(n => n.key === 'triage')
    const review = DEFAULT_WORKFLOW.nodes.find(n => n.key === 'human_review')
    expect(triage?.enabled).toBe(false)
    expect(review?.enabled).toBe(false)
    expect(DEFAULT_WORKFLOW.nodes.find(n => n.key === 'selfcheck')?.onDone).toBe('gerrit')
    expect(DEFAULT_WORKFLOW.nodes.find(n => n.key === 'selfcheck')?.onFail).toBe('human_review')
  })

  it('loadWorkflow falls back when workflow.json is invalid', () => {
    const dir = mkdtempSync(join(tmpdir(), 'ap-wf-'))
    const prev = process.env.TAHP_ADAPT_PIPELINE_DIR
    process.env.TAHP_ADAPT_PIPELINE_DIR = dir
    try {
      writeFileSync(workflowConfigPath(), JSON.stringify({ id: 'bad', nodes: [] }), 'utf-8')
      const wf = loadWorkflow()
      expect(wf.id).toBe(DEFAULT_WORKFLOW.id)
    } finally {
      if (prev === undefined) delete process.env.TAHP_ADAPT_PIPELINE_DIR
      else process.env.TAHP_ADAPT_PIPELINE_DIR = prev
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('human_review stage stub is registered as human gate', () => {
    expect(getStage('human_review')?.isHumanGate).toBe(true)
  })
})

describe('adapt-pipeline store', () => {
  let tempDir = ''

  beforeEach(() => {
    registerDefaultStubStages()
    tempDir = mkdtempSync(join(tmpdir(), 'ap-store-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetStoreForTest()
  })

  afterEach(() => {
    resetStoreForTest()
    resetRegistryForTest()
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) {
      rmSync(tempDir, { recursive: true, force: true })
    }
  })

  it('createRun → saveRun → getRun round-trips', () => {
    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        components: ['krn', 'vext'],
        variant: 'userdebug',
      },
    })

    expect(run.status).toBe('draft')
    expect(run.artifacts).toEqual({})
    expect(run.stages.prereq?.status).toBe('pending')

    run.status = 'running'
    saveRun(run, { immediate: true })

    resetStoreForTest()
    const loaded = getRun(run.run_id)
    expect(loaded).not.toBeNull()
    expect(loaded?.status).toBe('running')
    expect(loaded?.project_code).toBe('KM9')

    const disk = readFileSync(join(adaptPipelineConfigDir(), 'runs', `${run.run_id}.json`), 'utf-8')
    expect(JSON.parse(disk).run_id).toBe(run.run_id)
  })

  it('buildRunPreview detects workspace conflict without persisting', () => {
    const holder = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'D:\\temp',
        workspace: 'D:\\temp',
        components: ['krn'],
        variant: 'userdebug',
      },
    })
    holder.status = 'running'
    saveRun(holder, { immediate: true })

    const preview = buildRunPreview({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'D:\\temp',
        workspace: 'D:\\temp',
        components: ['krn'],
        variant: 'userdebug',
      },
    })
    const conflict = findResourceConflict(preview)
    expect(conflict?.kind).toBe('workspace')
    expect(getRun(preview.run_id)).toBeNull()
  })

  it('deleteDraftRun removes draft from disk and index', () => {
    const run = createRun({
      project_code: 'KM9',
      build_context: {
        mapped_root: 'Z:\\',
        workspace: 'project/KM9_NEW',
        components: ['krn'],
        variant: 'userdebug',
      },
    })
    expect(deleteDraftRun(run.run_id)).toBe(true)
    expect(getRun(run.run_id)).toBeNull()
    expect(existsSync(join(adaptPipelineConfigDir(), 'runs', `${run.run_id}.json`))).toBe(false)
  })
})
