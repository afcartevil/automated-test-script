import { registerStageForTest } from '../registry'
import { computeResumePoints } from '../orchestrator'
import { takeSnapshot, fingerprint } from '../../git-snapshot'
import type { StageContext, StageDefinition, StageVerdict } from '../types'

export const humanReviewStageDefinition: StageDefinition = {
  key: 'human_review',
  label: '人工审核',
  consumes: ['triage'],
  produces: ['source'],
  isHumanGate: true,

  async start(ctx: StageContext) {
    ctx.log('等待人工审核修改结果')

    // Take "before" snapshot for code-change detection
    const root = ctx.run.build_context?.mapped_root
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

    // Attach triage conclusion summary if available
    const triageStage = ctx.run.stages.triage
    const triageSummary = triageStage?.summary as Record<string, unknown> | undefined
    if (triageSummary?.conclusion) {
      ctx.patchState({
        progress: {
          ...ctx.state.progress as Record<string, unknown>,
          triage_conclusion: triageSummary.conclusion,
          triage_evidence: triageSummary.evidence,
        },
      })
    }
  },

  evaluate(ctx: StageContext): StageVerdict {
    // Compute dynamic resume points based on artifact freshness
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
      message: '请审核 AI 故障分析结论并完成代码修改，完成后选择从哪个节点继续。',
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

  async handleHumanAction(ctx: StageContext, actionId: string, payload?: Record<string, unknown>) {
    if (actionId === 'confirm_done') {
      // Check if code changed by comparing snapshots
      const root = ctx.run.build_context?.mapped_root
      const prevFp = (ctx.state.progress as Record<string, unknown>)?.fingerprint_before as string | undefined
      let codeChanged = false

      if (root && prevFp) {
        try {
          const snap = await takeSnapshot([root])
          const currentFp = fingerprint(snap)
          codeChanged = currentFp !== prevFp
        } catch { /* assume changed to be safe */ codeChanged = true }
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
