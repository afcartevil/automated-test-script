import { cancelAdaptAgentRun, getAdaptAgentTask } from '../adapt-agent'
import { appendPipelineLog, emitPipelineEvent } from './events'
import { getStage, listStages } from './registry'
import { getRun, listActiveRunIds, saveRun } from './store'
import {
  getEnabledNodes,
  loadWorkflow,
  resolveOnDone,
} from './workflow'
import { setPipelineEventHandler, startSources } from './sources'
import type {
  ArtifactKind,
  NodeTarget,
  ObservedEvent,
  PipelineRun,
  ResumePoint,
  ResumeRequest,
  StageContext,
  StageState,
  StageVerdict,
  WorkflowDefinition,
  WorkflowNode,
} from './types'

const advanceChains = new Map<string, Promise<void>>()
const correlationIndex = new Map<string, { runId: string; nodeKey: string }>()
const advancingRuns = new Set<string>()

/** F7 前恒为 false；测试可覆盖 */
let sourceChangedCheckerForTest: ((run: PipelineRun) => boolean) | null = null

export function setSourceChangedCheckerForTest(
  fn: ((run: PipelineRun) => boolean) | null,
): void {
  sourceChangedCheckerForTest = fn
}

let artifactDownstream = new Map<ArtifactKind, ArtifactKind[]>()

function rebuildArtifactGraph(): void {
  const downstream = new Map<ArtifactKind, Set<ArtifactKind>>()
  for (const stage of listStages()) {
    const consumes = stage.consumes ?? []
    const produces = stage.produces ?? []
    for (const p of produces) {
      for (const c of consumes) {
        if (!downstream.has(c)) downstream.set(c, new Set())
        downstream.get(c)!.add(p)
      }
    }
  }
  artifactDownstream = new Map(
    [...downstream.entries()].map(([k, v]) => [k, [...v]]),
  )
}

function getDownstream(kind: ArtifactKind): ArtifactKind[] {
  if (artifactDownstream.size === 0) rebuildArtifactGraph()
  return artifactDownstream.get(kind) ?? []
}

function workflowFor(_run: PipelineRun): WorkflowDefinition {
  return loadWorkflow()
}

function emitPipeline(type: string, payload: Record<string, unknown>): void {
  emitPipelineEvent(type, payload)
}

function freshStageState(key: string): StageState {
  return { key, status: 'pending', attempt: 0, refs: {} }
}

function patchRun(run: PipelineRun, patch: Partial<PipelineRun>): void {
  Object.assign(run, patch)
  saveRun(run)
}

function patchStage(run: PipelineRun, nodeKey: string, patch: Partial<StageState>): void {
  const prev = run.stages[nodeKey] ?? freshStageState(nodeKey)
  run.stages[nodeKey] = { ...prev, ...patch }
  saveRun(run)
}

function createCtx(run: PipelineRun, node: WorkflowNode): StageContext {
  const nodeKey = node.key
  return {
    run,
    node,
    get state() {
      return run.stages[nodeKey] ?? freshStageState(nodeKey)
    },
    patchState(patch) {
      patchStage(run, nodeKey, patch)
    },
    patchRun(patch) {
      patchRun(run, patch)
    },
    log(line) {
      appendPipelineLog(run.run_id, nodeKey, line)
    },
  }
}

function registerCorrelations(runId: string, nodeKey: string, refs: Record<string, unknown>): void {
  for (const v of Object.values(refs)) {
    if (typeof v === 'string') {
      correlationIndex.set(v, { runId, nodeKey })
    } else if (Array.isArray(v)) {
      for (const item of v) {
        if (typeof item === 'string') correlationIndex.set(item, { runId, nodeKey })
      }
    }
  }
}

function clearCorrelationsForNode(runId: string, nodeKey: string): void {
  for (const [key, val] of correlationIndex.entries()) {
    if (val.runId === runId && val.nodeKey === nodeKey) {
      correlationIndex.delete(key)
    }
  }
}

function hasSourceChanged(run: PipelineRun): boolean {
  if (sourceChangedCheckerForTest) return sourceChangedCheckerForTest(run)
  return false
}

/** onFail 指向已停用节点时，不跳转（避免 skip 进下一 enabled 节点如 gerrit） */
function failTargetIsEnterable(wf: WorkflowDefinition, target: NodeTarget): boolean {
  if (target === 'END' || target === 'ABORT') return true
  const node = wf.nodes.find(n => n.key === target)
  return Boolean(node?.enabled)
}

async function detectSourceChangedAsync(run: PipelineRun): Promise<boolean> {
  return hasSourceChanged(run)
}

