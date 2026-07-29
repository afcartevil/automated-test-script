import { registerStageForTest } from '../registry'
import type { GerritChangeRef, PipelineDomain, StageContext, StageDefinition, StageVerdict } from '../types'
import {
  buildConflictChanges,
  detectDomainFileConflicts,
  probeGerritSubmit,
  startGerritDomainSubmit,
} from '../../gerrit-submit'

function domainsWithChanges(ctx: StageContext): PipelineDomain[] {
  return ctx.run.domains.filter(
    d => d.enabled && d.status === 'done' && (d.changed_files?.length ?? 0) > 0,
  )
}

function summarizeChanges(changes: GerritChangeRef[]): string {
  const submitted = changes.filter(c => c.status === 'submitted').length
  const blocked = changes.filter(c => c.status === 'blocked_conflict').length
  const failed = changes.filter(c => c.status === 'failed').length
  if (blocked) return `${blocked} 个域存在文件冲突`
  if (failed) return `${failed} 个域提交失败`
  if (!changes.length) return '无待提交变更'
  return `${submitted}/${changes.length} 域已提交`
}

function syncProgress(ctx: StageContext, patch: Record<string, unknown>): void {
  const prev = (ctx.state.progress ?? {}) as Record<string, unknown>
  const changes = (patch.changes ?? ctx.run.gerrit_changes ?? prev.changes) as GerritChangeRef[] | undefined
  ctx.patchState({
    progress: {
      ...prev,
      ...patch,
      changes,
      text: summarizeChanges(changes ?? []),
    },
  })
}

async function launchDomainSubmit(ctx: StageContext, domain: PipelineDomain): Promise<boolean> {
  const buildContext = ctx.run.build_context
  if (!buildContext?.mapped_root) {
    ctx.patchState({ progress: { state: 'error', error: '缺少 build_context，无法提交 Gerrit' } })
    ctx.log('缺少 build_context')
    return false
  }

  const result = startGerritDomainSubmit({
    runId: ctx.run.run_id,
    projectCode: ctx.run.project_code,
    domain,
    buildContext,
  })

  if (!result.ok) {
    const changes = [...(ctx.run.gerrit_changes ?? [])]
    const idx = changes.findIndex(c => c.domain_id === domain.domain_id)
    if (idx >= 0) {
      changes[idx] = { ...changes[idx], status: 'failed', error: result.error }
    }
    ctx.patchRun({ gerrit_changes: changes })
    syncProgress(ctx, { state: 'submit_failed', changes })
    ctx.log(`域 ${domain.domain_id} 提交启动失败: ${result.error}`)
    return false
  }

  ctx.patchState({
    refs: { ...ctx.state.refs, gerrit_task_id: result.taskId },
    progress: {
      ...(ctx.state.progress as Record<string, unknown>),
      state: 'submitting',
      current_domain_id: domain.domain_id,
    },
  })
  ctx.log(`开始提交域 ${domain.domain_label}: taskId=${result.taskId}`)
  return true
}

async function startNextDomainSubmit(ctx: StageContext): Promise<void> {
  const p = (ctx.state.progress ?? {}) as Record<string, unknown>
  const queue = (p.queue as string[]) ?? []
  const idx = Number(p.current_index ?? 0)
  if (idx >= queue.length) return

  const domain = ctx.run.domains.find(d => d.domain_id === queue[idx])
  if (!domain) {
    syncProgress(ctx, { current_index: idx + 1 })
    await startNextDomainSubmit(ctx)
    return
  }

  await launchDomainSubmit(ctx, domain)
}

