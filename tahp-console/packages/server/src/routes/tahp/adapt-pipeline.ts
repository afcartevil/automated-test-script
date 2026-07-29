/**
 * TAHP AI 适配流水线 REST 路由
 */
import Router from '@koa/router'
import { centralClient } from '../../services/tahp/sync/central-client'
import { isCentralConfigured } from '../../services/tahp/runtime-mode'
import { readPipelineLogs } from '../../services/tahp/adapt-pipeline/events'
import {
  abortRun,
  computeResumePoints,
  pauseRun,
  recover,
  resumeFrom,
  startRun,
  submitHumanAction,
} from '../../services/tahp/adapt-pipeline/orchestrator'
import { getStage, listStages } from '../../services/tahp/adapt-pipeline/registry'
import '../../services/tahp/adapt-pipeline/stages'
import {
  buildRunPreview,
  createRun,
  deleteDraftRun,
  findResourceConflict,
  getRun,
  listRuns,
} from '../../services/tahp/adapt-pipeline/store'
import { buildTimelineView } from '../../services/tahp/adapt-pipeline/timeline'
import type {
  CreateRunInput,
  PipelineRun,
  ResumeRequest,
  RunStatus,
  WorkflowDefinition,
} from '../../services/tahp/adapt-pipeline/types'
import {
  loadWorkflow,
  saveWorkflow,
} from '../../services/tahp/adapt-pipeline/workflow'
import { logger } from '../../services/logger'

export const tahpAdaptPipelineRoutes = new Router({ prefix: '/api/tahp/adapt-pipeline' })

function probeContextRun(): Readonly<PipelineRun> {
  const now = new Date().toISOString()
  return {
    run_id: '__probe__',
    workflow_id: 'adapt-default',
    workflow_version: 1,
    project_code: '',
    status: 'draft',
    current_node: null,
    iteration: 1,
    max_iterations: 3,
    created_at: now,
    updated_at: now,
    domains: [],
    build_context: {
      mapped_root: '',
      workspace: '',
      components: [],
      variant: 'userdebug',
    },
    stages: {},
    iterations: [],
    artifacts: {},
  }
}

function parseStatusFilter(raw: string | undefined): RunStatus[] | undefined {
  if (!raw?.trim()) return undefined
  return raw.split(',').map(s => s.trim()).filter(Boolean) as RunStatus[]
}

function parseLimit(raw: string | undefined): number | undefined {
  if (!raw) return undefined
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : undefined
}

function parseOffset(raw: string | undefined): number | undefined {
  if (!raw) return undefined
  const n = Number(raw)
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : undefined
}