/**
 * 方案 A：失败目标不可用（如 human_review 已停用）时，就地人工门 + 恢复点。
 */
async function parkFailedNodeForHuman(
  runId: string,
  nodeKey: string,
  error?: string,
): Promise<void> {
  const run = getRun(runId)
  if (!run) return

  const { points, recommended } = computeResumePoints(run)
  const recommendedOrSelf =
    recommended
    ?? points.find(p => p.node === nodeKey)?.node
    ?? nodeKey

  const message = error
    ? `阶段失败：${error}。请选择恢复点继续，或终止流水线。`
    : '阶段失败，请选择恢复点继续，或终止流水线。'

  const actions = [
    {
      id: 'confirm_done',
      label: '继续',
      fields: [
        { name: 'resume_node', label: '从哪里继续', required: true },
        { name: 'resume_scope', label: '范围' },
      ],
    },
    { id: 'abort', label: '终止流水线', danger: true },
  ]

  const prev = (run.stages[nodeKey]?.progress as Record<string, unknown> | undefined) ?? {}
  patchStage(run, nodeKey, {
    status: 'waiting_human',
    error,
    finished_at: new Date().toISOString(),
    progress: {
      ...prev,
      resume_points: { points, recommended: recommendedOrSelf },
      text: message,
    },
    human: {
      reason: 'stage_failed',
      message,
      actions,
    },
  })
  run.status = 'waiting_human'
  run.current_node = nodeKey
  saveRun(run, { immediate: true })
  emitPipeline('pipeline.waiting_human', {
    run_id: runId,
    node: nodeKey,
    reason: 'stage_failed',
    message,
    actions,
  })
}

async function handleStageFailure(
  runId: string,
  nodeKey: string,
  error?: string,
): Promise<void> {
  const run = getRun(runId)
  if (!run) return
  const wf = workflowFor(run)
  const node = wf.nodes.find(n => n.key === nodeKey)
  const target = node?.onFail ?? 'ABORT'

  if (!failTargetIsEnterable(wf, target)) {
    await parkFailedNodeForHuman(runId, nodeKey, error)
    return
  }
  await transition(runId, target)
}

export function refreshArtifacts(
  run: PipelineRun,
  node: WorkflowNode,
  kinds: ArtifactKind[],
): void {
  if (kinds.length === 0) return
  rebuildArtifactGraph()
  const now = new Date().toISOString()
  const progress = run.stages[node.key]?.progress as Record<string, unknown> | undefined
  const fingerprint = progress?.fingerprint as string | undefined

  for (const kind of kinds) {
    run.artifacts[kind] = {
      kind,
      produced_by: node.key,
      produced_at: now,
      fingerprint,
      stale: false,
    }
  }

  const visited = new Set<ArtifactKind>(kinds)
  const queue = [...kinds]
  while (queue.length > 0) {
    const k = queue.shift()!
    for (const downstream of getDownstream(k)) {
      if (visited.has(downstream)) continue
      visited.add(downstream)
      const existing = run.artifacts[downstream]
      if (existing) {
        run.artifacts[downstream] = {
          ...existing,
          stale: true,
          stale_reason: `${k} 已更新`,
        }
      }
      queue.push(downstream)
    }
  }
}

function nodeLabel(nodeKey: string): string {
  return getStage(nodeKey)?.label ?? nodeKey
}

export function computeResumePoints(run: PipelineRun): {
  points: ResumePoint[]
  recommended: string | null
} {
  rebuildArtifactGraph()
  const wf = workflowFor(run)
  const enabled = getEnabledNodes(wf)
  const points: ResumePoint[] = []

  for (const node of enabled) {
    const stage = getStage(node.key)
    const consumes = stage?.consumes ?? []
    const missing = consumes
      .filter(k => !run.artifacts[k] || run.artifacts[k]!.stale)
      .map(k => {
        const art = run.artifacts[k]
        const reason = !art ? '产物缺失' : (art.stale_reason ?? '产物已过期')
        return { kind: k, reason }
      })

    const safety = missing.length === 0 ? 'safe' : 'unsafe'
    let hint: string | undefined
    if (missing.length > 0) {
      hint = missing.map(m => `${m.kind}: ${m.reason}`).join('；')
    }

    points.push({
      node: node.key,
      label: nodeLabel(node.key),
      safety,
      missing: missing.length ? missing : undefined,
      hint,
    })
  }

  let recommended: string | null = null
  for (const node of enabled) {
    const stage = getStage(node.key)
    const produces = stage?.produces ?? []
    const hasStaleProduce = produces.some(
      p => !run.artifacts[p] || run.artifacts[p]!.stale,
    )
    const point = points.find(p => p.node === node.key)
    if (point?.safety === 'safe' && hasStaleProduce) {
      recommended = node.key
      break
    }
  }

  if (!recommended) {
    const failed = [...enabled]
      .reverse()
      .find(n => {
        const st = run.stages[n.key]
        return st?.status === 'failed'
          || (st?.status === 'waiting_human' && st.human?.reason === 'stage_failed')
      })
    if (failed) {
      const point = points.find(p => p.node === failed.key)
      if (point?.safety === 'safe') recommended = failed.key
    }
  }

  return { points, recommended }
}

