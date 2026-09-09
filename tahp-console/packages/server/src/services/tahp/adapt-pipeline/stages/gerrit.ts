import { registerStageForTest } from '../registry'
import type { GerritChangeRef, PipelineDomain, StageContext, StageDefinition, StageVerdict } from '../types'
import {
  cancelGerritSubmitTask,
  isGerritSubmitStreamFatal,
  isGerritSubmitTimedOut,
  probeGerritSubmit,
  startGerritRepoSubmit,
} from '../../gerrit-submit'
import { discoverRemoteRunner } from '../harness-bridge-exec'
import { fillMappedWorkspaceIfMissing } from '../mapped-workspace'
import {
  filterRepoGroupsBySelection,
  groupChangedFilesByRepo,
  type RepoChangeGroup,
} from '../repo-groups'
import { domainsWithChangedFiles } from '../workspace-changed-files'

function domainsWithChanges(ctx: StageContext): PipelineDomain[] {
  return domainsWithChangedFiles(ctx.run.domains)
}

function changeMatchesRepo(change: GerritChangeRef, repo: string, label?: string): boolean {
  if (!repo) return false
  if (change.repo === repo) return true
  if (label && change.repo === label) return true
  return false
}

function summarizeChanges(changes: GerritChangeRef[]): string {
  const submitted = changes.filter(c => c.status === 'submitted').length
  const blocked = changes.filter(c => c.status === 'blocked_conflict').length
  const failed = changes.filter(c => c.status === 'failed').length
  if (blocked) return `${blocked} 个仓存在历史冲突标记（将按仓合提，可重试）`
  if (failed) return `${failed} 个仓提交失败`
  if (!changes.length) return '无待提交变更'
  return `${submitted}/${changes.length} 仓已提交`
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

function ensureRunMappedWorkspace(ctx: StageContext): void {
  const prev = ctx.run.build_context
  if (prev?.mapped_root?.trim() && prev.linux_root?.trim()) return
  let disc: Record<string, unknown> | null = null
  if (!prev?.mapped_root?.trim()) {
    try {
      disc = discoverRemoteRunner()
    } catch { /* discover 失败不阻断提交，Gerrit 服务仍可按盘符换算 */ }
  }
  const next = fillMappedWorkspaceIfMissing(prev, disc)
  if (
    next.mapped_root !== (prev?.mapped_root ?? '')
    || next.linux_root !== prev?.linux_root
  ) {
    ctx.patchRun({ build_context: next })
    if (next.mapped_root) ctx.log(`mapped_root=${next.mapped_root}`)
    if (next.linux_root) ctx.log(`linux_root=${next.linux_root}`)
  }
}

function domainLabelOf(ctx: StageContext, domainId: string): string {
  return ctx.run.domains.find(d => d.domain_id === domainId)?.domain_label || domainId
}

function selectedRepoGroups(ctx: StageContext): RepoChangeGroup[] {
  const repos = groupChangedFilesByRepo(domainsWithChanges(ctx))
  return filterRepoGroupsBySelection(repos, ctx.run.gerrit_selected_repos)
}

async function launchRepoSubmit(ctx: StageContext, group: RepoChangeGroup): Promise<boolean> {
  ensureRunMappedWorkspace(ctx)
  const buildContext = ctx.run.build_context
  if (!buildContext) {
    ctx.patchState({ progress: { state: 'error', error: '缺少 build_context，无法提交 Gerrit' } })
    ctx.log('缺少 build_context')
    return false
  }

  const result = startGerritRepoSubmit({
    runId: ctx.run.run_id,
    projectCode: ctx.run.project_code,
    repo: group.repo,
    repoLabel: group.repo_label,
    files: group.files,
    domainIds: group.domain_ids,
    domainLabels: group.domain_ids.map(id => domainLabelOf(ctx, id)),
    buildContext,
  })

  if (!result.ok) {
    const changes = [...(ctx.run.gerrit_changes ?? [])]
    const idx = changes.findIndex(c => changeMatchesRepo(c, group.repo, group.repo_label))
    if (idx >= 0) {
      changes[idx] = { ...changes[idx], status: 'failed', error: result.error }
    }
    ctx.patchRun({ gerrit_changes: changes })
    syncProgress(ctx, { state: 'submit_failed', changes })
    ctx.log(`仓库 ${group.repo_label} 提交启动失败: ${result.error}`)
    return false
  }

  ctx.patchState({
    refs: { ...ctx.state.refs, gerrit_task_id: result.taskId },
    progress: {
      ...(ctx.state.progress as Record<string, unknown>),
      state: 'submitting',
      current_repo: group.repo,
      current_repo_label: group.repo_label,
      submit_started_at: new Date().toISOString(),
    },
  })
  ctx.log(`开始提交仓库 ${group.repo_label}: taskId=${result.taskId}`)
  return true
}

async function startNextRepoSubmit(ctx: StageContext): Promise<void> {
  const p = (ctx.state.progress ?? {}) as Record<string, unknown>
  const queue = (p.queue as string[]) ?? []
  const idx = Number(p.current_index ?? 0)
  if (idx >= queue.length) return

  const repo = queue[idx]
  const group = selectedRepoGroups(ctx).find(g => g.repo === repo)
    ?? groupChangedFilesByRepo(domainsWithChanges(ctx)).find(g => g.repo === repo)
  if (!group) {
    syncProgress(ctx, { current_index: idx + 1 })
    await startNextRepoSubmit(ctx)
    return
  }

  await launchRepoSubmit(ctx, group)
}

function findChangeIndex(
  changes: GerritChangeRef[],
  p: Record<string, unknown>,
  evRepo?: string,
): number {
  const repo = String(evRepo ?? p.current_repo ?? '')
  const label = String(p.current_repo_label ?? '')
  const byRepo = changes.findIndex(c => changeMatchesRepo(c, repo, label))
  if (byRepo >= 0) return byRepo
  const idx = Number(p.current_index ?? 0)
  return Number.isFinite(idx) && idx >= 0 && idx < changes.length ? idx : -1
}

export const gerritStageDefinition: StageDefinition = {
  key: 'gerrit',
  label: '提交 Gerrit',
  consumes: ['source', 'testresult'],

  async probe() {
    return probeGerritSubmit()
  },

  async start(ctx: StageContext) {
    ensureRunMappedWorkspace(ctx)
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

    const selected = filterRepoGroupsBySelection(repos, ctx.run.gerrit_selected_repos)
    if (!selected.length) {
      syncProgress(ctx, {
        state: 'awaiting_confirm_no_changes',
        changes: [],
        repos,
        message: '所选仓库无变更',
        text: '所选仓库无变更',
      })
      return
    }

    const queue = selected.map(g => g.repo)
    const initialChanges: GerritChangeRef[] = selected.map(g => ({
      domain_id: g.domain_ids[0] ?? g.repo_label,
      domain_ids: g.domain_ids,
      repo: g.repo,
      status: 'pending',
      files: g.files,
    }))
    ctx.patchRun({ gerrit_changes: initialChanges })
    syncProgress(ctx, {
      state: 'submitting',
      queue,
      current_index: 0,
      changes: initialChanges,
      text: `开始提交 ${selected.length} 个仓库`,
    })

    await startNextRepoSubmit(ctx)
  },

  async observe(ctx: StageContext, ev) {
    if (ev.source !== 'task-stream') return
    const taskId = ctx.state.refs?.gerrit_task_id as string | undefined
    if (!taskId || ev.correlation.taskId !== taskId) return

    const p = (ctx.state.progress ?? {}) as Record<string, unknown>
    const repo = String(ev.payload.repo ?? p.current_repo ?? '')
    const repoLabel = String(ev.payload.repo_label ?? p.current_repo_label ?? repo)

    if (ev.type === 'task.started') {
      ctx.log(`Gerrit Agent 已启动（${taskId}）`)
      return
    }

    if (ev.type === 'task.message') {
      const text = String(ev.payload.text ?? ev.payload.message ?? '').trim()
      if (text) ctx.log(text.slice(0, 500))
      if (text && isGerritSubmitStreamFatal(text)) {
        const err = 'ASF Bridge 会话已断开（齐治/SSH），请重试提交'
        const changes = [...(ctx.run.gerrit_changes ?? [])]
        const changeIdx = findChangeIndex(changes, p, repo)
        if (changeIdx >= 0) {
          changes[changeIdx] = { ...changes[changeIdx], status: 'failed', error: err }
        }
        ctx.patchRun({ gerrit_changes: changes })
        syncProgress(ctx, { state: 'submit_failed', changes, error: err })
        ctx.log(`仓库 ${repoLabel} 提交失败: ${err}`)
        try { cancelGerritSubmitTask(taskId) } catch { /* ignore */ }
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
      const changeIdx = findChangeIndex(changes, p, repo)
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
          ? `仓库 ${repoLabel || '未知'} 无新变更，沿用既有 CR`
          : `仓库 ${repoLabel || '未知'} Gerrit 提交完成`,
      )

      if (nextIndex < queue.length) {
        await startNextRepoSubmit(ctx)
      } else {
        syncProgress(ctx, { state: 'done' })
        ctx.log('全部所选仓库 Gerrit 提交完成')
      }
      return
    }

    if (ev.type === 'task.failed') {
      const changes = [...(ctx.run.gerrit_changes ?? [])]
      const changeIdx = findChangeIndex(changes, p, repo)
      const err = String(ev.payload.error ?? ev.payload.message ?? '提交失败')
      if (changeIdx >= 0) {
        changes[changeIdx] = { ...changes[changeIdx], status: 'failed', error: err }
      }
      ctx.patchRun({ gerrit_changes: changes })
      syncProgress(ctx, { state: 'submit_failed', changes, error: err })
      ctx.log(`仓库 ${repoLabel || repo || '未知'} 提交失败: ${err}`)
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
        message: '请勾选要提交到 Gerrit 的仓库（支持部分入库）。同一仓内多域改动会合并为一张 CR。',
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

    // 旧 run 可能仍停在 blocked_conflict；重试会按仓合提，不再拦截
    if (state === 'blocked_conflict') {
      return {
        status: 'waiting_human',
        reason: 'blocked_conflict',
        message: '此运行曾按域拆 CR 并记下跨域同文件。现已改为按仓合提：点重试即可把勾选仓库的全部改动提交，无需先拆文件。',
        actions: [
          { id: 'retry', label: '按仓合提，重试提交' },
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
        error: String(p.error ?? '部分仓库 Gerrit 提交失败'),
        retryable: true,
      }
    }

    if (state === 'submitting' && isGerritSubmitTimedOut(String(p.submit_started_at || ctx.state.started_at || ''))) {
      return {
        status: 'failed',
        error: 'Gerrit 提交超时（ASF Bridge 可能已断开），请重试',
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