export const gerritStageDefinition: StageDefinition = {
  key: 'gerrit',
  label: '提交 Gerrit',
  consumes: ['source', 'testresult'],

  async probe() {
    return probeGerritSubmit()
  },

  async start(ctx: StageContext) {
    const domains = domainsWithChanges(ctx)

    if (!domains.length) {
      syncProgress(ctx, { state: 'no_changes', changes: [] })
      ctx.log('无待提交变更文件')
      return
    }

    const conflicts = detectDomainFileConflicts(domains)
    if (conflicts.length) {
      const changes = buildConflictChanges(ctx.run.domains, conflicts)
      ctx.patchRun({ gerrit_changes: changes })
      syncProgress(ctx, { state: 'blocked_conflict', conflicts, changes })
      ctx.log(`检测到 ${conflicts.length} 个跨域文件冲突，禁止自动提交`)
      return
    }

    const queue = domains.map(d => d.domain_id)
    const initialChanges: GerritChangeRef[] = domains.map(d => ({
      domain_id: d.domain_id,
      repo: d.workspace_id,
      status: 'pending',
      files: d.changed_files ?? [],
    }))
    ctx.patchRun({ gerrit_changes: initialChanges })
    syncProgress(ctx, {
      state: 'submitting',
      queue,
      current_index: 0,
      changes: initialChanges,
    })

    await startNextDomainSubmit(ctx)
  },

  async observe(ctx: StageContext, ev) {
    if (ev.source !== 'task-stream') return
    const taskId = ctx.state.refs?.gerrit_task_id as string | undefined
    if (!taskId || ev.correlation.taskId !== taskId) return

    const p = (ctx.state.progress ?? {}) as Record<string, unknown>
    const domainId = String(ev.payload.domain_id ?? p.current_domain_id ?? '')

    if (ev.type === 'task.completed') {
      const changes = [...(ctx.run.gerrit_changes ?? [])]
      const changeIdx = changes.findIndex(c => c.domain_id === domainId)
      if (changeIdx >= 0) {
        changes[changeIdx] = {
          ...changes[changeIdx],
          status: 'submitted',
          change_url: ev.payload.change_url as string | undefined,
          change_number: ev.payload.change_number as string | undefined,
        }
      }
      ctx.patchRun({ gerrit_changes: changes })

      const nextIndex = Number(p.current_index ?? 0) + 1
      const queue = (p.queue as string[]) ?? []
      syncProgress(ctx, { current_index: nextIndex, changes })

      if (nextIndex < queue.length) {
        await startNextDomainSubmit(ctx)
      } else {
        syncProgress(ctx, { state: 'done' })
        ctx.log('全部域 Gerrit 提交完成')
      }
      return
    }

    if (ev.type === 'task.failed') {
      const changes = [...(ctx.run.gerrit_changes ?? [])]
      const changeIdx = changes.findIndex(c => c.domain_id === domainId)
      const err = String(ev.payload.error ?? ev.payload.message ?? '提交失败')
      if (changeIdx >= 0) {
        changes[changeIdx] = { ...changes[changeIdx], status: 'failed', error: err }
      }
      ctx.patchRun({ gerrit_changes: changes })
      syncProgress(ctx, { state: 'submit_failed', changes, error: err })
      ctx.log(`域 ${domainId} 提交失败: ${err}`)
    }
  },

  evaluate(ctx: StageContext): StageVerdict {
    const p = (ctx.state.progress ?? {}) as Record<string, unknown>
    const state = p.state as string | undefined
    const changes = ctx.run.gerrit_changes ?? []
    const queue = (p.queue as string[]) ?? []
    const idx = Number(p.current_index ?? 0)

    if (state === 'blocked_conflict') {
      return {
        status: 'waiting_human',
        reason: 'blocked_conflict',
        message: '检测到跨域文件冲突，无法自动提交 Gerrit。请人工协调后重试或跳过。',
        actions: [
          { id: 'retry', label: '冲突已解决，重试提交' },
          { id: 'skip', label: '跳过 Gerrit 提交' },
        ],
      }
    }

    if (state === 'no_changes') {
      return { status: 'done', summary: { text: '无待提交变更', submitted: 0 } }
    }

    if (state === 'submit_failed' || changes.some(c => c.status === 'failed')) {
      return {
        status: 'failed',
        error: String(p.error ?? '部分域 Gerrit 提交失败'),
        retryable: true,
      }
    }

    if (state === 'done' || (queue.length > 0 && idx >= queue.length && changes.every(c => c.status === 'submitted'))) {
      return {
        status: 'done',
        summary: {
          submitted: changes.filter(c => c.status === 'submitted').length,
          total: changes.length,
          changes,
        },
      }
    }

    return {
      status: 'running',
      progress: {
        ...p,
        percent: queue.length ? Math.min(99, Math.round((idx / queue.length) * 100)) : undefined,
        text: summarizeChanges(changes),
        changes,
      },
    }
  },
}

export function installGerritStage(): void {
  registerStageForTest(gerritStageDefinition)
}

installGerritStage()
