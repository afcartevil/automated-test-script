import { registerStageForTest } from '../registry'
import { computeResumePoints } from '../orchestrator'
import { takeSnapshot, fingerprint } from '../../git-snapshot'
import { groupChangedFilesByRepo } from '../repo-groups'
import { domainsWithWorkspaceChanges } from '../workspace-changed-files'
import type { StageContext, StageDefinition, StageVerdict } from '../types'

export const humanReviewStageDefinition: StageDefinition = {
  key: 'human_review',
  label: '人工审核',
  consumes: ['triage'],
  produces: ['source'],
  isHumanGate: true,

  async start(ctx: StageContext) {
    ctx.log('等待人工审核修改结果')

    const mappedRoot = ctx.run.build_context?.mapped_root ?? ''
    const workspace = ctx.run.build_context?.workspace ?? ''
    const root = mappedRoot
    if (root) {
      try {
        const snap = await takeSnapshot([root])
        ctx.patchState({
          progress: {
            snapshot_before: snap,
            fingerprint_before: fingerprint(snap),
          },
        })
      } catch { /* non-critical */ }
    }

    const triageStage = ctx.run.stages.triage
    const triageSummary = triageStage?.summary as Record<string, unknown> | undefined
    const filteredDomains = domainsWithWorkspaceChanges(ctx.run.domains, mappedRoot, workspace)
    const fileGroups = root
      ? groupChangedFilesByRepo(root, filteredDomains)
      : []
    const changedFiles = filteredDomains.flatMap(d =>
      d.changed_files.map(f => ({
        domain_id: d.domain_id,
        domain_label: d.domain_label,
        file: f,
      })),
    )

    ctx.patchState({
      progress: {
        ...(ctx.state.progress as Record<string, unknown>),
        triage_conclusion: triageSummary?.conclusion ?? null,
        triage_evidence: triageSummary?.evidence ?? null,
        triage_executed: Boolean(triageStage && triageStage.status === 'done'),
        changed_files: changedFiles,
        repo_groups: fileGroups,
        text: `变更文件 ${changedFiles.length} 个 / 仓库 ${fileGroups.length} 个`,
      },
    })
  },

  evaluate(ctx: StageContext): StageVerdict {
    const { points, recommended } = computeResumePoints(ctx.run)

    ctx.patchState({
      progress: {
        ...ctx.state.progress as Record<string, unknown>,
        resume_points: { points, recommended },
      },
    })

    return {
      status: 'waiting_human',
      reason: 'awaiting_review',
      message: '请审核流水线修改文件与故障分析结论（如有）。通过后可选择恢复点继续；入库仓库选择在 Gerrit 阶段进行。',
      actions: [
        {
          id: 'confirm_done',
          label: '继续',
          fields: [
            { name: 'resume_node', label: '从哪里继续', required: true },
            { name: 'resume_scope', label: '范围' },
          ],
        },
        { id: 'abort', label: '终止流水线', danger: true },
      ],
    }
  },

  async handleHumanAction(ctx: StageContext, actionId: string, _payload?: Record<string, unknown>) {
    if (actionId === 'confirm_done') {
      const root = ctx.run.build_context?.mapped_root
      const prevFp = (ctx.state.progress as Record<string, unknown>)?.fingerprint_before as string | undefined
      let codeChanged = false

      if (root && prevFp) {
        try {
          const snap = await takeSnapshot([root])
          const currentFp = fingerprint(snap)
          codeChanged = currentFp !== prevFp
        } catch { codeChanged = true }
      }

      ctx.patchState({
        progress: {
          ...ctx.state.progress as Record<string, unknown>,
          code_changed: codeChanged,
          resolved: true,
        },
      })

      if (codeChanged) {
        ctx.log('检测到代码变更，source 产物将标记为过期')
      } else {
        ctx.log('未检测到代码变更')
      }
    }
  },
}

export function installHumanReviewStage(): void {
  registerStageForTest(humanReviewStageDefinition)
}

installHumanReviewStage()