function enabledIndex(wf: WorkflowDefinition, nodeKey: string): number {
  return getEnabledNodes(wf).findIndex(n => n.key === nodeKey)
}

function resetStagesFrom(run: PipelineRun, wf: WorkflowDefinition, fromNodeKey: string): void {
  const enabled = getEnabledNodes(wf)
  const idx = enabledIndex(wf, fromNodeKey)
  if (idx < 0) throw new Error(`节点不在流程中: ${fromNodeKey}`)

  for (let i = idx; i < enabled.length; i++) {
    const key = enabled[i].key
    const prev = run.stages[key]
    if (prev && (Object.keys(prev.refs).length > 0 || prev.summary)) {
      const last = run.iterations[run.iterations.length - 1]
      if (last) {
        last.note = [last.note, `archived ${key}`].filter(Boolean).join('; ')
      }
    }
    clearCorrelationsForNode(run.run_id, key)
    run.stages[key] = freshStageState(key)
  }
}

function applyResumeScope(
  run: PipelineRun,
  wf: WorkflowDefinition,
  nodeKey: string,
  scope: 'continue' | 'restart',
): void {
  const node = wf.nodes.find(n => n.key === nodeKey)
  if (node) {
    node.params = { ...node.params, resume_scope: scope }
    if (nodeKey === 'build') {
      node.params.build_mode = scope === 'restart' ? 'full' : 'incremental'
    }
  }
  const prev = run.stages[nodeKey]?.progress ?? {}
  const progress: Record<string, unknown> = { ...prev, resume_scope: scope }
  if (nodeKey === 'build') {
    progress.build_mode = scope === 'restart' ? 'full' : 'incremental'
  }
  patchStage(run, nodeKey, { progress })
}

