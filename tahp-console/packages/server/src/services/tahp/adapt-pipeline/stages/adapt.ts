import {
  cancelAdaptAgentRun,
  getAdaptAgentTask,
  startAdaptAgentRun,
} from '../../adapt-agent'
import { getAdaptDomainLayout } from '../../adapt-layout/service'
import { flattenPathParams } from '../path-params'
import { registerStageForTest } from '../registry'
import type { ObservedEvent, PipelineDomain, StageContext, StageDefinition } from '../types'
import { mergeAbsolutePaths } from '../workspace-changed-files'

function enabledDomains(run: import('../types').PipelineRun): PipelineDomain[] {
  return run.domains.filter(d => d.enabled)
}

function cloneDomains(run: import('../types').PipelineRun): PipelineDomain[] {
  return run.domains.map(d => ({ ...d }))
}

function patchDomains(ctx: StageContext, domains: PipelineDomain[]): void {
  ctx.patchRun({ domains })
}

function findNextPending(domains: PipelineDomain[]): PipelineDomain | undefined {
  return domains.find(d => d.enabled && d.status === 'pending')
}

function findRunning(domains: PipelineDomain[]): PipelineDomain | undefined {
  return domains.find(d => d.enabled && d.status === 'running')
}

function applyResumeScopeToDomains(ctx: StageContext, domains: PipelineDomain[]): PipelineDomain[] {
  const scope = String(
    ctx.node.params?.resume_scope
    ?? ctx.state.progress?.resume_scope
    ?? 'continue',
  )
  if (scope !== 'restart') return domains
  return domains.map(d => {
    if (!d.enabled) return d
    return {
      ...d,
      status: 'pending' as const,
      adapt_task_id: undefined,
      error: undefined,
      changed_files: undefined,
    }
  })
}

function appendChangedFiles(
  domain: PipelineDomain,
  paths: string[],
): number {
  const merged = mergeAbsolutePaths([...(domain.changed_files ?? []), ...paths])
  const before = domain.changed_files?.length ?? 0
  domain.changed_files = merged
  return merged.length - before
}

async function launchDomain(ctx: StageContext, domain: PipelineDomain): Promise<string | null> {
  domain.changed_files = domain.changed_files ?? []

  const layout = await getAdaptDomainLayout(domain.domain_id, domain.workspace_id)
  const pathFlat = flattenPathParams(ctx.run.path_params)
  const layoutFields = (layout?.fields ?? []).map(f => ({
    name: f.name,
    label: f.label,
    required: f.required,
  }))
  const layoutNames = new Set(layoutFields.map(f => f.name))
  const formFields = [
    ...pathFlat.formFields.filter(f => !layoutNames.has(f.name)),
    ...layoutFields,
  ]

  const formData: Record<string, string> = { ...pathFlat.formData }
  for (const [k, v] of Object.entries(domain.form_data)) {
    formData[k] = String(v ?? '')
  }

  const result = startAdaptAgentRun({
    domainId: domain.domain_id,
    domainLabel: domain.domain_label,
    module: domain.module,
    relatedSkills: domain.related_skills,
    formData,
    formFields,
    workspaceId: domain.workspace_id,
  })

  if (!result.ok) {
    domain.status = 'failed'
    domain.error = result.error
    return null
  }

  domain.status = 'running'
  domain.adapt_task_id = result.taskId
  return result.taskId
}

function logAdaptTaskEvent(ctx: StageContext, ev: ObservedEvent, running: PipelineDomain): void {
  const label = running.domain_label || running.domain_id
  const prefix = `[${label}]`

  switch (ev.type) {
    case 'task.started':
      ctx.log(`${prefix} 适配任务已启动`)
      break
    case 'task.phase': {
      const msg = String(ev.payload.message ?? '').trim()
      if (msg) ctx.log(`${prefix} ${msg}`)
      break
    }
    case 'task.step': {
      const msg = String(ev.payload.message ?? '').trim()
      if (msg) ctx.log(`${prefix} ${msg}`)
      break
    }
    case 'task.plan': {
      const msg = String(ev.payload.message ?? ev.payload.summary ?? '').trim()
      if (msg) ctx.log(`${prefix} ${msg}`)
      break
    }
    case 'task.message': {
      if (ev.payload.level === 'stream') break
      const text = String(ev.payload.text ?? '').trim()
      if (text) ctx.log(`${prefix} ${text}`)
      break
    }
    case 'task.skill_use': {
      const skill = String(ev.payload.skill_id ?? ev.payload.skill ?? '').trim()
      if (skill) ctx.log(`${prefix} 使用 Skill: ${skill}`)
      break
    }
    case 'task.tool_completed': {
      const tool = String(ev.payload.tool ?? ev.payload.tool_name ?? '').trim()
      if (tool) ctx.log(`${prefix} 工具完成: ${tool}`)
      break
    }
    case 'task.file_change': {
      const file = String(ev.payload.path ?? '').trim()
      if (file) ctx.log(`${prefix} 修改文件: ${file}`)
      break
    }
    case 'task.user_input_requested':
      ctx.log(`${prefix} 等待用户输入配置`)
      break
    case 'task.approval_requested':
      ctx.log(`${prefix} 等待审批`)
      break
    case 'task.completed':
      ctx.log(`${prefix} 适配完成`)
      break
    case 'task.failed': {
      const err = String(ev.payload.error ?? ev.payload.message ?? '适配失败')
      const firstLine = err.split('\n').find(line => line.trim()) ?? err
      ctx.log(`${prefix} 失败: ${firstLine}`)
      break
    }
    default:
      break
  }
}

