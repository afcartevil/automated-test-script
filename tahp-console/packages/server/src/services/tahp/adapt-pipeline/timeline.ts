import { getStage } from './registry'
import { canFailCurrentStage, resolveAdaptMaxRetries } from './types'
import type { PipelineDomain, PipelineRun, TimelineView, WorkflowDefinition } from './types'
import { effectiveWorkflowForRun, getEnabledNodes } from './workflow'

function serializeDomainForTimeline(domain: PipelineDomain, retryMax: number) {
  return {
    domain_id: domain.domain_id,
    domain_label: domain.domain_label,
    status: domain.status,
    changed_files: domain.changed_files,
    related_skills: domain.related_skills,
    error: domain.error,
    adapt_task_id: domain.adapt_task_id,
    retry_count: domain.retry_count ?? 0,
    retry_max: retryMax,
  }
}

function buildNodeProgress(
  nodeKey: string,
  run: PipelineRun,
  state: PipelineRun['stages'][string] | undefined,
): TimelineView['nodes'][number]['progress'] | undefined {
  const progress = (state?.progress ?? {}) as Record<string, unknown>

  const out: NonNullable<TimelineView['nodes'][number]['progress']> = {}
  const percent = progress.percent ?? progress.progress
  if (typeof percent === 'number') out.percent = percent
  if (typeof progress.text === 'string' && progress.text) out.text = progress.text
  else if (typeof progress.message === 'string' && progress.message) out.text = progress.message
  if (progress.changes) out.changes = progress.changes

  // 编译 / 烧录 / Gerrit：透传面板所需字段
  for (const key of [
    'state', 'phase', 'message', 'error', 'result',
    'pkg_path', 'pkgPath', 'artifacts_dir',
    'flash_mode', 'flash_skill_id',
    'repos', 'queue', 'current_index', 'current_domain_id',
    'current_repo', 'current_repo_label',
    'repo_groups', 'changed_files',
    'total', 'passed', 'failed', 'running', 'failed_cases',
  ] as const) {
    if (progress[key] !== undefined) (out as Record<string, unknown>)[key] = progress[key]
  }

  if (nodeKey === 'adapt') {
    const retryMax = resolveAdaptMaxRetries(run.adapt_max_retries)
    const domains = run.domains.filter(d => d.enabled).map(d => serializeDomainForTimeline(d, retryMax))
    if (domains.length) out.domains = domains
  }

  return Object.keys(out).length ? out : undefined
}

function collectLoopTargets(workflow: WorkflowDefinition): Set<string> {
  const targets = new Set<string>()
  for (const node of workflow.nodes) {
    if (!node.enabled) continue
    if (node.onDoneEffect !== 'increment_iteration') continue
    const target = node.onDone
    if (!target || target === 'END' || target === 'ABORT') continue
    targets.add(target)
  }
  return targets
}

function runStartedAt(run: PipelineRun): string {
  return run.iterations[0]?.started_at ?? run.created_at
}

function nodeDurationMs(state: { started_at?: string; finished_at?: string }): number | undefined {
  if (!state.started_at) return undefined
  const end = state.finished_at ? new Date(state.finished_at).getTime() : Date.now()
  return Math.max(0, end - new Date(state.started_at).getTime())
}

function formatSummaryLine(
  state: PipelineRun['stages'][string] | undefined,
): string | undefined {
  if (!state?.summary) return undefined
  if (typeof state.summary === 'string') return state.summary || undefined
  const s = state.summary
  if (typeof s.domain_count === 'number') {
    return `${s.domain_count} 个域`
  }
  if (typeof s.passed === 'number' || typeof s.failed === 'number') {
    return `${Number(s.passed) || 0} 通过 / ${Number(s.failed) || 0} 失败`
  }
  if (typeof s.total === 'number' && typeof s.done === 'number') {
    return `${s.done}/${s.total} 域完成`
  }
  if (typeof s.text === 'string') return s.text
  const progress = state.progress as { text?: string } | undefined
  return progress?.text
}

export function buildTimelineView(
  run: PipelineRun,
  workflow: WorkflowDefinition = effectiveWorkflowForRun(run),
): TimelineView {
  const loopTargets = collectLoopTargets(workflow)
  const startedAt = runStartedAt(run)
  const now = run.finished_at ? new Date(run.finished_at).getTime() : Date.now()
  const nodes = getEnabledNodes(workflow).map(node => {
    const stage = getStage(node.key)
    const state = run.stages[node.key]
    const human = state?.human
      ? {
          reason: state.human.reason,
          message: state.human.message,
          actions: state.human.actions ?? [],
        }
      : undefined

    return {
      key: node.key,
      label: stage?.label ?? node.key,
      status: state?.status ?? 'pending',
      enabled: true,
      duration_ms: state ? nodeDurationMs(state) : undefined,
      progress: buildNodeProgress(node.key, run, state),
      error: state?.error,
      summary_line: formatSummaryLine(state),
      unavailable_reason: state?.availability && !state.availability.available
        ? state.availability.reason
        : (human?.reason === 'capability_unavailable' ? human.message : undefined),
      human,
      is_loop_target: loopTargets.has(node.key),
    }
  })

  const pendingHumanCount = Object.values(run.stages)
    .filter(s => s.status === 'waiting_human').length

  return {
    run_id: run.run_id,
    project_code: run.project_code,
    status: run.status,
    iteration: run.iteration,
    max_iterations: run.max_iterations,
    adapt_max_retries: resolveAdaptMaxRetries(run.adapt_max_retries),
    current_node: run.current_node,
    started_at: startedAt,
    duration_ms: Math.max(0, now - new Date(startedAt).getTime()),
    build_context: run.build_context,
    device_id: run.device_id,
    from_os: run.from_os,
    to_os: run.to_os,
    nodes,
    iterations: run.iterations,
    pending_human_count: pendingHumanCount,
    can_fail_current_stage: canFailCurrentStage(run),
  }
}