async function enter(runId: string, nodeKey: NodeTarget): Promise<void> {
  const run = getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)

  if (nodeKey === 'END') {
    run.status = 'passed'
    run.current_node = null
    run.finished_at = new Date().toISOString()
    const last = run.iterations[run.iterations.length - 1]
    if (last && last.verdict === 'running') {
      last.verdict = 'passed'
      last.finished_at = run.finished_at
    }
    saveRun(run, { immediate: true })
    emitPipeline('pipeline.run_completed', {
      run_id: runId,
      verdict: 'passed',
      duration_ms: Date.now() - new Date(run.created_at).getTime(),
    })
    return
  }

  if (nodeKey === 'ABORT') {
    const failedNode = run.current_node
    run.status = run.abort_reason ? 'aborted' : 'failed'
    run.current_node = null
    run.finished_at = new Date().toISOString()
    saveRun(run, { immediate: true })
    emitPipeline('pipeline.run_failed', {
      run_id: runId,
      error: run.abort_reason ?? run.stages[failedNode ?? '']?.error ?? 'aborted',
      node: failedNode,
    })
    return
  }

  const wf = workflowFor(run)
  const node = wf.nodes.find(n => n.key === nodeKey)
  if (!node) {
    run.status = 'failed'
    saveRun(run, { immediate: true })
    emitPipeline('pipeline.run_failed', {
      run_id: runId,
      error: `未知节点: ${nodeKey}`,
      node: nodeKey,
    })
    return
  }

  if (!node.enabled) {
    const enabled = getEnabledNodes(wf)
    const idx = enabled.findIndex(n => n.key === nodeKey)
    // 停用节点不在 enabled 列表中（idx=-1）时禁止“跳到首个节点”，避免失败误入 gerrit
    if (idx < 0) {
      const from = run.current_node
      if (from) {
        await parkFailedNodeForHuman(
          runId,
          from,
          run.stages[from]?.error ?? `失败目标节点已停用: ${nodeKey}`,
        )
        return
      }
      run.status = 'failed'
      saveRun(run, { immediate: true })
      emitPipeline('pipeline.run_failed', {
        run_id: runId,
        error: `失败目标节点已停用: ${nodeKey}`,
        node: nodeKey,
      })
      return
    }
    const next = enabled[idx + 1]
    await enter(runId, next ? next.key : 'END')
    return
  }

  const stage = getStage(node.key)
  if (!stage) {
    run.status = 'failed'
    patchStage(run, node.key, { status: 'failed', error: `未注册阶段: ${node.key}` })
    saveRun(run, { immediate: true })
    return
  }

  const prevNode = run.current_node
  run.current_node = node.key
  const state = run.stages[node.key] ?? freshStageState(node.key)
  run.stages[node.key] = state

  const availability = stage.probe
    ? await stage.probe({ run })
    : { available: true }

  if (!availability.available) {
    const mode = node.onUnavailable ?? 'manual_gate'
    if (mode === 'skip') {
      patchStage(run, node.key, { status: 'skipped' })
      const enabled = getEnabledNodes(wf)
      const idx = enabled.findIndex(n => n.key === node.key)
      const next = enabled[idx + 1]
      await transition(runId, next ? next.key : 'END')
      return
    }
    if (mode === 'fail') {
      patchStage(run, node.key, {
        status: 'failed',
        error: availability.reason ?? '能力不可用',
        availability,
      })
      await handleStageFailure(runId, node.key, availability.reason ?? '能力不可用')
      return
    }
    patchStage(run, node.key, {
      status: 'waiting_human',
      availability,
      human: {
        reason: 'capability_unavailable',
        message: availability.reason ?? '该能力尚未接入',
        actions: [
          { id: 'confirm_done', label: '已手工完成，继续' },
          { id: 'skip', label: '跳过' },
        ],
      },
    })
    run.status = 'waiting_human'
    saveRun(run, { immediate: true })
    emitPipeline('pipeline.waiting_human', {
      run_id: runId,
      node: node.key,
      reason: 'capability_unavailable',
      message: availability.reason ?? '该能力尚未接入',
      actions: run.stages[node.key].human?.actions ?? [],
    })
    return
  }

  patchStage(run, node.key, {
    status: 'running',
    started_at: new Date().toISOString(),
    attempt: (state.attempt ?? 0) + 1,
    human: undefined,
    error: undefined,
  })

  if (prevNode !== node.key) {
    emitPipeline('pipeline.node_changed', {
      run_id: runId,
      from: prevNode,
      to: node.key,
      iteration: run.iteration,
    })
  }

  const ctx = createCtx(run, node)
  await stage.start(ctx)
  registerCorrelations(runId, node.key, run.stages[node.key]?.refs ?? {})
  if (advancingRuns.has(runId)) {
    void advance(runId)
  } else {
    await advance(runId)
  }
}

async function transition(
  runId: string,
  target: NodeTarget,
  effect?: 'increment_iteration',
): Promise<void> {
  const run = getRun(runId)
  if (!run) return

  const fromNode = run.current_node
  if (fromNode) clearCorrelationsForNode(runId, fromNode)

  if (effect === 'increment_iteration') {
    if (hasSourceChanged(run)) {
      const next = run.iteration + 1
      if (next > run.max_iterations) {
        run.status = 'waiting_human'
        patchStage(run, fromNode ?? 'human_review', {
          status: 'waiting_human',
          human: {
            reason: 'max_iterations_exceeded',
            message: `已达最大迭代次数 ${run.max_iterations}`,
            actions: [
              { id: 'extend', label: '继续加一轮' },
              { id: 'abort', label: '终止', danger: true },
            ],
          },
        })
        saveRun(run, { immediate: true })
        emitPipeline('pipeline.waiting_human', {
          run_id: runId,
          node: fromNode,
          reason: 'max_iterations_exceeded',
          message: `已达最大迭代次数 ${run.max_iterations}`,
          actions: run.stages[fromNode ?? '']?.human?.actions ?? [],
        })
        return
      }
      run.iteration = next
      run.iterations.push({
        index: next,
        started_at: new Date().toISOString(),
        verdict: 'running',
      })
      emitPipeline('pipeline.iteration_started', {
        run_id: runId,
        iteration: next,
        trigger: 'loop',
      })
    }
  }

  emitPipeline('pipeline.node_changed', {
    run_id: runId,
    from: fromNode,
    to: target,
    iteration: run.iteration,
    reason: effect,
  })

  saveRun(run)
  await enter(runId, target)
}

