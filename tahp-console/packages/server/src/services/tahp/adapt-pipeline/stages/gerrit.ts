import { registerStageForTest } from '../registry'
import type { GerritChangeRef, PipelineDomain, StageContext, StageDefinition, StageVerdict } from '../types'
import {
  buildConflictChanges,
  detectDomainFileConflicts,
  probeGerritSubmit,
  startGerritDomainSubmit,
} from '../../gerrit-submit'
import {
  filterFilesBySelectedRepos,
  groupChangedFilesByRepo,
  resolveRepoForFile,
} from '../repo-groups'
import { basename, normalize } from 'path'
import { domainsWithChangedFiles } from '../workspace-changed-files'

function repoLabelForDomain(
  domainId: string,
  files: string[],
  repoGroups: ReturnType<typeof groupChangedFilesByRepo>,
  fallback: string,
): string {
  for (const g of repoGroups) {
    if (g.domain_ids.includes(domainId)) {
      return g.repo_label || basename(normalize(g.repo))
    }
  }
  const first = files[0]
  if (first) {
    const root = resolveRepoForFile(first)
    return basename(normalize(root))
  }
  return fallback
}

function domainsWithChanges(ctx: StageContext): PipelineDomain[] {
  return domainsWithChangedFiles(ctx.run.domains)
}

