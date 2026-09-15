import { registerStageForTest } from '../registry'
import { computeResumePoints } from '../orchestrator'
import { groupChangedFilesByRepo } from '../repo-groups'
import { domainsWithChangedFiles } from '../workspace-changed-files'
import type { StageContext, StageDefinition, StageVerdict } from '../types'

export const humanReviewStageDefinition: StageDefinition = {
  key: 'human_review',
  label: '人工审核',
  consumes: ['triage'],
  produces: ['source'],
  isHumanGate: true,

  async start(ctx: StageContext) {
    ctx.log('等待人工审核修改结果')

    const triageStage = ctx.run.stages.triage
    const triageSummary = triageStage?.summary as Record<string, unknown> | undefined
    const filteredDomains = domainsWithChangedFiles(ctx.run.domains)
    const fileGroups = groupChangedFilesByRepo(filteredDomains)
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
      message: '请审核流水线修改文件与故障分析结论（如有）。通过后请在下方选择恢复点继续；入库仓库选择在 Gerrit 阶段进行。',
      actions: [],
    }
  },

  async handleHumanAction(ctx: StageContext, actionId: string, _payload?: Record<string, unknown>) {
    if (actionId === 'confirm_done') {
      ctx.patchState({
        progress: {
          ...ctx.state.progress as Record<string, unknown>,
          resolved: true,
        },
      })
      ctx.log('人工审核已确认')
    }
  },
}

export function installHumanReviewStage(): void {
  registerStageForTest(humanReviewStageDefinition)
}

installHumanReviewStage()