function applyVerdict(
  run: PipelineRun,
  node: WorkflowNode,
  verdict: StageVerdict,
): 'handled' | 'transition' | 'retry' {
  const stage = getStage(node.key)!

  switch (verdict.status) {
    case 'running': {
      patchStage(run, node.key, {
        status: 'running',
        progress: verdict.progress as Record<string, unknown> | undefined,
        human: undefined,
        error: undefined,
      })
      if (run.status === 'waiting_human' || run.status === 'paused') {
        run.status = 'running'
        saveRun(run)
      }
      emitPipeline('pipeline.node_progress', {
        run_id: run.run_id,
        node: node.key,
        status: 'running',
        percent: (verdict.progress as { percent?: number } | undefined)?.percent,
        text: (verdict.progress as { text?: string } | undefined)?.text,
      })
      return 'handled'
    }
    case 'waiting_human': {
      patchStage(run, node.key, {
        status: 'waiting_human',
        human: {
          reason: verdict.reason,
          message: verdict.message,
          actions: verdict.actions,
        },
      })
      run.status = 'waiting_human'
      saveRun(run, { immediate: true })
      emitPipeline('pipeline.waiting_human', {
        run_id: run.run_id,
        node: node.key,
        reason: verdict.reason,
        message: verdict.message,
        actions: verdict.actions,
      })
      return 'handled'
    }
    case 'skipped': {
      patchStage(run, node.key, { status: 'skipped' })
      return 'transition'
    }
    case 'done': {
      patchStage(run, node.key, {
        status: 'done',
        finished_at: new Date().toISOString(),
        summary: verdict.summary,
      })
      refreshArtifacts(run, node, stage.produces ?? [])
      saveRun(run)
      return 'transition'
    }
    case 'failed': {
      patchStage(run, node.key, {
        status: 'failed',
        error: verdict.error,
        finished_at: new Date().toISOString(),
      })
      refreshArtifacts(run, node, verdict.produced ?? [])
      saveRun(run)
      const state = run.stages[node.key]!
      const maxAttempts = node.maxAttempts ?? 0
      if (verdict.retryable && state.attempt < maxAttempts) {
        return 'retry'
      }
      return 'transition'
    }
    default:
      return 'handled'
  }
}

async function awaitAdvanceIdle(runId: string): Promise<void> {
  let tail = advanceChains.get(runId)
  while (tail) {
    await tail
    const next = advanceChains.get(runId)
    if (!next || next === tail) break
    tail = next
  }
}

async function advanceOnce(runId: string): Promise<void> {
  advancingRuns.add(runId)
  try {
    const run = getRun(runId)
  if (!run || run.status === 'paused' || run.status === 'aborted') return

  const nodeKey = run.current_node
  if (!nodeKey) return

  const wf = workflowFor(run)
  const node = wf.nodes.find(n => n.key === nodeKey)
  if (!node) return

  const stage = getStage(node.key)
  if (!stage) return

  const existing = run.stages[node.key]
  // 人工门等待期间不要再 evaluate，避免把 waiting_human 冲成 running
  if (existing?.status === 'waiting_human') return

  const ctx = createCtx(run, node)
  const verdict = stage.evaluate(ctx)
  const outcome = applyVerdict(run, node, verdict)

  if (outcome === 'handled') return
  if (outcome === 'retry') {
    await enter(runId, nodeKey)
    return
  }

  const wf2 = workflowFor(run)
  const node2 = wf2.nodes.find(n => n.key === nodeKey)!
  const state = run.stages[nodeKey]

  if (verdict.status === 'skipped') {
    const enabled = getEnabledNodes(wf2)
    const idx = enabled.findIndex(n => n.key === nodeKey)
    const next = enabled[idx + 1]
    await transition(runId, next ? next.key : 'END')
    return
  }

  if (verdict.status === 'done') {
    const target = resolveOnDone(wf2, nodeKey)
    await transition(runId, target, node2.onDoneEffect)
    return
  }

  if (verdict.status === 'failed') {
    if (verdict.retryable && state && state.attempt < (node2.maxAttempts ?? 0)) {
      return
    }
    patchStage(run, nodeKey, { status: 'failed' })
    await handleStageFailure(runId, nodeKey, verdict.error ?? run.stages[nodeKey]?.error)
  }
  } finally {
    advancingRuns.delete(runId)
  }
}

export async function advance(runId: string): Promise<void> {
  const prev = advanceChains.get(runId) ?? Promise.resolve()
  const next = prev.then(() => advanceOnce(runId)).catch(err => {
    const run = getRun(runId)
    if (run) {
      run.status = 'failed'
      saveRun(run, { immediate: true })
      emitPipeline('pipeline.run_failed', {
        run_id: runId,
        error: String(err),
        node: run.current_node,
      })
    }
  })
  advanceChains.set(runId, next)
  await next
}