function applyRepoFilter(ctx: StageContext, domains: PipelineDomain[]): PipelineDomain[] {
  const selected = ctx.run.gerrit_selected_repos
  if (!selected?.length) return domains
  return domains
    .map(d => ({
      ...d,
      changed_files: filterFilesBySelectedRepos(d.changed_files ?? [], selected),
    }))
    .filter(d => (d.changed_files?.length ?? 0) > 0)
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
  if (!buildContext) {
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
    const domainsRaw = domainsWithChanges(ctx)

    if (!domainsRaw.length) {
      syncProgress(ctx, {
        state: 'awaiting_confirm_no_changes',
        changes: [],
        repos: [],
        text: '未检测到待提交变更（changed_files 无绝对路径）',
      })
      ctx.log('未检测到待提交变更，等待人工确认')
      return
    }

    // 写回过滤后的绝对路径，供选仓与提交使用
    const filteredById = new Map(domainsRaw.map(d => [d.domain_id, d.changed_files ?? []]))
    ctx.patchRun({
      domains: ctx.run.domains.map(d => {
        const files = filteredById.get(d.domain_id)
        return files ? { ...d, changed_files: files } : d
      }),
    })

    const repos = groupChangedFilesByRepo(domainsRaw)

    if (!ctx.run.gerrit_selected_repos?.length) {
      syncProgress(ctx, {
        state: 'awaiting_repo_selection',
        repos,
        text: `请选择要入库的仓库（共 ${repos.length} 个）`,
      })
      ctx.log(`等待人工选择入库仓库（${repos.length} 个）`)
      return
    }

    const domains = applyRepoFilter(ctx, domainsRaw)
    if (!domains.length) {
      syncProgress(ctx, {
        state: 'awaiting_confirm_no_changes',
        changes: [],
        repos,
        message: '所选仓库无变更',
        text: '所选仓库无变更',
      })
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
    const repoGroupsForSubmit = groupChangedFilesByRepo(domains)
    const initialChanges: GerritChangeRef[] = domains.map(d => ({
      domain_id: d.domain_id,
      repo: repoLabelForDomain(d.domain_id, d.changed_files ?? [], repoGroupsForSubmit, d.workspace_id),
      status: 'pending',
      files: d.changed_files ?? [],
    }))
    ctx.patchRun({ gerrit_changes: initialChanges })
    // 临时域文件列表到 run.domains 供后续 submit 使用
    const patchedDomains = ctx.run.domains.map(d => {
      const f = domains.find(x => x.domain_id === d.domain_id)
      return f ? { ...d, changed_files: f.changed_files } : d
    })
    ctx.patchRun({ domains: patchedDomains, gerrit_changes: initialChanges })
    syncProgress(ctx, {
      state: 'submitting',
      queue,
      current_index: 0,
      changes: initialChanges,
      text: `开始提交 ${domains.length} 个域`,
    })

    await startNextDomainSubmit(ctx)
  },

  async observe(ctx: StageContext, ev) {
    if (ev.source !== 'task-stream') return
    const taskId = ctx.state.refs?.gerrit_task_id as string | undefined
    if (!taskId || ev.correlation.taskId !== taskId) return

    const p = (ctx.state.progress ?? {}) as Record<string, unknown>
    const domainId = String(ev.payload.domain_id ?? p.current_domain_id ?? '')

    if (ev.type === 'task.started') {
      ctx.log(`Gerrit Agent 已启动（${taskId}）`)
      return
    }

    if (ev.type === 'task.message') {
      if (ev.payload.level === 'stream') {
        const text = String(ev.payload.text ?? '').trim()
        if (text) ctx.log(text.slice(0, 500))
      } else {
        const text = String(ev.payload.text ?? ev.payload.message ?? '').trim()
        if (text) ctx.log(text.slice(0, 500))
      }
      return
    }

    if (ev.type === 'task.tool_completed' || ev.type === 'task.tool_started') {
      const tool = String(ev.payload.tool ?? ev.payload.tool_name ?? '').trim()
      if (tool) ctx.log(`[tool] ${tool}`)
      return
    }

    if (ev.type === 'task.completed') {
      const alreadySubmitted = ev.payload.already_submitted === true
      const changes = [...(ctx.run.gerrit_changes ?? [])]
      const changeIdx = changes.findIndex(c => c.domain_id === domainId)
      if (changeIdx >= 0) {
        changes[changeIdx] = {
          ...changes[changeIdx],
          status: 'submitted',
          change_url: ev.payload.change_url as string | undefined,
          change_number: ev.payload.change_number as string | undefined,
          note: alreadySubmitted ? '无新变更，沿用既有 CR' : undefined,
        }
      }
      ctx.patchRun({ gerrit_changes: changes })

      const nextIndex = Number(p.current_index ?? 0) + 1
      const queue = (p.queue as string[]) ?? []
      syncProgress(ctx, { current_index: nextIndex, changes })
      ctx.log(
        alreadySubmitted
          ? `域 ${domainId || '未知'} 无新变更，沿用既有 CR`
          : `域 ${domainId || '未知'} Gerrit 提交完成`,
      )

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

    if (state === 'awaiting_repo_selection') {
      return {
        status: 'waiting_human',
        reason: 'select_repos',
        message: '请勾选要提交到 Gerrit 的仓库（支持部分入库），然后继续。',
        actions: [
          { id: 'submit_all_repos', label: '全部仓库入库' },
          {
            id: 'submit_selected_repos',
            label: '提交所选仓库',
            fields: [
              {
                name: 'selected_repos',
                label: '仓库列表（JSON 数组或逗号分隔路径）',
                required: true,
              },
            ],
          },
          { id: 'skip', label: '跳过提交', danger: true },
        ],
      }
    }

    if (state === 'awaiting_confirm_no_changes') {
      return {
        status: 'waiting_human',
        reason: 'no_changes',
        message: '未检测到待提交变更（changed_files 无绝对路径，或所选仓库无文件）。可确认跳过提交，或返回重新检查适配记录。',
        actions: [
          { id: 'confirm_done', label: '确认无变更并完成' },
          { id: 'skip', label: '跳过提交' },
          { id: 'retry', label: '重新统计选仓' },
        ],
      }
    }

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

  async handleHumanAction(ctx: StageContext, actionId: string, payload?: Record<string, unknown>) {
    const domainsRaw = domainsWithChanges(ctx)
    const repos = groupChangedFilesByRepo(domainsRaw)

    if (actionId === 'skip') {
      syncProgress(ctx, { state: 'no_changes', changes: ctx.run.gerrit_changes ?? [], repos: [] })
      return
    }

    if (actionId === 'retry') {
      ctx.patchRun({ gerrit_selected_repos: undefined })
      await gerritStageDefinition.start!(ctx)
      return
    }

    if (actionId === 'submit_all_repos') {
      if (!repos.length) {
        syncProgress(ctx, {
          state: 'awaiting_confirm_no_changes',
          repos: [],
          text: '无可选仓库',
        })
        return
      }
      ctx.patchRun({ gerrit_selected_repos: repos.map(r => r.repo) })
      await gerritStageDefinition.start!(ctx)
      return
    }

    if (actionId === 'submit_selected_repos') {
      let selected: string[] = []
      const raw = payload?.selected_repos
      if (Array.isArray(raw)) selected = raw.map(String)
      else if (typeof raw === 'string') {
        const t = raw.trim()
        if (t.startsWith('[')) {
          try { selected = (JSON.parse(t) as unknown[]).map(String) } catch {
            selected = t.split(/[,;\n]/).map(s => s.trim()).filter(Boolean)
          }
        } else {
          selected = t.split(/[,;\n]/).map(s => s.trim()).filter(Boolean)
        }
      }
      if (!selected.length) {
        syncProgress(ctx, { state: 'awaiting_repo_selection', repos, message: '未选择仓库' })
        return
      }
      ctx.patchRun({ gerrit_selected_repos: selected })
      await gerritStageDefinition.start!(ctx)
    }
  },
}

export function installGerritStage(): void {
  registerStageForTest(gerritStageDefinition)
}

installGerritStage()
