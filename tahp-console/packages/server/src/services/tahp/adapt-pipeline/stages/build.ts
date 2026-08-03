import { clearCapabilityPoll, createCapabilityStage } from '../capability'
import { buildCapability } from '../build-capability'
import { defaultBuildSkillId } from '../harness-skill-registry'
import { registerStageForTest } from '../registry'
import type { BuildCapabilityInput, StageContext, StageDefinition, StageVerdict } from '../types'

function resolveBuildMode(ctx: StageContext): 'full' | 'incremental' {
  const fromParams = ctx.node.params?.build_mode ?? ctx.state.progress?.build_mode
  if (fromParams === 'full' || fromParams === 'incremental') return fromParams
  return ctx.run.iteration === 1 ? 'full' : 'incremental'
}

const base = createCapabilityStage<BuildCapabilityInput>({
  key: 'build',
  label: '编译',
  capability: buildCapability,
  consumes: ['source'],
  produces: ['build'],
  pollIntervalMs: 3000,
  buildInput: ctx => {
    const bc = ctx.run.build_context
    const buildKind = bc.build_kind ?? (bc.native_target ? 'native_module' : 'whole_device')
    return {
      pipelineRunId: ctx.run.run_id,
      mappedRoot: bc.mapped_root,
      workspace: bc.workspace,
      mode: resolveBuildMode(ctx),
      components: bc.components ?? [],
      variant: bc.variant,
      parallelProfile: bc.parallel_profile,
      markets: bc.markets,
      buildKind,
      buildSkillId: bc.build_skill_id || defaultBuildSkillId(buildKind),
      pipelineStages: bc.pipeline_stages,
      lunch: bc.lunch,
      nativeTarget: bc.native_target,
      nativeComponent: bc.native_component,
    }
  },
  onSuccess: (ctx, result) => {
    ctx.patchState({
      summary: {
        artifacts_dir: result.artifactsDir ?? result.artifacts_dir,
        pkg_path: result.pkgPath ?? result.pkg_path,
        artifacts: result.artifacts,
        skill_id: result.skillId ?? result.skill_id,
      },
      progress: {
        ...ctx.state.progress,
        state: 'success',
        phase: 'done',
        progress: 100,
        result,
        text: String(result.artifactsDir ?? result.artifacts_dir ?? result.pkgPath ?? '编译完成'),
      },
    })
  },
})

const baseEvaluate = base.evaluate.bind(base)
const baseStart = base.start!.bind(base)
const baseCancel = base.cancel?.bind(base)

export const buildStageDefinition: StageDefinition = {
  ...base,
  evaluate(ctx: StageContext): StageVerdict {
    const p = ctx.state.progress as Record<string, unknown> | undefined
    const state = p?.state as string | undefined
    if (state === 'failed' || state === 'cancelled') {
      const err = String(p?.error ?? (state === 'cancelled' ? '编译已取消' : '编译失败'))
      return {
        status: 'waiting_human',
        reason: 'build_failed',
        message: `编译失败：${err}。可重新编译，或跳过烧录/自检直接前往提交 Gerrit。`,
        actions: [
          { id: 'retry_build', label: '重新编译' },
          { id: 'go_gerrit', label: '跳转到提交 Gerrit' },
        ],
      }
    }
    return baseEvaluate(ctx)
  },

  async handleHumanAction(ctx: StageContext, actionId: string) {
    if (actionId !== 'retry_build') return
    clearCapabilityPoll(ctx.run.run_id, 'build')
    const extId = ctx.state.refs?.build_run_id as string | undefined
    if (extId) {
      try { await buildCapability.cancel(extId) } catch { /* ignore */ }
    }
    ctx.patchState({
      progress: { state: 'pending', text: '重新编译…' },
      error: undefined,
      human: undefined,
      refs: { ...ctx.state.refs, build_run_id: undefined },
    })
    await baseStart(ctx)
  },

  async cancel(ctx: StageContext) {
    if (baseCancel) await baseCancel(ctx)
  },
}

export function installBuildStage(): void {
  registerStageForTest(buildStageDefinition)
}

installBuildStage()