export async function startRun(runId: string): Promise<void> {
  const run = getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)
  if (run.status !== 'draft' && run.status !== 'paused') {
    throw new Error(`无法启动 run，当前状态: ${run.status}`)
  }

  rebuildArtifactGraph()
  startSources()
  setPipelineEventHandler(handleObservedEvent)

  const wf = workflowFor(run)
  const first = getEnabledNodes(wf)[0]
  if (!first) throw new Error('workflow 无 enabled 节点')

  run.status = 'running'
  if (run.iterations.length === 0) {
    run.iterations.push({
      index: run.iteration,
      started_at: new Date().toISOString(),
      verdict: 'running',
    })
  }
  saveRun(run, { immediate: true })

  emitPipeline('pipeline.run_started', {
    run_id: runId,
    project_code: run.project_code,
    workflow_id: run.workflow_id,
    nodes: getEnabledNodes(wf).map(n => n.key),
  })

  await enter(runId, first.key)
  await awaitAdvanceIdle(runId)
}

export async function submitHumanAction(
  runId: string,
  nodeKey: string,
  actionId: string,
  payload?: Record<string, unknown>,
): Promise<void> {
  const run = getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)

  if (actionId === 'abort') {
    await abortRun(runId, String(payload?.reason ?? '用户终止'))
    return
  }

  if (actionId === 'extend') {
    run.max_iterations += 1
    saveRun(run)
    const progress = run.stages[nodeKey]?.progress as Record<string, unknown> | undefined
    const pendingResume = progress?.pending_resume_node
    if (typeof pendingResume === 'string' && pendingResume) {
      await resumeFrom(runId, {
        node: pendingResume,
        scope: (progress?.pending_resume_scope as 'continue' | 'restart') ?? 'continue',
        force: Boolean(progress?.pending_resume_force),
      })
      return
    }
    const wf = workflowFor(run)
    const node = wf.nodes.find(n => n.key === nodeKey)
    const target = resolveOnDone(wf, nodeKey)
    await transition(runId, target, node?.onDoneEffect)
    return
  }

  if (actionId === 'confirm_done') {
    const resumeNode = payload?.resume_node as string | undefined
    if (resumeNode) {
      await resumeFrom(runId, {
        node: resumeNode,
        scope: (payload?.resume_scope as 'continue' | 'restart') ?? 'continue',
        force: Boolean(payload?.force),
      })
      return
    }
    const wf = workflowFor(run)
    const node = wf.nodes.find(n => n.key === nodeKey)
    const stage = getStage(nodeKey)
    patchStage(run, nodeKey, {
      status: 'done',
      finished_at: new Date().toISOString(),
    })
    if (stage && node) {
      const kinds = stage.produces ?? []
      if (nodeKey === 'human_review' && !hasSourceChanged(run)) {
        // F7 前恒不刷新；未改代码时保持下游产物有效
      } else {
        refreshArtifacts(run, node, kinds)
      }
    }
    run.status = 'running'
    saveRun(run, { immediate: true })
    emitPipeline('pipeline.human_resolved', { run_id: runId, node: nodeKey, action_id: actionId })
    const target = resolveOnDone(wf, nodeKey)
    await transition(runId, target, node?.onDoneEffect)
    await awaitAdvanceIdle(runId)
    return
  }

  if (actionId === 'skip') {
    patchStage(run, nodeKey, { status: 'skipped' })
    run.status = 'running'
    saveRun(run)
    emitPipeline('pipeline.human_resolved', { run_id: runId, node: nodeKey, action_id: actionId })
    const wf = workflowFor(run)
    const target = resolveOnDone(wf, nodeKey)
    await transition(runId, target)
    await awaitAdvanceIdle(runId)
    return
  }

  if (actionId === 'go_gerrit') {
    patchStage(run, nodeKey, {
      status: 'skipped',
      finished_at: new Date().toISOString(),
      progress: {
        ...(run.stages[nodeKey]?.progress as Record<string, unknown> | undefined),
        state: 'skipped_to_gerrit',
        text: '跳过后续节点，前往 Gerrit',
      },
      human: undefined,
    })
    const skipMap: Record<string, string[]> = {
      build: ['flash', 'selfcheck', 'triage', 'human_review'],
      flash: ['selfcheck', 'triage', 'human_review'],
    }
    for (const mid of skipMap[nodeKey] ?? ['selfcheck', 'triage', 'human_review']) {
      const st = run.stages[mid]
      if (!st || st.status === 'done' || st.status === 'skipped') continue
      patchStage(run, mid, {
        status: 'skipped',
        progress: { text: '因跳转 Gerrit 跳过' },
      })
    }
    run.status = 'running'
    saveRun(run, { immediate: true })
    emitPipeline('pipeline.human_resolved', { run_id: runId, node: nodeKey, action_id: actionId })
    await transition(runId, 'gerrit')
    await awaitAdvanceIdle(runId)
    return
  }

  if (actionId === 'retry') {
    await resumeFrom(runId, { node: nodeKey, scope: 'continue' })
    return
  }

  const stage = getStage(nodeKey)
  if (stage?.handleHumanAction) {
    const wf = workflowFor(run)
    const node = wf.nodes.find(n => n.key === nodeKey)!
    const ctx = createCtx(run, node)
    await stage.handleHumanAction(ctx, actionId, payload)
    emitPipeline('pipeline.human_resolved', { run_id: runId, node: nodeKey, action_id: actionId })

    // 人工动作可能已启动异步任务或写入新 progress；须解除 waiting_human 闸门才能 re-evaluate
    const latest = getRun(runId)
    if (latest) {
      registerCorrelations(runId, nodeKey, latest.stages[nodeKey]?.refs ?? {})
      if (latest.stages[nodeKey]?.status === 'waiting_human') {
        patchStage(latest, nodeKey, { status: 'running', human: undefined })
        if (latest.status === 'waiting_human') latest.status = 'running'
        saveRun(latest, { immediate: true })
      }
    }
    await advance(runId)
    await awaitAdvanceIdle(runId)
  }
}