function syncRefs(ctx: StageContext, domains: PipelineDomain[], currentDomainId?: string): void {
  const taskIds = domains.map(d => d.adapt_task_id).filter((id): id is string => Boolean(id))
  ctx.patchState({
    refs: {
      ...ctx.state.refs,
      adapt_task_ids: taskIds,
      current_domain_id: currentDomainId,
    },
    progress: {
      ...ctx.state.progress,
      current_domain_id: currentDomainId,
    },
  })
}

async function startNextPending(ctx: StageContext): Promise<void> {
  const domains = cloneDomains(ctx.run)
  const next = findNextPending(domains)
  if (!next) {
    patchDomains(ctx, domains)
    return
  }

  const taskId = await launchDomain(ctx, next)
  patchDomains(ctx, domains)
  syncRefs(ctx, domains, next.domain_id)

  if (!taskId) {
    ctx.log(`域 ${next.domain_id} 启动失败: ${next.error ?? '未知错误'}`)
    return
  }

  ctx.log(`启动域 ${next.domain_label || next.domain_id} (${taskId})`)
}

export const adaptStageDefinition: StageDefinition = {
  key: 'adapt',
  label: 'AI 适配',
  consumes: ['prereq'],
  produces: ['source'],
  async start(ctx: StageContext) {
    let domains = cloneDomains(ctx.run)
    domains = applyResumeScopeToDomains(ctx, domains)
    patchDomains(ctx, domains)

    const running = findRunning(domains)
    if (running?.adapt_task_id) {
      syncRefs(ctx, domains, running.domain_id)
      return
    }

    await startNextPending(ctx)
  },
  async observe(ctx: StageContext, ev: ObservedEvent) {
    if (ev.source !== 'task-stream') return

    const domains = cloneDomains(ctx.run)
    const running = findRunning(domains)
    if (!running?.adapt_task_id) return
    if (ev.correlation.taskId !== running.adapt_task_id) return

    logAdaptTaskEvent(ctx, ev, running)

    if (ev.type === 'task.file_change') {
      const path = String(ev.payload.path ?? '').trim()
      if (path) {
        const added = appendChangedFiles(running, [path])
        if (added > 0) {
          patchDomains(ctx, domains)
          ctx.patchState({
            progress: {
              ...ctx.state.progress,
              current_domain_id: running.domain_id,
              changed_files_count: running.changed_files?.length ?? 0,
            },
          })
        }
      }
      return
    }

    if (ev.type === 'task.user_input_requested' || ev.type === 'task.approval_requested') {
      ctx.patchState({
        progress: {
          ...ctx.state.progress,
          current_domain_id: running.domain_id,
          pending_interaction: {
            type: ev.type,
            domain_id: running.domain_id,
            task_id: running.adapt_task_id,
            payload: ev.payload,
          },
        },
      })
      return
    }

    if (ev.type === 'task.completed') {
      running.status = 'done'
      running.error = undefined

      const fromPayload = Array.isArray(ev.payload.files_modified)
        ? (ev.payload.files_modified as unknown[]).map(String)
        : []
      const fromTask = (getAdaptAgentTask(running.adapt_task_id)?.fileChanges ?? [])
        .map(c => c.path)
      appendChangedFiles(running, [...fromPayload, ...fromTask])
      ctx.log(
        `[${running.domain_label || running.domain_id}] 已记录变更文件 ${running.changed_files?.length ?? 0} 个`,
      )

      patchDomains(ctx, domains)
      ctx.patchState({
        progress: {
          ...ctx.state.progress,
          pending_interaction: undefined,
          changed_files_count: running.changed_files?.length ?? 0,
        },
      })
      await startNextPending(ctx)
      return
    }

    if (ev.type === 'task.failed') {
      running.status = 'failed'
      running.error = String(ev.payload.error ?? ev.payload.message ?? '适配失败')
      patchDomains(ctx, domains)
      ctx.patchState({
        progress: {
          ...ctx.state.progress,
          pending_interaction: undefined,
        },
      })
    }
  },
  evaluate(ctx: StageContext) {
    const pending = ctx.state.progress?.pending_interaction as Record<string, unknown> | undefined
    if (pending) {
      return {
        status: 'waiting_human' as const,
        reason: 'adapt_interaction',
        message: '适配 Agent 等待人工输入或审批，请前往「AI 适配调试」处理后再继续。',
        actions: [
          { id: 'confirm_done', label: '已在适配调试处理完成' },
          { id: 'retry', label: '重试当前域' },
        ],
      }
    }

    const domains = enabledDomains(ctx.run)
    const total = domains.length
    const done = domains.filter(d => d.status === 'done').length
    const skipped = domains.filter(d => d.status === 'skipped').length
    const failed = domains.find(d => d.status === 'failed')

    if (failed) {
      return {
        status: 'failed' as const,
        error: failed.error ?? `域 ${failed.domain_id} 适配失败`,
        retryable: false,
      }
    }

    if (total > 0 && done + skipped === total) {
      return {
        status: 'done' as const,
        summary: { total, done, skipped },
      }
    }

    const running = domains.find(d => d.status === 'running')
    return {
      status: 'running' as const,
      progress: {
        percent: total ? Math.round((done / total) * 100) : 0,
        text: total ? `${done}/${total} 域` : '0/0 域',
        current_domain_id: running?.domain_id,
      },
    }
  },
  async cancel(ctx: StageContext) {
    const domains = cloneDomains(ctx.run)
    for (const d of domains) {
      if (d.status === 'running' && d.adapt_task_id) {
        await cancelAdaptAgentRun(d.adapt_task_id)
        d.status = 'pending'
        d.adapt_task_id = undefined
      }
    }
    patchDomains(ctx, domains)
  },
}

export function installAdaptStage(): void {
  registerStageForTest(adaptStageDefinition)
}

installAdaptStage()