tahpAdaptPipelineRoutes.post('/runs', async (ctx) => {
  try {
    const body = (ctx.request.body ?? {}) as CreateRunInput
    if (!body.project_code?.trim()) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 project_code' }
      return
    }
    if (!body.build_context?.workspace?.trim() || !body.build_context?.mapped_root?.trim()) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少 build_context.mapped_root / workspace' }
      return
    }
    const preview = buildRunPreview(body)
    const conflict = findResourceConflict(preview)
    if (conflict) {
      ctx.status = 409
      ctx.body = {
        success: false,
        error: conflict.detail,
        data: { conflict },
      }
      return
    }
    const run = createRun(body)
    const workflow = loadWorkflow()
    ctx.body = {
      success: true,
      data: {
        run_id: run.run_id,
        domains: run.domains,
        workflow,
      },
    }
  } catch (err) {
    logger.warn({ err }, '[adapt-pipeline] create run failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.get('/runs', async (ctx) => {
  try {
    const status = parseStatusFilter(String(ctx.query.status ?? ''))
    const limit = parseLimit(String(ctx.query.limit ?? ''))
    const offset = parseOffset(String(ctx.query.offset ?? ''))
    const data = listRuns({ status, limit, offset })
    ctx.body = { success: true, data }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.get('/runs/:runId', async (ctx) => {
  const run = getRun(ctx.params.runId)
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  ctx.body = { success: true, data: run }
})

tahpAdaptPipelineRoutes.delete('/runs/:runId', async (ctx) => {
  const runId = ctx.params.runId
  if (!getRun(runId)) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  if (!deleteDraftRun(runId)) {
    ctx.status = 400
    ctx.body = { success: false, error: '仅可删除草稿状态的运行' }
    return
  }
  ctx.body = { success: true, data: { ok: true } }
})

tahpAdaptPipelineRoutes.get('/runs/:runId/timeline', async (ctx) => {
  const run = getRun(ctx.params.runId)
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  ctx.body = { success: true, data: buildTimelineView(run) }
})

tahpAdaptPipelineRoutes.post('/runs/:runId/start', async (ctx) => {
  const runId = ctx.params.runId
  const run = getRun(runId)
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  const conflict = findResourceConflict(run)
  if (conflict) {
    ctx.status = 409
    ctx.body = {
      success: false,
      error: conflict.detail,
      data: { conflict },
    }
    return
  }
  try {
    await startRun(runId)
    ctx.body = { success: true, data: { ok: true } }
  } catch (err) {
    logger.warn({ err, runId }, '[adapt-pipeline] start run failed')
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.post('/runs/:runId/human-action', async (ctx) => {
  const runId = ctx.params.runId
  const body = (ctx.request.body ?? {}) as {
    node?: string
    action_id?: string
    payload?: Record<string, unknown>
  }
  const node = String(body.node ?? '').trim()
  const actionId = String(body.action_id ?? '').trim()
  if (!node || !actionId) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 node / action_id' }
    return
  }
  if (!getRun(runId)) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  try {
    await submitHumanAction(runId, node, actionId, body.payload)
    ctx.body = { success: true, data: { ok: true } }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.get('/runs/:runId/resume-points', async (ctx) => {
  const run = getRun(ctx.params.runId)
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  ctx.body = { success: true, data: computeResumePoints(run) }
})

tahpAdaptPipelineRoutes.post('/runs/:runId/resume', async (ctx) => {
  const runId = ctx.params.runId
  const run = getRun(runId)
  if (!run) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  const req = (ctx.request.body ?? {}) as ResumeRequest
  if (!req.node?.trim()) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 node' }
    return
  }
  try {
    await resumeFrom(runId, req)
    const updated = getRun(runId)!
    ctx.body = { success: true, data: { ok: true, iteration: updated.iteration } }
  } catch (err) {
    const missing = (err as Error & { missing?: unknown }).missing
    if (missing) {
      ctx.status = 409
      ctx.body = {
        success: false,
        error: (err as Error).message,
        data: { missing },
      }
      return
    }
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.post('/runs/:runId/pause', async (ctx) => {
  const runId = ctx.params.runId
  if (!getRun(runId)) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  try {
    await pauseRun(runId)
    ctx.body = { success: true, data: { ok: true } }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.post('/runs/:runId/abort', async (ctx) => {
  const runId = ctx.params.runId
  if (!getRun(runId)) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  const body = (ctx.request.body ?? {}) as { reason?: string }
  try {
    await abortRun(runId, body.reason)
    ctx.body = { success: true, data: { ok: true } }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.get('/runs/:runId/logs/:node', async (ctx) => {
  const runId = ctx.params.runId
  if (!getRun(runId)) {
    ctx.status = 404
    ctx.body = { success: false, error: 'run 不存在' }
    return
  }
  const tail = parseLimit(String(ctx.query.tail ?? '500')) ?? 500
  const lines = readPipelineLogs(runId, ctx.params.node, tail)
  ctx.body = { success: true, data: { lines } }
})

tahpAdaptPipelineRoutes.get('/prereqs/:projectCode', async (ctx) => {
  if (!isCentralConfigured()) {
    ctx.status = 503
    ctx.body = { success: false, error: '未配置中心连接' }
    return
  }
  try {
    const projectCode = ctx.params.projectCode
    const campaignId = ctx.query.campaign_id
      ? String(ctx.query.campaign_id)
      : undefined
    const data = await centralClient.resolveAdaptPrereqs({
      project_code: projectCode,
      campaign_id: campaignId,
    })
    ctx.body = {
      success: true,
      data: {
        project_code: data.project_code,
        campaign_id: data.campaign_id,
        from_os: data.from_os,
        to_os: data.to_os,
        domains: data.domains,
      },
    }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpAdaptPipelineRoutes.get('/workflow', async (ctx) => {
  const workflow = loadWorkflow()
  const nodes = await Promise.all(
    workflow.nodes.filter(n => n.enabled).map(async node => {
      const stage = getStage(node.key)
      const availability = stage?.probe
        ? await stage.probe({ run: probeContextRun() })
        : { available: true as const }
      return {
        key: node.key,
        label: stage?.label ?? node.key,
        availability,
      }
    }),
  )
  ctx.body = { success: true, data: { workflow, nodes } }
})

tahpAdaptPipelineRoutes.put('/workflow', async (ctx) => {
  const workflow = (ctx.request.body ?? {}) as WorkflowDefinition
  const result = saveWorkflow(workflow)
  if (!result.ok) {
    ctx.status = 400
    ctx.body = { success: false, error: 'workflow 校验失败', data: { errors: result.errors } }
    return
  }
  ctx.body = { success: true, data: { workflow } }
})

tahpAdaptPipelineRoutes.get('/capabilities', async (ctx) => {
  const items = await Promise.all(
    listStages().map(async stage => ({
      key: stage.key,
      label: stage.label,
      availability: stage.probe
        ? await stage.probe({ run: probeContextRun() })
        : { available: true as const },
    })),
  )
  ctx.body = { success: true, data: items }
})

/** 供 bootstrap 调用：注册阶段并恢复活跃 run */
export async function bootstrapAdaptPipeline(): Promise<void> {
  await recover()
}