export async function resumeFrom(runId: string, req: ResumeRequest): Promise<void> {
  const run = getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)

  const wf = workflowFor(run)
  const node = wf.nodes.find(n => n.key === req.node && n.enabled)
  if (!node) throw new Error(`节点不可用: ${req.node}`)

  const { points } = computeResumePoints(run)
  const point = points.find(p => p.node === req.node)
  if (point?.safety === 'unsafe' && !req.force) {
    const err = new Error('恢复点不安全，需 force 确认') as Error & { missing?: ResumePoint['missing'] }
    err.missing = point.missing
    throw err
  }

  const fromNode = run.current_node
  let sourceChanged = false

  if (fromNode) {
    sourceChanged = await detectSourceChangedAsync(run)
    if (sourceChanged) {
      // 标记 source 刷新并由产物图失效下游（编译产物等）
      const gateNode = wf.nodes.find(n => n.key === fromNode) ?? {
        key: fromNode,
        enabled: true,
      }
      refreshArtifacts(run, gateNode, ['source'])
    }
  }

  if (sourceChanged) {
    const next = run.iteration + 1
    if (next > run.max_iterations) {
      run.status = 'waiting_human'
      const gateKey = fromNode ?? req.node
      const prev = (run.stages[gateKey]?.progress as Record<string, unknown> | undefined) ?? {}
      patchStage(run, gateKey, {
        status: 'waiting_human',
        progress: {
          ...prev,
          pending_resume_node: req.node,
          pending_resume_scope: req.scope ?? 'continue',
          pending_resume_force: Boolean(req.force),
        },
        human: {
          reason: 'max_iterations_exceeded',
          message: `已达最大迭代次数 ${run.max_iterations}`,
          actions: [
            { id: 'extend', label: '继续加一轮' },
            { id: 'abort', label: '终止', danger: true },
          ],
        },
      })
      saveRun(run, { immediate: true })
      return
    }
    run.iteration = next
    run.iterations.push({
      index: next,
      started_at: new Date().toISOString(),
      verdict: 'running',
      resumed_from: req.node,
      note: req.force ? 'force resume' : undefined,
    })
    emitPipeline('pipeline.iteration_started', {
      run_id: runId,
      iteration: next,
      trigger: 'resume',
    })
  } else if (req.force && point?.safety === 'unsafe') {
    const last = run.iterations[run.iterations.length - 1]
    if (last) last.note = [last.note, 'force resume from unsafe'].filter(Boolean).join('; ')
  }

  const scope = req.scope ?? 'continue'
  applyResumeScope(run, wf, req.node, scope)
  resetStagesFrom(run, wf, req.node)
  run.status = 'running'
  saveRun(run, { immediate: true })

  emitPipeline('pipeline.resumed', {
    run_id: runId,
    from_node: fromNode,
    resume_node: req.node,
    scope,
    forced: Boolean(req.force),
    source_changed: sourceChanged,
    iteration: run.iteration,
  })

  await enter(runId, req.node)
  await awaitAdvanceIdle(runId)
}

export async function pauseRun(runId: string): Promise<void> {
  const run = getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)
  run.status = 'paused'
  saveRun(run, { immediate: true })
}

