import { createCapabilityStage } from '../capability'
import { registerStageForTest } from '../registry'
import type { BuildCapabilityInput } from '../types'

function resolveBuildMode(ctx: import('../types').StageContext): 'full' | 'incremental' {
  const fromParams = ctx.node.params?.build_mode ?? ctx.state.progress?.build_mode
  if (fromParams === 'full' || fromParams === 'incremental') return fromParams
  return ctx.run.iteration === 1 ? 'full' : 'incremental'
}

export const buildStageDefinition = createCapabilityStage<BuildCapabilityInput>({
  key: 'build',
  label: '编译',
  capability: null,
  consumes: ['source'],
  produces: ['build'],
  buildInput: ctx => ({
    mappedRoot: ctx.run.build_context.mapped_root,
    workspace: ctx.run.build_context.workspace,
    mode: resolveBuildMode(ctx),
    components: ctx.run.build_context.components,
    variant: ctx.run.build_context.variant,
    parallelProfile: ctx.run.build_context.parallel_profile,
    markets: ctx.run.build_context.markets,
  }),
  onSuccess: (ctx, result) => {
    ctx.patchState({
      summary: { artifacts_dir: result.artifactsDir, artifacts: result.artifacts },
    })
  },
})

export function installBuildStage(): void {
  registerStageForTest(buildStageDefinition)
}

installBuildStage()