export async function abortRun(runId: string, reason?: string): Promise<void> {
  const run = getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)

  const wf = workflowFor(run)
  // 先取消各阶段外部任务（编译 Agent / 适配 / 刷机等）
  for (const node of wf.nodes) {
    const state = run.stages[node.key]
    if (!state) continue
    if (state.status !== 'running' && state.status !== 'waiting_human' && state.status !== 'pending') {
      continue
    }
    const stage = getStage(node.key)
    if (!stage?.cancel) continue
    try {
      await stage.cancel(createCtx(run, node))
    } catch (err) {
      appendPipelineLog(runId, node.key, `终止时取消阶段失败: ${(err as Error).message}`)
    }
  }

  // 兜底：取消仍标记 running 的适配域任务
  for (const d of run.domains) {
    if (d.adapt_task_id && (d.status === 'running' || d.status === 'pending')) {
      try {
        await cancelAdaptAgentRun(d.adapt_task_id)
      } catch { /* ignore */ }
    }
  }

  run.abort_reason = reason
  run.status = 'aborted'
  await enter(runId, 'ABORT')
}

function handleObservedEvent(ev: ObservedEvent): void {
  const taskId = ev.correlation.taskId
  const deviceId = ev.correlation.deviceId
  const key = taskId ?? deviceId
  if (!key) return

  const ref = correlationIndex.get(key)
  if (!ref) return

  const run = getRun(ref.runId)
  if (!run || run.status !== 'running') return

  const stage = getStage(ref.nodeKey)
  if (!stage) return

  const wf = workflowFor(run)
  const node = wf.nodes.find(n => n.key === ref.nodeKey)
  if (!node) return

  const ctx = createCtx(run, node)
  void (async () => {
    if (stage.observe) {
      await stage.observe(ctx, ev)
      registerCorrelations(ref.runId, ref.nodeKey, getRun(ref.runId)?.stages[ref.nodeKey]?.refs ?? {})
    }
    // 即便无 observe（或 observe 已写完终态），也需 advance 驱动转移；
    // 否则自检等异步节点会停在 running。
    await advance(ref.runId)
  })()
}

function detectLostExternalTask(run: PipelineRun, nodeKey: string): boolean {
  if (nodeKey !== 'adapt') return false
  return run.domains.some(d =>
    d.enabled
    && d.status === 'running'
    && Boolean(d.adapt_task_id)
    && !getAdaptAgentTask(d.adapt_task_id!),
  )
}

function markLostAfterRestart(runId: string, nodeKey: string): void {
  const run = getRun(runId)
  if (!run) return
  const actions = [
    { id: 'retry', label: '重试' },
    { id: 'confirm_done', label: '已手工完成，继续' },
    { id: 'abort', label: '终止', danger: true },
  ]
  patchStage(run, nodeKey, {
    status: 'waiting_human',
    human: {
      reason: 'lost_after_restart',
      message: '服务重启后外部任务已丢失，请确认状态后选择重试或手工完成。',
      actions,
    },
  })
  run.status = 'waiting_human'
  saveRun(run, { immediate: true })
  emitPipeline('pipeline.waiting_human', {
    run_id: runId,
    node: nodeKey,
    reason: 'lost_after_restart',
    message: '服务重启后外部任务已丢失，请确认状态后选择重试或手工完成。',
    actions,
  })
}

export async function recover(): Promise<void> {
  rebuildArtifactGraph()
  startSources()
  setPipelineEventHandler(handleObservedEvent)
  correlationIndex.clear()

  for (const runId of listActiveRunIds()) {
    const run = getRun(runId)
    if (!run) continue

    for (const [nodeKey, state] of Object.entries(run.stages)) {
      if (state.status === 'running' || state.status === 'waiting_human') {
        registerCorrelations(runId, nodeKey, state.refs ?? {})
      }
    }

    if (run.status === 'running' && run.current_node) {
      const nodeKey = run.current_node
      if (detectLostExternalTask(run, nodeKey)) {
        markLostAfterRestart(runId, nodeKey)
        continue
      }

      const stage = getStage(nodeKey)
      if (stage) {
        const wf = workflowFor(run)
        const node = wf.nodes.find(n => n.key === nodeKey)
        if (node) {
          const ctx = createCtx(run, node)
          const verdict = stage.evaluate(ctx)
          if (verdict.status === 'waiting_human') {
            run.status = 'waiting_human'
            patchStage(run, node.key, {
              status: 'waiting_human',
              human: {
                reason: verdict.reason,
                message: verdict.message,
                actions: verdict.actions,
              },
            })
            saveRun(run, { immediate: true })
          } else {
            await advance(runId)
          }
        }
      }
    }
  }
}

/** 仅测试 */
export function resetOrchestratorForTest(): void {
  advanceChains.clear()
  correlationIndex.clear()
  artifactDownstream.clear()
  advancingRuns.clear()
  sourceChangedCheckerForTest = null
}
